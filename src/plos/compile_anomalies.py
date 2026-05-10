"""
Compile pass for `compiled/anomalies.md`.

The second compiled artifact in PLOS. Two heuristics feed the artifact:

1. **Percentage-deviation (Slice 1).** Recurring numeric fields whose
   latest value differs from a 3-prior rolling mean by more than
   `DEVIATION_THRESHOLD_PCT` percent. Implemented by `compute_deviations`.

2. **Expectation gaps (Slice 2).** Recurring monthly statements
   (utility, mortgage, bank) that have not arrived for the
   currently-due calendar month — i.e., no `extracted_fields` row
   exists with a `source_document_date` in the month whose
   `GRACE_DAY` deadline has most recently passed. Cadence is implicit:
   any `(entity, field)` pair in `EXPECTATION_FIELDS` with at least
   one historical row is considered "expected at monthly cadence."
   Implemented by `compute_expectation_gaps`.

Both heuristics share one shell: `run` calls them, builds a manifest
that hands Claude the pre-computed lists, and lets Claude render the
prose under `## Spending deviations` / `## Expectation gaps`. The
statistics + gap detection live in Python (deterministic, auditable);
Claude's job is prose, not arithmetic.

If BOTH lists are empty, `run` short-circuits with a deterministic
"no deviations / no missing statements" artifact and never invokes
Claude — cheap and reproducible.

Slice 3 (unexpected charges) will fold in a third section under the
same artifact, using the same pre-compute + Claude-render split.

Per the merge contract in CONVENTIONS.md, compiled artifacts are
regenerated end-to-end every pass — no incremental merge. The only
discipline is the atomic temp+fsync+rename write so a reader never
sees a half-written file.

The "as-of" date the gap detector treats as today can be overridden
via the `PLOS_ANOMALIES_AS_OF` env var (`YYYY-MM-DD`). Useful for
demos and tests; falls back to the system's UTC date when unset.

Run from the repo root:
    python -m plos.compile_anomalies
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from sqlite3 import Connection

from dotenv import load_dotenv

from plos import db

logger = logging.getLogger("plos.compile_anomalies")

ARTIFACT_PATH = Path("compiled/anomalies.md")
REQUIRED_SECTIONS = ("## Spending deviations", "## Expectation gaps")
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

# Slice 2 — fields whose absence in the currently-due calendar month
# represents an "expectation gap" (a recurring monthly statement
# that hasn't arrived). One representative field per monthly-statement
# document type — the others from the same document arrive together,
# so flagging on all six fields would just multi-count one missing
# document. Paystubs are excluded (biweekly, not monthly); the YTD
# and consumption fields are excluded by the same logic as
# ELIGIBLE_FIELDS.
EXPECTATION_FIELDS: frozenset[str] = frozenset(
    {
        "last_utility_bill_amount",
        "last_mortgage_statement_amount",
        "last_statement_balance",
    }
)

# A statement covering month M is considered "due" on or before
# the GRACE_DAY of month M. Once GRACE_DAY of M has passed without a
# row in M, month M is overdue. Default 20 per ARCHITECTURE.md
# ("by the 20th of the month it was due").
GRACE_DAY: int = 20

# Override "today" for testing and demo by setting this env var to
# a YYYY-MM-DD date string. Defaults to today's UTC date.
AS_OF_ENV_VAR = "PLOS_ANOMALIES_AS_OF"


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


@dataclass(frozen=True)
class ExpectationGap:
    """One missing-statement gap for a single (entity, field) pair."""

    entity_id: int
    entity_slug: str
    entity_wiki_path: str
    field_name: str
    last_seen_date: str
    expected_month: str  # YYYY-MM
    days_overdue: int


def _currently_due_month(as_of: date) -> date:
    """First day of the calendar month whose GRACE_DAY has most recently passed.

    If `as_of.day >= GRACE_DAY`, the current calendar month is due.
    Otherwise, the previous calendar month is the most recent one whose
    deadline has elapsed.
    """
    if as_of.day >= GRACE_DAY:
        return as_of.replace(day=1)
    if as_of.month == 1:
        return date(as_of.year - 1, 12, 1)
    return as_of.replace(month=as_of.month - 1, day=1)


def _next_month_start(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


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


def compute_expectation_gaps(
    conn: Connection,
    *,
    as_of: date | None = None,
) -> list[ExpectationGap]:
    """Return list of (entity, field) pairs whose expected monthly statement
    is missing for the currently-due calendar month.

    Cadence is implicit: any `(entity_id, field_name)` pair in
    `EXPECTATION_FIELDS` with at least one historical `extracted_fields`
    row is treated as "expected at monthly cadence." If no row exists with
    `source_document_date` in the currently-due month (per
    `_currently_due_month(as_of)`), the pair is flagged as a gap.

    Slice 2 flags at most one gap per `(entity, field)` pair — the
    currently-due month only. Older missed months that were flagged in
    earlier passes and never resolved are not re-flagged here; the
    audit-pass story (later Phase 5) is the right place for that
    accumulation.

    Returned list is sorted by `days_overdue` descending (the staler the
    gap, the higher in the list), tie-broken by entity_slug + field_name
    for stability.
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc).date()

    placeholders = ",".join("?" * len(EXPECTATION_FIELDS))
    rows = conn.execute(
        f"""
        SELECT
          ef.entity_id,
          e.slug AS entity_slug,
          e.wiki_path AS entity_wiki_path,
          ef.field_name,
          ef.source_document_date
        FROM extracted_fields ef
        JOIN entities e ON e.id = ef.entity_id
        WHERE ef.field_name IN ({placeholders})
          AND ef.source_document_date IS NOT NULL
        ORDER BY ef.entity_id, ef.field_name, ef.source_document_date ASC
        """,
        tuple(sorted(EXPECTATION_FIELDS)),
    ).fetchall()

    due_month_start = _currently_due_month(as_of)
    due_month_end_exclusive = _next_month_start(due_month_start)
    due_deadline = due_month_start.replace(day=GRACE_DAY)

    groups: dict[tuple[int, str], list] = {}
    for row in rows:
        groups.setdefault((row["entity_id"], row["field_name"]), []).append(row)

    gaps: list[ExpectationGap] = []
    for (entity_id, field_name), group in groups.items():
        any_in_due_month = any(
            due_month_start.isoformat()
            <= row["source_document_date"]
            < due_month_end_exclusive.isoformat()
            for row in group
        )
        if any_in_due_month:
            continue
        last_seen = group[-1]
        gaps.append(
            ExpectationGap(
                entity_id=entity_id,
                entity_slug=last_seen["entity_slug"],
                entity_wiki_path=last_seen["entity_wiki_path"],
                field_name=field_name,
                last_seen_date=last_seen["source_document_date"],
                expected_month=due_month_start.strftime("%Y-%m"),
                days_overdue=(as_of - due_deadline).days,
            )
        )
    gaps.sort(key=lambda g: (-g.days_overdue, g.entity_slug, g.field_name))
    return gaps


