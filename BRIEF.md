# PLOS — Brief

**Document type:** Project brief
**Status:** v2.5 (current)
**Audience:** First-time readers landing on this repo. The shortest path to "what is this and why does it exist."

---

## Changes in this revision (v2 → v2.5)

The brief absorbs the artifact-routing decisions from the foundation docs. The "Anytime — browse" and "Anytime — ask" sections now describe two answer surfaces: Dataview dashboards as the default for cross-entity views, and a small set of compiled artifacts as named exceptions for cases where synthesis goes beyond aggregation. Nothing else materially changes; the system's purpose, constraints, and success criteria are unchanged from v2.

---

## What this is

PLOS — "Personal Life Operating System" — is a self-hosted document pipeline that turns physical mail, email attachments, and digital files into a structured, searchable, interlinked knowledge base in Obsidian. Documents get scanned, dropped, or emailed in. They get OCR'd, classified, and routed. Their data lands as YAML frontmatter on entity pages — properties, accounts, vehicles, people, organizations. The user browses, queries, and asks natural-language questions; cross-entity views render via Dataview dashboards, a small set of compiled artifacts handle cases where synthesis goes beyond aggregation, and ad-hoc analytical queries run through an LLM with access to the captured data.

It is built for a single household. One person owns it, edits it, and runs it. It is not a product, not a SaaS, not a multi-tenant system, and never tries to be.

---

## Why this exists

Two purposes, stated honestly so the rest of the repo can be evaluated against them.

**1. A working personal system.** PLOS is built for households whose paper trails have outgrown manual organization — the kind that accumulate streams of statements, bills, notices, and records across multiple properties, accounts, family members, and business entities. Past a certain scale, manual ingestion stops working: values drift between intake passes, data goes stale on the pages where it should be current, and adding a new domain means more manual work rather than less. PLOS exists so that scanning a piece of mail is enough — the relevant entity pages update with current values, anomalies and deadlines surface in a weekly digest, and ad-hoc questions about the household get sourced answers without manual SQL.

**2. A portfolio reference for AI-collaborative work.** This public repo demonstrates how a complex personal infrastructure project can be designed and built collaboratively with AI. The methodology, decision evolution, architecture, and code are intended to be readable as a worked example. The actual operating instance contains real household data and is private; this repo contains a fictional sample household under `examples/sample-vault/` that demonstrates the system end-to-end.

These two purposes shape every constraint and trade-off below. They are also, deliberately, the only purposes — there is no "and someday this could be a product" agenda underneath.

---

## Who runs it

A single owner. No team, no contributors, no commercial users. Other household members are read consumers via Obsidian on their own devices. The system is sized for household scale: thousands of documents over a lifetime, not millions; tens of entities, not thousands. Decisions that would only matter at larger scale (sharding, role-based access, audit compliance, multi-tenancy) are explicitly out of scope.

---

## The experience target

**Daily — capture.** Scan something, walk away. Or forward a statement from your inbox to your dedicated capture address. Or drop a file into a watched folder. The document is OCR'd, archived, and the relevant entity pages get their fresh values within one worker poll cycle. No CLI required, no per-document attention.

**Weekly — review.** A Sunday-morning email digest covers what came in, what deadlines are approaching, and what looks anomalous. Triage of unusual items happens in a vault page (`_review/queue.md`), not buried in email.

**Anytime — browse.** Obsidian is the search and browse surface. Click from a property to its mortgage to the lender to the latest statement PDF. Cross-entity views render in two places. Most live as Dataview dashboards under `dashboards/` — total insurance premium, household loan obligations, vehicles needing service, upcoming renewals — queried at view-time so they are always current. A small number live as compiled artifacts under `compiled/`, regenerated on a schedule by Claude Code when the answer requires synthesis beyond aggregation: what to do this week, what looks anomalous this month, what tax documents are still missing. The split is governed by an explicit decision rule documented in the wiki's `CONVENTIONS.md`.

