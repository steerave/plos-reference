"""
Tests for the Beacon Software pay-stub extractor.

Mirrors test_extractor_electric.py / _mortgage_mrcooper.py /
_bank_first_davenport.py: clean OCR text, whitespace variants,
partial/missing fields, non-matching documents, and the route()
entity-matching behavior (employer + employee name).
"""

from __future__ import annotations

from datetime import date

import pytest

from plos.extractors import registry
from plos.extractors.graduated import paystub_beacon_software

SAMPLE_PAYSTUB_TEXT = """\
Beacon Software
Earnings statement

Employee
Employee:        Joe Sample
Employee ID:     E-001

Pay period:      April 1, 2026 - April 14, 2026
Period ending:   2026-04-14
Pay date:        2026-04-17

Earnings
  Gross pay:                $4,615.38
  Federal income tax:         $612.40
  State income tax:           $184.62
  FICA + Medicare:            $353.08
  Pre-tax deductions:         $320.00
  -------------------------
  Net pay:                  $3,145.28

Year-to-date
  YTD gross:               $36,923.04
  YTD net:                 $25,162.24
"""


@pytest.fixture
def doc():
    return registry.DocumentMeta(
        paperless_id=88,
        paperless_url="http://localhost:8888/documents/88/",
        document_date=date(2026, 4, 17),
        correspondent="Beacon Software",
    )


def test_extracts_full_field_set_from_clean_paystub(doc):
    fields = paystub_beacon_software.extract(SAMPLE_PAYSTUB_TEXT, doc)

    assert fields == {
        "last_paystub_gross": 4615.38,
        "last_paystub_net": 3145.28,
        "last_paystub_period_end": "2026-04-14",
        "last_paystub_url": "http://localhost:8888/documents/88/",
        "paystub_employee_name": "Joe Sample",
        "paystub_employer": "Beacon Software",
        "last_paystub_ytd_gross": 36923.04,
    }


def test_returns_none_for_unrelated_document(doc):
    assert (
        paystub_beacon_software.extract("This is an Anthropic pay stub.", doc) is None
    )


def test_returns_none_when_employer_present_but_gross_missing(doc):
    text = (
        "Beacon Software\n"
        "Employee: Joe Sample\n"
        "Period ending: 2026-04-14\n"
        "Net pay: $3,145.28\n"
    )
    assert paystub_beacon_software.extract(text, doc) is None


def test_returns_none_when_employer_present_but_net_missing(doc):
    text = (
        "Beacon Software\n"
        "Employee: Joe Sample\n"
        "Period ending: 2026-04-14\n"
        "Gross pay: $4,615.38\n"
    )
    assert paystub_beacon_software.extract(text, doc) is None


def test_returns_none_when_employer_present_but_period_missing(doc):
    text = (
        "Beacon Software\n"
        "Employee: Joe Sample\n"
        "Gross pay: $4,615.38\n"
        "Net pay: $3,145.28\n"
    )
    assert paystub_beacon_software.extract(text, doc) is None


def test_returns_none_when_employer_present_but_employee_missing(doc):
    text = (
        "Beacon Software\n"
        "Period ending: 2026-04-14\n"
        "Gross pay: $4,615.38\n"
        "Net pay: $3,145.28\n"
    )
    assert paystub_beacon_software.extract(text, doc) is None


def test_omits_ytd_when_unparseable(doc):
    """Stub with no YTD line still extracts the period fields."""
    text = (
        "Beacon Software\n"
        "Employee: Joe Sample\n"
        "Period ending: 2026-04-14\n"
        "Gross pay: $4,615.38\n"
        "Net pay: $3,145.28\n"
    )
    fields = paystub_beacon_software.extract(text, doc)
    assert fields is not None
    assert "last_paystub_ytd_gross" not in fields


def test_handles_collapsed_whitespace(doc):
    """Paperless OCR sometimes collapses runs of spaces to one."""
    collapsed = (
        "Beacon Software Earnings statement "
        "Employee: Joe Sample "
        "Period ending: 2026-04-14 "
        "Gross pay: $4,615.38 Net pay: $3,145.28 "
        "YTD gross: $36,923.04"
    )
    fields = paystub_beacon_software.extract(collapsed, doc)
    assert fields["last_paystub_gross"] == 4615.38
    assert fields["last_paystub_net"] == 3145.28
    assert fields["paystub_employee_name"] == "Joe Sample"
    assert fields["last_paystub_period_end"] == "2026-04-14"
    assert fields["last_paystub_ytd_gross"] == 36923.04


