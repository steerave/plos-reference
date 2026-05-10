"""
Compile pass for `compiled/anomalies.md`.

The second compiled artifact in PLOS. Walks the SQLite `extracted_fields`
audit trail, identifies recurring numeric fields whose latest value
deviates by more than `DEVIATION_THRESHOLD_PCT` from a baseline of their
prior `MIN_HISTORY` values, and shells out to the Claude Code CLI to
render a human-readable `compiled/anomalies.md`.

The statistics are computed in Python; Claude's job is prose, not
arithmetic. This keeps detection deterministic and auditable, and keeps
the per-run cost bounded — Claude is invoked at most once per compile
pass, with a pre-aggregated deviation list rather than the full audit
history.

Slice 1 ships only the percentage-deviation heuristic. Slices 2/3
will fold in expectation-gaps ("statement didn't arrive by the 20th")
and unexpected-charges into the same artifact under separate section
headings; the frontmatter and `run` shell shape stay constant.

Per the merge contract in CONVENTIONS.md, compiled artifacts are
regenerated end-to-end every pass — no incremental merge. The only
discipline is the atomic temp+fsync+rename write so a reader never
sees a half-written file.

Run from the repo root:
    python -m plos.compile_anomalies
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from sqlite3 import Connection

from dotenv import load_dotenv

from plos import db

logger = logging.getLogger("plos.compile_anomalies")

ARTIFACT_PATH = Path("compiled/anomalies.md")
REQUIRED_SECTIONS = ("## Spending deviations",)
DEVIATION_THRESHOLD_PCT = 20.0
MIN_HISTORY = 3

# Recurring numeric fields appropriate for percentage-deviation analysis.
# Excluded by design:
#   - last_paystub_ytd_gross: monotonically increasing across the year
#   - last_statement_balance: drifts with deposits/withdrawals, deviation
#     against rolling mean is meaningless
#   - last_utility_bill_kwh: not a money field; consumption-vs-cost is a
#     Slice 2+ concern
ELIGIBLE_FIELDS: frozenset[str] = frozenset(
    {
        "last_utility_bill_amount",
        "last_mortgage_statement_amount",
        "last_paystub_gross",
        "last_paystub_net",
        "last_statement_deposits",
        "last_statement_withdrawals",
    }
)


@dataclass(frozen=True)
class Deviation:
    """One flagged percentage-deviation result for a single (entity, field) pair."""

    entity_id: int
    entity_slug: str
    entity_wiki_path: str
    field_name: str
    current_value: float
    baseline_value: float
    delta_pct: float
    current_source_date: str
    current_paperless_url: str | None


def compute_deviations(
    conn: Connection,
    *,
    min_history: int = MIN_HISTORY,
    threshold_pct: float = DEVIATION_THRESHOLD_PCT,
) -> list[Deviation]:
    """Return the percentage-deviation hits across every eligible field.

    For each `(entity_id, field_name)` group in `extracted_fields` whose
    `field_name` is in `ELIGIBLE_FIELDS`: order by `source_document_date`
    ascending; take the most recent row as the *current* value and the
    `min_history` rows immediately before it as the baseline; compute
    `(current - mean(baseline)) / mean(baseline) * 100`; include if the
    absolute value of that percentage meets or exceeds `threshold_pct`.

    Groups with fewer than `min_history + 1` rows are skipped — there's
    no defensible baseline to compare against.

    Returned list is sorted by `abs(delta_pct)` descending so the most
    salient anomalies are first.
    """
    if min_history < 1:
        raise ValueError(f"min_history must be >= 1 (got {min_history})")
    placeholders = ",".join("?" * len(ELIGIBLE_FIELDS))
    rows = conn.execute(
        f"""
        SELECT
          ef.entity_id,
          e.slug AS entity_slug,
          e.wiki_path AS entity_wiki_path,
          ef.field_name,
          CAST(ef.field_value AS REAL) AS value,
          ef.source_document_date,
          d.paperless_url
        FROM extracted_fields ef
        JOIN entities e ON e.id = ef.entity_id
        LEFT JOIN documents d ON d.id = ef.document_id
        WHERE ef.field_name IN ({placeholders})
          AND ef.source_document_date IS NOT NULL
          AND ef.field_value IS NOT NULL
        ORDER BY ef.entity_id, ef.field_name, ef.source_document_date ASC
        """,
        tuple(sorted(ELIGIBLE_FIELDS)),
    ).fetchall()

    groups: dict[tuple[int, str], list] = {}
    for row in rows:
        groups.setdefault((row["entity_id"], row["field_name"]), []).append(row)

    deviations: list[Deviation] = []
    for (entity_id, field_name), group in groups.items():
        if len(group) < min_history + 1:
            continue
        current_row = group[-1]
        baseline_rows = group[-(min_history + 1) : -1]
        baseline_mean = sum(r["value"] for r in baseline_rows) / len(baseline_rows)
        if baseline_mean == 0:
            continue
        delta_pct = (current_row["value"] - baseline_mean) / baseline_mean * 100.0
        if abs(delta_pct) < threshold_pct:
            continue
        deviations.append(
            Deviation(
                entity_id=entity_id,
                entity_slug=current_row["entity_slug"],
                entity_wiki_path=current_row["entity_wiki_path"],
                field_name=field_name,
                current_value=current_row["value"],
                baseline_value=baseline_mean,
                delta_pct=delta_pct,
                current_source_date=current_row["source_document_date"],
                current_paperless_url=current_row["paperless_url"],
            )
        )
    deviations.sort(key=lambda d: abs(d.delta_pct), reverse=True)
    return deviations


def _vault_relative(path: str) -> str:
    """Render an entity wiki_path as a leading-slash provenance arrow target."""
    return "/" + path.lstrip("/")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


PROMPT_PREAMBLE = """\
You are the compile pass for `compiled/anomalies.md` in the PLOS
(Personal Life Operating System) vault. Your job: produce a fresh
`anomalies.md` markdown file that reports the percentage-deviation
anomalies pre-computed for you below. Each deviation is a single fact:
which entity, which recurring field, the current value, the rolling
baseline, and the percentage delta. Render each as a one-bullet
human-readable item.

