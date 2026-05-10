"""
Tests for the audit pass.

The audit pass is pure deterministic Python (no Claude). Tests exercise:
- Frontmatter / body parsing.
- Each of the three finding categories.
- A clean (no-drift) audit.
- Report rendering (frontmatter counts + per-artifact sections).
- Atomic write + missing-artifact-skipped behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from plos import audit_pass
from plos.audit_pass import FindingCategory


# -----------------------------------------------------------------------------
# Helpers + fixtures
# -----------------------------------------------------------------------------


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Vault scaffold with one real source file the artifacts can cite."""
    root = tmp_path / "vault"
    _write(
        root / "source" / "properties" / "123-main" / "index.md",
        "---\nentity: property\nslug: 123-main\n---\n# 123 Main\n",
    )
    _write(
        root / "source" / "people" / "joe" / "index.md",
        "---\nentity: person\nslug: joe\n---\n# Joe\n",
    )
    return root


CLEAN_ARTIFACT = """\
---
type: compiled
artifact: this-week
refreshed: 2026-05-10T12:00:00Z
sources_read:
  - /source/people/joe/index.md
  - /source/properties/123-main/index.md
compile_pass_version: 1
---

# This Week

## Must do

- **Joe's license.** Renew before Friday.
  → /source/people/joe/index.md

## Should do

- **State Farm renewal.** Coming up.
  → /source/properties/123-main/index.md
"""


# -----------------------------------------------------------------------------
# Parsing helpers
# -----------------------------------------------------------------------------


def test_split_frontmatter_separates_correctly():
    text = "---\nfoo: bar\n---\n\n# Body\n\nContent\n"
    fm, body = audit_pass._split_frontmatter(text)
    assert "foo: bar" in fm
    assert body.startswith("\n# Body")


def test_split_frontmatter_handles_no_frontmatter():
    text = "# Just a Body\n\nContent\n"
    fm, body = audit_pass._split_frontmatter(text)
    assert fm == ""
    assert body == text


def test_split_frontmatter_handles_unclosed_frontmatter():
    """A `---` opener without a closer is malformed; treat as no frontmatter."""
    text = "---\nfoo: bar\n# Body never gets a closing fence\n"
    fm, body = audit_pass._split_frontmatter(text)
    assert fm == ""
    assert body == text


def test_parse_frontmatter_sources_returns_list():
    fm = "sources_read:\n  - /a/b.md\n  - /c/d.md\n"
    assert audit_pass._parse_frontmatter_sources(fm) == ["/a/b.md", "/c/d.md"]


def test_parse_frontmatter_sources_empty_when_key_missing():
    fm = "other_key: 1\n"
    assert audit_pass._parse_frontmatter_sources(fm) == []


def test_parse_frontmatter_sources_empty_on_malformed_yaml():
    assert audit_pass._parse_frontmatter_sources("not: : : yaml") == []


def test_extract_arrow_citations_finds_all():
    body = (
        "## Foo\n"
        "- bullet.\n"
        "  → /source/people/joe/index.md\n"
        "- another.\n"
        "  → /source/properties/123-main/index.md\n"
    )
    cites = audit_pass._extract_arrow_citations(body)
    assert "/source/people/joe/index.md" in cites
    assert "/source/properties/123-main/index.md" in cites
    assert len(cites) == 2


def test_extract_arrow_citations_returns_empty_when_no_arrows():
    assert audit_pass._extract_arrow_citations("# Body with no arrows\n") == []


# -----------------------------------------------------------------------------
# audit_artifact — finding categories
# -----------------------------------------------------------------------------


def test_audit_artifact_clean_artifact_has_no_findings(vault):
    _write(vault / "compiled" / "this-week.md", CLEAN_ARTIFACT)
    result = audit_pass.audit_artifact(vault, Path("compiled/this-week.md"))
    assert result.findings == []
    assert set(result.declared_sources) == {
        "/source/people/joe/index.md",
        "/source/properties/123-main/index.md",
    }
    assert set(result.cited_paths) == {
        "/source/people/joe/index.md",
        "/source/properties/123-main/index.md",
    }


