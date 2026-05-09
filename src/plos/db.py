"""
SQLite sidecar — schema and connection helper.

The vault is the source of truth; this database holds document metadata,
the extraction audit trail, and corrections. Schema is the four-table
design from ARCHITECTURE.md.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY,
  paperless_id INTEGER UNIQUE NOT NULL,
  paperless_url TEXT NOT NULL,
  content_hash TEXT,
  ocr_hash TEXT,
  title TEXT,
  document_date DATE,
  data_effective_date DATE,
  correspondent TEXT,
  document_type TEXT,
  sensitivity TEXT DEFAULT 'public',
  status TEXT DEFAULT 'new',
  review_reason TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS entities (
  id INTEGER PRIMARY KEY,
  type TEXT NOT NULL,
  domain TEXT NOT NULL,
  slug TEXT UNIQUE NOT NULL,
  wiki_path TEXT NOT NULL,
  aliases TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS extracted_fields (
  id INTEGER PRIMARY KEY,
  document_id INTEGER REFERENCES documents(id),
  entity_id INTEGER NOT NULL REFERENCES entities(id),
  field_name TEXT NOT NULL,
  field_value TEXT,
  confidence REAL DEFAULT 0.85,
  handler TEXT,
  source_document_date DATE,
  extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS corrections (
  id INTEGER PRIMARY KEY,
  entity_id INTEGER REFERENCES entities(id),
  field_name TEXT,
  correct_value TEXT,
  source_document_id INTEGER,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    """Open the sidecar database. Path defaults to PLOS_DB_PATH from the env."""
    if path is None:
        path = os.environ["PLOS_DB_PATH"]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create the four tables. Safe to call repeatedly."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()
