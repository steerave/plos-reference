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
---

# Properties

Most-recent electric bill per property. Reads live from each property's
`source/properties/<slug>/index.md` frontmatter; the worker writes those
fields whenever a new utility bill is consumed and matched to the
property.

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

## How to read this

- **Last Bill ($)** is the amount due on the most recent extracted
  electric bill. Older readings are not held in frontmatter — they
  live in the SQLite sidecar's `extracted_fields` table for trend
  queries (Phase 3+).
- **As Of** is the bill's due date. If a property has no row, no
  bill has been processed for it yet.
- **Source** links back to the original PDF in Paperless. Click to
  verify any value against the source document.
- A blank cell means the field was never extracted — either the
  property has no electric account configured, or the relevant bill
  hasn't been ingested yet.
