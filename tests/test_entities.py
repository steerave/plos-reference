"""Tests for the entity matcher."""

from __future__ import annotations

from pathlib import Path

import pytest

from plos import entities


def _property(vault: Path, slug: str, frontmatter: dict) -> Path:
    """Materialize source/properties/<slug>/index.md with the given frontmatter."""
    folder = vault / "source" / "properties" / slug
    folder.mkdir(parents=True, exist_ok=True)
    fm_lines = "\n".join(f"{k}: {v}" for k, v in frontmatter.items())
    (folder / "index.md").write_text(
        f"---\n{fm_lines}\n---\n\n# {slug}\n",
        encoding="utf-8",
    )
    return folder / "index.md"


@pytest.fixture
def two_properties(tmp_path):
    _property(
        tmp_path,
        "123-main-davenport",
        {"entity": "property", "electric_account": "ACCT-12345"},
    )
    _property(
        tmp_path,
        "456-oak-st",
        {"entity": "property", "electric_account": "ACCT-67890"},
    )
    return tmp_path


def test_finds_property_by_account(two_properties):
    path = entities.find_property_by_electric_account("ACCT-12345", two_properties)
    assert path is not None
    assert path.parent.name == "123-main-davenport"


def test_returns_none_for_unknown_account(two_properties):
    assert entities.find_property_by_electric_account("ACCT-XX", two_properties) is None


def test_returns_none_when_no_properties_dir(tmp_path):
    assert entities.find_property_by_electric_account("ACCT-12345", tmp_path) is None


def test_skips_property_without_electric_account(tmp_path):
    """A property entity that hasn't declared an electric account is invisible to this matcher."""
    _property(tmp_path, "no-electric", {"entity": "property"})
    _property(
        tmp_path,
        "with-electric",
        {"entity": "property", "electric_account": "ACCT-12345"},
    )
    path = entities.find_property_by_electric_account("ACCT-12345", tmp_path)
    assert path is not None
    assert path.parent.name == "with-electric"


def test_returns_first_when_duplicates(tmp_path):
    """Defensive: two properties claiming the same account is a data error;
    we return the first lexicographically and let the user fix the data."""
    _property(
        tmp_path,
        "a-duplicate",
        {"entity": "property", "electric_account": "ACCT-12345"},
    )
    _property(
        tmp_path,
        "b-duplicate",
        {"entity": "property", "electric_account": "ACCT-12345"},
    )
    path = entities.find_property_by_electric_account("ACCT-12345", tmp_path)
    assert path.parent.name == "a-duplicate"


def test_handles_property_with_malformed_frontmatter(tmp_path):
    """Bad YAML in one property doesn't break matching against the others."""
    bad = tmp_path / "source" / "properties" / "broken"
    bad.mkdir(parents=True)
    (bad / "index.md").write_text("---\nthis: is: not: valid yaml\n---\n", encoding="utf-8")
    _property(
        tmp_path,
        "good",
        {"entity": "property", "electric_account": "ACCT-12345"},
    )
    path = entities.find_property_by_electric_account("ACCT-12345", tmp_path)
    assert path.parent.name == "good"


# -----------------------------------------------------------------------------
# find_property_by_mortgage_loan_number
# -----------------------------------------------------------------------------


@pytest.fixture
def two_mortgaged_properties(tmp_path):
    _property(
        tmp_path,
        "123-main-davenport",
        {"entity": "property", "mortgage_loan_number": "LN-9912345"},
    )
    _property(
        tmp_path,
        "456-oak-st",
        {"entity": "property", "mortgage_loan_number": "LN-7766554"},
    )
    return tmp_path


def test_finds_property_by_loan_number(two_mortgaged_properties):
    path = entities.find_property_by_mortgage_loan_number(
        "LN-9912345", two_mortgaged_properties
    )
    assert path is not None
    assert path.parent.name == "123-main-davenport"


def test_returns_none_for_unknown_loan_number(two_mortgaged_properties):
    assert (
        entities.find_property_by_mortgage_loan_number(
            "LN-XX", two_mortgaged_properties
        )
        is None
    )


def test_skips_property_without_loan_number(tmp_path):
    """A property entity that hasn't declared a mortgage is invisible to this matcher."""
    _property(tmp_path, "rented-out", {"entity": "property"})
    _property(
        tmp_path,
        "owned",
        {"entity": "property", "mortgage_loan_number": "LN-9912345"},
    )
    path = entities.find_property_by_mortgage_loan_number("LN-9912345", tmp_path)
    assert path is not None
    assert path.parent.name == "owned"


