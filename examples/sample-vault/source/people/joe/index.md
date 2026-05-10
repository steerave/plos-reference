---
type: source
entity: person
slug: joe
status: active
legal_name: Joe Sample
birthdate: '1985-03-12'
drivers_license_expiry: '2026-05-15'
employer_current: Beacon Software
locked_fields: []
---

# Joe Sample

Fictional household member used by the Phase 3 Slice 3 demo. Owner of
the demo property (`[[123-main-davenport]]`) and signer on the demo
checking account (`[[first-davenport-checking-4521]]`).

## Current key facts

- **Employer:** Beacon Software (fictional). Pay stubs land here when a
  Beacon Software stub matching `legal_name` + `employer_current` is
  consumed.
- **Birthdate:** 1985-03-12 — placeholder so later phases have a date
  field to aggregate against.

## Notes

The real `people/<name>/` shape carries far more — identity, medical,
account-access, employment history. Phase 3 keeps it tight: enough
frontmatter to route a pay stub onto this record. Phase 4+ will fill
in the rest as new compile passes need it.
