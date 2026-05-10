"""
Tests for `scripts/scheduled_run.py`.

The wrapper is exercised against an in-memory SQLite (substituted for
the file path resolution via monkeypatch of `db.connect`). Wrapped
modules are stand-in objects with `main()` callbacks that succeed,
raise, or sys.exit.

Production tasks (plos.compile_this_week, etc.) are NOT invoked from
these tests — we mock `importlib.import_module` to return a controlled
stub.
"""

from __future__ import annotations

import sqlite3
import sys
import types
from pathlib import Path

import pytest

# conftest.py already adds scripts/ to sys.path so this import works.
import scheduled_run  # type: ignore[import-not-found]

from plos import db


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    db.init_schema(c)
    yield c
    c.close()


@pytest.fixture
def shared_conn(tmp_path: Path, monkeypatch) -> sqlite3.Connection:
    """A tmp-file SQLite — each `db.connect()` reopens the same file.

    scheduled_run calls `db.connect()` multiple times and closes the
    connection between writes. We patch `db.connect()` to open a fresh
    connection to a tmp-file DB so reads after writes see the same
    rows. Returns one persistent connection the test uses to inspect
    state.
    """
    db_path = tmp_path / "test.db"

    def fresh_conn() -> sqlite3.Connection:
        c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        return c

    monkeypatch.setattr(scheduled_run.db, "connect", fresh_conn)

    # Initialise schema once via the patched connect path.
    init = fresh_conn()
    try:
        db.init_schema(init)
    finally:
        init.close()

    inspect = fresh_conn()
    yield inspect
    inspect.close()


def _stub_module(*, main_callback) -> types.ModuleType:
    """Build a stand-in module object with the given main() behaviour."""
    mod = types.ModuleType("stub")
    mod.main = main_callback  # type: ignore[attr-defined]
    return mod


# -----------------------------------------------------------------------------
# run_task — success path
# -----------------------------------------------------------------------------


def test_run_task_records_success_row(shared_conn, monkeypatch):
    calls = {"main": 0}

    def fake_main():
        calls["main"] += 1

    monkeypatch.setitem(scheduled_run.TASKS, "fake_task", "plos.fake_task")
    monkeypatch.setattr(
        scheduled_run.importlib,
        "import_module",
        lambda name: _stub_module(main_callback=fake_main),
    )
    exit_code, status, err = scheduled_run.run_task("fake_task")
    assert exit_code == 0
    assert status == "success"
    assert err is None
    assert calls["main"] == 1

    row = shared_conn.execute(
        "SELECT * FROM scheduled_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["task_name"] == "fake_task"
    assert row["exit_status"] == "success"
    assert row["error_summary"] is None
    assert row["started_at"] is not None
    assert row["completed_at"] is not None


# -----------------------------------------------------------------------------
# run_task — error path
# -----------------------------------------------------------------------------


def test_run_task_records_error_when_main_raises(shared_conn, monkeypatch):
    def fake_main():
        raise RuntimeError("boom: subprocess died")

    monkeypatch.setitem(scheduled_run.TASKS, "fake_task", "plos.fake_task")
    monkeypatch.setattr(
        scheduled_run.importlib,
        "import_module",
        lambda name: _stub_module(main_callback=fake_main),
    )
    exit_code, status, err = scheduled_run.run_task("fake_task")
    assert exit_code == 1
    assert status == "error"
    assert "RuntimeError" in err
    assert "boom" in err

    row = shared_conn.execute(
        "SELECT * FROM scheduled_runs WHERE task_name='fake_task' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["exit_status"] == "error"
    assert "RuntimeError" in row["error_summary"]
    assert row["completed_at"] is not None


def test_run_task_records_error_on_systemexit_nonzero(shared_conn, monkeypatch):
    def fake_main():
        raise SystemExit(7)

    monkeypatch.setitem(scheduled_run.TASKS, "fake_task", "plos.fake_task")
    monkeypatch.setattr(
        scheduled_run.importlib,
        "import_module",
        lambda name: _stub_module(main_callback=fake_main),
    )
    exit_code, status, err = scheduled_run.run_task("fake_task")
    assert exit_code == 7
    assert status == "error"
    assert "SystemExit" in err


def test_run_task_treats_systemexit_zero_as_success(shared_conn, monkeypatch):
    """main() that calls sys.exit(0) is a clean exit, not an error."""

    def fake_main():
        raise SystemExit(0)

    monkeypatch.setitem(scheduled_run.TASKS, "fake_task", "plos.fake_task")
    monkeypatch.setattr(
        scheduled_run.importlib,
        "import_module",
        lambda name: _stub_module(main_callback=fake_main),
    )
    exit_code, status, _ = scheduled_run.run_task("fake_task")
    assert exit_code == 0
    assert status == "success"


# -----------------------------------------------------------------------------
# run_task — unknown task name
# -----------------------------------------------------------------------------


def test_run_task_unknown_task_returns_2(shared_conn, monkeypatch):
    """Unknown task name exits 2; no row is inserted (the caller is
    misconfigured, not a task that ran and failed)."""
    monkeypatch.setattr(
        scheduled_run.importlib,
        "import_module",
        lambda name: pytest.fail("import_module must not be called"),
    )
    exit_code, status, err = scheduled_run.run_task("not_a_real_task")
    assert exit_code == 2
    assert status == "error"
    assert "unknown task" in err

    rows = shared_conn.execute(
        "SELECT * FROM scheduled_runs WHERE task_name='not_a_real_task'"
    ).fetchall()
    assert rows == []


# -----------------------------------------------------------------------------
# Real task list — every entry is a real, importable module with main()
# -----------------------------------------------------------------------------


def test_task_map_points_to_real_modules():
    """Every entry in TASKS must point to a real `plos.*` module that has
    a `main()` callable. Catches typos / forgotten registrations."""
    import importlib

    for task_name, module_name in scheduled_run.TASKS.items():
        module = importlib.import_module(module_name)
        assert callable(getattr(module, "main", None)), (
            f"TASKS['{task_name}'] -> {module_name} has no callable main()"
        )


# -----------------------------------------------------------------------------
# Idempotent schema init
# -----------------------------------------------------------------------------


def test_record_start_creates_scheduled_runs_table_if_missing(
    tmp_path: Path, monkeypatch
):
    """Fresh DB without scheduled_runs gets the table on first wrapper call."""
    db_path = tmp_path / "empty.db"

    def fresh_conn():
        c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        return c

    monkeypatch.setattr(scheduled_run.db, "connect", fresh_conn)
    # Deliberately NOT calling db.init_schema first — the wrapper does it.

    run_id = scheduled_run._record_start("compile_this_week")
    assert isinstance(run_id, int) and run_id > 0

    inspect = fresh_conn()
    try:
        row = inspect.execute(
            "SELECT * FROM scheduled_runs WHERE id = ?", (run_id,)
        ).fetchone()
        assert row["exit_status"] == "running"
    finally:
        inspect.close()
