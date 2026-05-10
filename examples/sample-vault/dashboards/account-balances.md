---
type: dashboard
dashboard: account-balances
sources_queried:
  - source/accounts
fields_read:
  - bank
  - purpose
  - owners
  - last_statement_balance
  - last_statement_end_date
  - last_statement_deposits
  - last_statement_withdrawals
  - last_statement_url
---

# Account balances

Latest known balance per financial account. Reads live from each
account's `source/accounts/<slug>/index.md` frontmatter; the worker
writes those fields whenever a bank statement matching `account_number`
is consumed.

## Latest statement per account

```dataview
TABLE WITHOUT ID
  file.link as "Account",
  bank as "Bank",
  purpose as "Purpose",
  last_statement_balance as "Ending Balance ($)",
  last_statement_deposits as "Deposits ($)",
  last_statement_withdrawals as "Withdrawals ($)",
  last_statement_end_date as "As Of",
  last_statement_url as "Source"
FROM "source/accounts"
WHERE entity = "account"
SORT last_statement_end_date DESC
```

## How to read this

- **Ending Balance ($)** is the close-of-period balance from the most
  recent statement. Multi-month deltas and cash-flow trends require
  multiple statements per account; that's a Phase 4+ dashboard.
- **As Of** is the statement period's end date.
- **Source** links back to the original PDF in Paperless. Click to
  verify any value against the source document.
- A blank row means the account has no extracted statements yet —
  hand-authored frontmatter (bank, purpose, account_number) is enough
  for the row to appear once a statement lands.
