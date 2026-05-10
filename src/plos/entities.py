"""
Entity matching — map an extracted field value back to the entity record
(an `index.md` file) it belongs to.

Each matcher walks the relevant `source/<type>/` subtree, parses each
`index.md`'s YAML frontmatter, and returns the first matching file's
path. Phase 2 added the electric-account matcher; Phase 3 adds matchers
for mortgage loan numbers, bank account numbers, and pay-stub
employee/employer combinations.

The matchers are deliberately stateless — no in-memory cache, no SQLite
mirror. The vault is the source of truth (ARCHITECTURE design principle
1) and parsing a few dozen tiny YAML headers per worker poll is free.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _read_frontmatter(path: Path) -> dict[str, Any]:
    """Return the YAML frontmatter of a markdown file as a dict, {} on parse failure."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    closing = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing = i
            break
    if closing is None:
        return {}
    try:
        loaded = yaml.safe_load("\n".join(lines[1:closing])) or {}
    except yaml.YAMLError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _find_in(
    vault_root: Path, subdir: str, predicate
) -> Path | None:
    """Return the first index.md under `vault_root/source/<subdir>/` matching predicate."""
    folder = vault_root / "source" / subdir
    if not folder.is_dir():
        return None
    for index_path in sorted(folder.glob("*/index.md")):
        fm = _read_frontmatter(index_path)
        if predicate(fm):
            return index_path
    return None


def find_property_by_electric_account(account: str, vault_root: Path) -> Path | None:
    """Return the property whose electric_account frontmatter equals `account`."""
    return _find_in(
        vault_root, "properties", lambda fm: fm.get("electric_account") == account
    )


def find_property_by_mortgage_loan_number(
    loan_number: str, vault_root: Path
) -> Path | None:
    """Return the property whose mortgage_loan_number frontmatter equals `loan_number`."""
    return _find_in(
        vault_root,
        "properties",
        lambda fm: fm.get("mortgage_loan_number") == loan_number,
    )


def find_account_by_account_number(
    account_number: str, vault_root: Path
) -> Path | None:
    """Return the account whose account_number frontmatter equals `account_number`."""
    return _find_in(
        vault_root,
        "accounts",
        lambda fm: fm.get("account_number") == account_number,
    )


def find_person_by_employer_and_name(
    legal_name: str, employer: str, vault_root: Path
) -> Path | None:
    """Return the person whose legal_name and employer_current both match.

    Both fields must match for a routing decision — `legal_name` alone
    isn't enough (a household could have multiple people with the same
    surname), and `employer_current` alone isn't enough (multiple people
    could share an employer).
    """
    return _find_in(
        vault_root,
        "people",
        lambda fm: (
            fm.get("legal_name") == legal_name
            and fm.get("employer_current") == employer
        ),
    )
