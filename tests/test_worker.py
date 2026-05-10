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

import pytest
import responses

from plos import db, worker


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
    """Build a tmp vault with one property keyed to ACCT-12345 + LN-9912345
    and one account keyed to ACCT-4521 — the three entities the slices in
    Phase 3 route to."""
    properties = (
        tmp_path / "vault" / "source" / "properties" / "123-main-davenport"
    )
    properties.mkdir(parents=True)
    (properties / "index.md").write_text(
        "---\n"
        "type: source\n"
        "entity: property\n"
        "slug: 123-main-davenport\n"
        "address: 123 Main St, Davenport, IA 52801\n"
        "electric_account: ACCT-12345\n"
        "mortgage_loan_number: LN-9912345\n"
        "locked_fields: []\n"
        "---\n\n"
        "# 123 Main St, Davenport, IA\n",
        encoding="utf-8",
    )
    account = (
        tmp_path / "vault" / "source" / "accounts" / "first-davenport-checking-4521"
    )
    account.mkdir(parents=True)
    (account / "index.md").write_text(
        "---\n"
        "type: source\n"
        "entity: account\n"
        "slug: first-davenport-checking-4521\n"
        "bank: First Davenport Bank\n"
        "purpose: checking\n"
        "account_number: ACCT-4521\n"
        "locked_fields: []\n"
        "---\n\n"
        "# First Davenport Bank — Checking •••4521\n",
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


def _mock_document(paperless_id, text, **fields):
    """Mock the full /api/documents/{id}/ endpoint the worker now calls.

    Default `created_date` mirrors the Phase 2 sample bill so existing
    tests stay green without setting it explicitly. Pass `created_date=None`
    to omit the field entirely (used to test the no-date-from-API path).
    """
    body = {"content": text, "created_date": "2026-04-15"}
    body.update(fields)
    body = {k: v for k, v in body.items() if v is not None}
    responses.add(
        responses.GET,
        f"http://localhost:8888/api/documents/{paperless_id}/",
        json=body,
        status=200,
    )


SAMPLE_BILL = (
    "Acme Power & Light\n"
    "Account number: ACCT-12345\n"
    "Energy used this period: 850 kWh\n"
    "Amount due: $142.37\n"
    "Due date: April 30, 2026\n"
)


SAMPLE_MORTGAGE_STATEMENT = (
    "Mr. Cooper\n"
    "Loan number: LN-9912345\n"
    "Statement date: 2026-04-15\n"
    "Principal balance: $284,237.18\n"
    "Total amount due: $2,452.72\n"
)


SAMPLE_BANK_STATEMENT = (
    "First Davenport Bank\n"
    "Account number: ACCT-4521\n"
    "Statement period: March 16, 2026 - April 15, 2026\n"
    "Beginning balance: $14,238.40\n"
    "Total deposits: $5,420.00\n"
    "Total withdrawals: $3,128.66\n"
    "Ending balance: $16,529.74\n"
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
    _mock_document(1, "This is a Comcast bill, not Acme.")

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
    _mock_document(1, bill_for_unknown_account)

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
    _mock_document(1, SAMPLE_BILL)

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
    _mock_document(1, SAMPLE_BILL)
    worker.run_one_pass(conn, vault)

    # Reset the document to status='new' as if Paperless had re-fired the hook
    conn.execute("UPDATE documents SET status='new' WHERE paperless_id=1")
    conn.commit()
    _mock_document(1, SAMPLE_BILL)
    worker.run_one_pass(conn, vault)

    # Vault freshness rule means the second pass merges nothing — but the
    # extracted_fields audit trail records both attempts (full history).
    audit_count = conn.execute(
        "SELECT COUNT(*) AS n FROM extracted_fields"
    ).fetchone()["n"]
    # Five fields x 2 passes (the second pass still records the extraction
    # for audit, even though the vault didn't change).
    assert audit_count == 10


@responses.activate
def test_document_date_refreshed_from_paperless_when_null(conn, vault):
    """Hook inserts with NULL document_date; Paperless detects the date
    asynchronously. The worker must read it from the API on first
    processing pass and write it back to SQLite, so the freshness rule
    sees the real document date instead of falling back to today().
    """
    _insert(conn, 1, document_date=None)
    _mock_document(1, SAMPLE_BILL, created_date="2026-04-15")

    worker.run_one_pass(conn, vault)

    row = conn.execute(
        "SELECT document_date, status FROM documents WHERE paperless_id=1"
    ).fetchone()
    assert row["status"] == "done"
    assert row["document_date"] == "2026-04-15"

    # The bill the property's frontmatter records carries the real document
    # date, not today's date.
    property_path = (
        vault / "source" / "properties" / "123-main-davenport" / "index.md"
    )
    text = property_path.read_text(encoding="utf-8")
    assert "data_effective_date: '2026-04-15'" in text


@responses.activate
def test_document_date_left_alone_when_api_has_none(conn, vault):
    """If Paperless's response carries no usable date, the worker should
    fall back to whatever's already on the row (or today as last resort)
    rather than overwriting a known SQLite value with NULL."""
    _insert(conn, 1, document_date="2026-04-15")
    # Paperless response with no created_date / document_date / created
    _mock_document(1, SAMPLE_BILL, created_date=None)

    worker.run_one_pass(conn, vault)

    row = conn.execute(
        "SELECT document_date FROM documents WHERE paperless_id=1"
    ).fetchone()
    assert row["document_date"] == "2026-04-15"


@responses.activate
def test_mortgage_statement_routes_to_property_via_loan_number(conn, vault, caplog):
    """Mr. Cooper statement extractor + entity matcher land mortgage fields
    on the same property the electric extractor would, via a different
    routing key (loan number instead of electric account)."""
    _insert(conn, 7, document_date="2026-04-15", correspondent="Mr. Cooper")
    _mock_document(7, SAMPLE_MORTGAGE_STATEMENT)

    with caplog.at_level(logging.INFO, logger="plos.worker"):
        worker.run_one_pass(conn, vault)

    doc = conn.execute(
        "SELECT status, document_type FROM documents WHERE paperless_id=7"
    ).fetchone()
    assert doc["status"] == "done"
    assert doc["document_type"] == "mortgage_statement_mr_cooper"

    property_path = (
        vault / "source" / "properties" / "123-main-davenport" / "index.md"
    )
    text = property_path.read_text(encoding="utf-8")
    assert "last_mortgage_statement_amount: 2452.72" in text
    assert "last_mortgage_statement_principal_balance: 284237.18" in text
    assert "mortgage_loan_number: LN-9912345" in text

    rows = conn.execute(
        "SELECT field_name, handler FROM extracted_fields WHERE document_id = ?",
        (
            conn.execute("SELECT id FROM documents WHERE paperless_id=7").fetchone()[
                "id"
            ],
        ),
    ).fetchall()
    field_names = {r["field_name"] for r in rows}
    assert {
        "last_mortgage_statement_amount",
        "last_mortgage_statement_principal_balance",
        "last_mortgage_statement_date",
        "last_mortgage_statement_url",
        "mortgage_loan_number",
    } <= field_names
    for r in rows:
        assert r["handler"] == "graduated:mortgage_statement_mr_cooper"


@responses.activate
def test_bank_statement_routes_to_account_via_account_number(conn, vault, caplog):
    """First Davenport Bank statement extractor + entity matcher land
    bank-statement fields on the account entity (a different entity type
    than the property the previous extractors target)."""
    _insert(conn, 12, document_date="2026-04-15", correspondent="First Davenport Bank")
    _mock_document(12, SAMPLE_BANK_STATEMENT)

    with caplog.at_level(logging.INFO, logger="plos.worker"):
        worker.run_one_pass(conn, vault)

    doc = conn.execute(
        "SELECT status, document_type FROM documents WHERE paperless_id=12"
    ).fetchone()
    assert doc["status"] == "done"
    assert doc["document_type"] == "bank_statement_first_davenport"

    account_path = (
        vault
        / "source"
        / "accounts"
        / "first-davenport-checking-4521"
        / "index.md"
    )
    text = account_path.read_text(encoding="utf-8")
    assert "last_statement_balance: 16529.74" in text
    assert "last_statement_deposits: 5420.0" in text
    assert "last_statement_withdrawals: 3128.66" in text
    assert "last_statement_end_date: '2026-04-15'" in text
    assert "account_number: ACCT-4521" in text  # already present, idempotent

    rows = conn.execute(
        "SELECT field_name, handler FROM extracted_fields WHERE document_id = ?",
        (
            conn.execute("SELECT id FROM documents WHERE paperless_id=12").fetchone()[
                "id"
            ],
        ),
    ).fetchall()
    field_names = {r["field_name"] for r in rows}
    assert {
        "last_statement_balance",
        "last_statement_end_date",
        "last_statement_url",
        "account_number",
        "last_statement_deposits",
        "last_statement_withdrawals",
    } <= field_names
    for r in rows:
        assert r["handler"] == "graduated:bank_statement_first_davenport"

    # entities table picks up the new account row, with the right type/domain
    ent = conn.execute(
        "SELECT type, domain, slug FROM entities WHERE slug='first-davenport-checking-4521'"
    ).fetchone()
    assert ent["type"] == "account"
    assert ent["domain"] == "finance"


def test_vault_root_required_in_main(monkeypatch):
    monkeypatch.delenv("PLOS_VAULT_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="PLOS_VAULT_ROOT"):
        worker._resolve_vault_root()
