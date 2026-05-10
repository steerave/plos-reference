"""
Graduated extractor for Beacon Software pay stubs.

Recognizes a Beacon Software pay stub by the employer name in the
OCR'd text, then pulls gross/net for the period, YTD gross, period end
date, and the employee's name with whitespace-tolerant regex. Returns
None if the employer header is absent OR if gross / net / period end /
employee name can't be parsed.

`route` locates the person whose `legal_name` and `employer_current`
both match — the routing key is a (name, employer) pair, since neither
alone is unique in a household.

Sensitivity classification (pay stubs are confidential by default) is
deferred to Phase 4+ per the architecture's deferred-features list. For
Phase 3, the extractor treats the document like any other: the worker
writes its fields into the person's frontmatter and records the audit
trail in SQLite. The body redaction pipeline lands later.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from plos import entities
from plos.extractors.registry import DocumentMeta, RouteResult

EMPLOYER = "Beacon Software"


def extract(text: str, document: DocumentMeta) -> dict[str, Any] | None:
    if EMPLOYER not in text:
        return None

    gross = _amount_after(text, "Gross pay")
    net = _amount_after(text, "Net pay")
    period_end = _period_end(text)
    employee = _employee_name(text)
    if gross is None or net is None or period_end is None or employee is None:
        return None

    fields: dict[str, Any] = {
        "last_paystub_gross": gross,
        "last_paystub_net": net,
        "last_paystub_period_end": period_end.isoformat(),
        "last_paystub_url": document.paperless_url,
        "paystub_employee_name": employee,
        "paystub_employer": EMPLOYER,
    }
    if (ytd := _amount_after(text, "YTD gross")) is not None:
        fields["last_paystub_ytd_gross"] = ytd
    return fields


def _amount_after(text: str, label: str) -> float | None:
    pattern = rf"{re.escape(label)}[:\s]+\$?([\d,]+\.\d{{2}})"
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def _period_end(text: str) -> date | None:
    """Parse the end date of 'Pay period: <start> - <end>' or 'Period ending: <date>'."""
    # Try the explicit "Period ending" label first
    label_explicit = r"Period\s+ending"
    m = re.search(
        rf"{label_explicit}[:\s]+(\d{{4}}-\d{{2}}-\d{{2}})", text, re.IGNORECASE
    )
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            pass
    m = re.search(
        rf"{label_explicit}[:\s]+([A-Z][a-z]+\s+\d{{1,2}},\s*\d{{4}})",
        text,
        re.IGNORECASE,
    )
    if m:
        try:
            return datetime.strptime(m.group(1), "%B %d, %Y").date()
        except ValueError:
            return None
    # Otherwise try the "Pay period: <start> - <end>" range form
    m = re.search(
        r"Pay\s+period[:\s]+"
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


def _employee_name(text: str) -> str | None:
    """Pull the employee name off the 'Employee: <First Last>' line.

    We require the literal colon so the section header "Employee\\n" by
    itself doesn't match, and we capture exactly two Capitalized words
    so a greedy match doesn't bleed into the following label (the OCR
    often runs lines together — "Employee: Joe Sample Period ending:
    ..." — and a more permissive regex would swallow "Period" too).
    """
    m = re.search(r"Employee:\s+([A-Z][a-z]+\s+[A-Z][a-z]+)", text)
    if not m:
        return None
    return m.group(1)


def route(fields: dict[str, Any], vault_root: Path) -> RouteResult:
    """Find the person whose legal_name + employer_current match this stub."""
    employee = fields.get("paystub_employee_name")
    employer = fields.get("paystub_employer")
    if not employee or not employer:
        return RouteResult(path=None, missing_key=True)
    return RouteResult(
        path=entities.find_person_by_employer_and_name(
            employee, employer, vault_root
        ),
        missing_key=False,
    )
