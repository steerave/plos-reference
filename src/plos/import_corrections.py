"""
Import the vault's `corrections.md` file into the SQLite corrections
table and apply each entry to the corresponding entity's frontmatter.

The Phase 4c override path. Per the merge contract in
`examples/sample-vault/CONVENTIONS.md`:

> Corrections always win. A `corrections` row for the entity+field
> beats every other source.

Mechanically, this script:

1. Reads `<vault_root>/corrections.md` — a YAML-frontmatter file with
   a `corrections:` list of `{slug, field, value, source, reason}`
   entries.
2. For each entry: locates the entity index.md by slug, calls
   `vault.apply_correction(path, field, value)` (which sets the
   value AND adds the field to `locked_fields:`), and inserts/updates
   a row in the SQLite `corrections` table for audit.

The script is idempotent: running it twice produces the same state.
Removing entries from corrections.md does NOT undo the correction —
this v1 is append-only by design. Phase 5+ may add a sync mode.

Run from the repo root:
    python -m plos.import_corrections
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from . import db, entities, vault

logger = logging.getLogger("plos.import_corrections")

CORRECTIONS_PATH = "corrections.md"


@dataclass(frozen=True)
class Correction:
    """One row of corrections.md, parsed."""

    slug: str
    field: str
    value: Any
    source: str | None = None
    reason: str | None = None


def parse_corrections_file(path: Path) -> list[Correction]:
    """Parse a corrections.md file. Returns [] if the file is missing or empty."""
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    fm, _body = vault._split(text)
    raw_list = fm.get("corrections") or []
    if not isinstance(raw_list, list):
        raise ValueError(
            f"{path}: 'corrections' frontmatter must be a list, got {type(raw_list).__name__}"
        )
    out: list[Correction] = []
    for i, entry in enumerate(raw_list):
        if not isinstance(entry, dict):
            raise ValueError(
                f"{path}: corrections[{i}] must be a mapping, got "
                f"{type(entry).__name__}"
            )
        for required in ("slug", "field", "value"):
            if required not in entry:
                raise ValueError(
                    f"{path}: corrections[{i}] missing required key {required!r}"
                )
        out.append(
            Correction(
                slug=entry["slug"],
                field=entry["field"],
                value=entry["value"],
                source=entry.get("source"),
                reason=entry.get("reason"),
            )
        )
    return out


def _ensure_entity_id(conn: sqlite3.Connection, slug: str) -> int | None:
    """Return entities.id for `slug` if it exists in SQLite, else None.

    The SQLite entities row only exists if the worker has already
    routed at least one document to it. If the user is correcting a
    brand-new entity, the corrections row's entity_id stays NULL (we
    omit the row rather than fail; the audit gap is acceptable for v1
    and matches how the schema currently allows it).
    """
    row = conn.execute(
        "SELECT id FROM entities WHERE slug = ?", (slug,)
    ).fetchone()
    return row["id"] if row else None


def _record_correction(
    conn: sqlite3.Connection, entity_id: int, correction: Correction
) -> None:
    """Insert or update the corrections-table row for this entity+field.

    Uses ON CONFLICT semantics manually: delete any prior correction
    for the same entity+field, then insert the new value. Keeps the
    table normalised at one row per entity+field pair.
    """
    conn.execute(
        "DELETE FROM corrections WHERE entity_id = ? AND field_name = ?",
        (entity_id, correction.field),
    )
    conn.execute(
        "INSERT INTO corrections (entity_id, field_name, correct_value, "
        "source_document_id) VALUES (?, ?, ?, NULL)",
        (entity_id, correction.field, _coerce_text(correction.value)),
    )


def _coerce_text(value: Any) -> str | None:
    """SQLite TEXT-column coercion. Lists/dicts get JSON-encoded."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    import json

    return json.dumps(value, sort_keys=True)


def apply_one(
    conn: sqlite3.Connection,
    correction: Correction,
    vault_root: Path,
) -> str:
    """Apply a single correction. Returns one of:
      - 'applied' — entity found, frontmatter updated (or already correct)
      - 'no_entity' — entity slug not found in the vault
    """
    entity_path = entities.find_by_slug(correction.slug, vault_root)
    if entity_path is None:
        logger.warning(
            "correction skipped: entity slug %r not found in vault", correction.slug
        )
        return "no_entity"

    vault.apply_correction(entity_path, correction.field, correction.value)
    entity_id = _ensure_entity_id(conn, correction.slug)
    if entity_id is not None:
        _record_correction(conn, entity_id, correction)
    else:
        logger.info(
            "entity %r not in SQLite entities table yet (no documents routed); "
            "frontmatter updated but corrections audit row skipped",
            correction.slug,
        )
    logger.info(
        "applied correction: %s.%s = %r",
        correction.slug,
        correction.field,
        correction.value,
    )
    return "applied"


def run(vault_root: Path) -> dict[str, int]:
    """Apply every correction in `<vault_root>/corrections.md`.

    Returns counts by outcome: {'applied': N, 'no_entity': M, 'errored': K}.
    Per-entry errors do not abort the run; the failing entry is logged
    and counted, the rest proceed.
    """
    counts: dict[str, int] = {"applied": 0, "no_entity": 0, "errored": 0}
    corrections_file = vault_root / CORRECTIONS_PATH
    corrections = parse_corrections_file(corrections_file)
    if not corrections:
        logger.info("no corrections to apply (file missing or empty)")
        return counts

    conn = db.connect()
    try:
        for correction in corrections:
            try:
                outcome = apply_one(conn, correction, vault_root)
                conn.commit()
                counts[outcome] = counts.get(outcome, 0) + 1
            except Exception:
                logger.exception(
                    "correction failed: %s.%s",
                    correction.slug,
                    correction.field,
                )
                conn.rollback()
                counts["errored"] += 1
    finally:
        conn.close()
    return counts


def _resolve_vault_root() -> Path:
    raw = os.environ.get("PLOS_VAULT_ROOT")
    if not raw:
        raise RuntimeError("PLOS_VAULT_ROOT not set in environment")
    p = Path(raw)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()


def main() -> None:
    load_dotenv(override=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    vault_root = _resolve_vault_root()
    counts = run(vault_root)
    logger.info("import_corrections complete: %s", counts)


if __name__ == "__main__":
    main()