def _vault_relative(path: str) -> str:
    """Render an entity wiki_path as a leading-slash provenance arrow target."""
    return "/" + path.lstrip("/")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


PROMPT_PREAMBLE = """\
You are the compile pass for `compiled/anomalies.md` in the PLOS
(Personal Life Operating System) vault. Your job: produce a fresh
`anomalies.md` markdown file that reports the anomalies pre-computed
for you below. Two heuristics feed this artifact:

1. **Spending deviations.** Recurring numeric fields whose latest value
   sits more than 20% above or below a 3-prior rolling mean. Each
   deviation is a single fact: entity, field, current value, baseline,
   and percentage delta.

2. **Expectation gaps.** Recurring monthly statements (utility,
   mortgage, bank) that have NOT arrived for the currently-due
   calendar month. Each gap is a single fact: entity, field, last seen
   date, expected month, and days overdue (relative to the 20th of the
   expected month).

You render each as a one-bullet human-readable item under its section.
You are NOT detecting anomalies — the lists below are authoritative.

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

## Expectation gaps

- **<Entity short label> — <statement type> for <Mon YYYY>: not received (last seen <YYYY-MM-DD>, <N> day(s) overdue).** <plain-language note on what's missing and what to check>.
  → /source/...

---
*Generated by monthly anomalies compile pass. To regenerate: `compile anomalies`.*
```

Rules:

- Render one bullet per deviation in the deviation list, one bullet per
  gap in the gap list. Do NOT invent additional bullets — the lists
  below are exhaustive.
- Every bullet cites its entity's `wiki_path` as a `→ /source/...`
  arrow on its own line under the bullet.
- The `sources_read:` frontmatter list must include every path you cite.
- Money values: render with a `$` and two decimal places.
- Percentages: round to the nearest whole percent (e.g. "+29%").
- If either list is empty, still render its section heading, with a
  single `- _(no deviations ≥20% this window)_` or
  `- _(no missing statements this window)_` placeholder bullet.
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
    vault_root: Path,
    deviations: list[Deviation],
    gaps: list[ExpectationGap] | None = None,
    *,
    as_of: date | None = None,
) -> str:
    """Return the markdown blob the compile pass feeds to Claude.

    Bundles `as_of` (or today's UTC date), the pre-computed deviation
    and gap lists, and the `index.md` of every cited entity for context.
    """
    if gaps is None:
        gaps = []
    today = (as_of or datetime.now(timezone.utc).date()).isoformat()
    parts: list[str] = [
        f"# Manifest\n\nAs-of date (UTC): {today}\n",
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

    parts.append("\n## Pre-computed expectation gaps\n\n")
    if not gaps:
        parts.append("_(no missing statements this window)_\n")
    else:
        for g in gaps:
            parts.append(
                f"- entity_slug: `{g.entity_slug}`\n"
                f"  wiki_path: `{_vault_relative(g.entity_wiki_path)}`\n"
                f"  field: `{g.field_name}`\n"
                f"  last_seen_date: {g.last_seen_date}\n"
                f"  expected_month: {g.expected_month}\n"
                f"  days_overdue: {g.days_overdue}\n"
            )

    cited_paths: set[Path] = set()
    for d in deviations:
        cited_paths.add(vault_root / Path(d.entity_wiki_path))
    for g in gaps:
        cited_paths.add(vault_root / Path(g.entity_wiki_path))
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


def _empty_anomalies_artifact(as_of: date | None = None) -> str:
    """The deterministic body written when both deviation + gap lists are empty.

    Skipping Claude in this case is both cheap (no subprocess, no token
    spend) and safer: empty sections are contractually flat facts, not
    synthesis tasks. The shape mirrors what Claude would emit given
    empty lists, so downstream readers (audit pass, notifications)
    see a stable artifact regardless of whether the model was invoked.
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc).date()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    month_label = as_of.strftime("%B %Y")
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
        "## Expectation gaps\n"
        "\n"
        "- _(no missing statements this window)_\n"
        "\n"
        "---\n"
        "*Generated by monthly anomalies compile pass. "
        "To regenerate: `compile anomalies`.*\n"
    )


