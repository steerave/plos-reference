---
type: source
entity: property
slug: 123-main-davenport
status: active
address: 123 Main St, Davenport, IA 52801
purchased: 2018-06-15
purpose: primary-residence
owners:
  - joe
mortgage_servicer_current: Mr. Cooper
insurance_carrier_current: State Farm
hoa: false
electric_account: ACCT-12345
electric_provider: Acme Power & Light
locked_fields: []
---

# 123 Main St, Davenport, IA

**Use:** Primary residence.

## Current key facts

- **Mortgage:** Mr. Cooper, balance ~$284k, monthly P&I $1,840
  → mortgage/current-statement.txt
- **Property tax:** $4,200/yr, escrowed in mortgage
  → tax/2025-statement.txt
- **Insurance:** State Farm SF-XYZ-001, renews Sept 12
  → insurance/current-policy.txt
- **HOA:** None.
- **Electric:** Acme Power & Light, account `ACCT-12345`
  → utilities/electric/current-statement.txt

## History

- 2018-06: Purchased.
- 2026-02: Mortgage transferred PennyMac → Mr. Cooper.
  → mortgage/servicer-history.md

## Documents

Subfolders: `mortgage/`, `insurance/`, `tax/`, `utilities/`.

## Notes

Fictional property used as the Phase 2 demo target. The worker writes
`last_utility_bill_*` fields here when an electric bill matching
`electric_account` is consumed; the dashboard at
`dashboards/properties.md` queries those fields live.
