from __future__ import annotations

import importlib

import pytest

from plos import db


@pytest.fixture
def hook():
    # Loaded fresh per test so module-level state doesn't leak between cases.
    return importlib.import_module("post_consume_hook")


@pytest.fixture
def hook_env(tmp_path, monkeypatch):
    db_path = tmp_path / "plos.db"
    conn = db.connect(db_path)
    db.init_schema(conn)
    conn.close()

    monkeypatch.setenv("PLOS_DB_PATH_IN_CONTAINER", str(db_path))
    monkeypatch.setenv("DOCUMENT_ID", "42")
    monkeypatch.setenv("DOCUMENT_FILE_NAME", "some-bill.pdf")
    monkeypatch.setenv("DOCUMENT_CORRESPONDENT", "Acme Power")
    monkeypatch.setenv("PAPERLESS_URL_PUBLIC", "http://localhost:8000")
    return db_path


def _read_documents(db_path):
    conn = db.connect(db_path)
    try:
        return conn.execute(
            "SELECT paperless_id, paperless_url, title, correspondent, status FROM documents"
        ).fetchall()
    finally:
        conn.close()


def test_main_inserts_row(hook, hook_env):
    rc = hook.main()
    assert rc == 0

    rows = _read_documents(hook_env)
    assert len(rows) == 1
    assert rows[0]["paperless_id"] == 42
    assert rows[0]["paperless_url"] == "http://localhost:8000/documents/42/"
    assert rows[0]["title"] == "some-bill.pdf"
    assert rows[0]["correspondent"] == "Acme Power"
    assert rows[0]["status"] == "new"


def test_main_is_idempotent_on_duplicate(hook, hook_env):
    assert hook.main() == 0
    assert hook.main() == 0
    rows = _read_documents(hook_env)
    assert len(rows) == 1


def test_main_swallows_exceptions(hook, tmp_path, monkeypatch):
    # Point at a path under a file (not a directory) — the parent isn't a dir,
    # so any DB write would raise. The hook must still return 0.
    bogus_parent = tmp_path / "not-a-dir"
    bogus_parent.write_text("file, not a directory")
    monkeypatch.setenv("PLOS_DB_PATH_IN_CONTAINER", str(bogus_parent / "plos.db"))
    monkeypatch.setenv("DOCUMENT_ID", "99")
    monkeypatch.setenv("DOCUMENT_FILE_NAME", "x.pdf")

    assert hook.main() == 0
