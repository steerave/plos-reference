#!/usr/bin/env python3
"""
Deterministically generate the sample document PDFs used by the
phase-by-phase demos and the test suite.

Run from the repo root to produce all fixtures:
    python tests/fixtures/sample_documents/build.py

Each generator below writes one PDF with reproducible bytes (no
embedded timestamps), so re-running this script during CI or refactors
does not produce diff churn.

Generated outputs:
    electric_acme_2026_01.pdf         — Phase 5 Slice 1: Acme bill (Jan baseline)
    electric_acme_2026_02.pdf         — Phase 5 Slice 1: Acme bill (Feb baseline)
    electric_acme_2026_03.pdf         — Phase 5 Slice 1: Acme bill (Mar baseline)
    electric_acme_2026_04.pdf         — Phase 2: Acme Power & Light bill (current)
    mortgage_mrcooper_2026_04.pdf     — Phase 3 Slice 1: Mr. Cooper statement
    bank_first_davenport_2026_04.pdf  — Phase 3 Slice 2: First Davenport Bank
    paystub_beacon_2026_04.pdf        — Phase 3 Slice 3: Beacon Software stub
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

FIXTURES = Path(__file__).resolve().parent

ELECTRIC_OUTPUT = FIXTURES / "electric_acme_2026_04.pdf"
ELECTRIC_OUTPUT_2026_01 = FIXTURES / "electric_acme_2026_01.pdf"
ELECTRIC_OUTPUT_2026_02 = FIXTURES / "electric_acme_2026_02.pdf"
ELECTRIC_OUTPUT_2026_03 = FIXTURES / "electric_acme_2026_03.pdf"
MORTGAGE_OUTPUT = FIXTURES / "mortgage_mrcooper_2026_04.pdf"
BANK_OUTPUT = FIXTURES / "bank_first_davenport_2026_04.pdf"
PAYSTUB_OUTPUT = FIXTURES / "paystub_beacon_2026_04.pdf"


def _new_canvas(path: Path, title: str, author: str, subject: str) -> canvas.Canvas:
    # invariant=1 makes reportlab emit a content-derived /ID instead of a
    # time-based one, so re-running this script produces byte-identical
    # PDFs and `git diff` stays quiet between regenerations.
    c = canvas.Canvas(str(path), pagesize=LETTER, invariant=1)
    c.setTitle(title)
    c.setAuthor(author)
    c.setSubject(subject)
    c.setCreator("plos-reference fixture builder")
    c.setProducer("plos-reference fixture builder")
    return c


def build_electric_bill_for(
    path: Path,
    *,
    statement_date: str,
    service_period: str,
    kwh: int,
    amount: str,
    due_date: str,
) -> None:
    """Render one Acme Power & Light bill with the supplied per-period values.

    All Acme fixtures share the same layout, branding, and account
    metadata. Only the four cells under "Service period" / "Energy used"
    / "Charges" / "Amount due" / "Due date" vary, plus the statement
    date itself. Re-running with the same arguments produces a
    byte-identical PDF (reportlab `invariant=1`).
    """
    c = _new_canvas(
        path,
        title="Acme Power & Light — Statement",
        author="Acme Power & Light",
        subject="Monthly electric statement",
    )

    width, _ = LETTER
    left = 1 * inch
    right = width - 1 * inch
    y = 10 * inch

    c.setFont("Helvetica-Bold", 22)
    c.drawString(left, y, "Acme Power & Light")
    y -= 0.3 * inch
    c.setFont("Helvetica-Oblique", 11)
    c.drawString(left, y, "Reliable energy since 1987")
    y -= 0.5 * inch

    c.setFont("Helvetica-Bold", 12)
    c.drawString(left, y, "Service address")
    y -= 0.22 * inch
    c.setFont("Helvetica", 11)
    c.drawString(left, y, "123 Main St")
    y -= 0.2 * inch
    c.drawString(left, y, "Davenport, IA 52801")
    y -= 0.45 * inch

    rows = [
        ("Account number:", "ACCT-12345"),
        ("Statement date:", statement_date),
        ("Service period:", service_period),
        ("Energy used this period:", f"{kwh} kWh"),
        ("Charges this period:", f"${amount}"),
    ]
    c.setFont("Helvetica", 11)
    for label, value in rows:
        c.drawString(left, y, label)
        c.drawString(left + 2.5 * inch, y, value)
        y -= 0.28 * inch

    y -= 0.4 * inch
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(right, y, f"Amount due:    ${amount}")
    y -= 0.3 * inch
    c.drawRightString(right, y, f"Due date:      {due_date}")

    y -= 0.8 * inch
    c.setFont("Helvetica", 10)
    c.drawString(left, y, "Please remit payment to:")
    y -= 0.2 * inch
    c.drawString(left, y, "Acme Power & Light")
    y -= 0.2 * inch
    c.drawString(left, y, "PO Box 90210, Davenport IA 52801")

    c.showPage()
    c.save()


def build_electric_bill(path: Path) -> None:
    """Phase 2 demo bill — April 2026, $142.37, 850 kWh.

    Thin wrapper over `build_electric_bill_for` that supplies the
    historical April values. The resulting bytes are identical to the
    pre-Phase-5 hand-rolled output (verified by SHA256 round-trip).
    """
    build_electric_bill_for(
        path,
        statement_date="2026-04-15",
        service_period="March 15, 2026 - April 14, 2026",
        kwh=850,
        amount="142.37",
        due_date="April 30, 2026",
    )


def build_mortgage_statement(path: Path) -> None:
    c = _new_canvas(
        path,
        title="Mr. Cooper — Mortgage Statement",
        author="Mr. Cooper",
        subject="Monthly mortgage statement",
    )

    width, _ = LETTER
    left = 1 * inch
    right = width - 1 * inch
    y = 10 * inch

    c.setFont("Helvetica-Bold", 22)
    c.drawString(left, y, "Mr. Cooper")
    y -= 0.3 * inch
    c.setFont("Helvetica-Oblique", 11)
    c.drawString(left, y, "Home Loan Servicing")
    y -= 0.5 * inch

    c.setFont("Helvetica-Bold", 12)
    c.drawString(left, y, "Property")
    y -= 0.22 * inch
    c.setFont("Helvetica", 11)
    c.drawString(left, y, "123 Main St")
    y -= 0.2 * inch
    c.drawString(left, y, "Davenport, IA 52801")
    y -= 0.45 * inch

    rows = [
        ("Statement date:", "2026-04-15"),
        ("Loan number:", "LN-9912345"),
        ("Principal balance:", "$284,237.18"),
        ("Interest rate:", "3.875%"),
    ]
    c.setFont("Helvetica", 11)
    for label, value in rows:
        c.drawString(left, y, label)
        c.drawString(left + 2.5 * inch, y, value)
        y -= 0.28 * inch

    y -= 0.4 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(left, y, "Monthly payment breakdown")
    y -= 0.28 * inch
    c.setFont("Helvetica", 11)
    breakdown = [
        ("Principal & interest", "$1,840.22"),
        ("Escrow (taxes + insurance)", "$612.50"),
        ("Other", "$0.00"),
    ]
    for label, value in breakdown:
        c.drawString(left + 0.25 * inch, y, label)
        c.drawRightString(right, y, value)
        y -= 0.24 * inch

    y -= 0.1 * inch
    c.line(left + 0.25 * inch, y, right, y)
    y -= 0.28 * inch
    c.setFont("Helvetica-Bold", 13)
    c.drawString(left + 0.25 * inch, y, "Total amount due:")
    c.drawRightString(right, y, "$2,452.72")

    y -= 0.4 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(left, y, "Payment due date:    May 1, 2026")

    y -= 0.8 * inch
    c.setFont("Helvetica", 10)
    c.drawString(left, y, "Please remit payment to:")
    y -= 0.2 * inch
    c.drawString(left, y, "Mr. Cooper")
    y -= 0.2 * inch
    c.drawString(left, y, "PO Box 60516, Dallas TX 75266")

    c.showPage()
    c.save()


def build_bank_statement(path: Path) -> None:
    c = _new_canvas(
        path,
        title="First Davenport Bank — Statement",
        author="First Davenport Bank",
        subject="Monthly checking statement",
    )

    width, _ = LETTER
    left = 1 * inch
    right = width - 1 * inch
    y = 10 * inch

    c.setFont("Helvetica-Bold", 22)
    c.drawString(left, y, "First Davenport Bank")
    y -= 0.3 * inch
    c.setFont("Helvetica-Oblique", 11)
    c.drawString(left, y, "Local banking since 1924")
    y -= 0.5 * inch

    c.setFont("Helvetica-Bold", 12)
    c.drawString(left, y, "Account holder")
    y -= 0.22 * inch
    c.setFont("Helvetica", 11)
    c.drawString(left, y, "Joe Sample")
    y -= 0.2 * inch
    c.drawString(left, y, "123 Main St")
    y -= 0.2 * inch
    c.drawString(left, y, "Davenport, IA 52801")
    y -= 0.45 * inch

    rows = [
        ("Account number:", "ACCT-4521"),
        ("Statement period:", "March 16, 2026 - April 15, 2026"),
    ]
    c.setFont("Helvetica", 11)
    for label, value in rows:
        c.drawString(left, y, label)
        c.drawString(left + 2.5 * inch, y, value)
        y -= 0.28 * inch

    y -= 0.4 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(left, y, "Account activity summary")
    y -= 0.28 * inch
    c.setFont("Helvetica", 11)
    summary = [
        ("Beginning balance:", "$14,238.40"),
        ("Total deposits:", "$5,420.00"),
        ("Total withdrawals:", "$3,128.66"),
    ]
    for label, value in summary:
        c.drawString(left + 0.25 * inch, y, label)
        c.drawRightString(right, y, value)
        y -= 0.24 * inch

    y -= 0.1 * inch
    c.line(left + 0.25 * inch, y, right, y)
    y -= 0.28 * inch
    c.setFont("Helvetica-Bold", 13)
    c.drawString(left + 0.25 * inch, y, "Ending balance:")
    c.drawRightString(right, y, "$16,529.74")

    y -= 0.8 * inch
    c.setFont("Helvetica", 10)
    c.drawString(left, y, "Questions about this statement?")
    y -= 0.2 * inch
    c.drawString(left, y, "Visit your local branch on Brady Street.")

    c.showPage()
    c.save()


def build_paystub(path: Path) -> None:
    c = _new_canvas(
        path,
        title="Beacon Software — Pay Stub",
        author="Beacon Software",
        subject="Bi-weekly pay stub",
    )

    width, _ = LETTER
    left = 1 * inch
    right = width - 1 * inch
    y = 10 * inch

    c.setFont("Helvetica-Bold", 22)
    c.drawString(left, y, "Beacon Software")
    y -= 0.3 * inch
    c.setFont("Helvetica-Oblique", 11)
    c.drawString(left, y, "Earnings statement")
    y -= 0.5 * inch

    c.setFont("Helvetica-Bold", 12)
    c.drawString(left, y, "Employee")
    y -= 0.22 * inch
    c.setFont("Helvetica", 11)
    c.drawString(left, y, "Employee:        Joe Sample")
    y -= 0.2 * inch
    c.drawString(left, y, "Employee ID:     E-001")
    y -= 0.45 * inch

    rows = [
        ("Pay period:", "April 1, 2026 - April 14, 2026"),
        ("Period ending:", "2026-04-14"),
        ("Pay date:", "2026-04-17"),
    ]
    c.setFont("Helvetica", 11)
    for label, value in rows:
        c.drawString(left, y, label)
        c.drawString(left + 2 * inch, y, value)
        y -= 0.28 * inch

    y -= 0.4 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(left, y, "Earnings")
    y -= 0.28 * inch
    c.setFont("Helvetica", 11)
    earnings = [
        ("Gross pay:", "$4,615.38"),
        ("Federal income tax:", "$612.40"),
        ("State income tax:", "$184.62"),
        ("FICA + Medicare:", "$353.08"),
        ("Pre-tax deductions:", "$320.00"),
    ]
    for label, value in earnings:
        c.drawString(left + 0.25 * inch, y, label)
        c.drawRightString(right, y, value)
        y -= 0.24 * inch

    y -= 0.1 * inch
    c.line(left + 0.25 * inch, y, right, y)
    y -= 0.28 * inch
    c.setFont("Helvetica-Bold", 13)
    c.drawString(left + 0.25 * inch, y, "Net pay:")
    c.drawRightString(right, y, "$3,145.28")

    y -= 0.5 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(left, y, "Year-to-date")
    y -= 0.28 * inch
    c.setFont("Helvetica", 11)
    ytd = [
        ("YTD gross:", "$36,923.04"),
        ("YTD net:", "$25,162.24"),
    ]
    for label, value in ytd:
        c.drawString(left + 0.25 * inch, y, label)
        c.drawRightString(right, y, value)
        y -= 0.24 * inch

    c.showPage()
    c.save()


def build_all() -> None:
    build_electric_bill(ELECTRIC_OUTPUT)
    print(f"wrote {ELECTRIC_OUTPUT}")

    # Phase 5 Slice 1 — three months of Acme baseline so the existing
    # April bill ($142.37) registers as ~29% over the Jan-Mar mean
    # (~$110.07) when the anomalies compile pass runs. Amounts chosen
    # so the baseline mean lands at a clean number for the demo.
    build_electric_bill_for(
        ELECTRIC_OUTPUT_2026_01,
        statement_date="2026-01-15",
        service_period="December 15, 2025 - January 14, 2026",
        kwh=642,
        amount="108.42",
        due_date="January 31, 2026",
    )
    print(f"wrote {ELECTRIC_OUTPUT_2026_01}")
    build_electric_bill_for(
        ELECTRIC_OUTPUT_2026_02,
        statement_date="2026-02-15",
        service_period="January 15, 2026 - February 14, 2026",
        kwh=663,
        amount="112.18",
        due_date="February 28, 2026",
    )
    print(f"wrote {ELECTRIC_OUTPUT_2026_02}")
    build_electric_bill_for(
        ELECTRIC_OUTPUT_2026_03,
        statement_date="2026-03-15",
        service_period="February 15, 2026 - March 14, 2026",
        kwh=648,
        amount="109.61",
        due_date="March 31, 2026",
    )
    print(f"wrote {ELECTRIC_OUTPUT_2026_03}")

    build_mortgage_statement(MORTGAGE_OUTPUT)
    print(f"wrote {MORTGAGE_OUTPUT}")
    build_bank_statement(BANK_OUTPUT)
    print(f"wrote {BANK_OUTPUT}")
    build_paystub(PAYSTUB_OUTPUT)
    print(f"wrote {PAYSTUB_OUTPUT}")


if __name__ == "__main__":
    build_all()
