---
type: dashboard
dashboard: properties
sources_queried:
  - source/properties
fields_read:
  - address
  - electric_provider
  - last_utility_bill_amount
  - last_utility_bill_date
  - last_utility_bill_kwh
  - last_utility_bill_url
  - mortgage_servicer_current
  - last_mortgage_statement_amount
  - last_mortgage_statement_principal_balance
  - last_mortgage_statement_date
  - last_mortgage_statement_url
---

# Properties

Per-property snapshot. Each row's frontmatter is written by the worker
when a matching document (utility bill, mortgage statement) is consumed
and routed to that property.

## Latest electric bill per property

```dataview
TABLE WITHOUT ID
  file.link as "Property",
  address as "Address",
  electric_provider as "Provider",
  last_utility_bill_amount as "Last Bill ($)",
  last_utility_bill_kwh as "kWh",
  last_utility_bill_date as "As Of",
  last_utility_bill_url as "Source"
FROM "source/properties"
WHERE entity = "property"
SORT last_utility_bill_date DESC
```

## Latest mortgage statement per property

```dataview
TABLE WITHOUT ID
  file.link as "Property",
  mortgage_servicer_current as "Servicer",
  last_mortgage_statement_amount as "Total Due ($)",
  last_mortgage_statement_principal_balance as "Principal Balance ($)",
  last_mortgage_statement_date as "As Of",
  last_mortgage_statement_url as "Source"
FROM "source/properties"
WHERE entity = "property" AND mortgage_loan_number
SORT last_mortgage_statement_date DESC
```

## How to read this

- **Last Bill ($)** is the amount due on the most recent extracted
  electric bill. **Total Due ($)** is the total amount due on the most
  recent mortgage statement (P&I + escrow). Older readings live in the
  SQLite sidecar's `extracted_fields` table for trend queries (Phase 4+).
- **As Of** is the document's reference date — bill due date for the
  electric row, statement date for the mortgage row.
- **Source** links back to the original PDF in Paperless. Click to
  verify any value against the source document.
- The mortgage table excludes properties that have no `mortgage_loan_number`
  (rentals owned outright, etc.) so the row is empty rather than blank.
- A blank cell means the field was never extracted — either the
  property has no relevant account configured, or the relevant document
  hasn't been ingested yet.
