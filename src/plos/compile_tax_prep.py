"""
Compile pass for `compiled/tax-prep.md`.

The third compiled artifact in PLOS — the final one in the v1 set.

`tax-prep.md` is a gap-surfacing artifact: it tells the user which
tax documents have arrived for the active tax year and which are
still missing. Unlike `this-week.md` (priority reasoning) and
`anomalies.md` (statistics + missing-statement detection),
`tax-prep.md` reads from a per-year inventory file that the user
maintains: `source/tax/<year>/expected-documents.md`. Each entry in
that file's YAML frontmatter `expected:` list declares one document
the user expects this tax year, with a `received: bool` flag that
flips when the document lands.

Slice 1 of tax-prep ships two sections — `## Received` and
`## Missing` — driven entirely by the explicit `received:` flag in
the inventory. The richer `## For the accountant` (running totals
across the vault) and `## Outstanding actions` (chase list) sections
from `docs/artifact-templates.md` are deferred: they require
aggregation across `extracted_fields` and/or synthesis that's
better landed when the operating instance is closer to a real tax
filing.

The same statistics-in-Python / prose-in-Claude split from
`compile_anomalies.py` applies: `compute_tax_prep` returns a
structured `TaxPrepResult`; Claude renders the bullets and any
framing prose. Combined empty-state short-circuit when there's no
inventory file for the resolved tax year — write a deterministic
"no inventory configured for <year>" artifact without invoking
Claude.

Tax-year resolution mirrors the US individual tax calendar: in
January through April, the active tax year is the previous calendar
year (the filing window); from May onwards, the active tax year is
the current calendar year (the collection window). Override via
the `PLOS_TAX_YEAR` env var for testing and demos.

Run from the repo root:
    python -m plos.compile_tax_prep
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

logger = logging.getLogger("plos.compile_tax_prep")

ARTIFACT_PATH = Path("compiled/tax-prep.md")
REQUIRED_SECTIONS = ("## Received", "## Missing")
TAX_INVENTORY_FILENAME = "expected-documents.md"
TAX_YEAR_ENV_VAR = "PLOS_TAX_YEAR"


@dataclass(frozen=True)
class ExpectedDocument:
    """One expected-document entry from the tax-year inventory."""

    name: str
    source: str | None
    received: bool
    received_date: str | None
    received_path: str | None
    notes: str | None


@dataclass(frozen=True)
class TaxPrepResult:
    """Categorized output of `compute_tax_prep`.

    `received` and `missing` partition the inventory by the `received:`
    flag. Order within each list mirrors the inventory file's order so
    the user controls grouping by editing one place.
    """

    tax_year: int
    inventory_path: Path
    received: list[ExpectedDocument]
    missing: list[ExpectedDocument]


def _default_tax_year(as_of: date) -> int:
    """Return the currently-active tax year given an as-of date.

    US individuals file tax year N during Jan-Apr of year N+1, then
    collect documents for tax year N+1 from May onwards. So the
    active tax year is `as_of.year - 1` during the filing window
    (Jan-Apr) and `as_of.year` outside it.
    """
    if as_of.month <= 4:
        return as_of.year - 1
    return as_of.year


def _read_frontmatter(path: Path) -> dict[str, Any]:
    """Parse the YAML frontmatter of a markdown file as a dict.

    Returns `{}` on any malformed input — missing delimiters,
    unparseable YAML, non-dict YAML root. Callers treat `{}` as
    "no usable inventory."
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    closing = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing = i
            break
    if closing is None:
        return {}
    try:
        loaded = yaml.safe_load("\n".join(lines[1:closing])) or {}
    except yaml.YAMLError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def compute_tax_prep(
    vault_root: Path,
    *,
    tax_year: int | None = None,
    as_of: date | None = None,
) -> TaxPrepResult | None:
    """Read `source/tax/<year>/expected-documents.md` and partition entries.

    Returns `None` when the inventory file doesn't exist for the
    resolved tax year — callers (e.g. `run()`) short-circuit on
    this and write a "no inventory configured" deterministic
    artifact.

    `tax_year` defaults to `_default_tax_year(as_of)` if unset.
    `as_of` defaults to today's UTC date if unset.

    Entries with `received: true` land in the `received` list;
    everything else (including entries missing the flag entirely)
    lands in `missing`. Non-dict entries in the YAML list are
    silently skipped — invalid inventory rows should not crash the
    compile pass.
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc).date()
    if tax_year is None:
        tax_year = _default_tax_year(as_of)

    inventory_path = (
        vault_root / "source" / "tax" / str(tax_year) / TAX_INVENTORY_FILENAME
    )
    if not inventory_path.is_file():
        return None

    fm = _read_frontmatter(inventory_path)
    raw_list = fm.get("expected")
    if not isinstance(raw_list, list):
        return TaxPrepResult(
            tax_year=tax_year,
            inventory_path=inventory_path,
            received=[],
            missing=[],
        )

    received: list[ExpectedDocument] = []
    missing: list[ExpectedDocument] = []
    for entry in raw_list:
        if not isinstance(entry, dict):
            continue
        # YAML parses bare YYYY-MM-DD values as `date` objects; normalise
        # to ISO strings so downstream consumers (manifest, prompt,
        # tests) see a consistent type.
        raw_received_date = entry.get("received_date")
        received_date = (
            raw_received_date.isoformat()
            if isinstance(raw_received_date, date)
            else raw_received_date
        )
        doc = ExpectedDocument(
            name=str(entry.get("name", "")),
            source=entry.get("source"),
            received=bool(entry.get("received", False)),
            received_date=received_date,
            received_path=entry.get("received_path"),
            notes=entry.get("notes"),
        )
        if doc.received:
            received.append(doc)
        else:
            missing.append(doc)

    return TaxPrepResult(
        tax_year=tax_year,
        inventory_path=inventory_path,
        received=received,
        missing=missing,
    )


def _vault_relative(path: Path, vault_root: Path) -> str:
    """Render an in-vault path as `/source/...` for the manifest."""
    rel = path.resolve().relative_to(vault_root.resolve())
    return "/" + str(rel).replace("\\", "/")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


PROMPT_PREAMBLE = """\
You are the compile pass for `compiled/tax-prep.md` in the PLOS
(Personal Life Operating System) vault. Your job: produce a fresh
`tax-prep.md` markdown file that surfaces the gap between expected
and received tax documents for the active tax year. The manifest
below carries two pre-computed lists — received and missing — drawn
from the user's per-year inventory file
(`source/tax/<year>/expected-documents.md`). You render each as a
single bullet under its section.

