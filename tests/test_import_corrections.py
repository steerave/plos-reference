"""
Tests for the corrections.md import workflow.

Covers parsing (well-formed entries, missing required fields, malformed
list), per-entry application (entity found/missing, idempotency, audit
trail), and the multi-entry run loop (counts by outcome, error
isolation).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from plos import db, import_corrections, vault


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def conn(tmp_path, monkeypatch):
    db_path = tmp_path / "plos.db"
    monkeypatch.setenv("PLOS_DB_PATH", str(db_path))
    c = db.connect(db_path)
    db.init_schema(c)
    yield c
    c.close()


@pytest.fixture
def vault_root(tmp_path: Path) -> Path:
    """Build a tmp vault with one property, one account, one person."""
    root = tmp_path / "vault"
    (root / "source" / "properties" / "123-main-davenport").mkdir(parents=True)
    (root / "source" / "properties" / "123-main-davenport" / "index.md").write_text(
        "---\n"
        "type: source\n"
        "entity: property\n"
        "slug: 123-main-davenport\n"
        "electric_account: ACCT-12345\n"
        "locked_fields: []\n"
        "last_utility_bill_amount: 142.37\n"
        "data_effective_date: '2026-04-30'\n"
        "---\n\n# 123 Main\n",
        encoding="utf-8",
    )
    (root / "source" / "people" / "joe").mkdir(parents=True)
    (root / "source" / "people" / "joe" / "index.md").write_text(
        "---\n"
        "type: source\n"
        "entity: person\n"
        "slug: joe\n"
        "legal_name: Joe Sample\n"
        "locked_fields: []\n"
        "---\n\n# Joe\n",
        encoding="utf-8",
    )
    return root


def _write_corrections(vault_root: Path, content: str) -> Path:
    p = vault_root / "corrections.md"
    p.write_text(content, encoding="utf-8")
    return p


# -----------------------------------------------------------------------------
# parse_corrections_file
# -----------------------------------------------------------------------------


def test_parse_returns_empty_when_file_missing(tmp_path):
    assert import_corrections.parse_corrections_file(tmp_path / "missing.md") == []


def test_parse_returns_empty_when_corrections_list_absent(vault_root):
    p = _write_corrections(vault_root, "---\ntype: corrections\n---\n\n# Empty.\n")
    assert import_corrections.parse_corrections_file(p) == []


def test_parse_reads_well_formed_entries(vault_root):
    p = _write_corrections(
        vault_root,
        "---\n"
        "type: corrections\n"
        "corrections:\n"
        "  - slug: 123-main-davenport\n"
        "    field: last_utility_bill_amount\n"
        "    value: 142.99\n"
        "    source: 'http://localhost:8888/documents/4/'\n"
        "    reason: 'OCR misread the cents.'\n"
        "  - slug: joe\n"
        "    field: birthdate\n"
        "    value: '1985-03-12'\n"
        "    source: 'hand-entered'\n"
        "---\n",
    )
    out = import_corrections.parse_corrections_file(p)
    assert len(out) == 2
    assert out[0].slug == "123-main-davenport"
    assert out[0].field == "last_utility_bill_amount"
    assert out[0].value == 142.99
    assert out[0].source == "http://localhost:8888/documents/4/"
    assert out[0].reason == "OCR misread the cents."
    assert out[1].slug == "joe"
    assert out[1].field == "birthdate"
    assert out[1].reason is None  # optional, not provided


def test_parse_rejects_corrections_not_a_list(vault_root):
    p = _write_corrections(
        vault_root,
        "---\ntype: corrections\ncorrections: 'oops, a string'\n---\n",
    )
    with pytest.raises(ValueError, match="must be a list"):
        import_corrections.parse_corrections_file(p)


def test_parse_rejects_entry_missing_slug(vault_root):
    p = _write_corrections(
        vault_root,
        "---\n"
        "type: corrections\n"
        "corrections:\n"
        "  - field: birthdate\n"
        "    value: '1985-03-12'\n"
        "---\n",
    )
    with pytest.raises(ValueError, match="missing required key 'slug'"):
        import_corrections.parse_corrections_file(p)


def test_parse_rejects_entry_missing_field(vault_root):
    p = _write_corrections(
        vault_root,
        "---\n"
        "type: corrections\n"
        "corrections:\n"
        "  - slug: joe\n"
        "    value: '1985-03-12'\n"
        "---\n",
    )
    with pytest.raises(ValueError, match="missing required key 'field'"):
        import_corrections.parse_corrections_file(p)


# -----------------------------------------------------------------------------
# apply_one
# -----------------------------------------------------------------------------


def test_apply_one_writes_value_and_locks_field(conn, vault_root):
    correction = import_corrections.Correction(
        slug="123-main-davenport",
        field="last_utility_bill_amount",
        value=142.99,
    )
    outcome = import_corrections.apply_one(conn, correction, vault_root)

    assert outcome == "applied"
    text = (vault_root / "source" / "properties" / "123-main-davenport" / "index.md").read_text(
        encoding="utf-8"
    )
    assert "last_utility_bill_amount: 142.99" in text
    assert "last_utility_bill_amount" in text  # in locked_fields too


def test_apply_one_skips_when_entity_not_in_vault(conn, vault_root):
    correction = import_corrections.Correction(
        slug="ghost-entity-not-here",
        field="birthdate",
        value="2000-01-01",
    )
    outcome = import_corrections.apply_one(conn, correction, vault_root)
    assert outcome == "no_entity"


def test_apply_one_records_corrections_row_when_entity_in_sqlite(conn, vault_root):
    """If the entity already has an entities-table row (worker routed a doc
    to it earlier), the correction's audit trail lands in SQLite."""
    conn.execute(
        "INSERT INTO entities (type, domain, slug, wiki_path) "
        "VALUES ('property', 'properties', '123-main-davenport', "
        "'source/properties/123-main-davenport/index.md')"
    )
    conn.commit()
    correction = import_corrections.Correction(
        slug="123-main-davenport",
        field="last_utility_bill_amount",
        value=142.99,
        source="hand-entered",
        reason="OCR misread.",
    )
    import_corrections.apply_one(conn, correction, vault_root)

    rows = conn.execute(
        "SELECT entity_id, field_name, correct_value FROM corrections"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["field_name"] == "last_utility_bill_amount"
    assert rows[0]["correct_value"] == "142.99"


def test_apply_one_skips_audit_row_when_entity_not_in_sqlite(conn, vault_root):
    """If the entity exists in the vault but no document has routed to it
    yet, entities-table is empty and corrections audit is skipped (frontmatter
    still gets written so the lock takes effect)."""
    correction = import_corrections.Correction(
        slug="joe",
        field="birthdate",
        value="1985-03-12",
    )
    outcome = import_corrections.apply_one(conn, correction, vault_root)

    assert outcome == "applied"
    text = (vault_root / "source" / "people" / "joe" / "index.md").read_text(encoding="utf-8")
    assert "birthdate: '1985-03-12'" in text
    rows = conn.execute("SELECT COUNT(*) AS n FROM corrections").fetchone()
    assert rows["n"] == 0


def test_apply_one_idempotent_audit(conn, vault_root):
    """Re-applying the same correction does not double the audit row."""
    conn.execute(
        "INSERT INTO entities (type, domain, slug, wiki_path) "
        "VALUES ('property', 'properties', '123-main-davenport', 'x')"
    )
    conn.commit()
    correction = import_corrections.Correction(
        slug="123-main-davenport",
        field="last_utility_bill_amount",
        value=142.99,
    )
    import_corrections.apply_one(conn, correction, vault_root)
    import_corrections.apply_one(conn, correction, vault_root)

    rows = conn.execute("SELECT COUNT(*) AS n FROM corrections").fetchone()
    assert rows["n"] == 1


def test_apply_one_replaces_prior_audit_when_value_changes(conn, vault_root):
    """If the user revises the corrected value, the audit row reflects the latest."""
    conn.execute(
        "INSERT INTO entities (type, domain, slug, wiki_path) "
        "VALUES ('property', 'properties', '123-main-davenport', 'x')"
    )
    conn.commit()
    import_corrections.apply_one(
        conn,
        import_corrections.Correction(
            slug="123-main-davenport",
            field="last_utility_bill_amount",
            value=142.99,
        ),
        vault_root,
    )
    import_corrections.apply_one(
        conn,
        import_corrections.Correction(
            slug="123-main-davenport",
            field="last_utility_bill_amount",
            value=143.00,
        ),
        vault_root,
    )

    rows = conn.execute(
        "SELECT correct_value FROM corrections WHERE field_name='last_utility_bill_amount'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["correct_value"] == "143.0"


# -----------------------------------------------------------------------------
# run() — multi-entry loop
# -----------------------------------------------------------------------------


def test_run_with_no_file_returns_zero_counts(conn, vault_root):
    counts = import_corrections.run(vault_root)
    assert counts == {"applied": 0, "no_entity": 0, "errored": 0}


def test_run_applies_all_entries_and_returns_counts(conn, vault_root):
    _write_corrections(
        vault_root,
        "---\n"
        "type: corrections\n"
        "corrections:\n"
        "  - slug: 123-main-davenport\n"
        "    field: last_utility_bill_amount\n"
        "    value: 142.99\n"
        "  - slug: joe\n"
        "    field: birthdate\n"
        "    value: '1985-03-12'\n"
        "  - slug: ghost-not-here\n"
        "    field: x\n"
        "    value: y\n"
        "---\n",
    )
    counts = import_corrections.run(vault_root)
    assert counts == {"applied": 2, "no_entity": 1, "errored": 0}


# -----------------------------------------------------------------------------
# main / env
# -----------------------------------------------------------------------------


def test_resolve_vault_root_requires_env_var(monkeypatch):
    monkeypatch.delenv("PLOS_VAULT_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="PLOS_VAULT_ROOT"):
        import_corrections._resolve_vault_root()
