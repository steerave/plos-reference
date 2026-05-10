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

## Phase 3 conventions (decided during the mortgage/bank/paystub build)

Phase 3 added three more graduated extractors and crossed three new
entity-type boundaries (property→property again via a new key, then
account, then person). The core architectural decisions:

### Each extractor module exports both `extract` and `route`

Phase 2's `EXTRACTORS` registry held `(handler_name, extract_fn)`
tuples and the worker hardcoded `entities.find_property_by_electric_account`
as the only way to route. Phase 3 generalises:

```python
def extract(text: str, document: DocumentMeta) -> dict[str, Any] | None
def route(fields: dict[str, Any], vault_root: Path) -> RouteResult
```

`EXTRACTORS` is now a list of `(handler_name, module)` tuples; adding
a new extractor is still one import + one tuple entry, the only widening
is that the module must expose `route` alongside `extract`. The worker
calls `module.route(...)` — no per-doc-type branches in the worker.

### `RouteResult(path, missing_key)` distinguishes two failure modes

`route` returns a small `NamedTuple` with two fields. The worker
dispatches:

- `RouteResult(Path(...), False)` — entity matched; merge + done.
- `RouteResult(None,    True)`    — extractor recognised the document
  but the routing key wasn't extractable (e.g. an Acme bill OCR'd
  without a parseable account number). Worker writes `needs_review`
  with reason `no_routing_key_in_extraction`.
- `RouteResult(None,    False)`   — routing key extracted, but no
  entity in the vault claims it. Worker writes `needs_review` with
  reason `unmatched_entity`.

The Phase 2 `no_account_in_extraction` review reason was generalised
to `no_routing_key_in_extraction` so the registry can hold extractors
keyed off any field, not just `electric_account`.

### Composite routing keys

Bank statements route to accounts via a single field (`account_number`).
Pay stubs require a *pair* — `legal_name` + `employer_current` — because
neither alone is unique in a household. The pattern is the same: the
extractor's `extract` returns both fields, and the extractor's `route`
checks both before delegating to the entity matcher
(`entities.find_person_by_employer_and_name`). No registry change
needed; composite keys are just a property of the extractor's `route`
implementation.

### Worker derives entity type + domain from the matched path

The worker upserts each matched entity into SQLite's `entities` table
with a `(type, domain)` pair. To stay generic, it derives both from
the matched index.md path via a small dict:

```python
_ENTITY_TYPE_FROM_DIR = {
    "properties":    ("property",     "properties"),
    "accounts":      ("account",      "finance"),
    "people":        ("person",       "family"),
    "vehicles":      ("vehicle",      "vehicles"),
    "organizations": ("organization", "organizations"),
}
```

Adding a new entity type is one entry here plus one extractor whose
`route` returns a path under the matching `source/<dir>/`. No worker
logic change.

### Worker refreshes `documents.document_date` from the Paperless API

Paperless's date-detection runs asynchronously after consume. The
post-consume hook inserts the row with `document_date = NULL`, so the
worker would silently fall back to `date.today()` and the merge
contract's freshness rule was meaningless for any field updated more
than once per calendar day. Phase 3 fixed this: the worker now calls
`paperless.get_document(id)` once per pass (one round trip for both
`content` and `created_date`), and writes the API's date back to
SQLite when present. `paperless.get_document_text(id)` still exists
for callers that only need the body, but the worker doesn't use it.

### Sample data conventions

Phase 3 fictional providers (all kept in the public reference repo):

- **Mr. Cooper** mortgage statements, loan number `LN-9912345`,
  principal balance $284,237.18, total amount due $2,452.72.
  Routes to the existing property `123-main-davenport`.
- **First Davenport Bank** checking statements, account `ACCT-4521`,
  ending balance $16,529.74. Routes to the new account
  `first-davenport-checking-4521`.
- **Beacon Software** pay stubs for *Joe Sample*, gross $4,615.38,
  net $3,145.28, YTD gross $36,923.04. Routes to the new person
  `joe`.

The sample-bill builder at `tests/fixtures/sample_bills/build.py`
emits all four PDFs (Phase 2 + Phase 3) deterministically — reportlab
is invoked with `invariant=1` so re-running the script produces
byte-identical PDFs and `git diff` stays quiet between regenerations.

### Deferrals (still deferred at end of Phase 3)

Out of scope for Phase 3 by design; flagged here so future-Claude
doesn't read them as gaps:

- **Sensitivity classification.** Pay stubs are treated like any other
  document; the `documents.sensitivity` field stays at the default
  `'public'`. Phase 4+ work.
- **Multi-statement aggregation dashboards.** `account-balances.md`
  shows the latest only. A "cash-flow over N months" dashboard
  requires a backlog of statements per account; Phase 3 ships one
  per account.