You are NOT detecting received/missing — the categorization was done
upstream by the inventory file's `received: bool` flags. You render.

Output format — match this shape exactly:

```
---
type: compiled
artifact: tax-prep
refreshed: <ISO-8601 UTC timestamp you set to right now>
tax_year: <integer year from manifest>
refresh_cadence: monthly (weekly Jan-Apr)
sources_read:
  - <every /source/... path you cite in the body>
compile_pass_version: 1
---

# Tax Prep — Tax Year <YYYY>

**Status:** <N> of <M> expected documents received.

## Received

- <Document name>. <Optional short context (received date, source)>.
  → /source/tax/<year>/...

## Missing

- **<Document name>.** <Optional plain-language framing of what to chase, drawn from the inventory's `notes:` and `source:` fields>.
  → /source/tax/<year>/expected-documents.md

---
*Generated by monthly tax-prep compile pass. To regenerate: `compile tax-prep`.*
```

Rules:

- One bullet per entry. Render the received list under `## Received`,
  the missing list under `## Missing`. Order matches the manifest.
- Every received bullet that has a `received_path` cites that path
  with a `→ /source/...` arrow on its own line under the bullet.
  Received entries without a `received_path` cite the inventory
  file itself.
- Every missing bullet cites the inventory file as the provenance
  for "the user expected this": `→ /source/tax/<year>/expected-documents.md`.
- The `sources_read:` frontmatter list must include every path you
  cite — at minimum the inventory file, plus every distinct
  `received_path` cited.
- `Status:` line uses the manifest's `received_count` and
  `total_count` exactly.
- If the received list is empty, render `- _(nothing received yet)_`
  under the heading. If the missing list is empty, render
  `- _(nothing outstanding)_`. The headings stay.
- Do not include any commentary, explanation, or code fences around
  the document. Emit the markdown only — your response must be
  copy-pasted directly into `tax-prep.md` with no edits.

Manifest follows.

"""


PROMPT_INSTRUCTION = """

Now produce the rendered `tax-prep.md` document. Output the markdown
directly — no commentary, no preamble, no closing remarks. The first
character of your response must be the opening `---` of the YAML
frontmatter; the last character must be the final newline of the
footer.
"""


def build_manifest(vault_root: Path, result: TaxPrepResult) -> str:
    """Return the markdown blob the compile pass feeds to Claude.

    Bundles the tax year, both lists (received + missing) with full
    entry details, and the inventory file's content as provenance.
    """
    inv_rel = _vault_relative(result.inventory_path, vault_root)
    parts: list[str] = [
        f"# Manifest\n\n"
        f"Tax year: {result.tax_year}\n"
        f"Inventory file: {inv_rel}\n"
        f"Received count: {len(result.received)}\n"
        f"Missing count: {len(result.missing)}\n"
        f"Total count: {len(result.received) + len(result.missing)}\n",
        "\n## Received entries\n\n",
    ]
    if not result.received:
        parts.append("_(none)_\n")
    else:
        for doc in result.received:
            parts.append(_render_doc(doc))

    parts.append("\n## Missing entries\n\n")
    if not result.missing:
        parts.append("_(none)_\n")
    else:
        for doc in result.missing:
            parts.append(_render_doc(doc))

    parts.append(
        f"\n## {inv_rel}\n\n"
        f"```markdown\n{_read_text(result.inventory_path)}\n```\n"
    )

    return "".join(parts)


def _render_doc(doc: ExpectedDocument) -> str:
    """Render one inventory entry as a structured manifest bullet."""
    lines = [f"- name: {doc.name}"]
    if doc.source:
        lines.append(f"  source: {doc.source}")
    if doc.received_date:
        lines.append(f"  received_date: {doc.received_date}")
    if doc.received_path:
        lines.append(f"  received_path: /{doc.received_path.lstrip('/')}")
    if doc.notes:
        lines.append(f"  notes: {doc.notes}")
    return "\n".join(lines) + "\n"


def _validate_response(response: str) -> None:
    """Raise if the Claude response doesn't look like a valid tax-prep.md."""
    stripped = response.lstrip("﻿").lstrip()
    if not stripped.startswith("---"):
        raise ValueError(
            "compile_tax_prep: response does not start with YAML frontmatter "
            "delimiter (---); refusing to write."
        )
    for heading in REQUIRED_SECTIONS:
        if heading not in response:
            raise ValueError(
                f"compile_tax_prep: response missing required section heading "
                f"{heading!r}; refusing to write."
            )