def run(
    vault_root: Path,
    conn: Connection,
    claude_cmd: str = "claude",
    *,
    as_of: date | None = None,
) -> Path:
    """Compute deviations + gaps, invoke Claude (or short-circuit),
    atomic-write.

    Returns the path written. Raises on subprocess failure or invalid
    Claude response — in either case the existing file (if any) is
    preserved.

    The short-circuit fires only when BOTH lists are empty. If either
    has at least one entry, Claude is invoked with both pre-computed
    lists in the manifest.
    """
    deviations = compute_deviations(conn)
    gaps = compute_expectation_gaps(conn, as_of=as_of)
    target = vault_root / ARTIFACT_PATH

    if not deviations and not gaps:
        logger.info(
            "no deviations >=%.0f%% and no missing statements this window; "
            "writing deterministic artifact without invoking Claude",
            DEVIATION_THRESHOLD_PCT,
        )
        _atomic_write(target, _empty_anomalies_artifact(as_of=as_of))
        return target

    manifest = build_manifest(vault_root, deviations, gaps, as_of=as_of)
    prompt = PROMPT_PREAMBLE + manifest + PROMPT_INSTRUCTION

    logger.info(
        "invoking %s --print (%d deviations, %d gaps, manifest length: %d chars)",
        claude_cmd,
        len(deviations),
        len(gaps),
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


def _resolve_as_of() -> date | None:
    """Pull the optional PLOS_ANOMALIES_AS_OF env var as a date.

    Returns None when unset (callers default to today's UTC date).
    Raises `ValueError` from `date.fromisoformat` if set but malformed —
    a typo in the override should fail loud, not silently use today.
    """
    raw = os.environ.get(AS_OF_ENV_VAR)
    if not raw:
        return None
    return date.fromisoformat(raw)


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    vault_root = _resolve_vault_root()
    as_of = _resolve_as_of()
    if as_of is not None:
        logger.info("as-of override active: %s", as_of.isoformat())
    with db.connect() as conn:
        target = run(vault_root, conn, as_of=as_of)
    logger.info("compile anomalies complete: %s", target)


if __name__ == "__main__":
    main()
