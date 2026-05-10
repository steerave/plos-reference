"""
Tests for the vault indexer.

Exercises:
- review_reason JSON parsing (well-formed, plain-string, malformed).
- proposed-slug extraction.
- _resolve_unmatched (vault file present -> status flips; absent -> stays).
- Queue page rendering (frontmatter counts, section grouping, bullet shape,
  empty-queue marker).
- run() end-to-end (resolution + page atomic write).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from plos import db, indexer


# -----------------------------------------------------------------------------
# Fixtures + helpers
# -----------------------------------------------------------------------------


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    db.init_schema(c)
    yield c
    c.close()


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    root.mkdir()
    return root


def _insert_needs_review(
    conn: sqlite3.Connection,
    *,
    paperless_id: int,
    title: str,
    review_reason: str | None,
    document_type: str | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO documents
            (paperless_id, paperless_url, title, status, review_reason,
             document_type)
        VALUES (?, ?, ?, 'needs_review', ?, ?)
        """,
        (
            paperless_id,
            f"http://localhost:8888/documents/{paperless_id}/",
            title,
            review_reason,
            document_type,
        ),
    )
    conn.commit()
    return cur.lastrowid


def _claude_unmatched_blob(
    slug: str,
    *,
    ptype: str = "property",
    doc_type: str = "utility_bill_gas",
    rationale: str = "Looks like a gas bill from a new utility",
    fields: dict | None = None,
) -> str:
    return json.dumps(
        {
            "reason": "claude_unmatched_entity",
            "doc_type": doc_type,
            "rationale": rationale,
            "fields": fields or {"amount": "100.00"},
            "proposed_entity": {
                "type": ptype,
                "slug": slug,
                "frontmatter_seed": {"slug": slug},
            },
        },
        sort_keys=True,
    )


# -----------------------------------------------------------------------------
# parse_review_reason
# -----------------------------------------------------------------------------


def test_parse_review_reason_none_returns_none():
    assert indexer.parse_review_reason(None) is None
    assert indexer.parse_review_reason("") is None


def test_parse_review_reason_plain_string_returns_none():
    assert indexer.parse_review_reason("claude_unrecognized") is None
    assert indexer.parse_review_reason("no_routing_key_in_extraction") is None


def test_parse_review_reason_valid_json_returns_dict():
    blob = _claude_unmatched_blob("midamerican")
    parsed = indexer.parse_review_reason(blob)
    assert parsed is not None
    assert parsed["reason"] == "claude_unmatched_entity"
    assert parsed["proposed_entity"]["slug"] == "midamerican"


def test_parse_review_reason_malformed_json_returns_none():
    assert indexer.parse_review_reason("{not json") is None


def test_parse_review_reason_non_object_root_returns_none():
    assert indexer.parse_review_reason("[1, 2, 3]") is None


# -----------------------------------------------------------------------------
# _proposed_slug
# -----------------------------------------------------------------------------


def test_proposed_slug_extracts_slug_and_type():
    parsed = json.loads(_claude_unmatched_blob("midamerican", ptype="organization"))
    assert indexer._proposed_slug(parsed) == ("midamerican", "organization")


def test_proposed_slug_returns_none_for_non_unmatched_reason():
    assert indexer._proposed_slug({"reason": "claude_unrecognized"}) is None


def test_proposed_slug_returns_none_when_proposed_entity_absent():
    assert indexer._proposed_slug({"reason": "claude_unmatched_entity"}) is None


def test_proposed_slug_returns_none_when_slug_missing_or_empty():
    assert (
        indexer._proposed_slug(
            {
                "reason": "claude_unmatched_entity",
                "proposed_entity": {"type": "property"},  # no slug
            }
        )
        is None
    )
    assert (
        indexer._proposed_slug(
            {
                "reason": "claude_unmatched_entity",
                "proposed_entity": {"type": "property", "slug": ""},
            }
        )
        is None
    )