# -----------------------------------------------------------------------------
# find_account_by_account_number
# -----------------------------------------------------------------------------


def _account(vault: Path, slug: str, frontmatter: dict) -> Path:
    folder = vault / "source" / "accounts" / slug
    folder.mkdir(parents=True, exist_ok=True)
    fm_lines = "\n".join(f"{k}: {v}" for k, v in frontmatter.items())
    (folder / "index.md").write_text(
        f"---\n{fm_lines}\n---\n\n# {slug}\n",
        encoding="utf-8",
    )
    return folder / "index.md"


def test_finds_account_by_number(tmp_path):
    _account(
        tmp_path,
        "first-davenport-checking-4521",
        {"entity": "account", "account_number": "ACCT-4521"},
    )
    _account(
        tmp_path,
        "beacon-savings-7788",
        {"entity": "account", "account_number": "ACCT-7788"},
    )
    path = entities.find_account_by_account_number("ACCT-4521", tmp_path)
    assert path is not None
    assert path.parent.name == "first-davenport-checking-4521"


def test_returns_none_for_unknown_account_number(tmp_path):
    _account(
        tmp_path,
        "first-davenport-checking-4521",
        {"entity": "account", "account_number": "ACCT-4521"},
    )
    assert entities.find_account_by_account_number("ACCT-XX", tmp_path) is None


def test_account_lookup_returns_none_when_no_accounts_dir(tmp_path):
    assert entities.find_account_by_account_number("ACCT-4521", tmp_path) is None


# -----------------------------------------------------------------------------
# find_person_by_employer_and_name
# -----------------------------------------------------------------------------


def _person(vault: Path, slug: str, frontmatter: dict) -> Path:
    folder = vault / "source" / "people" / slug
    folder.mkdir(parents=True, exist_ok=True)
    fm_lines = "\n".join(f"{k}: {v}" for k, v in frontmatter.items())
    (folder / "index.md").write_text(
        f"---\n{fm_lines}\n---\n\n# {slug}\n",
        encoding="utf-8",
    )
    return folder / "index.md"


def test_finds_person_by_employer_and_name(tmp_path):
    _person(
        tmp_path,
        "joe",
        {
            "entity": "person",
            "legal_name": "Joe Sample",
            "employer_current": "Beacon Software",
        },
    )
    path = entities.find_person_by_employer_and_name(
        "Joe Sample", "Beacon Software", tmp_path
    )
    assert path is not None
    assert path.parent.name == "joe"


def test_person_lookup_requires_both_name_and_employer(tmp_path):
    """Name-only or employer-only matches don't count — both must agree."""
    _person(
        tmp_path,
        "joe-beacon",
        {
            "entity": "person",
            "legal_name": "Joe Sample",
            "employer_current": "Beacon Software",
        },
    )
    _person(
        tmp_path,
        "joe-other",
        {
            "entity": "person",
            "legal_name": "Joe Sample",
            "employer_current": "Other Inc",
        },
    )
    path = entities.find_person_by_employer_and_name(
        "Joe Sample", "Beacon Software", tmp_path
    )
    assert path is not None
    assert path.parent.name == "joe-beacon"


def test_person_lookup_returns_none_when_no_people_dir(tmp_path):
    assert (
        entities.find_person_by_employer_and_name(
            "Joe Sample", "Beacon Software", tmp_path
        )
        is None
    )


# -----------------------------------------------------------------------------
# find_by_slug
# -----------------------------------------------------------------------------


def test_find_by_slug_resolves_property(tmp_path):
    _property(tmp_path, "123-main-davenport", {"entity": "property"})
    path = entities.find_by_slug("123-main-davenport", tmp_path)
    assert path is not None
    assert path.parent.name == "123-main-davenport"
    assert path.parent.parent.name == "properties"


def test_find_by_slug_resolves_account(tmp_path):
    _account(tmp_path, "first-davenport-checking-4521", {"entity": "account"})
    path = entities.find_by_slug("first-davenport-checking-4521", tmp_path)
    assert path is not None
    assert path.parent.parent.name == "accounts"


def test_find_by_slug_resolves_person(tmp_path):
    _person(tmp_path, "joe", {"entity": "person"})
    path = entities.find_by_slug("joe", tmp_path)
    assert path is not None
    assert path.parent.parent.name == "people"


def test_find_by_slug_returns_none_for_unknown(tmp_path):
    _property(tmp_path, "real", {"entity": "property"})
    assert entities.find_by_slug("nonexistent-slug", tmp_path) is None


def test_find_by_slug_returns_none_when_no_source_dir(tmp_path):
    assert entities.find_by_slug("123-main-davenport", tmp_path) is None
