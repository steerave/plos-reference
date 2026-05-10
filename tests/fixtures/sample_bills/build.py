#!/usr/bin/env python3
"""
Deterministically generate the Phase 2 sample electric-bill PDF.

Run from the repo root:
    python tests/fixtures/sample_bills/build.py

Produces tests/fixtures/sample_bills/electric_acme_2026_04.pdf — a
fictional Acme Power & Light bill the test suite and demo both consume.
The output bytes are reproducible (no embedded timestamps), so re-running
this script during CI or refactors does not produce diff churn.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

OUTPUT = Path(__file__).resolve().parent / "electric_acme_2026_04.pdf"


def build_bill(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.setTitle("Acme Power & Light — Statement")
    c.setAuthor("Acme Power & Light")
    c.setSubject("Monthly electric statement")
    c.setCreator("plos-reference fixture builder")
    c.setProducer("plos-reference fixture builder")

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


if __name__ == "__main__":
    build_bill(OUTPUT)
    print(f"wrote {OUTPUT}")
