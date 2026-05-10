"""
Graduated extractor for First Davenport Bank statements.

Recognizes a First Davenport Bank monthly statement by the bank name
in the OCR'd text, then pulls ending balance, statement period end,
account number, and total deposits/withdrawals with whitespace-tolerant
regex. Returns None if the bank header is absent OR if ending balance /
statement end / account number can't be parsed (bank matched but body
unrecognizable — better to bail than to write a half-extracted record
into the vault).

`route` locates the account whose `account_number` frontmatter equals
the value this extractor pulled.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from plos import entities
from plos.extractors.registry import DocumentMeta, RouteResult

BANK = "First Davenport Bank"


def extract(text: str, document: DocumentMeta) -> dict[str, Any] | None:
    if BANK not in text:
        return None

    ending_balance = _ending_balance(text)
    period_end = _period_end(text)
    account_number = _account_number(text)
    if ending_balance is None or period_end is None or account_number is None:
        return None

    fields: dict[str, Any] = {
        "last_statement_balance": ending_balance,
        "last_statement_end_date": period_end.isoformat(),
        "last_statement_url": document.paperless_url,
        "account_number": account_number,
    }
    if (deposits := _amount_after(text, "Total deposits")) is not None:
        fields["last_statement_deposits"] = deposits
    if (withdrawals := _amount_after(text, "Total withdrawals")) is not None:
        fields["last_statement_withdrawals"] = withdrawals
    return fields


def _amount_after(text: str, label: str) -> float | None:
    """Pull a $X,XXX.XX amount that follows the given label."""
    pattern = rf"{re.escape(label)}[:\s]+\$?([\d,]+\.\d{{2}})"
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def _ending_balance(text: str) -> float | None:
    return _amount_after(text, "Ending balance")


def _period_end(text: str) -> date | None:
    """Parse the end date of 'Statement period: <start> - <end>'."""
    m = re.search(
        r"Statement\s+period[:\s]+"
        r"(?:[A-Z][a-z]+\s+\d{1,2},\s*\d{4}|\d{4}-\d{2}-\d{2})\s*-\s*"
        r"((?:[A-Z][a-z]+\s+\d{1,2},\s*\d{4}|\d{4}-\d{2}-\d{2}))",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    raw = m.group(1)
    try:
        if re.match(r"\d{4}-\d{2}-\d{2}", raw):
            return date.fromisoformat(raw)
        return datetime.strptime(raw, "%B %d, %Y").date()
    except ValueError:
        return None


def _account_number(text: str) -> str | None:
    m = re.search(r"Account\s+number[:\s]+([A-Z0-9][A-Z0-9\-]+)", text, re.IGNORECASE)
    if not m:
        return None
    return m.group(1)


def route(fields: dict[str, Any], vault_root: Path) -> RouteResult:
    """Find the account whose account_number matches this statement."""
    account_number = fields.get("account_number")
    if not account_number:
        return RouteResult(path=None, missing_key=True)
    return RouteResult(
        path=entities.find_account_by_account_number(account_number, vault_root),
        missing_key=False,
    )
