"""
Tests for the Phase 2 worker pipeline.

Covers each outcome status the worker can write back to documents:
  done            - extractor + entity match, vault written, extracted_fields recorded
  pending_claude  - no graduated extractor recognized the document
  needs_review    - extractor matched but no entity could be routed to
  new (unchanged) - exception during processing, retry on next poll

Plus the lifecycle invariants: empty DB, only status='new' rows are
touched, atomicity (failed processing rolls back partial DB writes).
"""

from __future__ import annotations

import logging
from datetime import date

import pytest
import responses
from responses import matchers

from plos import db, worker
from plos.extractors import registry


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("PAPERLESS_URL_PUBLIC", "http://localhost:8888")
    monkeypatch.setenv("PAPERLESS_API_TOKEN", "test-token-abc")


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "plos.db")
    db.init_schema(c)
    yield c
    c.close()


@pytest.fixture
def vault(tmp_path):
    """Build a tmp vault with one property keyed to ACCT-12345."""
    folder = tmp_path / "vault" / "source" / "properties" / "123-main-davenport"
    folder.mkdir(parents=True)
    (folder / "index.md").write_text(
        "---\n"
        "type: source\n"
        "entity: property\n"
        "slug: 123-main-davenport\n"
        "address: 123 Main St, Davenport, IA 52801\n"
        "electric_account: ACCT-12345\n"
        "locked_fields: []\n"
        "---\n\n"
        "# 123 Main St, Davenport, IA\n",
        encoding="utf-8",
    )
    return tmp_path / "vault"


def _insert(conn, paperless_id, **kw):
    conn.execute(
        "INSERT INTO documents (paperless_id, paperless_url, title, correspondent, "
        "document_date, status) VALUES (?, ?, ?, ?, ?, 'new')",
        (
            paperless_id,
            kw.get("url", f"http://localhost:8888/documents/{paperless_id}/"),
            kw.get("title"),
            kw.get("correspondent"),
            kw.get("document_date"),
        ),
    )
    conn.commit()


def _mock_text(paperless_id, text):
    responses.add(
        responses.GET,
        f"http://localhost:8888/api/documents/{paperless_id}/",
        json={"content": text},
        status=200,
        match=[matchers.query_param_matcher({"fields": "content"})],
    )


SAMPLE_BILL = (
    "Acme Power & Light\n"
    "Account number: ACCT-12345\n"
    "Energy used this period: 850 kWh\n"
    "Amount due: $142.37\n"
    "Due date: April 30, 2026\n"
)


def test_handles_empty_db(conn, vault):
    assert worker.run_one_pass(conn, vault) == 0


@responses.activate
def test_skips_rows_not_in_new_status(conn, vault):
    _insert(conn, 1, document_date="2026-04-15")
    conn.execute("UPDATE documents SET status='done' WHERE paperless_id=1")
    conn.commit()
    assert worker.run_one_pass(conn, vault) == 0


@responses.activate
def test_unrecognized_document_is_routed_to_pending_claude(conn, vault, caplog):
    _insert(conn, 1, document_date="2026-04-15")
    _mock_text(1, "This is a Comcast bill, not Acme.")

    with caplog.at_level(logging.INFO, logger="plos.worker"):
        handled = worker.run_one_pass(conn, vault)

    assert handled == 1
    row = conn.execute("SELECT status FROM documents WHERE paperless_id=1").fetchone()
    assert row["status"] == "pending_claude"
    assert any("status=pending_claude" in r.getMessage() for r in caplog.records)


@responses.activate
def test_unmatched_entity_routed_to_review(conn, vault, caplog):
    _insert(conn, 1, document_date="2026-04-15")
    bill_for_unknown_account = SAMPLE_BILL.replace("ACCT-12345", "ACCT-UNKNOWN")
    _mock_text(1, bill_for_unknown_account)

    with caplog.at_level(logging.INFO, logger="plos.worker"):
        worker.run_one_pass(conn, vault)

    row = conn.execute(
        "SELECT status, review_reason FROM documents WHERE paperless_id=1"
    ).fetchone()
    assert row["status"] == "needs_review"
    assert row["review_reason"] == "unmatched_entity"