def test_audit_artifact_flags_undeclared_citation(vault):
    """Body cites /source/people/joe/index.md but it's not in sources_read."""
    artifact = (
        "---\n"
        "type: compiled\n"
        "sources_read:\n"
        "  - /source/properties/123-main/index.md\n"
        "---\n\n"
        "## Must do\n"
        "- Joe stuff.\n"
        "  → /source/people/joe/index.md\n"
    )
    _write(vault / "compiled" / "this-week.md", artifact)
    result = audit_pass.audit_artifact(vault, Path("compiled/this-week.md"))
    undeclared = [
        f for f in result.findings
        if f.category == FindingCategory.UNDECLARED_CITATION
    ]
    assert len(undeclared) == 1
    assert undeclared[0].path == "/source/people/joe/index.md"


def test_audit_artifact_flags_unused_declaration(vault):
    """sources_read declares /source/people/joe/index.md but body doesn't cite it."""
    artifact = (
        "---\n"
        "type: compiled\n"
        "sources_read:\n"
        "  - /source/people/joe/index.md\n"
        "  - /source/properties/123-main/index.md\n"
        "---\n\n"
        "## Must do\n"
        "- Property stuff.\n"
        "  → /source/properties/123-main/index.md\n"
    )
    _write(vault / "compiled" / "this-week.md", artifact)
    result = audit_pass.audit_artifact(vault, Path("compiled/this-week.md"))
    unused = [
        f for f in result.findings
        if f.category == FindingCategory.UNUSED_DECLARATION
    ]
    assert len(unused) == 1
    assert unused[0].path == "/source/people/joe/index.md"


def test_audit_artifact_flags_nonexistent_citation(vault):
    """A cited path that doesn't exist on disk fires a hallucination finding."""
    artifact = (
        "---\n"
        "type: compiled\n"
        "sources_read:\n"
        "  - /source/people/jane/index.md\n"
        "---\n\n"
        "## Must do\n"
        "- Jane stuff.\n"
        "  → /source/people/jane/index.md\n"
    )
    _write(vault / "compiled" / "this-week.md", artifact)
    result = audit_pass.audit_artifact(vault, Path("compiled/this-week.md"))
    nonexistent = [
        f for f in result.findings
        if f.category == FindingCategory.NONEXISTENT_CITATION
    ]
    assert len(nonexistent) == 1
    assert nonexistent[0].path == "/source/people/jane/index.md"


def test_audit_artifact_multiple_categories_at_once(vault):
    """One artifact can produce findings across all three categories."""
    artifact = (
        "---\n"
        "type: compiled\n"
        "sources_read:\n"
        "  - /source/properties/123-main/index.md\n"  # declared, used → fine
        "  - /source/people/jane/index.md\n"           # declared, not cited → unused + nonexistent
        "---\n\n"
        "## Must do\n"
        "- Property.\n"
        "  → /source/properties/123-main/index.md\n"
        "- Joe (undeclared but exists).\n"
        "  → /source/people/joe/index.md\n"           # cited, not declared → undeclared
    )
    _write(vault / "compiled" / "this-week.md", artifact)
    result = audit_pass.audit_artifact(vault, Path("compiled/this-week.md"))
    categories = {f.category for f in result.findings}
    assert FindingCategory.UNDECLARED_CITATION in categories
    assert FindingCategory.UNUSED_DECLARATION in categories
    assert FindingCategory.NONEXISTENT_CITATION in categories


