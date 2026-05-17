"""
Drain the pending_claude queue using Claude Code as the long-tail extractor.

Phase 2/3 graduated extractors handle a closed set of fictional providers
(Acme Power & Light, Mr. Cooper, First Davenport Bank, Beacon Software).
Real-world bills that don't match any of those route to
`documents.status='pending_claude'` and wait. Phase 4b drains the queue:
for each pending_claude row, shell out to the `claude` CLI with the
OCR'd text plus the vault's entity manifest, ask for structured JSON
back, and either merge into a matched entity (status -> `done`) or mark
`needs_review` with Claude's proposal recorded in `extracted_fields`
for human triage.

Same invocation pattern as `compile_this_week.py`: subprocess.run on
`claude --print`, encoding='utf-8' for Windows safety, validate the
response shape before any write, atomic merge via
`vault.merge_frontmatter`.

Entity *creation* stays deferred — per ARCHITECTURE.md, the worker (and
this drain script) never autonomously create entity files. Claude can
*propose* a new entity in its response (`route_status: "unmatched_entity"`
plus a `proposed_entity` block), and the proposal lands in
`extracted_fields` and the SQLite review reason. A human reviews and
applies (Phase 5+ stands up the formal review-queue rendering).

Run from the repo root:
    python -m plos.drain_pending_claude
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from . import db, paperless, vault

logger = logging.getLogger("plos.drain_pending_claude")

HANDLER = "claude"

# Maps source/<dir>/ -> (entities.type, entities.domain), mirroring
# worker._ENTITY_TYPE_FROM_DIR. Kept in sync deliberately rather than
# imported — the worker and the drain are independent runtimes.
_ENTITY_TYPE_FROM_DIR: dict[str, tuple[str, str]] = {
    "properties": ("property", "properties"),
    "accounts": ("account", "finance"),
    "people": ("person", "family"),
    "vehicles": ("vehicle", "vehicles"),
    "organizations": ("organization", "organizations"),
}


PROMPT_PREAMBLE = """\
You are processing a single document that the PLOS graduated extractors
couldn't classify. Read the OCR text, extract structured fields, identify
which entity in the vault this document belongs to, and respond with JSON.

The vault has these source entities (full index.md content for each
follows). Match the document to one of them by looking at frontmatter
fields like account numbers, addresses, names, employer, etc.

"""


PROMPT_INSTRUCTION = """

Respond with ONE JSON object — no commentary, no preamble, no closing
remarks. The first character of your response must be `{` and the last
must be `}`. If you wrap the JSON in a markdown code fence, the
parser tolerates ```json ... ```; anything else is rejected.

JSON schema:

```
{
  "doc_type": "<short snake_case label, e.g. 'utility_bill_gas',
                'mortgage_statement', 'insurance_policy', 'unknown'>",
  "route_status": "matched" | "unmatched_entity" | "unrecognized",
  "entity_type": "property" | "account" | "person" | "vehicle"
                 | "organization" | null,
  "entity_slug": "<exact slug of the matched entity, or null>",
  "fields": {
    "<field_name>": "<value>",
    ...
  },
  "rationale": "<one-sentence explanation of how you classified this>",
  "proposed_entity": {  // only when route_status='unmatched_entity'
    "type": "...",
    "slug": "...",
    "frontmatter_seed": { ... }
  }
}
```

Routing rules:

- `matched`: the document belongs to an entity that already exists in
  the vault. Set `entity_type` and `entity_slug` to the matching
  entity. The script will merge `fields` into that entity's
  frontmatter via the standard merge contract.
- `unmatched_entity`: you can extract structured fields, but no
  existing entity matches. Provide a `proposed_entity` with the type,
  a kebab-case slug, and a frontmatter seed (just the routing-key
  fields, not the extracted bill fields). The script will mark the
  document `needs_review` and record both your fields and your
  proposal for a human to apply.
- `unrecognized`: the OCR text is unintelligible or this isn't a
  document type PLOS handles. The script will mark `needs_review`
  with reason `claude_unrecognized` and record nothing.

