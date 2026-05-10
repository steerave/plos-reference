"""
Graduated extractor for Acme Power & Light electric bills.

Recognizes the bill by the provider header in the OCR'd text, then
pulls amount due, due date, kWh used, and account number with simple
whitespace-tolerant regex. Returns None if the provider header is
absent OR if amount/due-date can't be parsed (provider matched but
body unrecognizable — better to bail than to return a half-extracted
record the worker would write into the vault).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from plos.extractors.registry import DocumentMeta

PROVIDER = "Acme Power & Light"


def extract(text: str, document: DocumentMeta) -> dict[str, Any] | None:
    if PROVIDER not in text:
        return None

    amount = _amount_due(text)
    due_date = _due_date(text)
    if amount is None or due_date is None:
        return None

    fields: dict[str, Any] = {
        "last_utility_bill_amount": amount,
        "last_utility_bill_date": due_date.isoformat(),
        "last_utility_bill_url": document.paperless_url,
    }
    if (kwh := _kwh(text)) is not None:
        fields["last_utility_bill_kwh"] = kwh
    if (account := _account(text)) is not None:
        fields["electric_account"] = account
    return fields


def _amount_due(text: str) -> float | None:
    m = re.search(r"Amount\s+due[:\s]+\$?([\d,]+\.\d{2})", text, re.IGNORECASE)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def _due_date(text: str) -> date | None:
    # ISO format first ("Due date: 2026-04-30")
    m = re.search(r"Due\s+date[:\s]+(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE)
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            pass
    # Long-form English ("Due date: April 30, 2026")
    m = re.search(
        r"Due\s+date[:\s]+([A-Z][a-z]+\s+\d{1,2},\s*\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        try:
            return datetime.strptime(m.group(1), "%B %d, %Y").date()
        except ValueError:
            return None
    return None


def _kwh(text: str) -> int | None:
    m = re.search(r"(\d{1,6})\s*kWh", text, re.IGNORECASE)
    if not m:
        return None
    return int(m.group(1))


def _account(text: str) -> str | None:
    m = re.search(r"Account\s+number[:\s]+([A-Z0-9][A-Z0-9\-]+)", text, re.IGNORECASE)
    if not m:
        return None
    return m.group(1)
