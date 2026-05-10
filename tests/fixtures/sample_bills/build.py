#!/usr/bin/env python3
"""
Deterministically generate the sample document PDFs used by the
phase-by-phase demos and the test suite.

Run from the repo root to produce all fixtures:
    python tests/fixtures/sample_bills/build.py

Each generator below writes one PDF with reproducible bytes (no
embedded timestamps), so re-running this script during CI or refactors
does not produce diff churn.

Generated outputs:
    electric_acme_2026_04.pdf         — Phase 2: Acme Power & Light bill
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


def build_electric_bill(path: Path) -> None:
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
        ("Statement date:", "2026-04-15"),
        ("Service period:", "March 15, 2026 - April 14, 2026"),
        ("Energy used this period:", "850 kWh"),
        ("Charges this period:", "$142.37"),
    ]
    c.setFont("Helvetica", 11)
    for label, value in rows:
        c.drawString(left, y, label)
        c.drawString(left + 2.5 * inch, y, value)
        y -= 0.28 * inch

    y -= 0.4 * inch
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(right, y, "Amount due:    $142.37")
    y -= 0.3 * inch
    c.drawRightString(right, y, "Due date:      April 30, 2026")

    y -= 0.8 * inch
    c.setFont("Helvetica", 10)
    c.drawString(left, y, "Please remit payment to:")
    y -= 0.2 * inch
    c.drawString(left, y, "Acme Power & Light")
    y -= 0.2 * inch
    c.drawString(left, y, "PO Box 90210, Davenport IA 52801")

    c.showPage()
    c.save()


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
    build_mortgage_statement(MORTGAGE_OUTPUT)
    print(f"wrote {MORTGAGE_OUTPUT}")
    build_bank_statement(BANK_OUTPUT)
    print(f"wrote {BANK_OUTPUT}")
    build_paystub(PAYSTUB_OUTPUT)
    print(f"wrote {PAYSTUB_OUTPUT}")


if __name__ == "__main__":
    build_all()
