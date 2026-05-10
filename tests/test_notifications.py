"""
Tests for the weekly notifications digest.

SMTP is mocked at the smtplib boundary — no real network. SQL is
exercised against an in-memory SQLite seeded with `documents` +
`entities` + `extracted_fields` rows. Render is plain-text; assertions
target structure, not exact byte sequences.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from plos import db, notifications
from plos.notifications import ActivityRow, DigestPayload, SmtpConfig


# -----------------------------------------------------------------------------
# Fixtures + helpers
# -----------------------------------------------------------------------------


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    db.init_schema(c)
    yield c
    c.close()


def _insert_entity(
    conn: sqlite3.Connection,
    *,
    entity_type: str,
    domain: str,
    slug: str,
    wiki_path: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO entities (type, domain, slug, wiki_path) VALUES (?, ?, ?, ?)",
        (entity_type, domain, slug, wiki_path),
    )
    conn.commit()
    return cur.lastrowid


def _insert_document(
    conn: sqlite3.Connection,
    *,
    paperless_id: int,
    title: str,
    status: str,
    created_at: str,
    document_date: str | None = None,
) -> int:
    """Insert a document with an explicit created_at (overriding the DEFAULT)."""
    cur = conn.execute(
        """
        INSERT INTO documents
            (paperless_id, paperless_url, title, status, created_at, document_date)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            paperless_id,
            f"http://localhost:8888/documents/{paperless_id}/",
            title,
            status,
            created_at,
            document_date,
        ),
    )
    conn.commit()
    return cur.lastrowid


def _insert_extracted_field(
    conn: sqlite3.Connection,
    *,
    document_id: int,
    entity_id: int,
    field_name: str = "f",
    field_value: str = "v",
) -> None:
    conn.execute(
        """
        INSERT INTO extracted_fields
            (document_id, entity_id, field_name, field_value, handler)
        VALUES (?, ?, ?, ?, 'test')
        """,
        (document_id, entity_id, field_name, field_value),
    )
    conn.commit()


# -----------------------------------------------------------------------------
# fetch_recent_activity — window math + joins
# -----------------------------------------------------------------------------


def test_fetch_recent_activity_empty_db(conn):
    assert notifications.fetch_recent_activity(conn, as_of=date(2026, 5, 10)) == []


def test_fetch_recent_activity_includes_today_and_six_days_back(conn):
    """7-day window ending today: includes today and the previous 6 days."""
    for day, pid in (
        ("2026-05-04 09:00:00", 100),  # 6 days back — in
        ("2026-05-10 11:00:00", 101),  # today — in
        ("2026-05-03 09:00:00", 102),  # 7 days back — OUT (lower bound)
        ("2026-05-11 09:00:00", 103),  # tomorrow — OUT (upper bound)
    ):
        _insert_document(
            conn,
            paperless_id=pid,
            title=f"doc-{pid}.pdf",
            status="done",
            created_at=day,
        )
    rows = notifications.fetch_recent_activity(conn, as_of=date(2026, 5, 10))
    pids = {r.paperless_id for r in rows}
    assert pids == {100, 101}


def test_fetch_recent_activity_includes_routing_entity(conn):
    """A document with extracted_fields rows surfaces its entity slug+type."""
    entity_id = _insert_entity(
        conn,
        entity_type="property",
        domain="properties",
        slug="123-main-davenport",
        wiki_path="source/properties/123-main-davenport/index.md",
    )
    doc_id = _insert_document(
        conn,
        paperless_id=42,
        title="electric_acme_2026_04.pdf",
        status="done",
        created_at="2026-05-09 10:00:00",
    )
    _insert_extracted_field(conn, document_id=doc_id, entity_id=entity_id)

    rows = notifications.fetch_recent_activity(conn, as_of=date(2026, 5, 10))
    assert len(rows) == 1
    assert rows[0].entity_slug == "123-main-davenport"
    assert rows[0].entity_type == "property"


def test_fetch_recent_activity_unrouted_document_has_none_entity(conn):
    """A document with no extracted_fields rows (status=new) returns None entity."""
    _insert_document(
        conn,
        paperless_id=42,
        title="unrouted.pdf",
        status="new",
        created_at="2026-05-09 10:00:00",
    )
    rows = notifications.fetch_recent_activity(conn, as_of=date(2026, 5, 10))
    assert len(rows) == 1
    assert rows[0].entity_slug is None
    assert rows[0].entity_type is None