def _atomic_write(path: Path, content: str) -> None:
    """Write content to path via temp+rename. Mirrors vault.merge_frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _empty_tax_prep_artifact(tax_year: int) -> str:
    """The deterministic body written when no inventory file exists.

    Same shape as the rendered artifact, with both sections carrying
    a placeholder bullet so downstream readers (audit pass,
    notifications) see a stable contract.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        "---\n"
        "type: compiled\n"
        "artifact: tax-prep\n"
        f"refreshed: {now}\n"
        f"tax_year: {tax_year}\n"
        "refresh_cadence: monthly (weekly Jan-Apr)\n"
        "sources_read: []\n"
        "compile_pass_version: 1\n"
        "---\n"
        "\n"
        f"# Tax Prep — Tax Year {tax_year}\n"
        "\n"
        f"**Status:** No inventory configured for {tax_year}. "
        f"Create `source/tax/{tax_year}/expected-documents.md` "
        "with an `expected:` list in the frontmatter to begin tracking.\n"
        "\n"
        "## Received\n"
        "\n"
        "- _(no inventory configured)_\n"
        "\n"
        "## Missing\n"
        "\n"
        "- _(no inventory configured)_\n"
        "\n"
        "---\n"
        "*Generated by monthly tax-prep compile pass. "
        "To regenerate: `compile tax-prep`.*\n"
    )


def run(
    vault_root: Path,
    *,
    tax_year: int | None = None,
    as_of: date | None = None,
    claude_cmd: str = "claude",
) -> Path:
    """Read inventory, invoke Claude (or short-circuit), atomic-write.

    Returns the path written. Raises on subprocess failure or invalid
    Claude response — in either case the existing file (if any) is
    preserved.
    """
    target = vault_root / ARTIFACT_PATH
    result = compute_tax_prep(vault_root, tax_year=tax_year, as_of=as_of)

    if result is None:
        # No inventory file — short-circuit. Resolve the tax_year for the
        # header even though we can't read it from the (nonexistent) file.
        resolved_year = tax_year if tax_year is not None else _default_tax_year(
            as_of or datetime.now(timezone.utc).date()
        )
        logger.info(
            "no inventory file at source/tax/%d/%s; writing deterministic "
            "no-inventory artifact without invoking Claude",
            resolved_year,
            TAX_INVENTORY_FILENAME,
        )
        _atomic_write(target, _empty_tax_prep_artifact(resolved_year))
        return target

    manifest = build_manifest(vault_root, result)
    prompt = PROMPT_PREAMBLE + manifest + PROMPT_INSTRUCTION

    logger.info(
        "invoking %s --print (tax_year=%d, received=%d, missing=%d, "
        "manifest length: %d chars)",
        claude_cmd,
        result.tax_year,
        len(result.received),
        len(result.missing),
        len(manifest),
    )
    # encoding="utf-8" is non-negotiable on Windows — both prompt and
    # response carry source-provenance arrows that cp1252 can't handle.
    completed = subprocess.run(
        [claude_cmd, "--print"],
        input=prompt,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )
    response = completed.stdout

    _validate_response(response)

    _atomic_write(target, response)
    logger.info("wrote %s (%d bytes)", target, len(response))
    return target


def _resolve_vault_root() -> Path:
    """Pull PLOS_VAULT_ROOT from env. Same shape as compile_this_week."""
    raw = os.environ.get("PLOS_VAULT_ROOT")
    if not raw:
        raise RuntimeError("PLOS_VAULT_ROOT not set in environment")
    p = Path(raw)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()


def _resolve_tax_year() -> int | None:
    """Pull the optional PLOS_TAX_YEAR env var as an int.

    Returns `None` when unset (callers default to
    `_default_tax_year(today)`). Raises `ValueError` from `int()` if
    set but non-numeric — a typo'd override should fail loud.
    """
    raw = os.environ.get(TAX_YEAR_ENV_VAR)
    if not raw:
        return None
    return int(raw)


def main() -> None:
    load_dotenv(override=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    vault_root = _resolve_vault_root()
    tax_year = _resolve_tax_year()
    if tax_year is not None:
        logger.info("tax-year override active: %d", tax_year)
    target = run(vault_root, tax_year=tax_year)
    logger.info("compile tax-prep complete: %s", target)


if __name__ == "__main__":
    main()