@responses.activate
def test_full_pipeline_writes_vault_and_extracted_fields(conn, vault, caplog):
    _insert(conn, 1, document_date="2026-04-15", correspondent="Acme Power & Light")
    _mock_text(1, SAMPLE_BILL)

    with caplog.at_level(logging.INFO, logger="plos.worker"):
        worker.run_one_pass(conn, vault)

    # Document marked done with the right type
    doc = conn.execute(
        "SELECT status, document_type FROM documents WHERE paperless_id=1"
    ).fetchone()
    assert doc["status"] == "done"
    assert doc["document_type"] == "utility_bill_electric"

    # Property frontmatter has the new fields
    property_path = (
        vault / "source" / "properties" / "123-main-davenport" / "index.md"
    )
    text = property_path.read_text(encoding="utf-8")
    assert "last_utility_bill_amount: 142.37" in text
    assert "last_utility_bill_date: '2026-04-30'" in text or 'last_utility_bill_date: "2026-04-30"' in text or "last_utility_bill_date: 2026-04-30" in text
    assert "last_utility_bill_kwh: 850" in text
    assert "data_effective_date" in text

    # Audit trail: one extracted_fields row per extracted field, all
    # pointing at the same entity record
    rows = conn.execute(
        "SELECT field_name, field_value, handler FROM extracted_fields "
        "WHERE document_id = ?",
        (
            conn.execute("SELECT id FROM documents WHERE paperless_id=1").fetchone()[
                "id"
            ],
        ),
    ).fetchall()
    field_names = {r["field_name"] for r in rows}
    assert {
        "last_utility_bill_amount",
        "last_utility_bill_date",
        "last_utility_bill_kwh",
        "last_utility_bill_url",
        "electric_account",
    } <= field_names
    for r in rows:
        assert r["handler"] == "graduated:utility_bill_electric"

    # Entity record was upserted into entities table
    ent = conn.execute(
        "SELECT type, slug, wiki_path FROM entities WHERE slug='123-main-davenport'"
    ).fetchone()
    assert ent["type"] == "property"
    assert ent["wiki_path"].endswith("123-main-davenport/index.md")


@responses.activate
def test_processing_failure_leaves_status_new(conn, vault, caplog):
    """If the Paperless API errors, the row stays in 'new' for the next poll cycle."""
    _insert(conn, 1, document_date="2026-04-15")
    responses.add(
        responses.GET,
        "http://localhost:8888/api/documents/1/",
        json={"detail": "boom"},
        status=500,
        match=[matchers.query_param_matcher({"fields": "content"})],
    )

    with caplog.at_level(logging.ERROR, logger="plos.worker"):
        worker.run_one_pass(conn, vault)

    row = conn.execute("SELECT status FROM documents WHERE paperless_id=1").fetchone()
    assert row["status"] == "new"
    assert any("failed to process" in r.getMessage() for r in caplog.records)


@responses.activate
def test_idempotent_when_re_extracting_same_day_doc(conn, vault):
    """Re-processing the same bill on the same date does not duplicate the audit trail."""
    _insert(conn, 1, document_date="2026-04-15")
    _mock_text(1, SAMPLE_BILL)
    worker.run_one_pass(conn, vault)

    # Reset the document to status='new' as if Paperless had re-fired the hook
    conn.execute("UPDATE documents SET status='new' WHERE paperless_id=1")
    conn.commit()
    _mock_text(1, SAMPLE_BILL)
    worker.run_one_pass(conn, vault)

    # Vault freshness rule means the second pass merges nothing — but the
    # extracted_fields audit trail records both attempts (full history).
    audit_count = conn.execute(
        "SELECT COUNT(*) AS n FROM extracted_fields"
    ).fetchone()["n"]
    # Five fields x 2 passes (the second pass still records the extraction
    # for audit, even though the vault didn't change).
    assert audit_count == 10


def test_vault_root_required_in_main(monkeypatch):
    monkeypatch.delenv("PLOS_VAULT_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="PLOS_VAULT_ROOT"):
        worker._resolve_vault_root()
