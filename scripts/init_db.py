"""
One-shot helper: create the SQLite schema at PLOS_DB_PATH.

Idempotent — re-runs are no-ops because db.init_schema uses CREATE TABLE IF NOT EXISTS.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from plos import db


def main() -> int:
    load_dotenv(override=True)
    path = os.environ.get("PLOS_DB_PATH")
    if not path:
        print("PLOS_DB_PATH is not set — copy .env.template to .env and edit", file=sys.stderr)
        return 1
    conn = db.connect(path)
    db.init_schema(conn)
    conn.close()
    print(f"schema initialized at {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
