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
