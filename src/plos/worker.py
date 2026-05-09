"""
Background worker — polls SQLite for new documents and logs them.

Phase 1: pick up rows with status='new', log them, mark status='done'.
No extraction, no Paperless REST calls, no vault writes — those land in Phase 2.
"""

from __future__ import annotations

import logging
import os
import signal
import sqlite3
import sys
import time

from . import db

logger = logging.getLogger("plos.worker")

DEFAULT_POLL_SECONDS = 60


def run_one_pass(conn: sqlite3.Connection) -> int:
    """Process every row currently in status='new'. Returns the count handled."""
    rows = conn.execute(
        "SELECT id, paperless_id, title, correspondent "
        "FROM documents WHERE status = 'new' ORDER BY id"
    ).fetchall()
    for row in rows:
        logger.info(
            "new document id=%s paperless_id=%s title=%r correspondent=%r",
            row["id"],
            row["paperless_id"],
            row["title"],
            row["correspondent"],
        )
        conn.execute("UPDATE documents SET status = 'done' WHERE id = ?", (row["id"],))
    conn.commit()
    return len(rows)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    poll_seconds = int(os.environ.get("PLOS_WORKER_POLL_SECONDS", DEFAULT_POLL_SECONDS))
    conn = db.connect()

    stop = False

    def _stop(_signum, _frame):
        nonlocal stop
        stop = True
        logger.info("stop signal received — shutting down after current pass")

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    logger.info("worker started — polling every %ds", poll_seconds)
    while not stop:
        try:
            run_one_pass(conn)
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
