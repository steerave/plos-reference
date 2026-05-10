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

The sample-document builder at `tests/fixtures/sample_documents/build.py`
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
- **`corrections.md` + `import_corrections.py`.** Vault-wide override
  file with provenance. Phase 4c.
- **Audit pass against `sources_read:`.** Phase 5+.
- **The other two compiled artifacts** (`anomalies.md`, `tax-prep.md`).
  Phase 5.

## Phase 4b conventions (decided during the pending_claude drain build)

Phase 4b adds the second use of the Claude Code CLI: long-tail
extraction. Same shell-out pattern as the compile pass, different
input/output contract.

### One Claude call per pending document

`drain_pending_claude.process_one(conn, row, vault_root)` shells out
to `claude --print` per document, builds a per-doc prompt
(preamble + entity manifest + OCR text + JSON-shape instruction),
and parses Claude's response into a `ClaudeResult` dataclass. Cost
is bounded by the number of pending docs — typically a handful at
a time. No batching for v1 (each doc gets its own session, which
also keeps the failure blast radius small).

### Structured JSON contract

Claude returns a JSON object with shape:

```
{
  "doc_type": "<short snake_case label>",
  "route_status": "matched" | "unmatched_entity" | "unrecognized",
  "entity_type": "property" | "account" | "person" | ... | null,
  "entity_slug": "<slug or null>",
  "fields": { "<field>": <value>, ... },
  "rationale": "<one-sentence explanation>",
  "proposed_entity": { ... }   // only when unmatched_entity
}
```

The parser tolerates `\`\`\`json ... \`\`\`` code-fence wrapping
because Claude often emits JSON that way despite the prompt asking
for plain JSON. Anything else — non-JSON, top-level non-object,
unknown `route_status` — raises `ValueError` and the script marks
the doc `needs_review` with reason `claude_invalid_response`.

### handler = 'claude'

`extracted_fields.handler` for Claude-extracted matches is the
literal string `'claude'`, distinct from the four `graduated:*`
handlers. The schema's example enum already named this; Phase 4b
makes it real.

### Unmatched proposals live in review_reason as JSON

`extracted_fields.entity_id` is `NOT NULL` in the schema, so audit
rows can't land for documents that didn't match an existing entity.
Phase 4b's pragmatic workaround: JSON-encode Claude's full proposal
(rationale + extracted fields + proposed entity skeleton) into the
`documents.review_reason` TEXT column. The shape is:

```json
{
  "reason": "claude_unmatched_entity",
  "doc_type": "...",
  "rationale": "...",
  "fields": { ... },
  "proposed_entity": { ... }
}
```

A Phase 5+ review-queue renderer will consume this. Other
review_reason values stay short single-token strings
(`claude_unrecognized`, `claude_invalid_response`,
`claude_matched_without_slug`, `empty_ocr_text`); only the
unmatched-entity branch carries JSON.

### Drain never auto-creates entities

ARCHITECTURE.md is clear: "the worker never autonomously creates
entity files; entity creation always happens through a Claude Code
session with human review." Phase 4b's drain *is* a Claude Code
session — but the script still doesn't auto-create. Claude
*proposes* a new entity (the `proposed_entity` block); a human
later applies the proposal. Phase 5+ stands up the formal
apply-from-queue surface.

### Subprocess failure leaves status untouched for retry

Per the worker's pattern: any `subprocess.CalledProcessError` (or
other exception in `process_one`) rolls back the open transaction
and leaves `documents.status='pending_claude'`. The next drain
run retries it. Counts are reported as
`{'done': N, 'needs_review': M, 'errored': K}` at the end of the
run, so transient failures stay visible in stdout.

### Out of scope at end of Phase 4b

- **Auto-applying `proposed_entity` blocks.** A human inspects the
  review_reason JSON and decides. Phase 5+ tooling.
- **`_review/queue.md` rendering.** Reading SQLite for queued
  proposals and rendering them as a vault page is Phase 5+.