Output format — match this shape exactly:

```
---
type: compiled
artifact: anomalies
refreshed: <ISO-8601 UTC timestamp you set to right now>
refresh_cadence: monthly
sources_read:
  - <every /source/... path you cite in the body>
compile_pass_version: 1
---

# Anomalies — <Mon YYYY>

## Spending deviations

- **<Entity short label> — <field, human-readable>: <current> ($X) vs <baseline>-month avg ($Y).** <plain-language framing of the delta and what it implies>.
  → /source/...

---
*Generated by monthly anomalies compile pass. To regenerate: `compile anomalies`.*
```

Rules:

- Render one bullet per deviation in the list. Do NOT add bullets for
  fields not in the deviation list — the statistics were computed
  upstream; you are not detecting anomalies, just rendering them.
- Every bullet cites its entity's `wiki_path` as a `→ /source/...`
  arrow on its own line under the bullet.
- The `sources_read:` frontmatter list must include every path you cite.
- Money values: render with a `$` and two decimal places.
- Percentages: round to the nearest whole percent (e.g. "+29%").
- If the deviation list is empty, do not output the body at all — the
  caller short-circuits this case before invoking you. But if for any
  reason you receive an empty list, output the section heading and a
  single `- _(no deviations ≥20% this window)_` bullet.
- Do not include any commentary, explanation, or code fences around
  the document. Emit the markdown only — your response must be
  copy-pasted directly into `anomalies.md` with no edits.

Manifest follows.

"""


PROMPT_INSTRUCTION = """

