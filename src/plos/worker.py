"""
Background worker — drains new documents through the Phase 2 pipeline.

Each poll cycle:
  1. SELECT documents.* WHERE status='new'
  2. For each row: fetch OCR text from Paperless, dispatch to graduated
     extractors, route the matched bill to its property entity, atomically
     merge fields into that property's index.md, record one extracted_fields
     row per field, mark the document done.
  3. Sleep PLOS_WORKER_POLL_SECONDS, repeat.

Outcome statuses written back to documents.status:
  done            - extraction matched and vault was updated.
  pending_claude  - no graduated extractor recognized the document; it
                    sits for a future Claude Code session to handle.
  needs_review    - graduated extractor matched but no entity could be
                    routed to (review_reason carries why).
  new             - left unchanged when processing raised an exception,
                    so the next poll retries.
"""

from __future__ import annotations

import logging
import os
import signal
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from . import db, entities, paperless, vault
from .extractors import registry

logger = logging.getLogger("plos.worker")

DEFAULT_POLL_SECONDS = 60


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


def _ensure_property_entity(
    conn: sqlite3.Connection, slug: str, wiki_path: str
) -> int:
    """Upsert and return entities.id for this property."""
    existing = conn.execute(
        "SELECT id FROM entities WHERE slug = ?", (slug,)
    ).fetchone()
    if existing:
        return existing["id"]
    cursor = conn.execute(
        "INSERT INTO entities (type, domain, slug, wiki_path) VALUES (?, ?, ?, ?)",
        ("property", "properties", slug, wiki_path),
    )
    return cursor.lastrowid


def _process_document(
    conn: sqlite3.Connection, row: sqlite3.Row, vault_root: Path
) -> None:
    text = paperless.get_document_text(row["paperless_id"])
    document_date = _parse_date(row["document_date"])
    meta = registry.DocumentMeta(
        paperless_id=row["paperless_id"],
        paperless_url=row["paperless_url"],
        document_date=document_date,
        correspondent=row["correspondent"],
    )

    result = registry.dispatch(text, meta)
    if result is None:
        conn.execute(
            "UPDATE documents SET status='pending_claude' WHERE id = ?", (row["id"],)
        )
        logger.info(
            "no extractor id=%s paperless_id=%s status=pending_claude",
            row["id"],
            row["paperless_id"],
        )
        return

    handler, fields = result
    account = fields.get("electric_account")
    if not account:
        conn.execute(
            "UPDATE documents SET status='needs_review', review_reason=? WHERE id=?",
            ("no_account_in_extraction", row["id"]),
        )
        logger.info(
            "matched but no account id=%s extractor=%s status=needs_review",
            row["id"],
            handler,
        )
        return

    property_path = entities.find_property_by_electric_account(account, vault_root)
    if property_path is None:
        conn.execute(
            "UPDATE documents SET status='needs_review', review_reason=? WHERE id=?",
            ("unmatched_entity", row["id"]),
        )
        logger.info(
            "unmatched entity id=%s extractor=%s account=%s status=needs_review",
            row["id"],
            handler,
            account,
        )
        return

    source_doc_date = document_date or date.today()
    changed = vault.merge_frontmatter(property_path, fields, source_doc_date)

    slug = property_path.parent.name
    wiki_path = str(property_path.relative_to(vault_root)).replace("\\", "/")
    entity_id = _ensure_property_entity(conn, slug, wiki_path)
    for field_name, field_value in fields.items():
        conn.execute(
            "INSERT INTO extracted_fields "
            "(document_id, entity_id, field_name, field_value, handler, source_document_date) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                row["id"],
                entity_id,
                field_name,
                str(field_value),
                handler,
                source_doc_date.isoformat(),
            ),
        )

    conn.execute(
        "UPDATE documents SET status='done', document_type='utility_bill_electric' WHERE id=?",
        (row["id"],),
    )
    logger.info(
        "extracted id=%s paperless_id=%s extractor=%s property=%s changed=%s status=done",
        row["id"],
        row["paperless_id"],
        handler,
        slug,
        sorted(changed.keys()),
    )


def run_one_pass(conn: sqlite3.Connection, vault_root: Path) -> int:
    """Process every row currently in status='new'. Returns count handled."""
    rows = conn.execute(
        "SELECT id, paperless_id, paperless_url, title, correspondent, document_date "
        "FROM documents WHERE status = 'new' ORDER BY id"
    ).fetchall()
    for row in rows:
        try:
            _process_document(conn, row, vault_root)
        except Exception:
            logger.exception(
                "failed to process document id=%s paperless_id=%s — leaving status=new for retry",
                row["id"],
                row["paperless_id"],
            )
            conn.rollback()
            continue
        conn.commit()
    return len(rows)


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
    poll_seconds = int(os.environ.get("PLOS_WORKER_POLL_SECONDS", DEFAULT_POLL_SECONDS))
    vault_root = _resolve_vault_root()
    conn = db.connect()

    stop = False

    def _stop(_signum, _frame):
        nonlocal stop
        stop = True
        logger.info("stop signal received — shutting down after current pass")

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    logger.info(
        "worker started — polling every %ds, vault_root=%s", poll_seconds, vault_root
    )
    while not stop:
        try:
            run_one_pass(conn, vault_root)
        except Exception:
            logger.exception("worker pass failed")
        for _ in range(poll_seconds):
            if stop:
                break
            time.sleep(1)

    conn.close()
    logger.info("worker stopped")


if __name__ == "__main__":
    main()