- **Schema migration to allow `extracted_fields.entity_id IS NULL`.**
  Would let unmatched audit rows land properly, but requires SQLite
  table-rebuild migration on existing databases. Defer until the
  audit-pass story (Phase 5) makes it load-bearing.

## Phase 4c conventions (decided during the corrections workflow build)

Phase 4c lands the override surface called out in
`examples/sample-vault/CONVENTIONS.md` under the merge contract's
first rule: "Corrections always win." Two new pieces of code, one new
vault file:

### `corrections.md` is YAML-frontmatter-only

The file at `<vault_root>/corrections.md` carries the override list
in its YAML frontmatter under a `corrections:` key:

```yaml
---
type: corrections
corrections:
  - slug: 123-main-davenport
    field: last_utility_bill_amount
    value: 142.99
    source: 'http://localhost:8888/documents/4/'
    reason: 'OCR misread the cents column.'
---
```

The body of the file is prose for humans (when to use this vs.
`locked_fields:` directly, format docs, examples). `slug`, `field`,
and `value` are required per entry; `source` and `reason` are
optional but encouraged for the audit trail.

### `vault.apply_correction` is the only function that bypasses the freshness rule

`merge_frontmatter` honors the freshness rule from CONVENTIONS.md:
existing `data_effective_date >= source_doc_date` skips every field.
That rule is what makes ingestion order-independent for extracted
documents.

`apply_correction(path, field_name, value)` is the deliberate
exception. It:

1. Sets the field to the corrected value unconditionally.
2. Appends the field name to the entity's `locked_fields:` list (if
   not already there).
3. Atomically writes via temp+fsync+os.replace.

It does *not* touch `data_effective_date`. Corrections are orthogonal
to freshness — they're a separate axis of authority. Future merges
honor the correction because the field is now in `locked_fields:`,
not because of any date comparison.

### Corrections piggyback on `locked_fields:`

Phase 4c chose not to introduce a new "corrected" status alongside
`locked_fields`. The reason: `vault.merge_frontmatter` already skips
locked fields, and re-implementing the same skip logic via a SQLite
lookup would mean every merge call needs a database connection.
Subtraction wins — corrections set `locked_fields:` and the merge
contract works unchanged.

The trade-off: the entity frontmatter no longer distinguishes
"user-locked because they hand-curated this" from "locked because a
correction was imported." Both look like a `locked_fields:` entry. A
Phase 5+ audit pass can reconcile by cross-referencing the SQLite
`corrections` table — every `corrections` row's `field_name` should
appear in the corresponding entity's `locked_fields:`, and any
`locked_fields:` entry without a `corrections` row is a hand-lock.

### `import_corrections` is append-only in v1

Removing an entry from `corrections.md` does NOT undo the correction.
The entity's `locked_fields:` and the SQLite `corrections` row both
persist. To undo, the user manually edits both surfaces. Phase 5+ may
add a sync mode where `corrections.md` is the source of truth.

The reason for append-only-first: a sync mode would need to compare
"what's in the file now" with "what's in SQLite + the entity files"
and remove the diff. That's a larger semantic step (delete-and-
unlock-and-restore-data-effective-date) and worth taking only when
the audit-pass story gives it a clear shape.

### Audit row shape

`corrections` table per the schema:

```
INTEGER id, INTEGER entity_id (FK), TEXT field_name,
TEXT correct_value, INTEGER source_document_id, TIMESTAMP created_at
```

`source_document_id` stays NULL in v1 — the `source:` field in
corrections.md is a free-text URL/note, not a Paperless document ID.
A Phase 5+ enhancement could parse Paperless URLs out of `source:` and
back-fill the FK.

If the entity has not yet been seen by the worker (no `entities`
table row), the import script applies the frontmatter correction and
SKIPS the audit row — `corrections.entity_id` is FK-constrained.
That's logged at INFO level. A subsequent worker run that creates
the entity will not back-fill the audit; for now the absence of an
audit row when frontmatter has the lock is itself the signal that
the correction predates any worker activity.

### Out of scope at end of Phase 4c

