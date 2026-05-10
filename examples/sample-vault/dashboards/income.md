---
type: dashboard
dashboard: income
sources_queried:
  - source/people
fields_read:
  - legal_name
  - employer_current
  - last_paystub_gross
  - last_paystub_net
  - last_paystub_ytd_gross
  - last_paystub_period_end
  - last_paystub_url
---

# Income

Latest pay stub per household member. Reads live from each person's
`source/people/<slug>/index.md` frontmatter; the worker writes those
fields whenever a pay stub matching `legal_name` + `employer_current`
is consumed.

## Latest pay stub per person

```dataview
TABLE WITHOUT ID
  file.link as "Person",
  legal_name as "Name",
  employer_current as "Employer",
  last_paystub_gross as "Gross ($)",
  last_paystub_net as "Net ($)",
  last_paystub_ytd_gross as "YTD Gross ($)",
  last_paystub_period_end as "As Of",
  last_paystub_url as "Source"
FROM "source/people"
WHERE entity = "person"
SORT last_paystub_period_end DESC
```

## How to read this

- **Gross ($)** and **Net ($)** are this period's amounts — bi-weekly
  for most employers. **YTD Gross ($)** is the running year-to-date
  gross. The freshness rule on YTD is interesting: every new pay stub
  monotonically advances it, so a January stub processed after April
  cannot regress this column.
- **As Of** is the pay period's end date.
- **Source** links back to the original PDF in Paperless. Click to
  verify any value against the source document.
- A blank row means no pay stub has been processed for that person
  yet — the row appears once a stub matching their `legal_name` and
  `employer_current` lands.