# -----------------------------------------------------------------------------
# _resolve_unmatched — needs file existence
# -----------------------------------------------------------------------------


def test_resolve_unmatched_flips_status_when_entity_exists(conn, vault):
    """Entity file present in source/ -> status flips needs_review -> resolved."""
    doc_id = _insert_needs_review(
        conn,
        paperless_id=42,
        title="MidAmerican.pdf",
        review_reason=_claude_unmatched_blob("midamerican", ptype="organization"),
    )
    _write(vault / "source" / "organizations" / "midamerican" / "index.md", "---\n---\n")

    rows = indexer._fetch_needs_review(conn)
    resolved = indexer._resolve_unmatched(conn, vault, rows)
    assert len(resolved) == 1
    assert resolved[0].document_id == doc_id
    assert resolved[0].proposed_slug == "midamerican"
    assert resolved[0].resolved_to == "source/organizations/midamerican/index.md"

    status = conn.execute(
        "SELECT status FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()["status"]
    assert status == "resolved"


def test_resolve_unmatched_keeps_status_when_entity_absent(conn, vault):
    """No file at source/<type>/<slug>/index.md -> row stays needs_review."""
    doc_id = _insert_needs_review(
        conn,
        paperless_id=42,
        title="MidAmerican.pdf",
        review_reason=_claude_unmatched_blob("midamerican"),
    )
    # No entity file created.

    rows = indexer._fetch_needs_review(conn)
    resolved = indexer._resolve_unmatched(conn, vault, rows)
    assert resolved == []
    status = conn.execute(
        "SELECT status FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()["status"]
    assert status == "needs_review"


def test_resolve_unmatched_skips_non_json_reasons(conn, vault):
    """A plain-string review_reason has no proposal — never resolvable."""
    _insert_needs_review(
        conn,
        paperless_id=42,
        title="x.pdf",
        review_reason="claude_unrecognized",
    )
    # Create an entity with the same string as a "slug" — shouldn't trigger.
    _write(
        vault / "source" / "organizations" / "claude_unrecognized" / "index.md",
        "---\n---\n",
    )
    rows = indexer._fetch_needs_review(conn)
    assert indexer._resolve_unmatched(conn, vault, rows) == []


def test_resolve_unmatched_idempotent(conn, vault):
    """Once a row is resolved, re-running the indexer doesn't re-resolve it."""
    _insert_needs_review(
        conn,
        paperless_id=42,
        title="x.pdf",
        review_reason=_claude_unmatched_blob("foo", ptype="organization"),
    )
    _write(vault / "source" / "organizations" / "foo" / "index.md", "---\n---\n")

    first = indexer._resolve_unmatched(conn, vault, indexer._fetch_needs_review(conn))
    assert len(first) == 1
    second = indexer._resolve_unmatched(conn, vault, indexer._fetch_needs_review(conn))
    assert second == []  # row no longer in needs_review


# -----------------------------------------------------------------------------
# render_queue_page
# -----------------------------------------------------------------------------


def test_render_queue_page_empty_queue_emits_marker():
    page = indexer.render_queue_page(
        [], resolved_this_run=0, refreshed="2026-05-10T12:00:00Z"
    )
    assert page.startswith("---\n")
    assert "queued: 0" in page
    assert "resolved_this_run: 0" in page
    assert "by_reason: {}" in page
    assert "queue is empty" in page


def test_render_queue_page_status_line_includes_counts():
    rows = [
        indexer.NeedsReviewRow(
            document_id=1,
            paperless_id=42,
            paperless_url="http://x/42/",
            title="x.pdf",
            review_reason="claude_unrecognized",
            document_type=None,
            created_at="2026-05-10",
        )
    ]
    page = indexer.render_queue_page(
        rows, resolved_this_run=2, refreshed="2026-05-10T12:00:00Z"
    )
    assert "**Status:** 1 document(s) need review. 2 resolved this run." in page


def test_render_queue_page_groups_under_distinct_sections():
    rows = [
        indexer.NeedsReviewRow(
            document_id=1,
            paperless_id=42,
            paperless_url="http://x/42/",
            title="claude.pdf",
            review_reason=_claude_unmatched_blob("midamerican"),
            document_type=None,
            created_at="2026-05-10",
        ),
        indexer.NeedsReviewRow(
            document_id=2,
            paperless_id=43,
            paperless_url="http://x/43/",
            title="legacy.pdf",
            review_reason="no_routing_key_in_extraction",
            document_type=None,
            created_at="2026-05-09",
        ),
    ]
    page = indexer.render_queue_page(
        rows, resolved_this_run=0, refreshed="2026-05-10T12:00:00Z"
    )
    assert "## Unmatched entity (Claude proposed)" in page
    assert "## Routing key not extracted" in page
    # Claude-proposed bullet carries slug + rationale
    assert "Proposed: `midamerican`" in page
    assert "Rationale: " in page
    # Plain-string reason bullet carries the reason inline
    assert "Reason detail: `no_routing_key_in_extraction`" in page


def test_render_queue_page_unknown_reason_lands_in_other():
    rows = [
        indexer.NeedsReviewRow(
            document_id=1,
            paperless_id=42,
            paperless_url="http://x/42/",
            title="x.pdf",
            review_reason="some_brand_new_reason",
            document_type=None,
            created_at="2026-05-10",
        )
    ]
    page = indexer.render_queue_page(
        rows, resolved_this_run=0, refreshed="2026-05-10T12:00:00Z"
    )
    assert "## Other" in page
    assert "some_brand_new_reason" in page


def test_render_queue_page_falls_back_to_paperless_id_when_title_null():
    rows = [
        indexer.NeedsReviewRow(
            document_id=1,
            paperless_id=42,
            paperless_url="http://x/42/",
            title=None,
            review_reason="claude_unrecognized",
            document_type=None,
            created_at="2026-05-10",
        )
    ]
    page = indexer.render_queue_page(
        rows, resolved_this_run=0, refreshed="2026-05-10T12:00:00Z"
    )
    assert "paperless_id=42" in page


# -----------------------------------------------------------------------------
# run — atomic write + integration
# -----------------------------------------------------------------------------


def test_run_writes_queue_page_atomically(conn, vault):
    """End-to-end: queued row stays queued, page lands at _review/queue.md."""
    _insert_needs_review(
        conn,
        paperless_id=42,
        title="x.pdf",
        review_reason="claude_unrecognized",
    )
    summary = indexer.run(vault, conn)
    assert summary["queued_before"] == 1
    assert summary["resolved_this_run"] == 0
    assert summary["queued_after"] == 1

    target = vault / "_review" / "queue.md"
    assert target.is_file()
    body = target.read_text(encoding="utf-8")
    assert "## Claude couldn't recognise" in body
    assert list(target.parent.glob("*.tmp")) == []


def test_run_resolves_and_renders_in_one_pass(conn, vault):
    """If the proposed entity exists, the row is resolved and queue is empty."""
    _insert_needs_review(
        conn,
        paperless_id=42,
        title="MidAmerican.pdf",
        review_reason=_claude_unmatched_blob("midamerican", ptype="organization"),
    )
    _write(vault / "source" / "organizations" / "midamerican" / "index.md", "---\n---\n")

    summary = indexer.run(vault, conn)
    assert summary["queued_before"] == 1
    assert summary["resolved_this_run"] == 1
    assert summary["queued_after"] == 0

    body = (vault / "_review" / "queue.md").read_text(encoding="utf-8")
    assert "1 resolved this run" in body
    # No section bullets for the resolved doc
    assert "## Unmatched entity (Claude proposed)" not in body


# -----------------------------------------------------------------------------
# Env handling
# -----------------------------------------------------------------------------


def test_resolve_vault_root_requires_env_var(monkeypatch):
    monkeypatch.delenv("PLOS_VAULT_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="PLOS_VAULT_ROOT"):
        indexer._resolve_vault_root()
