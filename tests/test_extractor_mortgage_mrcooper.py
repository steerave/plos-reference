"""
Tests for the Mr. Cooper mortgage-statement extractor.

Mirrors the shape of test_extractor_electric.py: clean OCR text,
whitespace variants, partial/missing fields, non-matching documents,
and the route() entity-matching behavior.
"""

from __future__ import annotations

from datetime import date

import pytest

from plos.extractors import registry
from plos.extractors.graduated import mortgage_statement_mr_cooper

SAMPLE_STATEMENT_TEXT = """\
Mr. Cooper
Home Loan Servicing

Statement date:        2026-04-15
Loan number:           LN-9912345
Property:              123 Main St, Davenport, IA 52801

Principal balance:     $284,237.18
Interest rate:         3.875%

Monthly payment breakdown
  Principal & interest      $1,840.22
  Escrow (taxes + ins)        $612.50
  Other                         $0.00
  -------------------------
  Total amount due:         $2,452.72

Payment due date:      May 1, 2026

Please remit to:
Mr. Cooper
PO Box 60516, Dallas TX 75266
"""


@pytest.fixture
def doc():
    return registry.DocumentMeta(
        paperless_id=51,
        paperless_url="http://localhost:8888/documents/51/",
        document_date=date(2026, 4, 15),
        correspondent="Mr. Cooper",
    )


def test_extracts_full_field_set_from_clean_statement(doc):
    fields = mortgage_statement_mr_cooper.extract(SAMPLE_STATEMENT_TEXT, doc)

    assert fields == {
        "last_mortgage_statement_amount": 2452.72,
        "last_mortgage_statement_principal_balance": 284237.18,
        "last_mortgage_statement_date": "2026-04-15",
        "last_mortgage_statement_url": "http://localhost:8888/documents/51/",
        "mortgage_loan_number": "LN-9912345",
    }


def test_returns_none_for_unrelated_document(doc):
    assert mortgage_statement_mr_cooper.extract(
        "This is a Wells Fargo statement.", doc
    ) is None


def test_returns_none_when_servicer_present_but_amount_missing(doc):
    text = (
        "Mr. Cooper\n"
        "Statement date: 2026-04-15\n"
        "Loan number: LN-9912345\n"
        "(no amount line)\n"
    )
    assert mortgage_statement_mr_cooper.extract(text, doc) is None


def test_returns_none_when_servicer_present_but_loan_number_missing(doc):
    text = (
        "Mr. Cooper\n"
        "Statement date: 2026-04-15\n"
        "Total amount due: $2,452.72\n"
    )
    assert mortgage_statement_mr_cooper.extract(text, doc) is None


def test_returns_none_when_servicer_present_but_statement_date_missing(doc):
    text = (
        "Mr. Cooper\n"
        "Loan number: LN-9912345\n"
        "Total amount due: $2,452.72\n"
    )
    assert mortgage_statement_mr_cooper.extract(text, doc) is None


def test_omits_principal_when_unparseable(doc):
    """Statement with no principal-balance line still extracts amount/date/loan."""
    text = (
        "Mr. Cooper\n"
        "Loan number: LN-9912345\n"
        "Statement date: 2026-04-15\n"
        "Total amount due: $2,452.72\n"
    )
    fields = mortgage_statement_mr_cooper.extract(text, doc)
    assert fields is not None
    assert "last_mortgage_statement_principal_balance" not in fields


def test_handles_collapsed_whitespace(doc):
    """Paperless OCR sometimes collapses runs of spaces to one."""
    collapsed = (
        "Mr. Cooper Loan number: LN-9912345 "
        "Statement date: 2026-04-15 "
        "Principal balance: $284,237.18 "
        "Total amount due: $2,452.72"
    )
    fields = mortgage_statement_mr_cooper.extract(collapsed, doc)
    assert fields["last_mortgage_statement_amount"] == 2452.72
    assert fields["last_mortgage_statement_principal_balance"] == 284237.18
    assert fields["mortgage_loan_number"] == "LN-9912345"
    assert fields["last_mortgage_statement_date"] == "2026-04-15"


def test_accepts_long_form_statement_date(doc):
    text = (
        "Mr. Cooper\n"
        "Loan number: LN-9912345\n"
        "Statement date: April 15, 2026\n"
        "Total amount due: $2,452.72\n"
    )
    fields = mortgage_statement_mr_cooper.extract(text, doc)
    assert fields["last_mortgage_statement_date"] == "2026-04-15"


def test_amount_with_thousands_separator(doc):
    text = (
        "Mr. Cooper\n"
        "Loan number: LN-9912345\n"
        "Statement date: 2026-04-15\n"
        "Total amount due: $12,345.67\n"
    )
    fields = mortgage_statement_mr_cooper.extract(text, doc)
    assert fields["last_mortgage_statement_amount"] == 12345.67


def test_url_field_uses_document_paperless_url(doc):
    fields = mortgage_statement_mr_cooper.extract(SAMPLE_STATEMENT_TEXT, doc)
    assert fields["last_mortgage_statement_url"] == "http://localhost:8888/documents/51/"


def test_registered_in_global_registry():
    """Sanity check: the extractor is wired into registry.EXTRACTORS."""
    names = [name for name, _ in registry.EXTRACTORS]
    assert "graduated:mortgage_statement_mr_cooper" in names


def test_route_returns_property_path_for_known_loan_number(tmp_path):
    folder = tmp_path / "source" / "properties" / "123-main-davenport"
    folder.mkdir(parents=True)
    (folder / "index.md").write_text(
        "---\nentity: property\nmortgage_loan_number: LN-9912345\n---\n",
        encoding="utf-8",
    )
    fields = {"mortgage_loan_number": "LN-9912345"}
    result = mortgage_statement_mr_cooper.route(fields, tmp_path)
    assert result.missing_key is False
    assert result.path is not None
    assert result.path.parent.name == "123-main-davenport"


def test_route_signals_missing_key_when_loan_number_absent(tmp_path):
    result = mortgage_statement_mr_cooper.route({}, tmp_path)
    assert result.missing_key is True
    assert result.path is None


def test_route_returns_unmatched_when_no_property_has_loan_number(tmp_path):
    (tmp_path / "source" / "properties").mkdir(parents=True)
    fields = {"mortgage_loan_number": "LN-XX"}
    result = mortgage_statement_mr_cooper.route(fields, tmp_path)
    assert result.missing_key is False
    assert result.path is None
