# CLAUDE.md

Repo-level guidance for Claude Code. This is the public reference repo for PLOS — `plos-reference`. The actual operating instance and the real household vault are separate private repos and not present here.

## What this repo is

A self-hosted document pipeline that turns physical mail, email attachments, and digital files into a structured Obsidian-based knowledge base for a single household. Reference architecture, demonstration code, and a fictional sample vault. Not a product. Not multi-tenant.

## Read these first

Before doing any planning or implementation work, read in order:

1. `BRIEF.md` — what this is and why it exists
2. `ARCHITECTURE.md` — the v2.5 reference architecture (the source of truth for the design)
3. `EVOLUTION.md` — how the architecture got to its current shape (v1 → v2 → v2.5)

After those, as needed:

4. `examples/sample-vault/CONVENTIONS.md` — operating rules for the vault (routing, merge, frontmatter)
5. `examples/sample-vault/INDEX.md` — the answer key
6. `docs/source-layer-shapes.md` — entity-folder shapes
7. `docs/artifact-templates.md` — what compiled artifacts and dashboards look like at end-state
8. `docs/recurring-questions.md` — the question inventory the artifact set serves

## Design principles (carried forward from ARCHITECTURE)

These are non-negotiable and should guide every implementation decision:

1. **The vault is the source of truth.** Entity records live in Obsidian YAML frontmatter. SQLite is a sidecar.
2. **Free local extractors handle the hot path; AI handles the long tail.** Zero incremental cost.
3. **Subtraction over addition; named exceptions over implicit conventions.** When two designs would work, the simpler one wins. Exceptions are counted, not allowed to drift in.
4. **Demo-first.** Every phase ships a visible end-to-end slice.

## Routing rule (carried forward from CONVENTIONS)

> **Default:** Dataview at view-time for any cross-entity view, aggregation, filter, or sort.
> **Exception:** Compiled artifact only when the answer requires synthesis beyond aggregation — priority reasoning, anomaly detection from patterns, or gap-surfacing against an expected-document checklist.

The v1 set is exactly three compiled artifacts: `this-week.md`, `anomalies.md`, `tax-prep.md`. Adding a fourth requires explicit justification under the rule.

## Repo state

This repo is at the start of implementation. The three reference docs at the root are complete. The supporting reference docs in `docs/` are complete. The sample vault has its top-level governance documents (`INDEX.md`, `CONVENTIONS.md`) and the directory structure for `source/`, `compiled/`, `dashboards/`, but no populated entities yet — that lands incrementally during Phases 2–5.

The Python codebase (`src/`, `scripts/`, `tests/`) is stubbed. Nothing in it is implemented.

## Phasing

Per `ARCHITECTURE.md`:

- **Phase 1** — Substrate: Paperless + SQLite + post-consume hook + worker skeleton.
- **Phase 2** — One document type end-to-end + first Dataview dashboard. **Demo: utility bill → frontmatter update → dashboard renders the new value.**
- **Phase 3** — Three more document types: mortgage, bank statements, pay stubs.
- **Phase 4** — First compiled artifact (`this-week.md`) + Claude Code session workflow.
- **Phase 5** — Remaining compiled artifacts (`anomalies.md`, `tax-prep.md`), notifications, audit passes. **MVP marker.**
- **Phase 6+** — Beyond-finance domains; deferred features (CLI query wrapper, MCP server, Obsidian plugin).

## What is deliberately not in v1

Read the "What is not in v1" section of `ARCHITECTURE.md` before suggesting any of: AUTO-section rendering into entity bodies, cascade-on-update across the entity graph, a `vault_index` mirror table, full alias management, a fourth compiled artifact, push notifications, or per-field merge resolution strategies. Each was considered and deliberately deferred.

## Workflow expectations

- Plan before building. Use planning mode to propose a phase or vertical slice; review the plan before implementing.
- Subtract first. If a feature could be deferred without breaking the demo for the current phase, defer it.
- Atomic writes for any file the system regenerates. Compiled artifacts especially — write to a temp file and rename.
- Source provenance inline. Every compiled-artifact claim cites the source path it came from.
- Tests land alongside code, not in a later phase.

## Cost model

Anthropic's Claude Code subscription is the only AI dependency. It does triple duty: long-tail extraction, scheduled compile passes, and ad-hoc query interface. No additional API spend; no cloud hosting; no SaaS dependencies.

## Questions to ask early in planning

- Which phase is this work for?
- What's the smallest end-to-end slice that demonstrates this phase's value?
- What's deferred from this phase, and is the deferral noted somewhere?
- What's the demo at the end of this phase?

## Phase 2 conventions (decided during the electric-bill build)

The following decisions were made during Phase 2 implementation. Future
phases that extend this surface should follow them unless there's a
specific reason to deviate.

### Graduated-extractor interface

Every extractor under `src/plos/extractors/graduated/` is a module with
a top-level `extract` function:

```python
def extract(text: str, document: DocumentMeta) -> dict[str, Any] | None
```

- Returns `None` when the extractor doesn't recognize the document.
- Returns `None` when the provider header matches but the body is too
  malformed to yield the minimum viable field set — better to bail than
  to write a half-extracted record.
- `DocumentMeta` (defined in `extractors/registry.py`) carries
  `paperless_id`, `paperless_url`, `document_date`, and `correspondent`.
  Frozen dataclass — extractors can't mutate it back.
- The registry is a plain module-level list (`EXTRACTORS`) at the bottom
  of `registry.py`. Adding a new extractor is one import + one tuple
  entry. No auto-discovery, no plugin metaclass, no import-time side
  effects in the extractor modules themselves. This keeps test
  isolation free.

### Vault writer merge rules (apply in order, per field)

`vault.merge_frontmatter(path, updates, source_doc_date)` applies these
rules per field, in this order:

1. Skip if the field name appears in the target's `locked_fields:` list.
2. Skip every field if the existing `data_effective_date >= source_doc_date`
   (freshness rule — newer existing state wins, including same-day equal).
3. Otherwise apply, then bump `data_effective_date` to `source_doc_date`.

Returns the dict of fields that actually changed; empty dict means no
file write happened. Atomic write via temp + fsync + `os.replace()` is
non-negotiable here — a partial write to `index.md` corrupts YAML and
breaks every Dataview dashboard.

### Worker document-status taxonomy

The worker writes one of these to `documents.status` per row:

- `done` — graduated extractor matched, entity routed, vault written.
- `pending_claude` — no graduated extractor recognized the document; it
  sits for a future Claude Code session.
- `needs_review` — extractor matched but no entity was routable.
  `review_reason` is set to `no_account_in_extraction` (the bill
  matched but no account number could be parsed) or `unmatched_entity`
  (account parsed but no property in the vault claims it).
- `new` (unchanged) — left alone on a transient processing failure
  (Paperless 5xx, network error). Next poll cycle retries.

### Audit trail

The worker inserts one row into `extracted_fields` per field per
extraction, even when the vault freshness rule means no actual update
landed. This preserves the full extraction history for trend queries
and debugging — the vault holds the resolved current value, SQLite
holds every claim ever made.

### Sample data convention

Phase 2's sample property is `123-main-davenport`. Phase 2's sample
bill correspondent is `Acme Power & Light` (account `ACCT-12345`,
$142.37, 850 kWh). Both are fictional and live in the public reference
repo. Real-household entities and bills go in the separate private
operating-instance repo and never land here.
