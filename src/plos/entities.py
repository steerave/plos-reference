"""
Entity matching — map an extracted field value back to the entity record
(an `index.md` file) it belongs to.

Phase 2's only matcher routes electric bills to a property by its
`electric_account` frontmatter field. Phase 3+ will add matchers for
other utility account numbers, mortgage loan numbers, vehicle VINs,
etc. Each matcher walks the relevant `source/<type>/` subtree, parses
each `index.md`'s YAML frontmatter, and returns the first matching
file's path.

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


def find_property_by_electric_account(account: str, vault_root: Path) -> Path | None:
    """Return the path of the property index.md whose electric_account matches.

    Walks vault_root/source/properties/*/index.md. Returns the first match
    in lexicographic order, or None if no property has a matching account
    (or the properties directory doesn't exist).
    """
    properties_dir = vault_root / "source" / "properties"
    if not properties_dir.is_dir():
        return None
    for index_path in sorted(properties_dir.glob("*/index.md")):
        fm = _read_frontmatter(index_path)
        if fm.get("electric_account") == account:
            return index_path
    return None