Now produce the rendered `anomalies.md` document. Output the markdown
directly — no commentary, no preamble, no closing remarks. The first
character of your response must be the opening `---` of the YAML
frontmatter; the last character must be the final newline of the
footer.
"""


def build_manifest(
    vault_root: Path, deviations: list[Deviation]
) -> str:
    """Return the markdown blob the compile pass feeds to Claude.

    Bundles today's date, the pre-computed deviation list, and the
    `index.md` of every cited entity for context.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    parts: list[str] = [
        f"# Manifest\n\nToday's date (UTC): {today}\n",
        "\n## Pre-computed deviations\n\n",
    ]
    if not deviations:
        parts.append("_(no deviations this window)_\n")
    else:
        for d in deviations:
            parts.append(
                f"- entity_slug: `{d.entity_slug}`\n"
                f"  wiki_path: `{_vault_relative(d.entity_wiki_path)}`\n"
                f"  field: `{d.field_name}`\n"
                f"  current_value: {d.current_value:.2f}\n"
                f"  baseline_mean: {d.baseline_value:.2f} "
                f"(prior {MIN_HISTORY} rows)\n"
                f"  delta_pct: {d.delta_pct:+.2f}%\n"
                f"  current_source_date: {d.current_source_date}\n"
            )

    cited_paths: set[Path] = set()
    for d in deviations:
        cited_paths.add(vault_root / Path(d.entity_wiki_path))
    for path in sorted(cited_paths):
        if path.is_file():
            rel = _vault_relative(
                str(path.resolve().relative_to(vault_root.resolve())).replace(
                    "\\", "/"
                )
            )
            parts.append(f"\n## {rel}\n\n```markdown\n{_read_text(path)}\n```\n")

    return "".join(parts)


def _validate_response(response: str) -> None:
    """Raise if the Claude response doesn't look like a valid anomalies.md."""
    stripped = response.lstrip("﻿").lstrip()
    if not stripped.startswith("---"):
        raise ValueError(
            "compile_anomalies: response does not start with YAML frontmatter "
            "delimiter (---); refusing to write."
        )
    for heading in REQUIRED_SECTIONS:
        if heading not in response:
            raise ValueError(
                f"compile_anomalies: response missing required section heading "
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


def _empty_anomalies_artifact() -> str:
    """The deterministic body written when no field meets the threshold.

    Skipping Claude in this case is both cheap (no subprocess, no token
    spend) and safer: an empty section is a contractually flat fact, not
    a synthesis task. The same shape is what we'd expect Claude to emit
    given an empty deviation list, so callers downstream see a stable
    artifact whether or not the model was invoked.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    month_label = datetime.now(timezone.utc).strftime("%B %Y")
    return (
        "---\n"
        "type: compiled\n"
        "artifact: anomalies\n"
        f"refreshed: {now}\n"
        "refresh_cadence: monthly\n"
        "sources_read: []\n"
        "compile_pass_version: 1\n"
        "---\n"
        "\n"
        f"# Anomalies — {month_label}\n"
        "\n"
        "## Spending deviations\n"
        "\n"
        "- _(no deviations ≥20% this window)_\n"
        "\n"
        "---\n"
        "*Generated by monthly anomalies compile pass. "
        "To regenerate: `compile anomalies`.*\n"
    )


def run(
    vault_root: Path,
    conn: Connection,
    claude_cmd: str = "claude",
) -> Path:
    """Compute deviations, invoke Claude (or short-circuit), atomic-write.

    Returns the path written. Raises on subprocess failure or invalid
    Claude response — in either case the existing file (if any) is
    preserved.
    """
    deviations = compute_deviations(conn)
    target = vault_root / ARTIFACT_PATH

    if not deviations:
        logger.info(
            "no deviations >=%.0f%% this window; writing deterministic artifact "
            "without invoking Claude",
            DEVIATION_THRESHOLD_PCT,
        )
        _atomic_write(target, _empty_anomalies_artifact())
        return target

    manifest = build_manifest(vault_root, deviations)
    prompt = PROMPT_PREAMBLE + manifest + PROMPT_INSTRUCTION

    logger.info(
        "invoking %s --print (%d deviations, manifest length: %d chars)",
        claude_cmd,
        len(deviations),
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


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    vault_root = _resolve_vault_root()
    with db.connect() as conn:
        target = run(vault_root, conn)
    logger.info("compile anomalies complete: %s", target)


if __name__ == "__main__":
    main()
