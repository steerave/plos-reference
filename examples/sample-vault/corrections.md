---
type: corrections
corrections: []
---

# Corrections Log

This file is the canonical override surface for entity frontmatter.
The merge contract (see `CONVENTIONS.md`) says **corrections always
win** — they outrank both fresh extractions and the freshness rule
itself.

## How to add a correction

Edit the YAML `corrections:` list in the frontmatter above. Each entry
is a mapping with three required keys and two optional ones:

```yaml
- slug: 123-main-davenport       # required — the entity folder name
  field: last_utility_bill_amount  # required — the frontmatter field to override
  value: 142.99                  # required — the corrected value
  source: 'http://localhost:8888/documents/4/'  # optional — provenance
  reason: 'OCR misread cents.'   # optional — why this correction is right
```

Then run `python -m plos.import_corrections` from the repo root.
The script will, for each entry:

1. Locate the entity's `index.md` by slug under `source/<type>/<slug>/`.
2. Set the field to `value` and append the field name to the entity's
   `locked_fields:` list — so future graduated-extractor or
   Claude-fallback merges skip it on the freshness rule.
3. Insert (or update) a row in the SQLite `corrections` audit table
   if the entity has been seen by the worker before.

The script is idempotent: running it twice produces the same vault
state. **Removing an entry from this file does not undo the
correction** — that's a Phase 5+ sync mode. v1 is append-only by
design.

## When to use this vs. `locked_fields:` directly

- **Use `locked_fields:` directly** for one-off hand-curated values
  that have no canonical source document (e.g. a person's birthdate
  in a fresh entity record). No audit trail, no script run.
- **Use `corrections.md`** when you want provenance: the
  `source` and `reason` fields stay attached to the correction, and
  the SQLite audit row records who/when. Future audit passes
  (Phase 5+) will reconcile the two.

## Examples

The list above is currently empty — there are no corrections in the
sample vault. Real entries look like:

```yaml
corrections:
  - slug: 123-main-davenport
    field: last_utility_bill_amount
    value: 142.99
    source: 'http://localhost:8888/documents/4/'
    reason: |
      OCR misread the cents column on the April Acme bill — the
      printed bill clearly says $142.99 but extraction got 142.37.
  - slug: joe
    field: birthdate
    value: '1985-03-12'
    source: hand-entered
    reason: |
      Birthdate is canonical and not in any document; locking
      against any future extraction that might guess at it.
```

Both demonstrate the two main use cases: correcting an extraction
error against a real source, and locking a hand-curated value with
no source document.
