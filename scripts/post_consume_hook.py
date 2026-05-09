"""
Paperless-ngx post-consume hook. Runs INSIDE the Paperless container.

Receives document metadata via env vars Paperless sets (DOCUMENT_ID, etc.),
inserts one row in `documents` with status='new', exits in <100ms.

Stdlib-only by design: this script is bind-mounted into the Paperless
container and runs against the container's Python — no PLOS package, no
third-party deps. Any exception is swallowed and logged; a hook failure
must never break Paperless ingestion.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH_IN_CONTAINER = "/usr/src/paperless/plos/plos.db"
DEFAULT_PAPERLESS_URL_PUBLIC = "http://localhost:8000"


def _log_error(db_dir: Path, exc: BaseException) -> None:
    try:
        db_dir.mkdir(parents=True, exist_ok=True)
        with (db_dir / "hook.log").open("a", encoding="utf-8") as fh:
            ts = datetime.now(timezone.utc).isoformat()
            fh.write(f"{ts} post_consume_hook error: {exc!r}\n")
            fh.write(traceback.format_exc())
            fh.write("\n")
    except Exception:
        # Last resort: stderr. Paperless captures this in its own logs.
        print(f"post_consume_hook error (could not write hook.log): {exc!r}", file=sys.stderr)


def main() -> int:
    db_path = os.environ.get("PLOS_DB_PATH_IN_CONTAINER", DEFAULT_DB_PATH_IN_CONTAINER)
    db_dir = Path(db_path).parent

    try:
        document_id = os.environ["DOCUMENT_ID"]
        title = os.environ.get("DOCUMENT_FILE_NAME") or os.environ.get(
            "DOCUMENT_ORIGINAL_FILENAME"
        )
        correspondent = os.environ.get("DOCUMENT_CORRESPONDENT") or None
        public_url = os.environ.get("PAPERLESS_URL_PUBLIC", DEFAULT_PAPERLESS_URL_PUBLIC).rstrip(
            "/"
        )
        paperless_url = f"{public_url}/documents/{document_id}/"

        conn = sqlite3.connect(db_path, timeout=5.0)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO documents "
                "(paperless_id, paperless_url, title, correspondent, status) "
                "VALUES (?, ?, ?, ?, 'new')",
                (int(document_id), paperless_url, title, correspondent),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        _log_error(db_dir, exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
