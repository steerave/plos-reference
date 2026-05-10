---
type: source
entity: account
slug: first-davenport-checking-4521
status: active
bank: First Davenport Bank
purpose: checking
account_number: ACCT-4521
account_number_last4: '4521'
owners:
- joe
locked_fields: []
---

# First Davenport Bank — Checking •••4521

**Use:** Day-to-day household checking.

## Current key facts

- **Bank:** First Davenport Bank, branch on Brady Street.
- **Account ending:** `4521`. Full account number `ACCT-4521`.
- **Owners:** Joe (sole signer).
- **Routing:** local IA bank routing — kept in `account-access.md`, not
  here.

## Notes

Fictional account used as the Phase 3 Slice 2 demo target. The worker
writes `last_statement_*` fields here when a First Davenport Bank
statement matching `account_number` is consumed; the dashboard at
`dashboards/account-balances.md` queries those fields live.