def test_audit_artifact_no_frontmatter_treats_declared_as_empty(vault):
    """An artifact missing frontmatter still gets parsed; every cited path
    is treated as undeclared."""
    artifact = (
        "# Just a body\n"
        "→ /source/people/joe/index.md\n"
    )
    _write(vault / "compiled" / "this-week.md", artifact)
    result = audit_pass.audit_artifact(vault, Path("compiled/this-week.md"))
    undeclared = [
        f for f in result.findings
        if f.category == FindingCategory.UNDECLARED_CITATION
    ]
    assert len(undeclared) == 1


# -----------------------------------------------------------------------------
# audit_all — runs over the standard set, skips missing
# -----------------------------------------------------------------------------


def test_audit_all_skips_missing_artifacts(vault):
    """Only one of the three v1 artifacts present; the other two are skipped."""
    _write(vault / "compiled" / "this-week.md", CLEAN_ARTIFACT)
    results = audit_pass.audit_all(vault)
    assert len(results) == 1
    assert results[0].artifact == "compiled/this-week.md"


def test_audit_all_empty_vault_returns_empty_list(vault):
    """No compiled artifacts → no results."""
    assert audit_pass.audit_all(vault) == []


# -----------------------------------------------------------------------------
# _render_report — frontmatter + sections
# -----------------------------------------------------------------------------


def test_render_report_clean_run_states_all_passed(vault):
    _write(vault / "compiled" / "this-week.md", CLEAN_ARTIFACT)
    results = audit_pass.audit_all(vault)
    report = audit_pass._render_report(results, refreshed="2026-05-10T12:00:00Z")
    assert report.startswith("---\n")
    assert "findings_total: 0" in report
    assert "All 1 audited artifacts passed." in report
    assert "## /compiled/this-week.md" in report
    assert "_(clean —" in report


def test_render_report_empty_vault_states_nothing_to_audit(vault):
    report = audit_pass._render_report([], refreshed="2026-05-10T12:00:00Z")
    assert "audited_count: 0" in report
    assert "no compiled artifacts found" in report


def test_render_report_drift_emits_findings_under_each_artifact(vault):
    artifact = (
        "---\n"
        "type: compiled\n"
        "sources_read:\n"
        "  - /source/people/jane/index.md\n"  # nonexistent + unused
        "---\n\n"
        "→ /source/people/joe/index.md\n"   # exists but undeclared
    )
    _write(vault / "compiled" / "this-week.md", artifact)
    results = audit_pass.audit_all(vault)
    report = audit_pass._render_report(results, refreshed="2026-05-10T12:00:00Z")
    assert "findings_total: 3" in report
    assert "findings_undeclared_citation: 1" in report
    assert "findings_unused_declaration: 1" in report
    assert "findings_nonexistent_citation: 1" in report
    assert "undeclared citation" in report
    assert "unused declaration" in report
    assert "nonexistent citation" in report


# -----------------------------------------------------------------------------
# run — atomic write + integration
# -----------------------------------------------------------------------------


def test_run_writes_report_atomically(vault):
    _write(vault / "compiled" / "this-week.md", CLEAN_ARTIFACT)
    target, results = audit_pass.run(vault)
    assert target == vault / "_review" / "audit-report.md"
    body = target.read_text(encoding="utf-8")
    assert body.startswith("---\n")
    assert "All 1 audited artifacts passed." in body
    # No temp file leak
    assert list(target.parent.glob("*.tmp")) == []
    assert results[0].artifact == "compiled/this-week.md"


def test_run_overwrites_existing_report(vault):
    _write(vault / "_review" / "audit-report.md", "STALE\n")
    _write(vault / "compiled" / "this-week.md", CLEAN_ARTIFACT)
    target, _ = audit_pass.run(vault)
    body = target.read_text(encoding="utf-8")
    assert "STALE" not in body


# -----------------------------------------------------------------------------
# Env handling
# -----------------------------------------------------------------------------


def test_resolve_vault_root_requires_env_var(monkeypatch):
    monkeypatch.delenv("PLOS_VAULT_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="PLOS_VAULT_ROOT"):
        audit_pass._resolve_vault_root()