- **`tests/fixtures/sample_bills/` rename.** The folder name is now
  misleading (it holds mortgage statements, bank statements, and pay
  stubs alongside the original electric bill). Defer to a Phase 4
  housekeeping commit.
- **`_review/queue.md` rendering.** Phase 5 work; Phase 3's
  `needs_review` rows live in SQLite only.
- **Schema files in `_schema/`.** Still empty. Frontmatter conventions
  for new fields land in entity records and are referenced in
  `CONVENTIONS.md` if they need governance. Phase 4+ may stand up
  `_schema/` formally.

## Phase 4 conventions (decided during the this-week.md compile pass)

Phase 4 introduced compile passes — the first place in PLOS where
Claude Code is invoked to write back into the vault. Slice 1 lands the
first compiled artifact, `compiled/this-week.md`. Decisions captured
here so future phases can extend the pattern.

### Compile passes shell out to the `claude` CLI

Per `ARCHITECTURE.md` the same Claude Code subscription does triple
duty: scheduled compile passes, ad-hoc analytical sessions, long-tail
extraction. Phase 4 Slice 1 makes that concrete: a Python script
(`src/plos/compile_this_week.py`) builds a manifest and runs:

```python
subprocess.run(
    ["claude", "--print"],
    input=prompt,
    capture_output=True,
    text=True,
    check=True,
)
```

No second SDK dependency, no Anthropic API keys juggled separately —
the user's existing Claude Code authentication carries the call.
`--print` is the non-interactive flag. Future compile passes
(`anomalies.md`, `tax-prep.md`) follow the same shape.

### Manifest shape

The manifest is a single markdown blob the prompt template includes
verbatim. For `this-week`, it bundles:

- Today's date (UTC, ISO format).
- Every `source/*/*/index.md` (full file content, frontmatter + body).
- Every `dashboards/*.md` (full file).
- The previous `compiled/this-week.md` if present (for delta context).

Each piece is wrapped in a `## /vault/path/file.md` heading and a
fenced `markdown` block, so Claude can reason over paths and content
together. At sample-vault scale the entire manifest fits comfortably
in a single Claude Code session; if a real-world manifest gets
unwieldy, the natural next step is per-domain manifests, not a
streaming pipeline.

### Format-validation gate

Compile passes must never corrupt the artifact even if the AI
misbehaves. Every compile pass is wrapped in:

1. Run subprocess with `check=True` — non-zero exit raises
   `CalledProcessError` and no write happens.
2. Validate the response shape — the artifact must start with the
   YAML frontmatter delimiter (`---`) and contain every required
   section heading. If validation fails, the run raises and the
   existing file (if any) is preserved.
3. Atomic write — temp file + fsync + `os.replace`, the same
   discipline as `vault.merge_frontmatter`. A reader opening the
   artifact during regeneration sees the previous version or the new
   version, never a half-written file.

For `this-week.md` the required section headings are `## Must do`,
`## Should do`, `## Watching`. (`## Birthdays / dates this week` is
omitted by Claude when there's nothing in the window, so it's not in
the required set.)

### Source provenance is non-negotiable

Per ARCHITECTURE.md design principle: "Source provenance inline.
Every compiled-artifact claim cites the source path it came from."
The compile-pass prompt instructs Claude to emit `→ /source/...`
arrows under every bullet, and the artifact's `sources_read:`
frontmatter list must enumerate every cited path. This is the
contract that makes Phase 5+ audit passes possible — those compare
the `sources_read:` declared list against the `→ /source/...` arrows
present in the body, and flag any drift.

### Sample vault demo seeding

Phase 4 Slice 1 added two fictional deadline fields so the compile
pass has cross-domain content to surface against:

- `insurance_renewal_date: '2026-05-22'` on `123-main-davenport`
- `drivers_license_expiry: '2026-05-15'` on `joe`

Both fall inside a 14-day "this week" lookahead from the demo's
`currentDate` (2026-05-11). Future deadline fields land in entity
frontmatter directly without a schema entry; CONVENTIONS.md's
"naming is the contract" rule covers it for now. Phase 5+ may stand
up `_schema/` formally.

### Out of scope at end of Phase 4 Slice 1

- **Compile-pass scheduling.** v1 is manual `python -m
  plos.compile_this_week`. Wiring up Windows Task Scheduler or a
  Claude Code remote agent is a deployment detail that fits Phase 5.
- **`pending_claude` drain workflow.** Architecturally paired with
  the compile pass under "the same session pattern." Phase 4b.
- **`corrections.md` + `import_corrections.py`.** Vault-wide override
  file with provenance. Phase 4c.
- **Audit pass against `sources_read:`.** Phase 5+.
- **The other two compiled artifacts** (`anomalies.md`, `tax-prep.md`).
  Phase 5.
