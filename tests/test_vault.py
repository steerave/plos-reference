"""
Tests for the vault writer's atomic frontmatter merge.

The merge contract has three rules and one bookkeeping side effect:
  - Skip locked_fields
  - Skip everything when existing data_effective_date >= source_doc_date
  - Otherwise update, then bump data_effective_date
Each rule has a dedicated test; atomicity has its own test.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from plos import vault

PROPERTY_TEMPLATE = """---
type: source
entity: property
slug: 123-main-davenport
status: active
electric_account: ACCT-12345
locked_fields: []
---

# 123 Main St, Davenport, IA

Body content the merge must preserve.
"""


def _read_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    fm, _ = vault._split(text)
    return fm


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "index.md"
    p.write_text(content, encoding="utf-8")
    return p


def test_appends_new_keys(tmp_path):
    p = _write(tmp_path, PROPERTY_TEMPLATE)

    changed = vault.merge_frontmatter(
        p,
        {"last_utility_bill_amount": 142.37, "last_utility_bill_kwh": 850},
        date(2026, 4, 30),
    )

    assert changed == {"last_utility_bill_amount": 142.37, "last_utility_bill_kwh": 850}
    fm = _read_frontmatter(p)
    assert fm["last_utility_bill_amount"] == 142.37
    assert fm["last_utility_bill_kwh"] == 850
    assert fm["data_effective_date"] == "2026-04-30"


def test_overwrites_stale_value(tmp_path):
    p = _write(
        tmp_path,
        PROPERTY_TEMPLATE.replace(
            "locked_fields: []",
            "locked_fields: []\nlast_utility_bill_amount: 100.00\ndata_effective_date: 2026-03-15",
        ),
    )

    changed = vault.merge_frontmatter(
        p,
        {"last_utility_bill_amount": 142.37},
        date(2026, 4, 30),
    )

    assert changed == {"last_utility_bill_amount": 142.37}
    assert _read_frontmatter(p)["last_utility_bill_amount"] == 142.37


def test_locked_field_preserved(tmp_path):
    p = _write(
        tmp_path,
        PROPERTY_TEMPLATE.replace(
            "locked_fields: []",
            "locked_fields:\n  - last_utility_bill_amount\nlast_utility_bill_amount: 999.99",
        ),
    )

    changed = vault.merge_frontmatter(
        p,
        {"last_utility_bill_amount": 142.37, "last_utility_bill_kwh": 850},
        date(2026, 4, 30),
    )

    assert "last_utility_bill_amount" not in changed
    assert changed == {"last_utility_bill_kwh": 850}
    fm = _read_frontmatter(p)
    assert fm["last_utility_bill_amount"] == 999.99
    assert fm["last_utility_bill_kwh"] == 850


def test_freshness_skip_when_existing_is_newer(tmp_path):
    p = _write(
        tmp_path,
        PROPERTY_TEMPLATE.replace(
            "locked_fields: []",
            "locked_fields: []\ndata_effective_date: 2026-05-15",
        ),
    )

    changed = vault.merge_frontmatter(
        p,
        {"last_utility_bill_amount": 142.37},
        date(2026, 4, 30),
    )

    assert changed == {}
    fm = _read_frontmatter(p)
    assert "last_utility_bill_amount" not in fm
    assert fm["data_effective_date"] == date(2026, 5, 15)


def test_freshness_skip_when_existing_is_equal(tmp_path):
    """Equal dates should not overwrite — same-day re-extraction is idempotent."""
    p = _write(
        tmp_path,
        PROPERTY_TEMPLATE.replace(
            "locked_fields: []",
            "locked_fields: []\nlast_utility_bill_amount: 100.00\ndata_effective_date: 2026-04-30",
        ),
    )

    changed = vault.merge_frontmatter(
        p,
        {"last_utility_bill_amount": 142.37},
        date(2026, 4, 30),
    )

    assert changed == {}
    assert _read_frontmatter(p)["last_utility_bill_amount"] == 100.00


def test_no_op_when_value_unchanged(tmp_path):
    p = _write(
        tmp_path,
        PROPERTY_TEMPLATE.replace(
            "electric_account: ACCT-12345",
            "electric_account: ACCT-12345\nlast_utility_bill_amount: 142.37\ndata_effective_date: 2026-03-01",
        ),
    )

    changed = vault.merge_frontmatter(
        p,
        {"last_utility_bill_amount": 142.37},
        date(2026, 4, 30),
    )

    assert changed == {}
    fm = _read_frontmatter(p)
    assert fm["data_effective_date"] == date(2026, 3, 1)


def test_body_preserved(tmp_path):
    p = _write(tmp_path, PROPERTY_TEMPLATE)

    vault.merge_frontmatter(
        p, {"last_utility_bill_amount": 142.37}, date(2026, 4, 30)
    )

    body = p.read_text(encoding="utf-8").split("---\n", 2)[2]
    assert "Body content the merge must preserve." in body
    assert "# 123 Main St, Davenport, IA" in body


def test_atomic_write_leaves_no_temp(tmp_path):
    p = _write(tmp_path, PROPERTY_TEMPLATE)

    vault.merge_frontmatter(p, {"last_utility_bill_amount": 142.37}, date(2026, 4, 30))

    tmp = p.with_suffix(p.suffix + ".tmp")
    assert not tmp.exists(), "temp file should be renamed/removed after successful write"
    assert p.exists()


def test_no_write_when_nothing_changed(tmp_path):
    """If every update is locked or stale, the file must not be touched at all."""
    p = _write(
        tmp_path,
        PROPERTY_TEMPLATE.replace(
            "locked_fields: []",
            "locked_fields:\n  - last_utility_bill_amount",
        ),
    )
    original_mtime = p.stat().st_mtime_ns

    changed = vault.merge_frontmatter(
        p, {"last_utility_bill_amount": 142.37}, date(2026, 4, 30)
    )

    assert changed == {}
    assert p.stat().st_mtime_ns == original_mtime


def test_handles_file_with_no_frontmatter(tmp_path):
    p = _write(tmp_path, "# Bare markdown, no frontmatter\n\nBody.\n")

    changed = vault.merge_frontmatter(
        p, {"last_utility_bill_amount": 142.37}, date(2026, 4, 30)
    )

    assert changed == {"last_utility_bill_amount": 142.37}
    text = p.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    fm = yaml.safe_load(text.split("---\n")[1])
    assert fm["last_utility_bill_amount"] == 142.37
