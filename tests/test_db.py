from __future__ import annotations

import sqlite3

import pytest

from plos import db


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "plos.db")
    db.init_schema(c)
    yield c
    c.close()


def test_init_schema_creates_four_tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    names = {r["name"] for r in rows}
    assert {"documents", "entities", "extracted_fields", "corrections"} <= names


def test_init_schema_is_idempotent(conn):
    db.init_schema(conn)
    db.init_schema(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'documents'"
    ).fetchall()
    assert len(rows) == 1


def test_documents_defaults(conn):
    conn.execute(
        "INSERT INTO documents (paperless_id, paperless_url) VALUES (?, ?)",
        (1, "http://localhost:8000/documents/1/"),
    )
    conn.commit()
    row = conn.execute(
        "SELECT status, sensitivity FROM documents WHERE paperless_id = 1"
    ).fetchone()
    assert row["status"] == "new"
    assert row["sensitivity"] == "public"


def test_paperless_id_unique_constraint(conn):
    conn.execute(
        "INSERT INTO documents (paperless_id, paperless_url) VALUES (?, ?)",
        (1, "http://localhost:8000/documents/1/"),
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO documents (paperless_id, paperless_url) VALUES (?, ?)",
            (1, "http://localhost:8000/documents/1/"),
        )
        conn.commit()