def test_fetch_recent_activity_sorts_most_recent_first(conn):
    """ORDER BY created_at DESC."""
    for day, pid in (
        ("2026-05-05 09:00:00", 100),
        ("2026-05-09 09:00:00", 101),
        ("2026-05-07 09:00:00", 102),
    ):
        _insert_document(
            conn,
            paperless_id=pid,
            title=f"doc-{pid}.pdf",
            status="done",
            created_at=day,
        )
    rows = notifications.fetch_recent_activity(conn, as_of=date(2026, 5, 10))
    assert [r.paperless_id for r in rows] == [101, 102, 100]


# -----------------------------------------------------------------------------
# render_digest
# -----------------------------------------------------------------------------


def _payload(activity: list[ActivityRow]) -> DigestPayload:
    return DigestPayload(
        as_of=date(2026, 5, 10),
        window_start=date(2026, 5, 4),
        window_end=date(2026, 5, 10),
        activity=activity,
    )


def test_render_digest_subject_includes_as_of_date():
    subject, body = notifications.render_digest(_payload([]))
    assert subject == "PLOS digest — week ending 2026-05-10"


def test_render_digest_empty_window_states_no_activity():
    _, body = notifications.render_digest(_payload([]))
    assert "No documents processed this week." in body
    assert "Window: 2026-05-04 – 2026-05-10" in body


def test_render_digest_lists_each_activity_row():
    activity = [
        ActivityRow(
            document_id=1,
            paperless_id=42,
            title="electric_acme_2026_04.pdf",
            status="done",
            created_at="2026-05-09 10:00:00",
            entity_slug="123-main-davenport",
            entity_type="property",
        ),
        ActivityRow(
            document_id=2,
            paperless_id=43,
            title=None,  # null title still renders something
            status="pending_claude",
            created_at="2026-05-08 14:30:00",
            entity_slug=None,
            entity_type=None,
        ),
    ]
    _, body = notifications.render_digest(_payload(activity))
    assert "2 document(s) processed." in body
    assert "electric_acme_2026_04.pdf" in body
    assert "123-main-davenport (property)" in body
    assert "paperless_id=43" in body  # fallback when title is null
    assert "unrouted" in body  # fallback when no entity


# -----------------------------------------------------------------------------
# send_email — smtplib mocked
# -----------------------------------------------------------------------------


def _cfg() -> SmtpConfig:
    return SmtpConfig(
        host="smtp.example.com",
        port=587,
        username="user@example.com",
        password="secret",
        from_addr="user@example.com",
        to_addr="dest@example.com",
    )


def test_send_email_invokes_starttls_login_and_sendmessage():
    with patch("plos.notifications.smtplib.SMTP") as smtp_cls:
        smtp_instance = MagicMock()
        smtp_cls.return_value.__enter__.return_value = smtp_instance
        notifications.send_email("subj", "body", _cfg())

        smtp_cls.assert_called_once_with("smtp.example.com", 587)
        smtp_instance.starttls.assert_called_once()
        smtp_instance.login.assert_called_once_with("user@example.com", "secret")
        # send_message takes one positional EmailMessage arg
        smtp_instance.send_message.assert_called_once()
        msg = smtp_instance.send_message.call_args.args[0]
        assert msg["Subject"] == "subj"
        assert msg["From"] == "user@example.com"
        assert msg["To"] == "dest@example.com"
        assert msg.get_content().rstrip("\n") == "body"


# -----------------------------------------------------------------------------
# run — dry-run vs send routing
# -----------------------------------------------------------------------------


def test_run_dry_run_prints_and_does_not_call_smtp(conn, capsys):
    _insert_document(
        conn,
        paperless_id=100,
        title="some.pdf",
        status="done",
        created_at="2026-05-09 10:00:00",
    )
    with patch("plos.notifications.send_email") as send_email_mock:
        result = notifications.run(conn, as_of=date(2026, 5, 10), send=False)
        send_email_mock.assert_not_called()

    assert result["mode"] == "dry-run"
    assert result["activity_count"] == 1
    captured = capsys.readouterr().out
    assert "Subject: PLOS digest" in captured
    assert "some.pdf" in captured