- **Sync mode.** Remove-an-entry behaviour. Phase 5+.
- **Cross-correction conflict detection.** Two entries for the same
  entity+field apply in file order; no warning. Phase 5+ if it
  becomes a problem.
- **Schema enhancement: `corrections.source_document_url TEXT`.**
  Would let the audit row capture the free-text source from
  corrections.md without piggybacking on the FK column. Phase 5+.
- **Back-filling audit rows when the entity is later created by the
  worker.** Phase 5+ if needed.

## Phase 5 Slice 1 conventions (decided during the anomalies compile pass)

Phase 5 Slice 1 lands `compiled/anomalies.md`, the second compiled
artifact and the first to use a *pre-computed manifest* (vs Phase 4's
"hand Claude the raw vault and let it reason"). Decisions captured here
so subsequent anomalies slices and the other Phase 5 compile passes
extend the pattern.

### Statistics in Python, prose in Claude

The percentage-deviation math is pure arithmetic over the
`extracted_fields` audit trail (rolling mean, delta-vs-baseline) and
runs entirely in `compile_anomalies.compute_deviations`. The result is
a list of `Deviation` records; Claude's job is to render each as a
human-readable bullet under the `## Spending deviations` heading. This
split:

- Keeps detection deterministic — re-running with the same data
  produces the same set of flagged anomalies; only the prose around
  them varies.
- Keeps the cost bounded — Claude is invoked at most once per compile
  pass, with a pre-aggregated list, not the full audit history.
- Makes the contract auditable — the deviation list is testable in
  isolation against synthetic SQLite rows; the prompt is responsible
  only for rendering, not analysis.

Slices 2 and 3 (expectation gaps + unexpected charges) follow the same
pattern: detect in Python, render in Claude.

### `ELIGIBLE_FIELDS` allowlist as the policy surface

`compile_anomalies.ELIGIBLE_FIELDS` is the policy register for which
recurring numeric fields participate in deviation analysis. Slice 1
ships with six entries (utility amount, mortgage amount, paystub
gross/net, statement deposits/withdrawals). Three deliberate
exclusions are documented inline:

- `last_paystub_ytd_gross` — monotone across the year, deviation is
  meaningless.
- `last_statement_balance` — drifts with deposits/withdrawals; the
  baseline isn't a stable comparison.
- `last_utility_bill_kwh` — consumption, not money. A
  kWh-vs-cost-decomposition heuristic is a Slice 2+ concern.

Adding a new recurring-amount field to extractor output should be
followed by one of: (a) add it to `ELIGIBLE_FIELDS`, (b) explicitly
document why it doesn't qualify (excluded comment in the allowlist),
(c) accept that it won't trip anomalies until step (a). No silent
opt-in.

### Named thresholds, not magic numbers

`MIN_HISTORY = 3` (priors needed before any deviation can fire) and
`DEVIATION_THRESHOLD_PCT = 20.0` are module-level constants. The
20% threshold is straight from ARCHITECTURE.md; the 3-prior baseline
is the smallest sample that produces a defensible mean. Both are
overridable per `compute_deviations(..., min_history=..., threshold_pct=...)`
for testing, but the default constants are the operating policy.

### Empty-deviation short-circuit

If `compute_deviations` returns an empty list, `run()` writes a
deterministic "no deviations this window" artifact *without invoking
Claude*. Two reasons:

- Determinism. An empty result is a contractually flat fact, not a
  synthesis task. Re-running on the same data produces byte-stable
  output (modulo the `refreshed:` timestamp).
- Cost. No reason to spend a subprocess + Claude tokens on rendering
  "there's nothing here."

The artifact still carries the full frontmatter contract (`type:
compiled`, `artifact: anomalies`, `refresh_cadence: monthly`,
`compile_pass_version: 1`, `sources_read: []`) and the
`## Spending deviations` heading, so downstream readers (audit pass,
notifications digest) see the same shape whether the artifact was
machine-rendered or short-circuited.

### Most-recent-record windowing in v1

