"""
Vault indexer — review-queue self-cleaner and queue-page renderer.

Two responsibilities, one module:

1. **Self-clean the review queue.** When the Phase 4b drain marks a
   document `needs_review` with `review_reason='claude_unmatched_entity'`
   (JSON-encoded with a `proposed_entity.slug`), the row sits until a
   human creates the matching entity in the vault. The indexer scans
   the queue, parses the JSON proposal, and if the proposed slug now
   resolves to a real `source/<type>/<slug>/index.md`, flips the
   document's status from `needs_review` to `resolved`. The user's
   action (creating the entity file) is what triggers the cleanup —
   no manual mark-as-resolved step.

2. **Render `_review/queue.md`.** Walks every remaining
   `status='needs_review'` row, groups by `review_reason`, and writes
   a markdown page so the queue is visible inside the vault. Stable
   shape: even an empty queue renders the page (with a "nothing
   queued" marker) so downstream readers don't have to handle a
   missing file.

Slice 1 deliberately stops at "detect + mark + render." Applying
Claude's pre-computed `fields` block to the now-existing entity
(the natural follow-through) is a separate slice — the user might
have created the entity for reasons that differ from Claude's
extraction, and the automatic apply should be opt-in once it lands.

The new `'resolved'` status joins the documents.status taxonomy
defined in CLAUDE.md Phase 2 conventions:

  - `done`           — extractor matched, entity routed, vault written
  - `pending_claude` — no graduated extractor recognised the document
  - `needs_review`   — extraction matched but entity is missing or
                       unparseable
  - `resolved`       — was needs_review; user has since created the
                       proposed entity. The original extraction was
                       NOT auto-applied; the user can apply it
                       manually or via a future slice.
  - `new`            — unchanged; reserved for transient processing
                       failure retry

Run from the repo root:
    python -m plos.indexer
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from sqlite3 import Connection

from dotenv import load_dotenv

from plos import db, entities

logger = logging.getLogger("plos.indexer")

QUEUE_PATH = Path("_review/queue.md")

# review_reason discriminators we render distinct sections for. Order
# here is the order sections appear in queue.md. The actionable
# "Claude proposed an entity — go create it" case leads.
REASON_LABELS: tuple[tuple[str, str], ...] = (
    ("claude_unmatched_entity", "Unmatched entity (Claude proposed)"),
    ("no_routing_key_in_extraction", "Routing key not extracted"),
    ("unmatched_entity", "Unmatched entity (graduated extractor)"),
    ("claude_unrecognized", "Claude couldn't recognise"),
    ("claude_invalid_response", "Claude returned invalid response"),
    ("claude_matched_without_slug", "Claude matched but no slug"),
    ("empty_ocr_text", "Empty OCR text"),
)


@dataclass(frozen=True)
class NeedsReviewRow:
    """One row from `documents` with `status='needs_review'`."""

    document_id: int
    paperless_id: int
    paperless_url: str
    title: str | None
    review_reason: str | None
    document_type: str | None
    created_at: str


@dataclass(frozen=True)
class ResolvedRow:
    """A document the indexer resolved this run."""

    document_id: int
    paperless_id: int
    proposed_slug: str
    proposed_type: str | None
    resolved_to: str  # vault-relative path


def _fetch_needs_review(conn: Connection) -> list[NeedsReviewRow]:
    """Return every `documents` row currently flagged needs_review."""
    rows = conn.execute(
        """
        SELECT id, paperless_id, paperless_url, title, review_reason,
               document_type, created_at
        FROM documents
        WHERE status = 'needs_review'
        ORDER BY created_at DESC, id DESC
        """
    ).fetchall()
    return [
        NeedsReviewRow(
            document_id=r["id"],
            paperless_id=r["paperless_id"],
            paperless_url=r["paperless_url"],
            title=r["title"],
            review_reason=r["review_reason"],
            document_type=r["document_type"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


def parse_review_reason(text: str | None) -> dict | None:
    """Parse a review_reason value into a JSON dict, or None.

    Returns None when:
    - text is None or empty
    - text is a plain string (not JSON), e.g. 'claude_unrecognized'
    - JSON parses but the root is not a dict
    """
    if not text:
        return None
    stripped = text.lstrip()
    if not stripped.startswith("{"):
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _proposed_slug(parsed: dict | None) -> tuple[str, str | None] | None:
    """Extract (slug, type) from a parsed review_reason JSON proposal.

    Returns None when the proposal is absent, malformed, or has no slug.
    """
    if not parsed:
        return None
    if parsed.get("reason") != "claude_unmatched_entity":
        return None
    proposed = parsed.get("proposed_entity")
    if not isinstance(proposed, dict):
        return None
    slug = proposed.get("slug")
    if not isinstance(slug, str) or not slug:
        return None
    entity_type = proposed.get("type")
    if not isinstance(entity_type, str):
        entity_type = None
    return slug, entity_type


def _resolve_unmatched(
    conn: Connection,
    vault_root: Path,
    rows: list[NeedsReviewRow],
) -> list[ResolvedRow]:
    """For each row with a parseable proposal, check if the slug now exists.

    Resolution updates the documents table in place. The review_reason
    is kept (audit trail); only status flips needs_review -> resolved.
    """
    resolved: list[ResolvedRow] = []
    for row in rows:
        parsed = parse_review_reason(row.review_reason)
        proposal = _proposed_slug(parsed)
        if proposal is None:
            continue
        slug, entity_type = proposal
        entity_path = entities.find_by_slug(slug, vault_root)
        if entity_path is None:
            continue
        wiki_path = (
            str(entity_path.relative_to(vault_root)).replace("\\", "/")
        )
        conn.execute(
            "UPDATE documents SET status = 'resolved' WHERE id = ?",
            (row.document_id,),
        )
        conn.commit()
        resolved.append(
            ResolvedRow(
                document_id=row.document_id,
                paperless_id=row.paperless_id,
                proposed_slug=slug,
                proposed_type=entity_type,
                resolved_to=wiki_path,
            )
        )
        logger.info(
            "doc id=%d paperless_id=%d resolved -> %s",
            row.document_id,
            row.paperless_id,
            wiki_path,
        )
    return resolved


def _label_for_reason(reason: str | None, parsed: dict | None) -> str:
    """Pick the section label for a row based on its review_reason."""
    if parsed and parsed.get("reason"):
        key = parsed["reason"]
    else:
        key = reason or "unknown"
    for k, label in REASON_LABELS:
        if k == key:
            return label
    return "Other"


def _section_order() -> list[str]:
    return [label for _key, label in REASON_LABELS] + ["Other"]


def _render_bullet(row: NeedsReviewRow, parsed: dict | None) -> str:
    """Render one bullet for a queued document. Most actionable info first."""
    title = row.title or f"paperless_id={row.paperless_id}"
    lines = [f"- **doc {row.document_id} — {title}**"]
    if parsed and parsed.get("reason") == "claude_unmatched_entity":
        proposal = parsed.get("proposed_entity") or {}
        slug = proposal.get("slug") or "(missing slug)"
        ptype = proposal.get("type") or "(missing type)"
        rationale = parsed.get("rationale")
        lines.append(f"  - Proposed: `{slug}` ({ptype})")
        if rationale:
            lines.append(f"  - Rationale: {rationale}")
    elif (
        row.review_reason
        and len(row.review_reason) <= 80
        and not row.review_reason.startswith("{")
    ):
        lines.append(f"  - Reason detail: `{row.review_reason}`")
    lines.append(f"  - → {row.paperless_url}")
    return "\n".join(lines) + "\n"


def render_queue_page(
    rows: list[NeedsReviewRow],
    *,
    resolved_this_run: int,
    refreshed: str | None = None,
) -> str:
    """Render `_review/queue.md` for the given remaining-needs-review rows.

    `rows` should be POST-resolution — i.e. the rows that still need
    review after the indexer's clean-up pass. `resolved_this_run` is
    the count of rows the indexer just flipped; it's surfaced as a
    one-line status, not as bullets (the underlying documents have
    moved on).
    """
    if refreshed is None:
        refreshed = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    groups: dict[str, list[NeedsReviewRow]] = {}
    for row in rows:
        parsed = parse_review_reason(row.review_reason)
        label = _label_for_reason(row.review_reason, parsed)
        groups.setdefault(label, []).append(row)

    by_reason_counts: dict[str, int] = {
        label: len(items) for label, items in groups.items()
    }

    parts: list[str] = [
        "---\n",
        "type: review\n",
        "artifact: queue\n",
        f"refreshed: {refreshed}\n",
        f"queued: {len(rows)}\n",
        f"resolved_this_run: {resolved_this_run}\n",
    ]
    if by_reason_counts:
        parts.append("by_reason:\n")
        for label, count in sorted(by_reason_counts.items()):
            parts.append(f"  {label!r}: {count}\n")
    else:
        parts.append("by_reason: {}\n")
    parts.append("indexer_version: 1\n")
    parts.append("---\n\n")
    parts.append("# Review queue\n\n")
    if not rows and resolved_this_run == 0:
        parts.append("_(queue is empty — nothing needs review)_\n\n")
    else:
        parts.append(
            f"**Status:** {len(rows)} document(s) need review. "
            f"{resolved_this_run} resolved this run.\n\n"
        )

    for label in _section_order():
        items = groups.get(label, [])
        if not items:
            continue
        parts.append(f"## {label}\n\n")
        for row in items:
            parsed = parse_review_reason(row.review_reason)
            parts.append(_render_bullet(row, parsed))
        parts.append("\n")

    parts.append(
        "---\n"
        "*Generated by `python -m plos.indexer`. "
        "Auto-cleans when proposed entities are created in `source/`.*\n"
    )
    return "".join(parts)


def _atomic_write(path: Path, content: str) -> None:
    """Write content to path via temp+rename. Mirrors compile_*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def run(vault_root: Path, conn: Connection) -> dict[str, object]:
    """Run the indexer: resolve what's resolvable, then render the queue page.

    Returns a small summary dict:
      {
        "queued_before": N,
        "resolved_this_run": M,
        "queued_after": N - M,
        "queue_path": "/abs/path/to/_review/queue.md",
      }
    """
    rows_before = _fetch_needs_review(conn)
    resolved = _resolve_unmatched(conn, vault_root, rows_before)
    rows_after = _fetch_needs_review(conn)

    page = render_queue_page(rows_after, resolved_this_run=len(resolved))
    target = vault_root / QUEUE_PATH
    _atomic_write(target, page)
    logger.info(
        "wrote %s (queued_before=%d, resolved=%d, queued_after=%d)",
        target,
        len(rows_before),
        len(resolved),
        len(rows_after),
    )
    return {
        "queued_before": len(rows_before),
        "resolved_this_run": len(resolved),
        "queued_after": len(rows_after),
        "queue_path": str(target),
    }


def _resolve_vault_root() -> Path:
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
        summary = run(vault_root, conn)
    logger.info(
        "indexer complete: queued_before=%d, resolved=%d, queued_after=%d",
        summary["queued_before"],
        summary["resolved_this_run"],
        summary["queued_after"],
    )


if __name__ == "__main__":
    main()
