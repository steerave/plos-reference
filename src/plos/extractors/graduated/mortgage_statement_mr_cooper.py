"""
Graduated extractor for Mr. Cooper mortgage statements.

Recognizes a Mr. Cooper monthly statement by the servicer name in the
OCR'd text, then pulls amount due, principal balance, statement date,
and loan number with whitespace-tolerant regex. Returns None if the
servicer header is absent OR if amount/statement-date/loan-number can't
be parsed (servicer matched but body unrecognizable — better to bail
than to write a half-extracted record into the vault).

`route` locates the property whose `mortgage_loan_number` frontmatter
equals the loan number this extractor pulled.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from plos import entities
from plos.extractors.registry import DocumentMeta, RouteResult

SERVICER = "Mr. Cooper"


def extract(text: str, document: DocumentMeta) -> dict[str, Any] | None:
    if SERVICER not in text:
        return None

    amount = _amount_due(text)
    statement_date = _statement_date(text)
    loan_number = _loan_number(text)
    if amount is None or statement_date is None or loan_number is None:
        return None

    fields: dict[str, Any] = {
        "last_mortgage_statement_amount": amount,
        "last_mortgage_statement_date": statement_date.isoformat(),
        "last_mortgage_statement_url": document.paperless_url,
        "mortgage_loan_number": loan_number,
    }
    if (principal := _principal_balance(text)) is not None:
        fields["last_mortgage_statement_principal_balance"] = principal
    return fields


def _amount_due(text: str) -> float | None:
    # Mortgage statements typically use "Amount due" or "Total amount due"
    m = re.search(
        r"(?:Total\s+)?Amount\s+due[:\s]+\$?([\d,]+\.\d{2})", text, re.IGNORECASE
    )
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def _principal_balance(text: str) -> float | None:
    m = re.search(
        r"Principal\s+balance[:\s]+\$?([\d,]+\.\d{2})", text, re.IGNORECASE
    )
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def _statement_date(text: str) -> date | None:
    # Try ISO first, then long-form English. We accept "Statement date" or
    # "Bill date" — Mr. Cooper's published statements use "Statement date"
    # but OCR variations creep in.
    label = r"(?:Statement|Bill)\s+date"
    m = re.search(rf"{label}[:\s]+(\d{{4}}-\d{{2}}-\d{{2}})", text, re.IGNORECASE)
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            pass
    m = re.search(
        rf"{label}[:\s]+([A-Z][a-z]+\s+\d{{1,2}},\s*\d{{4}})", text, re.IGNORECASE
    )
    if m:
        try:
            return datetime.strptime(m.group(1), "%B %d, %Y").date()
        except ValueError:
            return None
    return None


def _loan_number(text: str) -> str | None:
    m = re.search(r"Loan\s+number[:\s]+([A-Z0-9][A-Z0-9\-]+)", text, re.IGNORECASE)
    if not m:
        return None
    return m.group(1)


def route(fields: dict[str, Any], vault_root: Path) -> RouteResult:
    """Find the property whose mortgage_loan_number matches this statement."""
    loan_number = fields.get("mortgage_loan_number")
    if not loan_number:
        return RouteResult(path=None, missing_key=True)
    return RouteResult(
        path=entities.find_property_by_mortgage_loan_number(loan_number, vault_root),
        missing_key=False,
    )
