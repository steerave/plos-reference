"""
Tests for the First Davenport Bank statement extractor.

Mirrors the shape of test_extractor_electric.py and
test_extractor_mortgage_mrcooper.py: clean OCR text, whitespace
variants, partial/missing fields, non-matching documents, and the
route() entity-matching behavior.
"""

from __future__ import annotations

from datetime import date

import pytest

from plos.extractors import registry
from plos.extractors.graduated import bank_statement_first_davenport

SAMPLE_STATEMENT_TEXT = """\
First Davenport Bank
Local banking since 1924

Account holder
Joe Sample
123 Main St
Davenport, IA 52801

Account number:        ACCT-4521
Statement period:      March 16, 2026 - April 15, 2026

Account activity summary
  Beginning balance:        $14,238.40
  Total deposits:           $5,420.00
  Total withdrawals:        $3,128.66
  -------------------------
  Ending balance:           $16,529.74

Questions about this statement?
Visit your local branch on Brady Street.
"""


@pytest.fixture
def doc():
    return registry.DocumentMeta(
        paperless_id=23,
        paperless_url="http://localhost:8888/documents/23/",
        document_date=date(2026, 4, 15),
        correspondent="First Davenport Bank",
    )


def test_extracts_full_field_set_from_clean_statement(doc):
    fields = bank_statement_first_davenport.extract(SAMPLE_STATEMENT_TEXT, doc)

    assert fields == {
        "last_statement_balance": 16529.74,
        "last_statement_end_date": "2026-04-15",
        "last_statement_url": "http://localhost:8888/documents/23/",
        "account_number": "ACCT-4521",
        "last_statement_deposits": 5420.00,
        "last_statement_withdrawals": 3128.66,
    }


def test_returns_none_for_unrelated_document(doc):
    assert (
        bank_statement_first_davenport.extract("This is a Chase statement.", doc)
        is None
    )


def test_returns_none_when_bank_present_but_balance_missing(doc):
    text = (
        "First Davenport Bank\n"
        "Account number: ACCT-4521\n"
        "Statement period: March 16, 2026 - April 15, 2026\n"
        "(no ending balance line)\n"
    )
    assert bank_statement_first_davenport.extract(text, doc) is None


def test_returns_none_when_bank_present_but_period_missing(doc):
    text = (
        "First Davenport Bank\n"
        "Account number: ACCT-4521\n"
        "Ending balance: $16,529.74\n"
    )
    assert bank_statement_first_davenport.extract(text, doc) is None


def test_returns_none_when_bank_present_but_account_missing(doc):
    text = (
        "First Davenport Bank\n"
        "Statement period: March 16, 2026 - April 15, 2026\n"
        "Ending balance: $16,529.74\n"
    )
    assert bank_statement_first_davenport.extract(text, doc) is None


def test_omits_deposits_withdrawals_when_unparseable(doc):
    """Statement with no deposits/withdrawals lines still extracts the rest."""
    text = (
        "First Davenport Bank\n"
        "Account number: ACCT-4521\n"
        "Statement period: March 16, 2026 - April 15, 2026\n"
        "Ending balance: $16,529.74\n"
    )
    fields = bank_statement_first_davenport.extract(text, doc)
    assert fields is not None
    assert "last_statement_deposits" not in fields
    assert "last_statement_withdrawals" not in fields


def test_handles_collapsed_whitespace(doc):
    """Paperless OCR sometimes collapses runs of spaces to one."""
    collapsed = (
        "First Davenport Bank Account number: ACCT-4521 "
        "Statement period: March 16, 2026 - April 15, 2026 "
        "Beginning balance: $14,238.40 "
        "Total deposits: $5,420.00 "
        "Total withdrawals: $3,128.66 "
        "Ending balance: $16,529.74"
    )
    fields = bank_statement_first_davenport.extract(collapsed, doc)
    assert fields["last_statement_balance"] == 16529.74
    assert fields["last_statement_deposits"] == 5420.00
    assert fields["account_number"] == "ACCT-4521"
    assert fields["last_statement_end_date"] == "2026-04-15"


def test_accepts_iso_period_dates(doc):
    text = (
        "First Davenport Bank\n"
        "Account number: ACCT-4521\n"
        "Statement period: 2026-03-16 - 2026-04-15\n"
        "Ending balance: $16,529.74\n"
    )
    fields = bank_statement_first_davenport.extract(text, doc)
    assert fields["last_statement_end_date"] == "2026-04-15"


def test_url_field_uses_document_paperless_url(doc):
    fields = bank_statement_first_davenport.extract(SAMPLE_STATEMENT_TEXT, doc)
    assert fields["last_statement_url"] == "http://localhost:8888/documents/23/"


def test_registered_in_global_registry():
    """Sanity check: the extractor is wired into registry.EXTRACTORS."""
    names = [name for name, _ in registry.EXTRACTORS]
    assert "graduated:bank_statement_first_davenport" in names


def test_route_returns_account_path_for_known_account_number(tmp_path):
    folder = tmp_path / "source" / "accounts" / "first-davenport-checking-4521"
    folder.mkdir(parents=True)
    (folder / "index.md").write_text(
        "---\nentity: account\naccount_number: ACCT-4521\n---\n",
        encoding="utf-8",
    )
    fields = {"account_number": "ACCT-4521"}
    result = bank_statement_first_davenport.route(fields, tmp_path)
    assert result.missing_key is False
    assert result.path is not None
    assert result.path.parent.name == "first-davenport-checking-4521"


def test_route_signals_missing_key_when_account_absent(tmp_path):
    result = bank_statement_first_davenport.route({}, tmp_path)
    assert result.missing_key is True
    assert result.path is None


def test_route_returns_unmatched_when_no_account_has_number(tmp_path):
    (tmp_path / "source" / "accounts").mkdir(parents=True)
    fields = {"account_number": "ACCT-XX"}
    result = bank_statement_first_davenport.route(fields, tmp_path)
    assert result.missing_key is False
    assert result.path is None