Slice 1 takes "the most recent row per `(entity, field)`" as the
current value and the three rows immediately before as the baseline.
There's no calendar-month framing — a current row from April 30
compared against priors from Jan 31 / Feb 28 / Mar 31 just works.
This is the simplest defensible windowing.

When Slice 2 (expectation-gaps) lands, it needs calendar windows by
design ("statement didn't arrive by the 20th of *the month it was
due*"). At that point both heuristics will promote to a single
calendar-month framing across the artifact. Until then, slicing on
record position is cleaner than slicing on dates.

### Sample data convention

Phase 5 Slice 1's demo data lives in
`tests/fixtures/sample_documents/`: four Acme Power & Light bills
(Jan/Feb/Mar/Apr 2026). Amounts are `$108.42 / $112.18 / $109.61 /
$142.37` — the Jan-Mar mean is `$110.07` and the April value is
+29.34% (the 0.34 over the 29% mark is what makes the test
`test_compute_deviations_flags_29_percent_over_baseline` pin to
~29.34, not exactly 29).

`build_electric_bill_for(path, *, statement_date, service_period,
kwh, amount, due_date)` is the parameterized builder; the old
`build_electric_bill(path)` is now a thin wrapper that supplies the
April values. The April PDF is byte-identical to its pre-Phase-5
output (verified by SHA256).

### Out of scope at end of Phase 5 Slice 1

- **Expectation-gaps section** (statement didn't arrive by the 20th).
  Requires per-entity expected-cadence frontmatter and a calendar-
  windowed view. Slice 2.
- **Unexpected-charges section.** Requires transaction-level
  ingestion and a subscription registry. Slice 3+.
- **Categorical aggregation** ("Dining out +49%"). Out of v1.
- **Calendar-month windowing** ("Window: April 1 – April 30" framing
  in the artifact body). Tied to Slice 2's expectation-gap math.
- **Audit pass** — comparing `sources_read:` frontmatter against the
  `→ /source/...` arrows in the body. Still deferred; sensible to
  land after `tax-prep.md` so it covers the full three-artifact set.
- **Compile-pass scheduling** (Windows Task Scheduler / Claude Code
  remote agent). Still manual. Separate Phase 5 plumbing slice.
- **`notifications.py` weekly digest** + **`indexer.py` review-queue
  self-clean.** Separate Phase 5 slices.

## Phase 5 Slice 2 conventions (decided during the expectation-gaps build)

Slice 2 adds the second heuristic to `compiled/anomalies.md`:
expectation gaps. Same compile pass, same `run()` shell, same prompt-
preamble + manifest contract — one new pre-compute function
(`compute_expectation_gaps`), one new section
(`## Expectation gaps`), one new env var (`PLOS_ANOMALIES_AS_OF`).
Decisions captured here so Slice 3 (unexpected charges) and later
artifacts extend the pattern.

### Implicit cadence from history

Any `(entity, field)` pair in `EXPECTATION_FIELDS` with at least one
historical row in `extracted_fields` is treated as "expected at
monthly cadence." There is no per-entity `expected_statements:`
frontmatter contract in Slice 2 — subtraction-first. Trade-offs:

- **Pro:** Zero new contract surface. Whatever the worker has been
  ingesting becomes the gap-detection scope automatically. New
  extractors plug in for free.
- **Con:** Can't distinguish a one-off doc (a paid-off mortgage's
  final statement) from an ongoing series. A future slice can add an
  opt-out frontmatter (`not_expected: [field, ...]`) if real-world
  data demands it; the operating instance is the right driver for
  that decision.

The three Slice 2 entries in `EXPECTATION_FIELDS` —
`last_utility_bill_amount`, `last_mortgage_statement_amount`,
`last_statement_balance` — each represent one monthly-statement
document type. They are NOT the same as `ELIGIBLE_FIELDS`
(deviation analysis): one statement emits multiple deposit /
withdrawal / balance fields, so flagging all of them as gaps would
multi-count one missing document. Using `last_statement_balance` as
the bank-statement-arrival signal (vs. the deposits/withdrawals
which feed deviations) keeps the gap surface clean.

### Currently-due month + GRACE_DAY

`_currently_due_month(as_of)` returns the first day of the calendar
month whose `GRACE_DAY` (20th) has most recently passed:

- `as_of=2026-05-21` → due month = May 2026 (May 20 has passed).
- `as_of=2026-05-19` → due month = April 2026 (still in grace for May).

A gap exists when no row in `extracted_fields` for the `(entity,
field)` pair has `source_document_date` inside the due month.
`days_overdue` is `(as_of - GRACE_DAY-of-due-month).days` — a fresh
gap reads as `1 day(s) overdue`; a stale one reads in tens of days.

Single-month focus in Slice 2: only the currently-due month is
flagged. Earlier missed months that were once current but never
arrived are not re-flagged here. The audit-pass story (later Phase 5)
is the right place to accumulate "you've been missing this for
N months" history if it becomes load-bearing.

### `PLOS_ANOMALIES_AS_OF` env var

Defaults to today's UTC date. Override with a `YYYY-MM-DD` string for
demos and tests. Malformed values raise on `_resolve_as_of()` rather
than silently fall back — a typo'd override should fail loud.

The `as_of` parameter is plumbed through `run(..., as_of=...)` and
`build_manifest(..., as_of=...)` and `_empty_anomalies_artifact(as_of=
...)` so test code can pin the date without monkey-patching `datetime`.

### Combined short-circuit

`run()` invokes Claude only when at least one of `deviations` or
`gaps` is non-empty. Both empty → write the deterministic
`_empty_anomalies_artifact(as_of=...)` (frontmatter + both section
headings + placeholder bullets in each). The shape mirrors what
Claude would emit, so downstream readers (audit pass,
`notifications.py`) see one stable contract regardless of how the
artifact was produced.

### Prompt contract: render, do not detect

The preamble explicitly instructs Claude: "You are NOT detecting
anomalies — the lists below are authoritative." Both pre-computed
lists are in the manifest; Claude renders one bullet per list item
and adds an empty-state placeholder bullet for any empty section.
This is the same statistics-in-Python / prose-in-Claude split from
Slice 1, just doubled.

### Test seed convention

`_seed_monthly_field` in `tests/test_compile_anomalies.py` is the
generalised version of Slice 1's `_seed_monthly_utility_history` —
it takes `entity_type` / `domain` / `subdir` / `field_name` and
inserts one row per `(date, value)` tuple. Use it for gap-detection
tests across property / account / person entity types without
duplicating boilerplate. Each call uses a slug+field-hashed
`paperless_id_base` to avoid UNIQUE-constraint collisions when
seeding two pairs in the same test.

### Out of scope at end of Phase 5 Slice 2

- **Per-entity expected-cadence frontmatter.** Implicit cadence is
  fine for v1; explicit override is Slice 2+ if real-world data
  demands it.
- **Biweekly / weekly / quarterly cadences.** Paystubs (biweekly)
  don't participate in `EXPECTATION_FIELDS`. A future slice could
  add a `CADENCE_FOR_FIELD` map if needed; for now monthly is the
  only supported rhythm.
- **Multi-month gap accumulation.** Only the currently-due month is
  flagged. Earlier-month gaps fall off after their pass.
- **Unexpected-charges section.** Requires transaction-level data
  and a subscription registry. Slice 3+.
- **Audit pass.** Still deferred to after `tax-prep.md`.
- **Compile-pass scheduling, notifications, indexer.** Separate
  Phase 5 slices.

## Phase 5 Slice 3 conventions (decided during the tax-prep build)

Phase 5 Slice 3 lands `compiled/tax-prep.md`, the third and final
compiled artifact in the v1 set. With this slice the three-artifact
trilogy — `this-week.md`, `anomalies.md`, `tax-prep.md` — is
complete, and the audit-pass story (compare `sources_read:` against
body `→ /source/...` arrows) is finally ready to land.

The compile pass mirrors the `compile_anomalies.py` shape: top-
level constants, a pure-Python `compute_*` function, a
`build_manifest` that pre-aggregates structured input for Claude,
a Claude-rendered body with a validation gate, atomic write,
and an empty-state short-circuit.

### Per-year inventory file is the source of truth

`source/tax/<year>/expected-documents.md` carries a YAML
frontmatter `expected:` list. Each entry is a dict with:

- `name: str` — human-readable label (required)
- `source: str` — optional context (employer / bank / county / etc.)
- `received: bool` — partitioning signal (default false)
- `received_date: date | str` — optional, YAML-date or ISO string;
  normalised to ISO string by `compute_tax_prep`
- `received_path: str` — optional, vault-relative path; used as
  the provenance arrow target on the received bullet
- `notes: str` — optional, surfaced to Claude for prose framing

Entries with `received: true` partition into the `received` list;
everything else lands in `missing`. Non-dict entries in the list
are silently skipped — invalid inventory rows don't crash the
compile pass.

This file is the single edit surface. No SQLite mirror, no
secondary registry. The user flips `received: true` and fills in
`received_date` + `received_path` when each document arrives;
the next compile pass surfaces the new state.

### Tax-year resolution

`_default_tax_year(as_of)` follows the US individual filing
calendar:

- `as_of.month <= 4` → previous calendar year (Jan-Apr is the
  filing window for the prior year)
- `as_of.month >= 5` → current calendar year (collection window)

Override with `PLOS_TAX_YEAR=YYYY`. Malformed values raise on
`int()` cast — a typo'd override should fail loud rather than
silently default to today's year.

### Two required sections only

Slice 1 of tax-prep ships `## Received` + `## Missing`. The
template at `docs/artifact-templates.md` also documents
`## For the accountant` (running totals across the vault) and
`## Outstanding actions` (chase list). Both are deferred:

- **For the accountant** requires cross-table joins on
  `extracted_fields` (charitable totals, rental income/expenses,
  estimated-tax payments). Worth landing when real tax-prep
  workflow drives the requirement.
- **Outstanding actions** is Claude synthesis on top of Claude
  synthesis — the missing list already implies the chase. Adding
  it would be writing the same information twice.

REQUIRED_SECTIONS is `("## Received", "## Missing")`. Later
slices add headings without breaking the existing validation
gate.

### Stub files for received_path provenance

The sample vault includes two stub files under
`source/tax/2026/received/` (`1098_mr_cooper.md`,
`property_tax_2026.md`) so the demo artifact's `→ /source/...`
arrows resolve to real files. They carry a
`type: tax-received-stub` frontmatter and a brief note that
they're placeholders. The operating instance would store actual
PDFs (or `.url` pointers back to Paperless) at these paths.

### Inventory-missing short-circuit

When `source/tax/<year>/expected-documents.md` doesn't exist
for the resolved tax year, `run` writes a deterministic
"no inventory configured for <year>" artifact without invoking
Claude. The shape mirrors what Claude would render given an
empty inventory: full frontmatter, both section headings,
placeholder bullets in each.

This is the right behaviour for new tax years before the user
seeds the inventory file — instead of failing, the artifact
self-documents what's missing.

### Out of scope at end of Phase 5 Slice 3

- **`## For the accountant` section.** Aggregated running totals
  from `extracted_fields`. Defer until real tax-prep workflow
  drives the requirement.
- **`## Outstanding actions` section.** Redundant with the
  Missing list. Defer.
- **File-presence-based received detection.** v1 trusts the
  inventory's `received: bool`. A cross-check pass could glob
  `received/` and warn when a `received: true` entry's
  `received_path` doesn't resolve.
- **Per-document Paperless linkage.** No `paperless_url:` field
  per entry yet. A future slice can add it once real-tax-doc
  ingestion is in play.
- **Multi-year aggregation** (year-over-year deltas, prior-year
  references). Phase 6+.
- **Audit pass.** Now unblocked — all three v1 artifacts ship.
  Next slice.
