# PLOS — Architecture

**Document type:** Reference architecture
**Status:** v2.5 (current)
**Audience:** Readers of the public repo who want to understand what this system is and how it works.

---

## Changes in this revision (v2 → v2.5)

The default rule "Dataview at view-time over pre-computation" still holds, but three named exceptions are introduced where synthesis genuinely exceeds aggregation: `this-week.md`, `anomalies.md`, and `tax-prep.md`. The wiki gains a folder split (`source/`, `compiled/`, `dashboards/`) and a `CONVENTIONS.md` document. The fourth runtime component (Claude Code) now runs scheduled compile passes in addition to ad-hoc sessions, with explicit commitments around atomicity and read-your-neighbour outputs. A new section on compile and audit passes covers the new scheduled work. The phased build adjusts so Phase 2 demos a Dataview dashboard (lower-cost demo than the worker), Phase 4 introduces the first compiled artifact, and Phase 5 adds the rest. Sections not affected (data model, capture flow, merge contract, review queue, notifications) are unchanged from v2.

---

## What this is

PLOS — "Personal Life Operating System" — is a self-hosted pipeline that turns physical mail, email attachments, and digital files into a structured, searchable, interlinked knowledge base in Obsidian. It is built for a single household: one person owns it, edits it, and runs it. It is not a product, not a SaaS, not a multi-tenant system, and never tries to be.

The reference implementation in this repo demonstrates the architecture against a fictional household — two LLCs (`Acme Holdings LLC` and `Beacon Properties LLC`), three rental properties, one primary residence, two vehicles, two children — with a synthetic corpus of ~20 sample documents under `examples/sample-vault/`. The architecture itself is general; the demo data is invented.

---

## Design principles

Four principles shape every decision in this document.

**1. The vault is the source of truth.** Entity records — properties, accounts, vehicles, people, organizations — live in Obsidian YAML frontmatter, edited by hand, version-controlled in git. SQLite is a sidecar that holds document metadata, the extraction audit trail, and corrections. Opening Obsidian and editing a frontmatter value is always safe and always wins where it matters.

**2. Free local extractors handle the hot path; AI handles the long tail.** Document types that occur frequently get a small Python script ("graduated extractor") that parses them deterministically at zero cost. Document types that occur rarely or have unpredictable formats are queued for the next Claude Code session and processed in bounded batches that fit within the user's existing subscription. The same Claude Code subscription runs the scheduled compile passes that produce the three compiled artifacts. Incremental cost is zero.

**3. Subtraction over addition; named exceptions over implicit conventions.** Where two designs would work, the simpler one wins. What v1 doesn't include is explicit, not accidental — listed in the deferred section at the bottom of this document and rationalized. Where exceptions to a default exist, they are named and counted, not allowed to drift in implicitly.

**4. Demo-first.** The reference repo ships a working end-to-end slice as the first deliverable. Cloning the repo and running the quickstart produces a visible result against the fictional corpus before any layer is "complete." Capability grows by adding vertical slices, not horizontal layers.

---

## The four runtime components

At runtime, only four things are running:

1. **Paperless-ngx**, in Docker, watching a consume folder, performing OCR, archiving originals, exposing a REST API. Paperless requires a Redis sidecar (Django cache and Celery broker); a small `redis:7-alpine` container runs alongside it. Redis is a named exception to the "fewer moving parts" preference — current Paperless-ngx provides no in-process fallback. PLOS code does not talk to Redis directly; from PLOS's perspective Paperless is still one logical component.
2. **A background worker** (`worker.py`), polling SQLite every 60 seconds for new jobs, extracting fields, writing additively to vault frontmatter over SMB.
3. **Obsidian**, on the user's machine, reading the vault as plain markdown. The Dataview plugin is required for the dashboard layer; cross-entity views render as Dataview query results inside markdown files under `dashboards/`.
4. **Claude Code**, run in two modes. *Scheduled compile passes* regenerate the three compiled artifacts on their cadences: `this-week.md` daily, `anomalies.md` monthly, `tax-prep.md` weekly during tax season and monthly otherwise. *Ad-hoc sessions* are opened occasionally to drain queued documents the graduated extractors don't cover, to create entity files for unmatched correspondents, and to answer ad-hoc analytical questions against the captured data.

