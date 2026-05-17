"""
Weekly digest — plain-text email summarising recent pipeline activity.

The delivery layer that turns the PLOS audit trail into a thing
the user actually reads. Phase 5 Slice 5 v1 ships ONE section —
"Recent activity" — listing every `documents` row created in the
past 7 days, with the routing entity (slug + type) and final
processing status per row.

Future slices will fold in deadlines (date-typed entity frontmatter
fields inside a lookahead window), anomalies + gaps + audit
findings summaries (parsing `compiled/anomalies.md` and
`_review/audit-report.md`), and the review-queue summary (counts
from `documents.status='needs_review'`). The architecture for those
is in ARCHITECTURE.md; v1 deliberately subtracts to the smallest
end-to-end slice that demonstrates "PLOS as a thing in your inbox."

Operational shape:

- **SMTP via stdlib `smtplib`** (no new dependency). STARTTLS on
  the standard submission port. Tested against Gmail; should work
  with any SMTP submission server that supports STARTTLS.
- **Dry-run by default.** First invocation prints the rendered
  email to stdout. Set `PLOS_NOTIFY_SEND=1` to actually send.
  This protects against accidental sends during development.
- **As-of override.** `PLOS_DIGEST_AS_OF=YYYY-MM-DD` pins "today"
  for tests and demos. Defaults to today's UTC date.
- **Activity window** is the past 7 days from `as_of`, end-
  inclusive (00:00 of as_of - 7 → 23:59 of as_of).

Required env vars (when sending):
  PLOS_SMTP_USERNAME
  PLOS_SMTP_PASSWORD     (Gmail App Password, not the account password)
  PLOS_NOTIFY_TO
Optional env vars:
  PLOS_SMTP_HOST         default: smtp.gmail.com
  PLOS_SMTP_PORT         default: 587
  PLOS_NOTIFY_FROM       default: PLOS_SMTP_USERNAME
  PLOS_NOTIFY_SEND       default unset → dry-run; "1" → send
  PLOS_DIGEST_AS_OF      default: today UTC

Run from the repo root:
    python -m plos.notifications
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from sqlite3 import Connection

from dotenv import load_dotenv

from plos import db

logger = logging.getLogger("plos.notifications")

DEFAULT_WINDOW_DAYS = 7
DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587

AS_OF_ENV_VAR = "PLOS_DIGEST_AS_OF"
SEND_ENV_VAR = "PLOS_NOTIFY_SEND"
SMTP_HOST_ENV_VAR = "PLOS_SMTP_HOST"
SMTP_PORT_ENV_VAR = "PLOS_SMTP_PORT"
SMTP_USERNAME_ENV_VAR = "PLOS_SMTP_USERNAME"
SMTP_PASSWORD_ENV_VAR = "PLOS_SMTP_PASSWORD"
NOTIFY_FROM_ENV_VAR = "PLOS_NOTIFY_FROM"
NOTIFY_TO_ENV_VAR = "PLOS_NOTIFY_TO"


@dataclass(frozen=True)
class ActivityRow:
    """One row from the recent-activity SQL — one document processed in the window."""

    document_id: int
    paperless_id: int
    title: str | None
    status: str
    created_at: str  # SQLite TIMESTAMP, stored as ISO string
    entity_slug: str | None
    entity_type: str | None


@dataclass(frozen=True)
class DigestPayload:
    """Everything `render_digest` needs to compose the email."""

    as_of: date
    window_start: date  # inclusive
    window_end: date  # inclusive (= as_of)
    activity: list[ActivityRow]


@dataclass(frozen=True)
class SmtpConfig:
    """Resolved SMTP settings + recipient. Pulled from env in `_resolve_smtp_config`."""

    host: str
    port: int
    username: str
    password: str
    from_addr: str
    to_addr: str


def fetch_recent_activity(
    conn: Connection,
    *,
    as_of: date,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> list[ActivityRow]:
    """Return documents.created_at within (as_of - window_days, as_of+1day).

    The lower bound is inclusive (00:00 of as_of - window_days + 1, so a
    7-day window starting today and looking back covers today + the
    previous 6 days). The upper bound is exclusive (the start of the
    day AFTER as_of) so that rows created today are included regardless
    of timestamp.

    Each row's entity routing is pulled from `extracted_fields` →
    `entities` (one entity per document, by the worker's contract).
    Documents that haven't been routed (no extracted_fields rows) come
    back with `entity_slug=None`, `entity_type=None`.
    """
    window_start = as_of - timedelta(days=window_days - 1)
    window_end_exclusive = as_of + timedelta(days=1)
    rows = conn.execute(
        """
        SELECT
          d.id AS document_id,
          d.paperless_id,
          d.title,
          d.status,
          d.created_at,
          (
            SELECT e.slug
            FROM extracted_fields ef
            JOIN entities e ON e.id = ef.entity_id
            WHERE ef.document_id = d.id
            LIMIT 1
          ) AS entity_slug,
          (
            SELECT e.type
            FROM extracted_fields ef
            JOIN entities e ON e.id = ef.entity_id
            WHERE ef.document_id = d.id
            LIMIT 1
          ) AS entity_type
        FROM documents d
        WHERE date(d.created_at) >= ?
          AND date(d.created_at) < ?
        ORDER BY d.created_at DESC, d.id DESC
        """,
        (window_start.isoformat(), window_end_exclusive.isoformat()),
    ).fetchall()
    return [
        ActivityRow(
            document_id=r["document_id"],
            paperless_id=r["paperless_id"],
            title=r["title"],
            status=r["status"],
            created_at=r["created_at"],
            entity_slug=r["entity_slug"],
            entity_type=r["entity_type"],
        )
        for r in rows
    ]


def render_digest(payload: DigestPayload) -> tuple[str, str]:
    """Return `(subject, body)` for the digest email.

    Body is plain text; structure follows a markdown-ish convention
    so it renders as plain text in any client but stays scannable.
    """
    subject = f"PLOS digest — week ending {payload.as_of.isoformat()}"

    lines: list[str] = [
        f"PLOS digest — week ending {payload.as_of.isoformat()}",
        "=" * 50,
        "",
        (
            f"Window: {payload.window_start.isoformat()} "
            f"– {payload.window_end.isoformat()} "
            "(7-day lookback, end-inclusive)"
        ),
        "",
        "Recent activity",
        "---------------",
        "",
    ]

    if not payload.activity:
        lines.append("No documents processed this week.")
    else:
        lines.append(f"{len(payload.activity)} document(s) processed.")
        lines.append("")
        for row in payload.activity:
            date_part = (row.created_at or "")[:10]  # YYYY-MM-DD slice
            title = row.title or f"paperless_id={row.paperless_id}"
            entity = (
                f"{row.entity_slug} ({row.entity_type})"
                if row.entity_slug
                else "unrouted"
            )
            lines.append(
                f"- {date_part}  {row.status:<14}  {title}  -> {entity}"
            )

    lines.extend(
        [
            "",
            "---",
            (
                "Generated by `python -m plos.notifications`. "
                "Source: SQLite `documents` table."
            ),
            "",
        ]
    )
    return subject, "\n".join(lines)


def send_email(
    subject: str,
    body: str,
    cfg: SmtpConfig,
) -> None:
    """Send a plain-text email via STARTTLS.

    Uses stdlib `smtplib` + `email.message.EmailMessage`. No new
    dependency. The TLS context is the default Python context
    (system trust roots).
    """
    msg = EmailMessage()
    msg["From"] = cfg.from_addr
    msg["To"] = cfg.to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP(cfg.host, cfg.port) as smtp:
        smtp.starttls(context=context)
        smtp.login(cfg.username, cfg.password)
        smtp.send_message(msg)


def _resolve_as_of() -> date:
    """Pull PLOS_DIGEST_AS_OF as a date, or today's UTC date."""
    raw = os.environ.get(AS_OF_ENV_VAR)
    if not raw:
        return datetime.now(timezone.utc).date()
    return date.fromisoformat(raw)


def _should_send() -> bool:
    """True iff PLOS_NOTIFY_SEND is set to a truthy string."""
    return os.environ.get(SEND_ENV_VAR, "").strip() in {"1", "true", "yes", "TRUE"}


def _resolve_smtp_config() -> SmtpConfig:
    """Pull SMTP + recipient config from env. Raises if required vars missing."""
    username = os.environ.get(SMTP_USERNAME_ENV_VAR)
    password = os.environ.get(SMTP_PASSWORD_ENV_VAR)
    to_addr = os.environ.get(NOTIFY_TO_ENV_VAR)
    missing = [
        name
        for name, val in (
            (SMTP_USERNAME_ENV_VAR, username),
            (SMTP_PASSWORD_ENV_VAR, password),
            (NOTIFY_TO_ENV_VAR, to_addr),
        )
        if not val
    ]
    if missing:
        raise RuntimeError(
            f"notifications: cannot send — missing env var(s): {', '.join(missing)}"
        )
    return SmtpConfig(
        host=os.environ.get(SMTP_HOST_ENV_VAR, DEFAULT_SMTP_HOST),
        port=int(os.environ.get(SMTP_PORT_ENV_VAR, str(DEFAULT_SMTP_PORT))),
        username=username,  # type: ignore[arg-type]
        password=password,  # type: ignore[arg-type]
        from_addr=os.environ.get(NOTIFY_FROM_ENV_VAR) or username,  # type: ignore[arg-type]
        to_addr=to_addr,  # type: ignore[arg-type]
    )


def run(
    conn: Connection,
    *,
    as_of: date | None = None,
    send: bool = False,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> dict[str, object]:
    """Build digest, render, and either print (dry-run) or send.

    Returns a small summary dict:
      {
        "as_of": "YYYY-MM-DD",
        "activity_count": N,
        "subject": "...",
        "mode": "dry-run" | "sent",
      }
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc).date()
    window_start = as_of - timedelta(days=window_days - 1)
    activity = fetch_recent_activity(conn, as_of=as_of, window_days=window_days)
    payload = DigestPayload(
        as_of=as_of,
        window_start=window_start,
        window_end=as_of,
        activity=activity,
    )
    subject, body = render_digest(payload)

    if send:
        cfg = _resolve_smtp_config()
        logger.info(
            "sending digest to %s via %s:%d", cfg.to_addr, cfg.host, cfg.port
        )
        send_email(subject, body, cfg)
        mode = "sent"
    else:
        logger.info(
            "dry-run — rendered digest (%d activity row(s), subject=%r)",
            len(activity),
            subject,
        )
        print("-" * 60)
        print(f"Subject: {subject}")
        print("-" * 60)
        print(body)
        print("-" * 60)
        mode = "dry-run"

    return {
        "as_of": as_of.isoformat(),
        "activity_count": len(activity),
        "subject": subject,
        "mode": mode,
    }


def main() -> None:
    load_dotenv(override=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    as_of = _resolve_as_of()
    send = _should_send()
    with db.connect() as conn:
        result = run(conn, as_of=as_of, send=send)
    logger.info(
        "notifications complete: mode=%s, activity_count=%d, as_of=%s",
        result["mode"],
        result["activity_count"],
        result["as_of"],
    )


if __name__ == "__main__":
    main()
