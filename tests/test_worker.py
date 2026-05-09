from __future__ import annotations

import logging

import pytest

from plos import db, worker


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "plos.db")
    db.init_schema(c)
    yield c
    c.close()


def _insert_new(conn, paperless_id: int, title: str, correspondent: str | None = None) -> None:
    conn.execute(
        "INSERT INTO documents (paperless_id, paperless_url, title, correspondent, status) "
        "VALUES (?, ?, ?, ?, 'new')",
        (paperless_id, f"http://localhost:8000/documents/{paperless_id}/", title, correspondent),
    )
    conn.commit()


def test_run_one_pass_processes_new_rows(conn, caplog):
    _insert_new(conn, 1, "alpha.pdf", "Acme Power")
    _insert_new(conn, 2, "beta.pdf")

    with caplog.at_level(logging.INFO, logger="plos.worker"):
        handled = worker.run_one_pass(conn)

    assert handled == 2
    statuses = [r["status"] for r in conn.execute("SELECT status FROM documents ORDER BY id")]
    assert statuses == ["done", "done"]

    messages = [r.getMessage() for r in caplog.records if r.name == "plos.worker"]
    assert any("paperless_id=1" in m and "title='alpha.pdf'" in m for m in messages)
    assert any("paperless_id=2" in m and "title='beta.pdf'" in m for m in messages)


def test_run_one_pass_skips_done_rows(conn, caplog):
    _insert_new(conn, 1, "alpha.pdf")
    conn.execute("UPDATE documents SET status = 'done' WHERE paperless_id = 1")
    conn.commit()

    with caplog.at_level(logging.INFO, logger="plos.worker"):
        handled = worker.run_one_pass(conn)

    assert handled == 0
    assert not [r for r in caplog.records if r.name == "plos.worker"]


def test_run_one_pass_handles_empty_db(conn):
    assert worker.run_one_pass(conn) == 0
