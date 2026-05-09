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