def test_run_send_invokes_smtp(conn, monkeypatch):
    monkeypatch.setenv(notifications.SMTP_USERNAME_ENV_VAR, "user@example.com")
    monkeypatch.setenv(notifications.SMTP_PASSWORD_ENV_VAR, "secret")
    monkeypatch.setenv(notifications.NOTIFY_TO_ENV_VAR, "dest@example.com")
    with patch("plos.notifications.send_email") as send_email_mock:
        result = notifications.run(conn, as_of=date(2026, 5, 10), send=True)
        send_email_mock.assert_called_once()
        args = send_email_mock.call_args
        # send_email is called as send_email(subject, body, cfg)
        subject, body, cfg = args.args
        assert subject.startswith("PLOS digest")
        assert "No documents processed" in body
        assert cfg.to_addr == "dest@example.com"
    assert result["mode"] == "sent"


def test_run_send_raises_when_required_env_var_missing(conn, monkeypatch):
    monkeypatch.delenv(notifications.SMTP_USERNAME_ENV_VAR, raising=False)
    monkeypatch.delenv(notifications.SMTP_PASSWORD_ENV_VAR, raising=False)
    monkeypatch.delenv(notifications.NOTIFY_TO_ENV_VAR, raising=False)
    with pytest.raises(RuntimeError, match="missing env var"):
        notifications.run(conn, as_of=date(2026, 5, 10), send=True)


# -----------------------------------------------------------------------------
# Env handling
# -----------------------------------------------------------------------------


def test_resolve_as_of_defaults_to_today_when_unset(monkeypatch):
    monkeypatch.delenv(notifications.AS_OF_ENV_VAR, raising=False)
    today = date.today()
    assert notifications._resolve_as_of() == today


def test_resolve_as_of_parses_iso_date(monkeypatch):
    monkeypatch.setenv(notifications.AS_OF_ENV_VAR, "2026-05-10")
    assert notifications._resolve_as_of() == date(2026, 5, 10)


def test_resolve_as_of_raises_on_malformed(monkeypatch):
    monkeypatch.setenv(notifications.AS_OF_ENV_VAR, "yesterday")
    with pytest.raises(ValueError):
        notifications._resolve_as_of()


def test_should_send_false_when_unset(monkeypatch):
    monkeypatch.delenv(notifications.SEND_ENV_VAR, raising=False)
    assert notifications._should_send() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE"])
def test_should_send_truthy_values(monkeypatch, value):
    monkeypatch.setenv(notifications.SEND_ENV_VAR, value)
    assert notifications._should_send() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "", "maybe"])
def test_should_send_falsy_values(monkeypatch, value):
    monkeypatch.setenv(notifications.SEND_ENV_VAR, value)
    assert notifications._should_send() is False


def test_resolve_smtp_config_uses_defaults_for_optional_vars(monkeypatch):
    monkeypatch.delenv(notifications.SMTP_HOST_ENV_VAR, raising=False)
    monkeypatch.delenv(notifications.SMTP_PORT_ENV_VAR, raising=False)
    monkeypatch.delenv(notifications.NOTIFY_FROM_ENV_VAR, raising=False)
    monkeypatch.setenv(notifications.SMTP_USERNAME_ENV_VAR, "user@example.com")
    monkeypatch.setenv(notifications.SMTP_PASSWORD_ENV_VAR, "secret")
    monkeypatch.setenv(notifications.NOTIFY_TO_ENV_VAR, "dest@example.com")
    cfg = notifications._resolve_smtp_config()
    assert cfg.host == "smtp.gmail.com"
    assert cfg.port == 587
    assert cfg.from_addr == "user@example.com"  # falls back to username


def test_resolve_smtp_config_lists_missing_vars(monkeypatch):
    monkeypatch.delenv(notifications.SMTP_USERNAME_ENV_VAR, raising=False)
    monkeypatch.delenv(notifications.SMTP_PASSWORD_ENV_VAR, raising=False)
    monkeypatch.delenv(notifications.NOTIFY_TO_ENV_VAR, raising=False)
    with pytest.raises(RuntimeError) as exc:
        notifications._resolve_smtp_config()
    msg = str(exc.value)
    assert notifications.SMTP_USERNAME_ENV_VAR in msg
    assert notifications.SMTP_PASSWORD_ENV_VAR in msg
    assert notifications.NOTIFY_TO_ENV_VAR in msg
