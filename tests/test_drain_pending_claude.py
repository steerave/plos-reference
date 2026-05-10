"""
Tests for the pending_claude drain workflow.

Mocks the `claude` CLI subprocess and the Paperless API. Asserts that
each route_status path (matched / unmatched_entity / unrecognized /
malformed) lands the right side effects: vault frontmatter, SQLite
documents.status, extracted_fields audit trail, JSON-encoded review
proposal on review_reason for unmatched.
"""

from __future__ import annotations

import json
import subprocess

import pytest
import responses

from plos import db, drain_pending_claude


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("PAPERLESS_URL_PUBLIC", "http://localhost:8888")
    monkeypatch.setenv("PAPERLESS_API_TOKEN", "test-token-abc")


@pytest.fixture
def conn(tmp_path, monkeypatch):
    # `db.connect()` reads PLOS_DB_PATH from env; point it at a tmp file so
    # drain_pending_claude.run() opens our test DB.
    db_path = tmp_path / "plos.db"
    monkeypatch.setenv("PLOS_DB_PATH", str(db_path))
    c = db.connect(db_path)
    db.init_schema(c)
    yield c
    c.close()


@pytest.fixture
def vault(tmp_path):
    """Build a tmp vault with one property keyed to ACCT-12345."""
    folder = tmp_path / "vault" / "source" / "properties" / "123-main-davenport"
    folder.mkdir(parents=True)
    (folder / "index.md").write_text(
        "---\n"
        "type: source\n"
        "entity: property\n"
        "slug: 123-main-davenport\n"
        "address: 123 Main St, Davenport, IA 52801\n"
        "electric_account: ACCT-12345\n"
        "locked_fields: []\n"
        "---\n\n"
        "# 123 Main St, Davenport, IA\n",
        encoding="utf-8",
    )
    return tmp_path / "vault"


def _insert_pending(conn, paperless_id, **kw):
    conn.execute(
        "INSERT INTO documents (paperless_id, paperless_url, title, "
        "correspondent, document_date, status) VALUES (?, ?, ?, ?, ?, "
        "'pending_claude')",
        (
            paperless_id,
            kw.get("url", f"http://localhost:8888/documents/{paperless_id}/"),
            kw.get("title"),
            kw.get("correspondent"),
            kw.get("document_date"),
        ),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM documents WHERE paperless_id=?", (paperless_id,)
    ).fetchone()["id"]


def _mock_paperless(paperless_id, content):
    responses.add(
        responses.GET,
        f"http://localhost:8888/api/documents/{paperless_id}/",
        json={"content": content, "created_date": "2026-04-15"},
        status=200,
    )