def test_accepts_long_form_period_ending(doc):
    text = (
        "Beacon Software\n"
        "Employee: Joe Sample\n"
        "Period ending: April 14, 2026\n"
        "Gross pay: $4,615.38\n"
        "Net pay: $3,145.28\n"
    )
    fields = paystub_beacon_software.extract(text, doc)
    assert fields["last_paystub_period_end"] == "2026-04-14"


def test_accepts_pay_period_range_when_no_explicit_end(doc):
    """When 'Period ending' is missing, fall back to the end of 'Pay period: <start> - <end>'."""
    text = (
        "Beacon Software\n"
        "Employee: Joe Sample\n"
        "Pay period: April 1, 2026 - April 14, 2026\n"
        "Gross pay: $4,615.38\n"
        "Net pay: $3,145.28\n"
    )
    fields = paystub_beacon_software.extract(text, doc)
    assert fields["last_paystub_period_end"] == "2026-04-14"


def test_url_field_uses_document_paperless_url(doc):
    fields = paystub_beacon_software.extract(SAMPLE_PAYSTUB_TEXT, doc)
    assert fields["last_paystub_url"] == "http://localhost:8888/documents/88/"


def test_registered_in_global_registry():
    """Sanity check: the extractor is wired into registry.EXTRACTORS."""
    names = [name for name, _ in registry.EXTRACTORS]
    assert "graduated:paystub_beacon_software" in names


def test_route_returns_person_path_for_known_name_employer(tmp_path):
    folder = tmp_path / "source" / "people" / "joe"
    folder.mkdir(parents=True)
    (folder / "index.md").write_text(
        "---\nentity: person\nlegal_name: Joe Sample\n"
        "employer_current: Beacon Software\n---\n",
        encoding="utf-8",
    )
    fields = {
        "paystub_employee_name": "Joe Sample",
        "paystub_employer": "Beacon Software",
    }
    result = paystub_beacon_software.route(fields, tmp_path)
    assert result.missing_key is False
    assert result.path is not None
    assert result.path.parent.name == "joe"


def test_route_signals_missing_key_when_employee_absent(tmp_path):
    fields = {"paystub_employer": "Beacon Software"}
    result = paystub_beacon_software.route(fields, tmp_path)
    assert result.missing_key is True
    assert result.path is None


def test_route_signals_missing_key_when_employer_absent(tmp_path):
    fields = {"paystub_employee_name": "Joe Sample"}
    result = paystub_beacon_software.route(fields, tmp_path)
    assert result.missing_key is True
    assert result.path is None


def test_route_returns_unmatched_when_no_person_matches_pair(tmp_path):
    folder = tmp_path / "source" / "people" / "alex"
    folder.mkdir(parents=True)
    (folder / "index.md").write_text(
        "---\nentity: person\nlegal_name: Alex Sample\n"
        "employer_current: Beacon Software\n---\n",
        encoding="utf-8",
    )
    fields = {
        "paystub_employee_name": "Joe Sample",
        "paystub_employer": "Beacon Software",
    }
    result = paystub_beacon_software.route(fields, tmp_path)
    assert result.missing_key is False
    assert result.path is None


def test_route_does_not_match_on_name_alone(tmp_path):
    """Two people share a name but have different employers — only the
    one whose employer matches the stub should be returned."""
    joe_at_beacon = tmp_path / "source" / "people" / "joe-beacon"
    joe_at_beacon.mkdir(parents=True)
    (joe_at_beacon / "index.md").write_text(
        "---\nentity: person\nlegal_name: Joe Sample\n"
        "employer_current: Beacon Software\n---\n",
        encoding="utf-8",
    )
    joe_at_other = tmp_path / "source" / "people" / "joe-other"
    joe_at_other.mkdir(parents=True)
    (joe_at_other / "index.md").write_text(
        "---\nentity: person\nlegal_name: Joe Sample\n"
        "employer_current: Other Inc\n---\n",
        encoding="utf-8",
    )
    fields = {
        "paystub_employee_name": "Joe Sample",
        "paystub_employer": "Beacon Software",
    }
    result = paystub_beacon_software.route(fields, tmp_path)
    assert result.path is not None
    assert result.path.parent.name == "joe-beacon"