Field-naming conventions (use these so future graduated extractors can
take over without renaming):

- Utility bills: `last_utility_bill_amount` (float, dollars),
  `last_utility_bill_date` (ISO date, the due date), `last_utility_bill_url`
  (the document's Paperless URL — passed to you below), `last_utility_bill_kwh`
  (int) for electric, plus `electric_account` / `gas_account` /
  `water_account` / `internet_account` for the routing key.
- Mortgage statements: `last_mortgage_statement_amount` (float, total
  due), `last_mortgage_statement_principal_balance` (float),
  `last_mortgage_statement_date` (ISO), `last_mortgage_statement_url`,
  `mortgage_loan_number` (string).
- Bank statements: `last_statement_balance`, `last_statement_end_date`,
  `last_statement_url`, `last_statement_deposits`,
  `last_statement_withdrawals`, `account_number`.
- Pay stubs: `last_paystub_gross`, `last_paystub_net`,
  `last_paystub_period_end`, `last_paystub_url`, `last_paystub_ytd_gross`,
  `paystub_employee_name`, `paystub_employer`.

Anything else, name the field with a `last_<thing>_*` prefix that's
specific (e.g. `last_insurance_premium_amount`).

OCR text and document metadata follow.

"""


@dataclass(frozen=True)
class ClaudeResult:
    """Parsed JSON response from Claude for one pending_claude doc."""

    doc_type: str
    route_status: str  # 'matched' | 'unmatched_entity' | 'unrecognized'
    entity_type: str | None
    entity_slug: str | None
    fields: dict[str, Any]
    rationale: str
    proposed_entity: dict[str, Any] | None


def _build_entity_manifest(vault_root: Path) -> str:
    """Bundle every entity index.md into the prompt manifest."""
    parts: list[str] = []
    source_root = vault_root / "source"
    if source_root.is_dir():
        for index_path in sorted(source_root.glob("*/*/index.md")):
            rel = "/" + str(index_path.resolve().relative_to(vault_root.resolve())).replace(
                "\\", "/"
            )
            parts.append(f"## {rel}\n\n```markdown\n{index_path.read_text(encoding='utf-8')}\n```\n\n")
    return "".join(parts)


def build_prompt(
    ocr_text: str, paperless_url: str, vault_root: Path
) -> str:
    """Assemble the per-document prompt sent to Claude."""
    manifest = _build_entity_manifest(vault_root)
    metadata = (
        f"Document Paperless URL (for `*_url` fields): {paperless_url}\n\n"
        f"OCR text:\n\n```\n{ocr_text}\n```\n"
    )
    return PROMPT_PREAMBLE + manifest + PROMPT_INSTRUCTION + metadata


_FENCE_RE = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)


def parse_response(raw: str) -> ClaudeResult:
    """Parse Claude's JSON response, tolerating ```json ... ``` fencing."""
    stripped = raw.strip()
    fence_match = _FENCE_RE.match(stripped)
    if fence_match:
        stripped = fence_match.group(1).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude response is not valid JSON: {e}") from e
    if not isinstance(parsed, dict):
        raise ValueError("Claude response must be a JSON object at top level")
    route_status = parsed.get("route_status")
    if route_status not in ("matched", "unmatched_entity", "unrecognized"):
        raise ValueError(
            f"Claude route_status must be matched|unmatched_entity|unrecognized, "
            f"got {route_status!r}"
        )
    return ClaudeResult(
        doc_type=parsed.get("doc_type") or "unknown",
        route_status=route_status,
        entity_type=parsed.get("entity_type"),
        entity_slug=parsed.get("entity_slug"),
        fields=parsed.get("fields") or {},
        rationale=parsed.get("rationale") or "",
        proposed_entity=parsed.get("proposed_entity"),
    )


def _dir_for_entity_type(entity_type: str) -> str | None:
    """Map a singular entity type ('property') to its source/<dir>/ name ('properties')."""
    for subdir, (type_name, _domain) in _ENTITY_TYPE_FROM_DIR.items():
        if type_name == entity_type:
            return subdir
    return None


def _entity_path(
    vault_root: Path, entity_type: str, slug: str
) -> Path | None:
    """Resolve an (entity_type, slug) pair to its index.md path; None if missing."""
    sub = _dir_for_entity_type(entity_type)
    if sub is None:
        return None
    candidate = vault_root / "source" / sub / slug / "index.md"
    return candidate if candidate.is_file() else None


def _ensure_entity(
    conn: sqlite3.Connection,
    entity_type: str,
    domain: str,
    slug: str,
    wiki_path: str,
) -> int:
    """Upsert and return entities.id. Same shape as worker._ensure_entity."""
    existing = conn.execute(
        "SELECT id FROM entities WHERE slug = ?", (slug,)
    ).fetchone()
    if existing:
        return existing["id"]
    cursor = conn.execute(
        "INSERT INTO entities (type, domain, slug, wiki_path) VALUES (?, ?, ?, ?)",
        (entity_type, domain, slug, wiki_path),
    )
    return cursor.lastrowid


def _record_extracted_fields(
    conn: sqlite3.Connection,
    document_id: int,
    entity_id: int,
    fields: dict[str, Any],
    source_doc_date: date,
) -> None:
    """Insert one extracted_fields row per field. entity_id is required —
    `extracted_fields.entity_id` is NOT NULL in the schema, so audit
    rows only land for documents that matched an entity. Unmatched
    Claude proposals are preserved on `documents.review_reason` instead
    (see process_one).
    """
    for name, value in fields.items():
        conn.execute(
            "INSERT INTO extracted_fields "
            "(document_id, entity_id, field_name, field_value, handler, "
            " source_document_date) VALUES (?, ?, ?, ?, ?, ?)",
            (
                document_id,
                entity_id,
                name,
                str(value) if value is not None else None,
                HANDLER,
                source_doc_date.isoformat(),
            ),
        )


def _parse_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def process_one(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    vault_root: Path,
    claude_cmd: str = "claude",
) -> str:
    """Process a single pending_claude document. Returns the new status."""
    paperless_id = row["paperless_id"]
    doc = paperless.get_document(paperless_id)
    text = doc.get("content") or ""
    if not text.strip():
        conn.execute(
            "UPDATE documents SET status='needs_review', review_reason=? WHERE id=?",
            ("empty_ocr_text", row["id"]),
        )
        logger.info(
            "doc id=%d paperless_id=%d: empty OCR -> needs_review",
            row["id"],
            paperless_id,
        )
        return "needs_review"

    prompt = build_prompt(text, row["paperless_url"], vault_root)
    logger.info(
        "doc id=%d paperless_id=%d: invoking %s --print (prompt length: %d chars)",
        row["id"],
        paperless_id,
        claude_cmd,
        len(prompt),
    )
    completed = subprocess.run(
        [claude_cmd, "--print"],
        input=prompt,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )

    try:
        result = parse_response(completed.stdout)
    except ValueError as e:
        conn.execute(
            "UPDATE documents SET status='needs_review', review_reason=? WHERE id=?",
            ("claude_invalid_response", row["id"]),
        )
        logger.warning(
            "doc id=%d paperless_id=%d: Claude response unparseable (%s) -> needs_review",
            row["id"],
            paperless_id,
            e,
        )
        return "needs_review"

    source_doc_date = _parse_date(row["document_date"]) or date.today()

    if result.route_status == "unrecognized":
        conn.execute(
            "UPDATE documents SET status='needs_review', review_reason=? WHERE id=?",
            ("claude_unrecognized", row["id"]),
        )
        logger.info(
            "doc id=%d paperless_id=%d: claude unrecognized (%s) -> needs_review",
            row["id"],
            paperless_id,
            result.rationale,
        )
        return "needs_review"

    if result.route_status == "unmatched_entity":
        # extracted_fields.entity_id is NOT NULL, so we can't write the
        # audit trail without a matched entity. Instead, JSON-encode
        # Claude's full proposal (extracted fields + proposed entity +
        # rationale) into documents.review_reason — a TEXT column —
        # so a Phase 5+ review-queue renderer can recover it cleanly.
        proposal_blob = json.dumps(
            {
                "reason": "claude_unmatched_entity",
                "doc_type": result.doc_type,
                "rationale": result.rationale,
                "fields": result.fields,
                "proposed_entity": result.proposed_entity,
            },
            sort_keys=True,
        )
        conn.execute(
            "UPDATE documents SET status='needs_review', review_reason=?, "
            "document_type=? WHERE id=?",
            (proposal_blob, result.doc_type, row["id"]),
        )
        logger.info(
            "doc id=%d paperless_id=%d: claude unmatched_entity (%s) -> needs_review",
            row["id"],
            paperless_id,
            result.rationale,
        )
        return "needs_review"

    # route_status == 'matched'
    if not result.entity_type or not result.entity_slug:
        conn.execute(
            "UPDATE documents SET status='needs_review', review_reason=? WHERE id=?",
            ("claude_matched_without_slug", row["id"]),
        )
        logger.warning(
            "doc id=%d paperless_id=%d: claude matched but no entity_slug/type -> needs_review",
            row["id"],
            paperless_id,
        )
        return "needs_review"

    entity_path = _entity_path(vault_root, result.entity_type, result.entity_slug)
    if entity_path is None:
        conn.execute(
            "UPDATE documents SET status='needs_review', review_reason=? WHERE id=?",
            ("claude_unmatched_entity", row["id"]),
        )
        logger.warning(
            "doc id=%d paperless_id=%d: claude said matched -> %s/%s but no such entity in vault",
            row["id"],
            paperless_id,
            result.entity_type,
            result.entity_slug,
        )
        return "needs_review"

    vault.merge_frontmatter(entity_path, result.fields, source_doc_date)
    subdir = _dir_for_entity_type(result.entity_type) or ""
    domain = _ENTITY_TYPE_FROM_DIR[subdir][1]
    wiki_path = str(entity_path.relative_to(vault_root)).replace("\\", "/")
    entity_id = _ensure_entity(
        conn, result.entity_type, domain, result.entity_slug, wiki_path
    )
    _record_extracted_fields(
        conn, row["id"], entity_id, result.fields, source_doc_date
    )
    conn.execute(
        "UPDATE documents SET status='done', document_type=? WHERE id=?",
        (result.doc_type, row["id"]),
    )
    logger.info(
        "doc id=%d paperless_id=%d: claude matched %s/%s -> done",
        row["id"],
        paperless_id,
        result.entity_type,
        result.entity_slug,
    )
    return "done"


def run(vault_root: Path, claude_cmd: str = "claude") -> dict[str, int]:
    """Drain every documents row in status='pending_claude'.

    Returns a count summary like {'done': 1, 'needs_review': 2}. On any
    per-doc exception, the row's status is left unchanged and the next
    drain attempt retries it.
    """
    conn = db.connect()
    counts: dict[str, int] = {"done": 0, "needs_review": 0, "errored": 0}
    rows = conn.execute(
        "SELECT id, paperless_id, paperless_url, title, correspondent, document_date "
        "FROM documents WHERE status='pending_claude' ORDER BY id"
    ).fetchall()
    if not rows:
        logger.info("no pending_claude documents to drain")
        conn.close()
        return counts

    for row in rows:
        try:
            new_status = process_one(conn, row, vault_root, claude_cmd)
            conn.commit()
            counts[new_status] = counts.get(new_status, 0) + 1
        except Exception:
            logger.exception(
                "doc id=%d paperless_id=%d: drain failed; status unchanged for retry",
                row["id"],
                row["paperless_id"],
            )
            conn.rollback()
            counts["errored"] += 1
    conn.close()
    return counts


def _resolve_vault_root() -> Path:
    raw = os.environ.get("PLOS_VAULT_ROOT")
    if not raw:
        raise RuntimeError("PLOS_VAULT_ROOT not set in environment")
    p = Path(raw)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()


def main() -> None:
    load_dotenv(override=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    vault_root = _resolve_vault_root()
    counts = run(vault_root)
    logger.info("drain complete: %s", counts)


if __name__ == "__main__":
    main()