**Anytime — ask.** Three compiled artifacts answer the highest-leverage cross-cutting questions on a schedule: `this-week.md` (priority reasoning across domains, refreshed daily), `anomalies.md` (pattern detection over recent transactions, refreshed monthly), and `tax-prep.md` (gap surfacing against the year's expected-document list). For ad-hoc analytical questions beyond what the dashboards and compiled artifacts cover — *"compare cleaning expenses across properties year-over-year,"* *"which mortgage has the highest current rate,"* *"how much did we spend on the silver van last quarter, and on what"* — a natural-language query interface answers from the same captured data, sourced. For v1 this happens through Claude Code sessions; future versions may wrap this in a CLI (`plos ask "..."`) or an MCP-based query client.

**On the go — read.** Mobile read access via vault sync. Many household lookups happen away from a desk — on the road, at appointments, mid-conversation — and the value of the system depends on its accessibility at those moments.

---

## Constraints

**Privacy is structural.** The reference repo (this one) is fully sanitized from commit one — fictional household, fictional addresses, fictional account fragments. The actual operating instance is private and stays private. The two are different repos by design, not by accident.

**Cost is zero incremental.** No new subscriptions. The existing Claude Code subscription does triple duty: it handles the long-tail extraction (document types not covered by the local extractors), runs the scheduled compile passes that regenerate the three compiled artifacts, *and* serves as the v1 query client for natural-language questions. Frequent document types use free local Python scripts. No API credits, no cloud hosting, no SaaS dependencies.

To be specific about the cost model: PLOS does require an active Claude Code subscription to be used at full capability. "Zero incremental" means no new spend beyond what the household is already paying for. A household that wants to use PLOS without an AI subscription would get the capture and Dataview dashboard layers but not the long-tail extraction, the compiled artifacts, or the natural-language query interface.

**Stack is local-first and open-source-first.** Windows-native dev and runtime. Paperless-ngx for OCR and archive, SQLite for the control plane, Python (stdlib-first) for everything else, Obsidian for the user-facing knowledge layer.

**Time is part-time.** Build phases assume a few hours per week of evening and weekend work, not full-time. The MVP target is ~5 weeks of clock time at that pace, with most heavy lifting (reprocessing, bounded Claude Code sessions) happening overnight.

**Scope is bounded.** Single household. No commercial path. Capabilities stop where the household use case stops.

---

## What success looks like

For the working system:

1. Scanning or forwarding a routine document produces a frontmatter update on the corresponding entity within one worker poll cycle, with a link back to the source PDF.
2. Manually editing the body of an entity page is always safe — automation never touches it. Compiled artifacts and dashboards live in their own folders and are never written into entity bodies.
3. Adding a new document type requires writing one extractor file and one schema entry. Adding a new domain requires writing schema entries — no runtime changes.
4. The Sunday digest contains real signal: deadlines and anomalies that would otherwise have been missed. Naive "value changed" noise is absent by design.
5. A non-trivial natural-language question (*"compare cleaning expenses across properties year-over-year"*) produces a sourced, correct answer without manual SQL or Dataview construction.
6. Reading `compiled/this-week.md` on a Monday morning produces a usable priority list without further work.
7. Other household members can find what they need in Obsidian without asking the owner.

For the reference repo:

1. A reader landing on the README understands what this is, why it exists, and what bar to hold the rest of the repo to within 90 seconds.
2. Cloning the repo and running the quickstart produces a visible result against the fictional sample vault within minutes.
3. The methodology and evolution documents are interesting enough to read end-to-end on their own merits.
4. The code holds up to inspection — clean, modular, defensively written, well-tested. No "AI slop" tells.
5. The repo demonstrates judgment, not just elaboration. What was deliberately *not* built is as visible as what was built.

---

## What this is NOT

Listed explicitly so a reader doesn't read these as gaps:

- Not a SaaS, not multi-tenant, not a hosted offering.
- Not a commercial product or service. There is no path to revenue and no intent to build one.
- Not a public knowledge base or community-edited wiki.
- Not a replacement for paid offerings (Notion, Evernote, dedicated accounting software). Where those are better tools for a need, the household uses them.
- Not aiming for arbitrary scale. Capabilities deliberately stop at household scope.
- Not built for outside contributions. The public repo is a reference artifact, not an open-source community project. Issues and PRs from outside readers are welcome as discussion but not as a development model.
- Not usable at full capability without an AI subscription. PLOS is built around the assumption that an existing Claude Code subscription is part of the toolkit; without one, the long-tail extraction, the scheduled compile passes, and the natural-language query features are unavailable.

---

## How to read the rest of the repo

After this brief, the natural reading order is:

1. **`EVOLUTION.md`** — how the architecture got to its current shape. Captures what was tried, what was rejected, and why. Most distinctive doc in the repo.
2. **`ARCHITECTURE.md`** — the current architecture as a reference document.
3. **`METHODOLOGY.md`** — how this was built collaboratively with AI tools.
4. **`examples/sample-vault/`** — the fictional household used for demos and tests.
5. **`src/` and `tests/`** — the actual code.

Casual readers can stop after the first three. Anyone wanting to run the system locally goes to the README quickstart.
