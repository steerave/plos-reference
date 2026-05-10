"""
Vault writer — atomic YAML-frontmatter merge for entity records.

Reads an entity's index.md, applies a dict of updates respecting the
merge contract from CONVENTIONS.md and ARCHITECTURE.md, then writes the
result atomically: a sibling temp file is fsynced and renamed over the
target. A partial write to a property's index.md would corrupt the YAML
and break Obsidian + every Dataview dashboard that queries it, so the
atomic-write discipline is non-negotiable here.

Merge rules (in order, applied per field):
  1. Skip if the field name appears in the target's `locked_fields:` list.
  2. Skip every field if existing `data_effective_date` >= source_doc_date.
  3. Otherwise update, and bump `data_effective_date` to source_doc_date.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

import yaml

_DELIM = "---"


def _split(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, body) for markdown with optional YAML frontmatter."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != _DELIM:
        return {}, text
    closing = None
    for i, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == _DELIM:
            closing = i
            break
    if closing is None:
        return {}, text
    fm_text = "".join(lines[1:closing])
    body = "".join(lines[closing + 1 :])
    fm = yaml.safe_load(fm_text) or {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, body


def _serialize(frontmatter: dict[str, Any], body: str) -> str:
    fm_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
    return f"{_DELIM}\n{fm_text}{_DELIM}\n{body}"


def _coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def merge_frontmatter(
    path: Path,
    updates: dict[str, Any],
    source_doc_date: date,
) -> dict[str, Any]:
    """
    Apply updates to the YAML frontmatter of path per the merge contract.

    Returns the dict of fields that actually changed (does not include the
    automatic data_effective_date bookkeeping). Empty dict means no write
    happened and the file is unchanged.
    """
    text = path.read_text(encoding="utf-8")
    frontmatter, body = _split(text)

    locked = frontmatter.get("locked_fields") or []
    existing_effective = _coerce_date(frontmatter.get("data_effective_date"))
    stale = existing_effective is not None and existing_effective >= source_doc_date

    changed: dict[str, Any] = {}
    for key, value in updates.items():
        if key in locked:
            continue
        if stale:
            continue
        if frontmatter.get(key) == value:
            continue
        frontmatter[key] = value
        changed[key] = value

    if not changed:
        return changed

    frontmatter["data_effective_date"] = source_doc_date.isoformat()
    new_text = _serialize(frontmatter, body)

    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return changed
