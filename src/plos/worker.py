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

from . import db, paperless, vault
from .extractors import registry

logger = logging.getLogger("plos.worker")

DEFAULT_POLL_SECONDS = 60

# Maps the source/<dir>/ name to (entities.type, entities.domain) for
# upserting into the `entities` table when a document is matched. Adding
# a new entity type means one entry here plus one extractor module that
# routes into it.
_ENTITY_TYPE_FROM_DIR: dict[str, tuple[str, str]] = {
    "properties": ("property", "properties"),
    "accounts": ("account", "finance"),
    "people": ("person", "family"),
    "vehicles": ("vehicle", "vehicles"),
    "organizations": ("organization", "organizations"),
}


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


def _api_document_date(doc: dict) -> date | None:
    """Pick a usable document date from Paperless's API response.

    Paperless's date-detection runs asynchronously after consume, so the
    date the post-consume hook saw may be NULL even though the API now
    has one. We check the explicit date fields first, then fall back to
    the `created` datetime which Paperless sets to the detected date.
    """
    for key in ("created_date", "document_date"):
        d = _parse_date(doc.get(key))
        if d is not None:
            return d
    return _parse_date(doc.get("created"))


def _ensure_entity(
    conn: sqlite3.Connection,
    entity_type: str,
    domain: str,
    slug: str,
    wiki_path: str,
) -> int:
    """Upsert and return entities.id for the given slug."""
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


def _entity_type_for(entity_path: Path, vault_root: Path) -> tuple[str, str]:
    """Derive (entity_type, domain) from a matched index.md path.

    Path shape is `vault_root/source/<dir>/<slug>/index.md`. The dir
    name maps to a pair via `_ENTITY_TYPE_FROM_DIR`.
    """
    rel = entity_path.relative_to(vault_root).parts
    if len(rel) < 3 or rel[0] != "source":
        raise ValueError(f"unexpected entity path: {entity_path}")
    return _ENTITY_TYPE_FROM_DIR[rel[1]]


def _process_document(
    conn: sqlite3.Connection, row: sqlite3.Row, vault_root: Path
) -> None:
    doc = paperless.get_document(row["paperless_id"])
    text = doc.get("content") or ""
    existing_date = _parse_date(row["document_date"])
    api_date = _api_document_date(doc)
    document_date = api_date or existing_date
    if api_date is not None and api_date != existing_date:
        conn.execute(
            "UPDATE documents SET document_date=? WHERE id=?",
            (api_date.isoformat(), row["id"]),
        )
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

    handler, module, fields = result
    route_result = module.route(fields, vault_root)
    if route_result.missing_key:
        conn.execute(
            "UPDATE documents SET status='needs_review', review_reason=? WHERE id=?",
            ("no_routing_key_in_extraction", row["id"]),
        )
        logger.info(
            "matched but routing key missing id=%s extractor=%s status=needs_review",
            row["id"],
            handler,
        )
        return
    if route_result.path is None:
        conn.execute(
            "UPDATE documents SET status='needs_review', review_reason=? WHERE id=?",
            ("unmatched_entity", row["id"]),
        )
        logger.info(
            "unmatched entity id=%s extractor=%s status=needs_review",
            row["id"],
            handler,
        )
        return

    entity_path: Path = route_result.path
    source_doc_date = document_date or date.today()
    changed = vault.merge_frontmatter(entity_path, fields, source_doc_date)

    slug = entity_path.parent.name
    wiki_path = str(entity_path.relative_to(vault_root)).replace("\\", "/")
    entity_type, domain = _entity_type_for(entity_path, vault_root)
    entity_id = _ensure_entity(conn, entity_type, domain, slug, wiki_path)
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

    document_type = handler.split(":", 1)[1] if ":" in handler else handler
    conn.execute(
        "UPDATE documents SET status='done', document_type=? WHERE id=?",
        (document_type, row["id"]),
    )
    logger.info(
        "extracted id=%s paperless_id=%s extractor=%s entity=%s changed=%s status=done",
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
    load_dotenv(override=True)
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
