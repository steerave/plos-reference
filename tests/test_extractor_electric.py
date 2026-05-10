"""
Tests for the Acme Power & Light electric-bill extractor.

Validates clean OCR text, OCR whitespace variants, partial/missing
fields, and non-matching documents. The end-to-end test in Slice 7
verifies the extractor against actual Paperless OCR output of the
sample PDF; these unit tests cover the parsing logic in isolation.
"""

from __future__ import annotations

from datetime import date

import pytest

from plos.extractors import registry
from plos.extractors.graduated import utility_bill_electric

SAMPLE_BILL_TEXT = """\
Acme Power & Light
Reliable energy since 1987

Service address
123 Main St
Davenport, IA 52801

Account number:        ACCT-12345
Statement date:        2026-04-15
Service period:        March 15, 2026 - April 14, 2026
Energy used this period:    850 kWh
Charges this period:        $142.37

                                   Amount due:    $142.37
                                   Due date:      April 30, 2026

Please remit payment to:
Acme Power & Light
PO Box 90210, Davenport IA 52801
"""


@pytest.fixture
def doc():
    return registry.DocumentMeta(
        paperless_id=42,
        paperless_url="http://localhost:8888/documents/42/",
        document_date=date(2026, 4, 15),
        correspondent="Acme Power & Light",
    )


def test_extracts_full_field_set_from_clean_bill(doc):
    fields = utility_bill_electric.extract(SAMPLE_BILL_TEXT, doc)

    assert fields == {
        "last_utility_bill_amount": 142.37,
        "last_utility_bill_date": "2026-04-30",
        "last_utility_bill_kwh": 850,
        "last_utility_bill_url": "http://localhost:8888/documents/42/",
        "electric_account": "ACCT-12345",
    }


def test_returns_none_for_unrelated_document(doc):
    assert utility_bill_electric.extract("This is a Comcast bill.", doc) is None


def test_returns_none_when_provider_present_but_amount_missing(doc):
    text = "Acme Power & Light - statement notification.\nNo amount due section here."
    assert utility_bill_electric.extract(text, doc) is None


def test_returns_none_when_provider_present_but_due_date_missing(doc):
    text = "Acme Power & Light\nAmount due: $142.37\nNo due date."
    assert utility_bill_electric.extract(text, doc) is None


def test_handles_collapsed_whitespace(doc):
    """Paperless OCR sometimes collapses runs of spaces to one."""
    collapsed = (
        "Acme Power & Light Account number: ACCT-12345 "
        "Energy used this period: 850 kWh "
        "Amount due: $142.37 Due date: April 30, 2026"
    )
    fields = utility_bill_electric.extract(collapsed, doc)
    assert fields["last_utility_bill_amount"] == 142.37
    assert fields["last_utility_bill_date"] == "2026-04-30"
    assert fields["last_utility_bill_kwh"] == 850
    assert fields["electric_account"] == "ACCT-12345"


def test_accepts_iso_due_date_format(doc):
    text = (
        "Acme Power & Light\n"
        "Amount due: $142.37\n"
        "Due date: 2026-04-30\n"
        "850 kWh used"
    )
    fields = utility_bill_electric.extract(text, doc)
    assert fields["last_utility_bill_date"] == "2026-04-30"


def test_url_field_uses_document_paperless_url(doc):
    fields = utility_bill_electric.extract(SAMPLE_BILL_TEXT, doc)
    assert fields["last_utility_bill_url"] == "http://localhost:8888/documents/42/"


def test_amount_with_thousands_separator(doc):
    text = (
        "Acme Power & Light\n"
        "Amount due: $1,234.56\n"
        "Due date: April 30, 2026\n"
        "9000 kWh used"
    )
    fields = utility_bill_electric.extract(text, doc)
    assert fields["last_utility_bill_amount"] == 1234.56


def test_omits_kwh_when_unparseable(doc):
    """Bill with no kWh figure still extracts amount/date — kwh just missing."""
    text = (
        "Acme Power & Light\n"
        "Amount due: $142.37\n"
        "Due date: April 30, 2026\n"
        "Account number: ACCT-12345\n"
    )
    fields = utility_bill_electric.extract(text, doc)
    assert "last_utility_bill_kwh" not in fields


def test_registered_in_global_registry():
    """Sanity check: the extractor is wired into registry.EXTRACTORS."""
    names = [name for name, _ in registry.EXTRACTORS]
    assert "graduated:utility_bill_electric" in names
