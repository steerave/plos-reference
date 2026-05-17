#!/usr/bin/env python3
"""
Wrapper that invokes a PLOS module on a schedule and records the run.

One consistent entry point for Windows Task Scheduler (or any other
scheduler) to call every PLOS task that has a `main()`. Records each
run in the SQLite `scheduled_runs` table so the user can see "did
the cron job actually fire today?" without trawling Event Viewer.

Usage:
    python scripts/scheduled_run.py <task-name>

Valid task names (each maps to `plos.<name>.main()`):

    compile_this_week     daily compile pass for compiled/this-week.md
    compile_anomalies     monthly compile pass for compiled/anomalies.md
    compile_tax_prep      monthly compile pass for compiled/tax-prep.md
    audit_pass            weekly artifact-provenance audit
    notifications         weekly digest (dry-run unless PLOS_NOTIFY_SEND=1)
    indexer               review-queue self-cleaner + queue.md renderer

Records in `scheduled_runs`:
    task_name              one of the names above
    started_at             ISO timestamp at wrapper entry
    completed_at           ISO timestamp at wrapper exit (success or
                           exception path)
    exit_status            'success' on clean main() / 'error' on raise
    error_summary          one-line `<ExcType>: <message>` if errored

Exits 0 on success, 1 on the wrapped task raising, 2 on a bad task
name (so Task Scheduler can distinguish "task ran and failed" from
"the schedule itself is misconfigured"). Working directory is pinned
to the repo root before invoking the task so `.env` loading and
relative paths resolve consistently regardless of how the scheduler
launches us.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Pin cwd to the repo root *before* dotenv/env-loading anywhere else
# in the import chain. `__file__` is `scripts/scheduled_run.py`; the
# repo root is its parent's parent.
REPO_ROOT = Path(__file__).resolve().parent.parent
os.chdir(REPO_ROOT)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

from plos import db  # noqa: E402

logger = logging.getLogger("plos.scheduled_run")

TASKS: dict[str, str] = {
    "compile_this_week": "plos.compile_this_week",
    "compile_anomalies": "plos.compile_anomalies",
    "compile_tax_prep": "plos.compile_tax_prep",
    "audit_pass": "plos.audit_pass",
    "notifications": "plos.notifications",
    "indexer": "plos.indexer",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record_start(task_name: str) -> int:
    """Insert the 'running' row, return its id, close the connection.

    Connection is short-lived deliberately — the wrapped task opens
    its own SQLite connection if it needs one, and overlapping
    long-held connections on the same file can deadlock under
    pessimistic locking modes.
    """
    conn = db.connect()
    try:
        db.init_schema(conn)
        cur = conn.execute(
            """
            INSERT INTO scheduled_runs (task_name, started_at, exit_status)
            VALUES (?, ?, 'running')
            """,
            (task_name, _now_iso()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _record_finish(
    run_id: int, exit_status: str, error_summary: str | None
) -> None:
    """Update the row at the end of the task. Best-effort: if the SQLite
    write itself fails, we log and continue — the schedule shouldn't
    crash because the audit row couldn't be updated."""
    try:
        conn = db.connect()
        try:
            conn.execute(
                """
                UPDATE scheduled_runs
                   SET completed_at = ?, exit_status = ?, error_summary = ?
                 WHERE id = ?
                """,
                (_now_iso(), exit_status, error_summary, run_id),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:  # pragma: no cover — defensive only
        logger.exception(
            "failed to update scheduled_runs row id=%d; "
            "the wrapped task's exit status is %s",
            run_id,
            exit_status,
        )


def run_task(task_name: str) -> tuple[int, str, str | None]:
    """Run one task, return (exit_code, status, error_summary).

    Pure function — extracted so tests can drive it without going
    through argparse / sys.exit / the logging setup.
    """
    if task_name not in TASKS:
        return 2, "error", f"unknown task '{task_name}'"

    run_id = _record_start(task_name)

    error_summary: str | None = None
    exit_code = 0
    status = "success"
    try:
        module = importlib.import_module(TASKS[task_name])
        module.main()
    except SystemExit as exc:
        # `main()` may call sys.exit() internally; treat non-zero
        # codes as errors but preserve the code.
        code = exc.code if isinstance(exc.code, int) else 1
        if code != 0:
            status = "error"
            error_summary = f"SystemExit: {code}"
            exit_code = code
    except Exception as exc:
        status = "error"
        error_summary = f"{type(exc).__name__}: {exc}"[:500]
        traceback.print_exc()
        exit_code = 1

    _record_finish(run_id, status, error_summary)
    return exit_code, status, error_summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a PLOS module on a schedule, recording the run."
    )
    parser.add_argument(
        "task",
        help=f"Task name. One of: {', '.join(sorted(TASKS))}",
    )
    args = parser.parse_args()

    load_dotenv(override=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )

    if args.task not in TASKS:
        # Match the run_task() convention but exit before recording a row.
        sys.stderr.write(
            f"unknown task '{args.task}'. Valid: {', '.join(sorted(TASKS))}\n"
        )
        return 2

    logger.info("scheduled_run start: task=%s", args.task)
    exit_code, status, error_summary = run_task(args.task)
    if status == "success":
        logger.info("scheduled_run complete: task=%s status=success", args.task)
    else:
        logger.error(
            "scheduled_run complete: task=%s status=error error=%r",
            args.task,
            error_summary,
        )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