Everything else — schemas, templates, the indexer, the notification engine — is configuration or scheduled scripts, not always-running infrastructure.

---

## Capture channels

Three input channels feed `paperless/consume/`:

- **Scanner** — physical mail and household paperwork. Configured to scan-to-folder over SMB.
- **Drop folder** — digital files dragged in or saved from a browser to a watched directory.
- **Dedicated email address** — a forwarding address (configured via Paperless's IMAP integration or a similar inbox poller) that pulls in attachments from forwarded statements, e-bills, and similar. Paperless treats these as ordinary inputs once they land in `consume/`.

All three terminate in the same place. From the worker's perspective, a forwarded utility-bill PDF and a scanned utility bill are indistinguishable; both flow through the same extraction pipeline.

---

## Vault layout

The wiki is organized into three top-level surfaces that correspond to three different write disciplines.

**`source/` — entity records and raw documents.** One folder per entity (property, vehicle, person, account, organization, tax year, project). Each entity folder has an `index.md` carrying YAML frontmatter (structured facts) and prose narrative. Documents live in subfolders close to the entity they primarily describe — a property's mortgage statements live under `source/properties/<slug>/mortgage/`, not in a generic `mortgage/` folder. Originals are immutable; extracted text sits next to the original (`policy-2025.pdf` and `policy-2025.txt`). This layer is canonical. The worker writes only into entity-record frontmatter; entity body prose and the documents themselves are never touched by automation.

**`compiled/` — three artifacts regenerated by scheduled Claude Code passes.** `this-week.md`, `anomalies.md`, and `tax-prep.md`. Each is a plain markdown file with frontmatter declaring its refresh time, refresh cadence, and source paths read. The compile passes are the only writers; humans should treat these files as read-only output.

**`dashboards/` — Dataview query files rendered live in Obsidian.** Cross-entity views — properties snapshot, upcoming renewals, cash flow, subscriptions, vehicles, medical, investments, projects, estate gaps, account access — live here as markdown files containing Dataview query blocks. Reading the file in Obsidian renders the result against current frontmatter. Dashboards are written by hand once and rarely change.

Three top-level documents at the wiki root govern the agent's interaction with this structure. `CLAUDE.md` carries development guidance: where things live, what to edit, what not to touch, naming conventions, anti-patterns, how to extend the system. It loads automatically when Claude Code operates on the wiki. `CONVENTIONS.md` carries operating rules: the routing decision rule (Dataview default; compiled artifact as named exception), the merge resolution rule, the frontmatter contract, and the wiki layout itself. `CLAUDE.md` references `CONVENTIONS.md` for any "how does the system actually decide X" question, which keeps development guidance separate from architectural rules so they can evolve independently. `INDEX.md` at the wiki root is the answer key: it maps every recurring household question to the artifact or dashboard that answers it.

A `_review/queue.md` page lives at the wiki root for triage of documents the worker couldn't auto-process, and a `_schema/` directory holds the per-domain schema files referenced by the worker.

---

## Data model

Four SQLite tables, all sidecar to the vault.

```sql
CREATE TABLE documents (
  id INTEGER PRIMARY KEY,
  paperless_id INTEGER UNIQUE NOT NULL,
  paperless_url TEXT NOT NULL,
  content_hash TEXT,
  ocr_hash TEXT,
  title TEXT,
  document_date DATE,            -- the date printed on the document itself
  data_effective_date DATE,      -- when applicable: when the document's data takes effect
  correspondent TEXT,
  document_type TEXT,
  sensitivity TEXT DEFAULT 'public',
  status TEXT DEFAULT 'new',     -- new | processing | done | pending_claude | needs_review
  review_reason TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE entities (
  id INTEGER PRIMARY KEY,
  type TEXT NOT NULL,            -- property | person | vehicle | organization | account
  domain TEXT NOT NULL,          -- finance | properties | vehicles | health | family
  slug TEXT UNIQUE NOT NULL,
  wiki_path TEXT NOT NULL,
  aliases TEXT,                  -- JSON array of normalized name variants
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE extracted_fields (
  id INTEGER PRIMARY KEY,
  document_id INTEGER REFERENCES documents(id),
  entity_id INTEGER NOT NULL REFERENCES entities(id),
  field_name TEXT NOT NULL,
  field_value TEXT,
  confidence REAL DEFAULT 0.85,
  handler TEXT,                  -- 'graduated:utility_bill' | 'claude'
  source_document_date DATE,
  extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE corrections (
  id INTEGER PRIMARY KEY,
  entity_id INTEGER REFERENCES entities(id),
  field_name TEXT,
  correct_value TEXT,
  source_document_id INTEGER,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

What is **not** here, and why:

- **No `vault_index` mirror table.** Vault frontmatter is parsed on-demand for cross-domain queries. At this corpus scale (low thousands of documents, low hundreds of entities), parsing is measured in milliseconds.
- **No `entity_links` table.** Relationships live in frontmatter as wikilinks; queries that need the relationship graph read frontmatter directly.
- **No separate `entity_aliases` table.** Aliases live in the `aliases` JSON column on `entities`. Lookup uses a generated normalized-text index column.
- **No separate `jobs` table.** Job state is a `status` enum on `documents`. There is no jobs lifecycle independent of a document.
- **No `graduated_types` registry.** Files in `extractors/graduated/` *are* the registry. The runtime discovers them by directory listing.

Each of these omissions is a deliberate choice; each was considered as a separate table during design and rejected for not earning its complexity at this scale.

---

## The capture and extraction flow

A document arrives in `paperless/consume/` from one of the three capture channels. Paperless OCRs it and assigns a `paperless_id`. A post-consume hook inserts one row in `documents` with `status='new'` and exits in under 100 ms.

The worker, on its next 60-second poll, picks up the document and runs through the pipeline:

1. **OCR check.** Empty OCR text or under 20 characters → mark `needs_review` with reason `unreadable` and stop.
2. **Duplicate check.** Matching `content_hash` or `ocr_hash` against an existing document → mark `needs_review` with reason `exact_duplicate` or `suspected_duplicate`.
3. **Sensitivity classification.** Based on `document_type`, set `sensitivity` and the markdown raw-text mode (`full` / `summary` / `metadata_only`).
4. **Correspondent resolution.** Look up the document's correspondent against the normalized `aliases` index on `entities`. No match → mark `needs_review` with reason `unmatched_entity` and stop. The worker never autonomously creates entity files; entity creation always happens through a Claude Code session with human review.
5. **Extraction dispatch.** If a graduated extractor exists for this document type, run it and produce `extracted_fields` rows. Otherwise, set `status='pending_claude'` for the next Claude Code session.
6. **Frontmatter merge.** For each extracted field, apply the resolution rule (next section) and write to the entity page's frontmatter over SMB. Body content is never touched.
7. **Review queue render.** If any document's `needs_review` state changed, re-render `_review/queue.md` in the vault.

Cross-entity views — a property's mortgage balance, a household's total insurance premium, a vehicle's last service date — are rendered by Dataview at view-time from `dashboards/`, querying frontmatter directly. The worker never writes to entity bodies, never writes to compiled artifacts, and never writes to dashboards. There is no AUTO-section machinery to maintain, no integrity check on HTML markers, no cascade rendering across the entity graph.

---

## The merge contract

Multiple documents will produce values for the same entity field at different times. Without a deterministic resolution rule, ingestion order silently determines truth — a known failure mode in which a January statement processed after an April statement leaves the vault holding January's value.

The rule, applied before any frontmatter write:

1. **Corrections always win.** A `corrections` row for the entity+field beats every other source.
2. **Locked fields are bypassed.** If the field appears in the entity's `locked_fields:` frontmatter list, the existing value is preserved. The worker still records the new extraction in `extracted_fields` for the audit trail.
3. **Otherwise, freshness wins.** Rank candidates by `COALESCE(data_effective_date, document_date)`. A future effective date beats a current document date — a May insurance renewal letter for July coverage outranks an April declaration page for the same policy.
4. **Tie-break** by `confidence`, then by `extracted_at`.

Every extraction is recorded in `extracted_fields` regardless of whether it changed the frontmatter. The vault holds the resolved current value; SQLite holds the full history.

This makes ingestion order-independent. Scanning a January statement after an April statement cannot regress the vault.

Two override mechanisms protect hand edits:

- **`locked_fields:` frontmatter list** — lightweight, per-entity. Add a field name; the worker bypasses it on every merge regardless of freshness. Use when you want to protect a hand-curated value without recording a specific override.
- **`corrections.md`** — vault-wide override file with provenance. Edit `corrections.md`, run `import_corrections.py`, future merges treat the correction as authoritative. Use when you want to record a specific corrected value that should win against future extractions.

Hand-edits to frontmatter that are NOT in `locked_fields:` and NOT recorded in `corrections.md` may be overwritten by a fresher extraction. This convention is the user's part of the contract.

---

## The review queue and the notification layer

Two surfaces handle anomalies and routine reporting.

**`_review/queue.md`** is a real-time vault page auto-rendered by the worker on every `needs_review` state change. Items are grouped by reason: `unmatched_entity`, `exact_duplicate`, `suspected_duplicate`, `unreadable`, `low_confidence`, `failed`. Each row links to the source document in Paperless. For unmatched entities, the row includes a *"to instantiate, run this in Claude Code: …"* prompt so triage converts cleanly into entity creation.

The vault indexer (`indexer.py`, every 10 minutes) self-cleans the queue: when a vault entity now exists matching the proposed name of an `unmatched_entity` job, the indexer marks the job resolved and the queue page drops the item on its next render. No manual "mark as resolved" step.

**The weekly digest** (`notifications.py`, Sunday morning, Gmail SMTP) covers the rest:

- **Recent activity** — what was processed this week, segmented by `owning_entity` so each LLC's reporting slice stays clean for tax and legal purposes.
- **Deadlines** — date-typed fields whose threshold has been crossed (insurance renewal, registration expiry, tax due dates).
- **Anomalies** — two heuristics. *Percentage deviation:* alert if a recurring numeric field deviates more than 20% from its 3-month rolling average. *Expectation gap:* alert if a recurring monthly statement hasn't arrived by the 20th of the month it was expected. Naive value-diff alerts are intentionally not implemented; they are noise for fields that legitimately change every cycle.
- **Review queue summary** — counts by reason with a link to `_review/queue.md`. No per-item detail in the email.

The vault page is the working surface for triage; the email is a periodic accountability nudge. The same anomaly heuristics that drive the Sunday digest also feed the monthly `compiled/anomalies.md` artifact described in the next section, so the analysis lives in two surfaces — email for accountability, vault file for inspection and to feed downstream compile passes.

---

## Query interface

Three surfaces serve different question shapes.

**Dataview dashboards (default).** For any question that reduces to a cross-entity view, aggregation, filter, or sort — *"current insurance premium per property,"* *"vehicles due for service,"* *"loan balances by lender,"* *"renewals in the next 60 days"* — a markdown file under `dashboards/` holds the Dataview query and Obsidian renders the result at view-time. Dashboards refresh automatically the moment the underlying frontmatter changes, cost nothing to run, and are version-controlled markdown like the rest of the wiki. Ten dashboards cover the recurring-question inventory documented in `PLOS-Recurring-Questions.md`.

**Compiled artifacts (named exceptions).** Three questions require synthesis beyond aggregation, so each gets a compiled artifact regenerated by a scheduled Claude Code pass:

- `compiled/this-week.md` — priority reasoning across domains, regenerated daily. Dataview can list everything with a date in the next seven days; it cannot rank those items by what genuinely warrants attention or fold in flags from the anomalies output.
- `compiled/anomalies.md` — pattern detection over recent transactions and statement arrival cadence, regenerated monthly after month close. Computes percentage deviation against rolling averages and detects expectation gaps — work that sits outside Dataview's aggregation primitives.
- `compiled/tax-prep.md` — checklist-vs-received gap surfacing against the year's expected-documents list, regenerated weekly during tax season and monthly otherwise. Reasons about what's still missing and why, not just what's present.

Each artifact is a markdown file with frontmatter declaring its refresh time, refresh cadence, and source paths read.

The decision rule for adding a fourth compiled artifact is explicit and documented in the wiki's `CONVENTIONS.md`: the question must require priority reasoning, pattern detection, or checklist-vs-received gap surfacing AND require capability Dataview cannot provide. When in doubt, start as Dataview — promoting a dashboard to a compiled artifact later is additive; the reverse is more work.

**Ad-hoc analytical queries — Claude Code.** For one-off, exploratory, or unexpected questions — *"compare cleaning expenses across properties year-over-year,"* *"which mortgage has the highest current rate,"* *"how much did we spend on the silver van last quarter, broken down by category"* — the v1 query interface is a Claude Code session against the repo. Same client used for compile passes, long-tail extraction, and entity creation. Same cost model. The mechanics:

- Claude Code has filesystem access to the vault and can run SQLite queries against the sidecar database via bash.
- `CLAUDE.md` at the wiki root primes the session on the schema, the resolution rule, the entity types, and the conventions for sourcing answers; `CONVENTIONS.md` is loaded on demand for architectural questions.
- A small `scripts/query_helpers.py` exposes common patterns (current value of field X for entity Y, time-series of field X for entity type Z, cross-entity aggregates) so the LLM doesn't have to reconstruct them every session.
- Answers are presented with their source documents linked back to Paperless, so the user can verify any number against its origin.

The substrate — vault-canonical frontmatter plus compiled artifacts plus SQLite extraction history — is fundamentally queryable by any LLM with filesystem and SQL access. The interface layer is replaceable; the substrate is not. **Future query interfaces** are deliberately deferred: a `plos ask "..."` CLI wrapper that launches a focused Claude Code session, an MCP server pattern that exposes the vault and SQLite as tools to any MCP-compatible client, an Obsidian plugin that puts a query box inside the daily browse surface. Each is a thin addition over the same substrate. Phase 6+.

---

## Compile and audit passes

Two classes of scheduled work run inside the existing Claude Code subscription.

**Compile passes** regenerate the three compiled artifacts on their cadences. Each pass takes a defined set of source paths as input, writes a single markdown file as output, and declares both in the artifact's frontmatter. Three commitments hold for every compile pass.

*Scheduled, not on-demand.* A daily cron-style trigger drives `this-week.md`. Monthly month-close drives `anomalies.md`. Weekly or monthly drives `tax-prep.md` depending on the calendar. On-demand regeneration is supported but is not the operating model; the operating model is "the file is fresh when you read it because the schedule kept it fresh."

*Atomic writes.* Each pass writes to a temporary file and renames into place. A reader opening a compiled artifact during a regeneration sees the previous version or the new version, never a half-written file.

*Allowed to read each other's outputs.* `this-week.md` reads `anomalies.md` to surface flagged items as part of the week's watching list. This creates a small dependency graph among compiled artifacts that the schedule needs to respect: monthly anomalies regenerate first (early in the month-close window), then daily this-week passes pick up the latest anomalies output on each subsequent run. The dependency graph is small enough to express directly in the schedule rather than through any orchestration layer.

**Audit passes** check that compiled artifacts are honest about their sources. Each artifact's frontmatter `sources_read:` field declares the paths the compile pass was given. An audit pass walks the artifact's content, extracts every `→ /source/...` reference, and confirms each is present under `sources_read:`. Claims that reference paths not declared in `sources_read:` are flagged. This catches two failure modes: drift between the prompt's source set and the artifact's actual claims, and synthesis that smuggles in conclusions without provenance.

Audit passes run on a separate schedule (weekly is sufficient) and produce a small report under `_review/` if any drift is found. They are intentionally cheap — read-only, no network, no LLM call required — so they can run unattended.

---

## Phased build

The build ships a working end-to-end slice first, then expands. Each phase is purely additive; no phase requires undoing earlier work.

| Phase | Slice | Demo |
|---|---|---|
| 1 | Substrate: Paperless + SQLite + post-consume hook + worker skeleton | Scan one document, see it in Paperless, see the row in SQLite, see the worker log it. |
| 2 | One document type end-to-end + first Dataview dashboard | Drop a fictional `Acme Power & Light` bill in `consume/`, watch the property's `last_utility_bill_amount` update in the vault, then open `dashboards/properties.md` and see the dashboard render the new value live. The dashboard is the demo surface — visibly end-to-end at a fraction of the worker's eventual scope. |
| 3 | Three more document types: mortgage statements, bank statements, pay stubs | Each new type validates the architecture without changing it. Demo expands; dashboard rows multiply. Frontmatter conventions consolidate in `CONVENTIONS.md` as new fields land. |
| 4 | First compiled artifact + Claude Code session workflow | Schedule `this-week.md` to regenerate daily, reading from frontmatter and from `dashboards/` outputs. The same session pattern (`generate_manifest.py`, bounded sessions, `corrections.md` import) drains the `pending_claude` queue and answers ad-hoc analytical questions. The compiled artifact joins the demo: open `this-week.md`, read what needs attention, click through to sources. |
| 5 | Remaining compiled artifacts + notifications + audit passes | Add `anomalies.md` (monthly) and `tax-prep.md` (weekly during tax season). Stand up the indexer, the weekly digest, and the audit-pass schedule. Receive a Sunday digest with deadlines and anomalies, segmented by owning entity; receive an audit-pass report if any compiled artifact drifts from its declared sources. |
| 6+ | Beyond-finance domains; deferred features (CLI query wrapper, MCP server, Obsidian plugin) | Add `_schema/health/`, `_schema/family/`, etc. as configuration, not architecture. |

The MVP marker is end of Phase 5. Total ~5 weeks of mostly passive clock time on the working system. Reprocessing of any backlog runs overnight inside the existing Claude Code subscription at zero incremental cost.

---

## What is not in v1

Explicitly deferred so the reader doesn't read these as gaps:

- **Generated `schema.yaml`** — v1 hand-writes ~200 lines of YAML. A markdown-driven generator with dry-run safety classification is interesting future work; it is not load-bearing for the daily use case.
- **AUTO-section rendering into entity bodies.** Compiled artifacts and Dataview dashboards live in their own folders; entity bodies remain untouched by automation. The class of bugs AUTO-section markers introduced (accidental editing, cascade firing on the wrong parent) cannot recur in this layout.
- **Cascade-on-update across the entity graph.** Dataview queries are always fresh at view-time; compiled artifacts regenerate on schedule and are allowed to read each other's outputs. Neither needs cascading.
- **A separate `vault_index` table.** Frontmatter is parsed on-demand.
- **Full alias management** — auto-merge, fuzzy candidates, merge history. v1 has the alias index for lookup; manual edits to the `aliases:` list are how new aliases get added.
- **A fourth compiled artifact.** Three is the v1 set, named in `CONVENTIONS.md`. Adding a fourth requires explicit justification under the decision rule (priority reasoning, pattern detection, or checklist-vs-received gap surfacing) AND a capability Dataview can't provide.
- **Streamlined query interfaces** — `plos ask` CLI, MCP server, Obsidian plugin. v1 ships with three surfaces (Dataview dashboards, scheduled compiled artifacts, Claude Code sessions); the interface layer evolves additively over the same substrate.
- **Push notifications, calendar integration, mobile apps, plugin layer beyond Dataview.** Each can come later as a thin addition; none change the architecture.
- **Per-field resolution strategies.** The default rule handles the vast majority of cases. Build per-field overrides only when a specific field demonstrably misbehaves.
- **Sophisticated entity merge tooling, fuzzy duplicate detection beyond hashes, historical compaction, per-handler confidence calibration.**

Each of these was considered during design. Each is omitted because the simpler alternative covers the use case at this scale.

---

## Success criteria

The architecture works if:

1. Scanning or forwarding a fictional utility bill produces a frontmatter update on the corresponding property page within one worker poll cycle, with a Paperless link to the source PDF; the corresponding Dataview dashboard renders the new value when next opened.
2. Manually editing the body of an entity page never has its content disturbed by automation. Compiled artifacts and dashboards live in separate folders and are never written into entity bodies.
3. Adding a new document type requires writing one extractor file and one schema entry — no changes to the worker, the indexer, or the database.
4. Adding a new domain requires writing schema entries — no changes to the runtime.
5. The Sunday digest contains real signal (deadlines, anomalies) and nothing else; the same anomaly output is captured in `compiled/anomalies.md` for in-vault review and feeds the daily `this-week.md` pass.
6. Reading `compiled/this-week.md` on a Monday morning produces a usable priority list with sourced items, without further work.
7. Asking a non-trivial natural-language question against the demo corpus through the Claude Code query interface produces a correct, sourced answer.
8. An audit pass run against the compiled artifacts finds no claims with missing source provenance.