def _patch_claude(monkeypatch, response_text):
    """Patch subprocess.run to return the given text as Claude's stdout."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = kwargs.get("input")
        return subprocess.CompletedProcess(cmd, 0, response_text, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return captured


# -----------------------------------------------------------------------------
# parse_response — the JSON parser
# -----------------------------------------------------------------------------


def test_parse_response_handles_bare_json():
    raw = json.dumps(
        {
            "doc_type": "utility_bill_gas",
            "route_status": "matched",
            "entity_type": "property",
            "entity_slug": "123-main-davenport",
            "fields": {"last_utility_bill_amount": 89.42},
            "rationale": "Gas bill from MidAmerican; matches the Davenport property.",
        }
    )
    result = drain_pending_claude.parse_response(raw)
    assert result.route_status == "matched"
    assert result.entity_slug == "123-main-davenport"
    assert result.fields == {"last_utility_bill_amount": 89.42}


def test_parse_response_strips_json_code_fence():
    raw = (
        "```json\n"
        '{"doc_type":"x","route_status":"unrecognized","fields":{},"rationale":"r"}\n'
        "```"
    )
    result = drain_pending_claude.parse_response(raw)
    assert result.route_status == "unrecognized"


def test_parse_response_rejects_non_json():
    with pytest.raises(ValueError, match="not valid JSON"):
        drain_pending_claude.parse_response("I cannot help with that.")


def test_parse_response_rejects_unknown_route_status():
    raw = json.dumps({"route_status": "weird", "fields": {}})
    with pytest.raises(ValueError, match="route_status"):
        drain_pending_claude.parse_response(raw)


# -----------------------------------------------------------------------------
# process_one — happy path: matched
# -----------------------------------------------------------------------------


@responses.activate
def test_matched_doc_merges_into_entity_and_marks_done(conn, vault, monkeypatch):
    doc_id = _insert_pending(conn, 99, document_date="2026-04-15")
    _mock_paperless(99, "MidAmerican Energy gas bill...")
    _patch_claude(
        monkeypatch,
        json.dumps(
            {
                "doc_type": "utility_bill_gas",
                "route_status": "matched",
                "entity_type": "property",
                "entity_slug": "123-main-davenport",
                "fields": {
                    "last_utility_bill_amount": 89.42,
                    "last_utility_bill_date": "2026-04-30",
                    "gas_account": "MA-77881",
                },
                "rationale": "MidAmerican gas bill at the Davenport address.",
            }
        ),
    )

    row = conn.execute(
        "SELECT * FROM documents WHERE paperless_id=99"
    ).fetchone()
    assert drain_pending_claude.process_one(conn, row, vault) == "done"
    conn.commit()

    # documents row updated
    after = conn.execute(
        "SELECT status, document_type FROM documents WHERE paperless_id=99"
    ).fetchone()
    assert after["status"] == "done"
    assert after["document_type"] == "utility_bill_gas"

    # vault merged
    text = (vault / "source" / "properties" / "123-main-davenport" / "index.md").read_text(
        encoding="utf-8"
    )
    assert "last_utility_bill_amount: 89.42" in text
    assert "gas_account: MA-77881" in text

    # extracted_fields audit trail per field, all under handler='claude'
    rows = conn.execute(
        "SELECT field_name, handler FROM extracted_fields WHERE document_id=?",
        (doc_id,),
    ).fetchall()
    assert {r["field_name"] for r in rows} == {
        "last_utility_bill_amount",
        "last_utility_bill_date",
        "gas_account",
    }
    for r in rows:
        assert r["handler"] == "claude"


# -----------------------------------------------------------------------------
# process_one — unmatched entity
# -----------------------------------------------------------------------------


@responses.activate
def test_unmatched_doc_marks_needs_review_with_proposal_blob(conn, vault, monkeypatch):
    doc_id = _insert_pending(conn, 100, document_date="2026-04-15")
    _mock_paperless(100, "Some bill from a totally new provider.")
    _patch_claude(
        monkeypatch,
        json.dumps(
            {
                "doc_type": "utility_bill_water",
                "route_status": "unmatched_entity",
                "entity_type": None,
                "entity_slug": None,
                "fields": {
                    "last_utility_bill_amount": 42.00,
                    "water_account": "AQUA-9988",
                },
                "rationale": "Aqua Inc water bill; no property in the vault claims AQUA-9988.",
                "proposed_entity": {
                    "type": "property",
                    "slug": "456-elsewhere",
                    "frontmatter_seed": {
                        "address": "456 Elsewhere St",
                        "water_account": "AQUA-9988",
                    },
                },
            }
        ),
    )

    row = conn.execute(
        "SELECT * FROM documents WHERE paperless_id=100"
    ).fetchone()
    assert drain_pending_claude.process_one(conn, row, vault) == "needs_review"
    conn.commit()

    after = conn.execute(
        "SELECT status, document_type, review_reason FROM documents WHERE paperless_id=100"
    ).fetchone()
    assert after["status"] == "needs_review"
    assert after["document_type"] == "utility_bill_water"
    blob = json.loads(after["review_reason"])
    assert blob["reason"] == "claude_unmatched_entity"
    assert blob["fields"]["water_account"] == "AQUA-9988"
    assert blob["proposed_entity"]["slug"] == "456-elsewhere"

    # No extracted_fields rows — entity_id is NOT NULL in the schema
    rows = conn.execute(
        "SELECT COUNT(*) AS n FROM extracted_fields WHERE document_id=?",
        (doc_id,),
    ).fetchone()
    assert rows["n"] == 0

    # Vault untouched
    text = (vault / "source" / "properties" / "123-main-davenport" / "index.md").read_text(
        encoding="utf-8"
    )
    assert "AQUA" not in text


# -----------------------------------------------------------------------------
# process_one — unrecognized
# -----------------------------------------------------------------------------


@responses.activate
def test_unrecognized_doc_marks_needs_review(conn, vault, monkeypatch):
    _insert_pending(conn, 101, document_date="2026-04-15")
    _mock_paperless(101, "scribbled-handwritten-thing")
    _patch_claude(
        monkeypatch,
        json.dumps(
            {
                "doc_type": "unknown",
                "route_status": "unrecognized",
                "entity_type": None,
                "entity_slug": None,
                "fields": {},
                "rationale": "Not a parseable document.",
            }
        ),
    )

    row = conn.execute(
        "SELECT * FROM documents WHERE paperless_id=101"
    ).fetchone()
    assert drain_pending_claude.process_one(conn, row, vault) == "needs_review"
    conn.commit()

    after = conn.execute(
        "SELECT status, review_reason FROM documents WHERE paperless_id=101"
    ).fetchone()
    assert after["status"] == "needs_review"
    assert after["review_reason"] == "claude_unrecognized"


# -----------------------------------------------------------------------------
# process_one — failure modes
# -----------------------------------------------------------------------------


@responses.activate
def test_invalid_json_response_marks_needs_review(conn, vault, monkeypatch):
    _insert_pending(conn, 102, document_date="2026-04-15")
    _mock_paperless(102, "An Acme bill…")
    _patch_claude(monkeypatch, "I'm sorry, I can't process this.")

    row = conn.execute(
        "SELECT * FROM documents WHERE paperless_id=102"
    ).fetchone()
    assert drain_pending_claude.process_one(conn, row, vault) == "needs_review"
    conn.commit()

    after = conn.execute(
        "SELECT status, review_reason FROM documents WHERE paperless_id=102"
    ).fetchone()
    assert after["status"] == "needs_review"
    assert after["review_reason"] == "claude_invalid_response"


@responses.activate
def test_empty_ocr_text_marks_needs_review_without_calling_claude(
    conn, vault, monkeypatch
):
    """If Paperless returns no content, we never spend a Claude call."""
    _insert_pending(conn, 103)
    _mock_paperless(103, "")
    sentinel = []

    def explode(*a, **kw):
        sentinel.append(("subprocess.run was called",))
        raise AssertionError("subprocess.run should not be called when OCR is empty")

    monkeypatch.setattr(subprocess, "run", explode)
    row = conn.execute(
        "SELECT * FROM documents WHERE paperless_id=103"
    ).fetchone()
    assert drain_pending_claude.process_one(conn, row, vault) == "needs_review"
    conn.commit()

    after = conn.execute(
        "SELECT review_reason FROM documents WHERE paperless_id=103"
    ).fetchone()
    assert after["review_reason"] == "empty_ocr_text"
    assert sentinel == []


@responses.activate
def test_matched_to_unknown_entity_falls_back_to_needs_review(
    conn, vault, monkeypatch
):
    """Claude says matched -> property/<slug>, but no such index.md exists."""
    _insert_pending(conn, 104, document_date="2026-04-15")
    _mock_paperless(104, "...")
    _patch_claude(
        monkeypatch,
        json.dumps(
            {
                "doc_type": "utility_bill_gas",
                "route_status": "matched",
                "entity_type": "property",
                "entity_slug": "ghost-property-not-in-vault",
                "fields": {"last_utility_bill_amount": 1.00},
                "rationale": "Hallucinated entity.",
            }
        ),
    )

    row = conn.execute(
        "SELECT * FROM documents WHERE paperless_id=104"
    ).fetchone()
    assert drain_pending_claude.process_one(conn, row, vault) == "needs_review"
    conn.commit()

    after = conn.execute(
        "SELECT review_reason FROM documents WHERE paperless_id=104"
    ).fetchone()
    assert after["review_reason"] == "claude_unmatched_entity"


# -----------------------------------------------------------------------------
# run() — multi-doc loop
# -----------------------------------------------------------------------------


@responses.activate
def test_run_processes_all_pending_claude_docs(conn, vault, monkeypatch):
    _insert_pending(conn, 200, document_date="2026-04-15")
    _insert_pending(conn, 201, document_date="2026-04-15")
    _mock_paperless(200, "doc 1")
    _mock_paperless(201, "doc 2")

    responses_q = [
        json.dumps(
            {
                "doc_type": "utility_bill_gas",
                "route_status": "matched",
                "entity_type": "property",
                "entity_slug": "123-main-davenport",
                "fields": {"gas_account": "MA-77881", "last_utility_bill_amount": 50.00},
                "rationale": "...",
            }
        ),
        json.dumps(
            {
                "doc_type": "unknown",
                "route_status": "unrecognized",
                "entity_type": None,
                "entity_slug": None,
                "fields": {},
                "rationale": "...",
            }
        ),
    ]

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, responses_q.pop(0), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    counts = drain_pending_claude.run(vault)

    assert counts == {"done": 1, "needs_review": 1, "errored": 0}


def test_run_with_no_pending_returns_zero_counts(conn, vault):
    counts = drain_pending_claude.run(vault)
    assert counts == {"done": 0, "needs_review": 0, "errored": 0}


@responses.activate
def test_run_leaves_status_unchanged_on_subprocess_failure(conn, vault, monkeypatch):
    _insert_pending(conn, 300, document_date="2026-04-15")
    _mock_paperless(300, "irrelevant")

    def boom(*a, **kw):
        raise subprocess.CalledProcessError(1, a[0], "", "claude crashed")

    monkeypatch.setattr(subprocess, "run", boom)
    counts = drain_pending_claude.run(vault)

    assert counts["errored"] == 1
    after = conn.execute(
        "SELECT status FROM documents WHERE paperless_id=300"
    ).fetchone()
    assert after["status"] == "pending_claude"  # untouched, will retry


# -----------------------------------------------------------------------------
# main / env
# -----------------------------------------------------------------------------


def test_resolve_vault_root_requires_env_var(monkeypatch):
    monkeypatch.delenv("PLOS_VAULT_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="PLOS_VAULT_ROOT"):
        drain_pending_claude._resolve_vault_root()
