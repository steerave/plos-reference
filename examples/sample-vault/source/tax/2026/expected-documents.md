---
type: tax-expected
tax_year: 2026
expected:
  - name: W-2 from Beacon Software
    source: employer
    received: false
    notes: arrives mid-January; chase HR if absent by Jan 31
  - name: 1098 mortgage interest from Mr. Cooper
    source: mortgage servicer
    received: true
    received_date: 2026-01-28
    received_path: source/tax/2026/received/1098_mr_cooper.md
  - name: 1099-INT from First Davenport Bank
    source: bank
    received: false
    notes: arrives end of January; bank usually mails late
  - name: Property tax statement (123 Main St)
    source: Scott County Treasurer (IA)
    received: true
    received_date: 2026-04-15
    received_path: source/tax/2026/received/property_tax_2026.md
  - name: Charitable contribution receipts
    source: various
    received: false
    notes: compile from year-end statements before April
---

# Expected tax documents — 2026

This file is the source of truth for which tax documents the
household expects this tax year. Edit the `expected:` list above to
add entries; flip `received: true` and fill in `received_date` and
`received_path` when each one arrives.

The monthly compile pass at `python -m plos.compile_tax_prep` reads
this file and regenerates `compiled/tax-prep.md` with the
received/missing split and a status line.

## Notes for this year

Sample-vault demo inventory. The two received items have placeholder
stubs at `source/tax/2026/received/`; the three missing items are
flagged so the compile pass surfaces them in the artifact's
**Missing** section.
