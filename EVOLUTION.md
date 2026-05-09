# PLOS — Design Evolution

**Document type:** Design history
**Status:** Captures the v1 → v2 architectural shift and the v2 → v2.5 compilation-hybrid refinement; updated as further significant evolutions occur.
**Audience:** Readers who already understand what PLOS is (see `BRIEF.md`) and want to understand how the architecture got to its current shape — what was tried, what was rejected, and why.

---

## Changes in this revision

A new section, "v2.5 — the compilation hybrid," is appended after the existing v1 → v2 narrative. It documents a refinement to v2's M3 decision (Dataview at view-time over pre-computation): the default holds, but three named exceptions are introduced where synthesis genuinely exceeds aggregation. The original v1 → v2 history is unchanged, including its lessons.

A short "Implementation reality" section is appended at the end, capturing one assumption that did not survive contact with the vendor stack: the original "single-container Paperless, no Redis" intent was rewritten during Phase 1 build because current Paperless-ngx hard-requires Redis with no in-process fallback. The architecture absorbs Redis as a named exception rather than re-litigating the rule.

---

## Why this document exists

Most architecture documents describe a system as if it sprang into being fully formed. This one captures a real iteration: the project started with one set of goals and one architectural approach, ran into a series of revealing observations, and ended up with a meaningfully different design. Recording that is useful for two reasons.

For the project itself, it makes the rationale behind specific choices durable — six months from now, when a contributor (or the original author returning after a break) wonders "why is there no `vault_index` table?", the answer is here, not lost in a chat history.

For a reader of this repo as a portfolio artifact, the iteration is the most distinctive thing on offer. Many projects show a finished architecture. Fewer show the pressure that shaped it.

---

## The starting point: v1 thinking

The original PLOS architecture — its final form was the v3.2 Blueprint backed by a 12-decision log (D1–D12) — was characterized by *comprehensive coverage*. Every plausible edge case was considered; most got dedicated machinery to handle them.

At peak elaboration, the v1 stack included:

- **9 SQLite tables** — `documents`, `jobs`, `entities`, `extracted_fields`, `corrections`, `graduated_types`, `vault_index`, `entity_aliases`, `entity_links`.
- **12 numbered architectural decisions** with rationale and rejected alternatives for each.
- **AUTO-section markers in entity bodies** delimited by HTML comments, with an integrity check that aborted writes on marker mismatch.
- **Cascade-on-update rendering** across the entity graph, opt-in per relationship via `cascade_on_update: true`, depth-capped at 1 level, with list-typed wikilink expansion as a first-class concern.
- **Generated `schema.yaml`** from per-domain markdown via a `build_schema.py` tool with dry-run mode and `SAFE` / `NEEDS_MIGRATION` / `BREAKING` classification.
- **A self-cleaning `_review/queue.md`** with closed-loop indexer resolution.
- **64 GitHub issues** organized across 8 phases.
- **A 7–8 week MVP timeline** with overnight Claude Code sessions to drain queues.

This was thorough. Each piece had been reviewed (often through external Gemini reviews creating pressure for sharper decisions). The decisions log captured rationale for every choice, and the rejected alternatives were preserved alongside.

It was also, in retrospect, optimized for the wrong goals.

---

## What surfaced the shift

Three observations in roughly the order they hit, each one reshaping more than it appeared to at first.

### Observation 1 — The portfolio purpose introduces legibility as a hard constraint

The intent for the project always included making it a public artifact demonstrating AI-collaborative work. v1 docs were optimized for completeness; portfolio readers reward judgment more than coverage.

A 9-table SQLite schema where four of the tables are derivable or denormalizable into another reads as *"this person let an LLM run."* A 4-table schema that makes considered choices reads as *"this person made decisions."* Same outcome. Different signal. The signal is what portfolio visitors actually evaluate.

The decisions log compounded this. Twelve decisions reads as either "comprehensive" or "elaborated past usefulness" depending on whether the reader thinks each decision earned its place. Seven decisions, where each is clearly load-bearing, reads unambiguously as the former.

### Observation 2 — The privacy gap makes the existing trajectory unworkable

Personal infrastructure projects of this kind accumulate identifying information naturally during design — legal entity names, addresses, account fragments, vendor relationships, household composition all show up as the working examples that make abstract architecture choices concrete. v1's planning docs accumulated such examples in the way any real implementation would.

This is fine while a project is private. It becomes a problem the moment a public release is contemplated. State business registries are public; real legal entity names link back to the people behind them. Addresses, account fragments, and household composition together create a findable identity dossier. The cost of getting this wrong on a public repo is asymmetric — accidentally publishing one identifier may be enough.

v1 had no plan for this. Sanitization was implicitly a future polish step. That doesn't work — once real identifiers exist in commit history, planning docs, and issue titles, sanitization becomes a separate project of its own, and a fragile one. Forgetting one reference is enough.

The fix isn't a sanitization pass. It's a structural separation: a public reference repo built clean from commit one with fictional data, and a private operating instance that stays private. That separation has architectural implications the v1 single-repo model didn't account for.

### Observation 3 — Maintenance cost on a personal system is real

Every layer in v1 was something that would have to be maintained, debugged, and remembered six months later when the code hadn't been touched. AUTO-marker integrity checks. Cascade rendering with opt-in flags and list-typed wikilink expansion. Dry-run schema generation with safety classification. Self-cleaning review queue resolution. Each individually defensible; collectively, more surface area than a part-time solo developer should be carrying for a household system.

The complexity-to-value math didn't pencil out. v1 was designed as if the build would happen full-time and every detail would stay loaded in memory. The reality of a personal system is evenings and weekends, with months between visits to specific subsystems.

---

## The meta-decisions that drove v2

Five decisions reshape the rest. Each one is a stance about *how to design*, not a specific architectural choice.

**M1 — Optimize for legibility, not coverage.** Where two designs would work, the simpler one wins. What v1 didn't include was incidental; what v2 doesn't include is deliberate, listed in `ARCHITECTURE.md`, and rationalized.

**M2 — Privacy is structural.** The reference repo is fully sanitized from commit one. The actual operating instance is private and stays private. Three repos: `plos-reference` (public, this one), `plos` (private operating instance), `plos-vault` (private real vault). Sanitization happens at the boundary, not as a polish step at the end.

**M3 — Dataview at view-time replaces body-rendered AUTO machinery.** Cross-entity views are queried from frontmatter at the moment of rendering, not pre-computed and written into entity-page bodies. This single insight cascades: it eliminates AUTO-section markers, the integrity check that protected them, the cascade rendering that kept them fresh, the apply_template overnight Claude run that initially populated them. Roughly a third of the worker's surface area disappears, and a class of bugs (markers getting accidentally edited, cascade firing on the wrong parent) ceases to exist.

**M4 — Demo-first vertical slicing replaces horizontal-layer phasing.** v1 phased as substrate → migration → templates → extractors → reprocessing → notifications. The first end-to-end working slice landed somewhere around week 6. v2 phases as vertical slices: a working end-to-end run for one document type ships by end of phase 2, then expands. For a portfolio repo, a runnable demo by week 2 is the right priority. For a part-time builder, an early end-to-end slice is also the only honest validation that the architecture works.

**M5 — The methodology is a first-class artifact.** The most distinctive thing about this project is *how* it was built — chat for design, external review for pressure, a decisions log for capture, Claude Code for implementation, a deliberate retreat from auto-mode planning when subtraction was needed. Documenting that loop is a rarer signal than documenting the system itself, and produces a portfolio artifact that few comparable projects have.

---

## What changed concretely

| Aspect | v1 | v2 |
|---|---|---|
| SQLite tables | 9 | 4 |
| Numbered architectural decisions | 12 | 7 (carried forward) |
| AUTO sections in entity bodies | Yes, with HTML markers + integrity check | No — Dataview queries at view-time |
| Cascade rendering across entity graph | Yes, opt-in per relationship | None — view-time queries are always fresh |
| Schema generation | `build_schema.py` with dry-run + classification | Hand-written YAML for v1 |
| `vault_index` mirror table | Yes | None — frontmatter parsed on demand |
| `entity_links` table | Yes | None — relationships from frontmatter wikilinks |
| `entity_aliases` table | Yes | JSON column on `entities` with normalized index |
| `jobs` table | Separate | `status` enum on `documents` |
| Graduated extractor registry | `graduated_types` table | Directory listing of `extractors/graduated/` |
| Backlog issues | 64 | ~20 (current implementation slice only) |
| MVP timeline | 7–8 weeks | ~5 weeks |
| Repo strategy | Single private repo plus separate vault | Three repos: public reference, private instance, private vault |
| Phasing model | Horizontal layers | Vertical slices, demo-first |
| Query interface | Implicit (Dataview only) | Explicit: Dataview for pre-built views, Claude Code session for ad-hoc analytical questions |

---

## What survived unchanged

The architectural core was load-bearing in v1 and remains load-bearing in v2. Listing what survived matters because it shows the v1 → v2 shift was about pruning, not redesign — the structural bones held up under scrutiny.

- **Vault-canonical, SQLite-as-sidecar.** The original Option C decision was correct and is preserved verbatim. Entity records live in vault frontmatter; SQLite holds document metadata, the extraction audit trail, and corrections.
- **The freshness resolution rule.** `MAX(COALESCE(data_effective_date, document_date))`, then confidence, then `extracted_at`. Order-independent ingestion; effective-date-aware for documents whose data takes effect later than their date (insurance renewals, leases, mortgage modifications).
- **`locked_fields:` per-entity overwrite protection.** Lightweight, frontmatter-local, complements `corrections.md`.
- **Worker doesn't autonomously create entity files.** Unmatched entities queue to `_review/queue.md` for human review through a Claude Code session.
- **`aliases:` indexed for correspondent resolution.** Now a JSON column rather than a separate table, but lookup behavior is identical.
- **`owning_entity` segmentation.** Tax/legal isolation across business entities in weekly digests is genuinely useful and stays.
- **Anomaly heuristics.** Percentage deviation against rolling 3-month average, plus expectation-gap detection. Specific, useful, not naive value-diff noise.
- **Real-time review queue page plus weekly digest summary.** Triage native to the vault, accountability via email.
- **Graduated extractor pattern.** Free local scripts for the hot path, AI for the long tail, $0 incremental cost.

---

## Lessons

Four things worth carrying into the next project of this shape.

**Auto-mode planning incentivizes elaboration; design needs a subtraction force.** v1 planning largely happened in Claude Code's auto mode, where the natural gradient is to add detail, anticipate edge cases, and cover bases. That mode is excellent for implementation; it is dangerous for design. v2 planning happens in chat, where pushback comes more easily and "do we actually need this?" is a natural question rather than friction. If you're using AI to plan, you need an explicit force pulling toward subtraction, or the design will accrete past usefulness.

**Privacy decisions are dramatically easier upfront than retroactive.** Once real identifiers exist in commit history, planning docs, and issue titles, sanitization becomes a separate project of its own — and a brittle one. Decide the public/private boundary on day one. Use placeholder data from the first commit. If a project will ever go public, treat it as public from the start. This applies to AI conversations during planning as well: anything that might end up in a public artifact should be discussed with placeholder names, not real ones.

**Dual purposes need to be named upfront.** v1 was implicitly a portfolio piece without ever stating it. The constraints that mattered for that purpose — legibility, demo-readiness, privacy — didn't show up in the brief, so they didn't shape early decisions. v2 names the dual purpose explicitly in `BRIEF.md`, and the constraints flow from it. Implicit goals don't drive design; named goals do.

**Use cases need to be enumerated explicitly, not inferred from architecture.** Even after the v2 brief was rewritten, two genuine daily-use patterns — email-forwarded capture and ad-hoc natural-language queries — were missing. Both turned out to be supported by the architecture (email as a capture channel; LLM with vault + SQL access as a query client), but the brief didn't *name* them as use cases, and the architecture wasn't actively shaped around them. The fix was to walk through the actual day-in-the-life of the system and ask "is this in the docs?" for every interaction. A surprising number weren't. Design from use cases forward, not from architecture backward.

---

## v2.5 — the compilation hybrid

### Why this section exists

v2 settled into M3 — Dataview at view-time over pre-computation — as a load-bearing simplification. It pruned a class of machinery (AUTO-section markers, cascade rendering, integrity checks) and the architecture got cleaner for it. But "no pre-computation" was always more rule-of-thumb than principle, and the cleaner answer turned out to be "default to view-time, with a small set of named exceptions where synthesis genuinely requires more." This section documents that refinement.

### What surfaced the shift

A pattern showed up across unrelated tooling I was watching during the v2 build: vendors that had previously rendered everything at query time were adding ingestion-time compilation layers — pre-computed digests, summary indexes, regenerated overviews. The convergence was not coincidence. View-time aggregation works for "show me the rows where X" but starts to break down for "tell me which of these things actually matters." The latter requires synthesis — priority reasoning, pattern detection across history, gap-surfacing against expectations — that aggregation primitives don't reach.

That observation prompted the question: does v2 already answer the synthesis use cases?

The honest answer was: mostly. The Sunday digest does priority and anomaly reporting via the notification engine; Dataview covers per-domain rollups; Claude Code answers ad-hoc questions on demand. Across the recurring-question inventory, only three answer surfaces felt genuinely under-served by the v2 set. A daily "what needs my attention this week" view that ranked items rather than just listing them. A monthly "what's unusual this month" view that persisted in the vault rather than only existing as an email each Sunday. A "what tax documents are still missing" view that reasoned against an explicit expected-documents list. Each of these gets asked enough to deserve a stable artifact, and each requires synthesis that Dataview cannot do.

### The decision rule

Rather than open the door to pre-computation generally, v2.5 adds a decision rule that stays close to M3:

> **Default:** Dataview at view-time for any cross-entity view, aggregation, filter, or sort.
> **Exception:** Compiled artifact only when the answer requires synthesis beyond aggregation — priority reasoning, anomaly detection from patterns, or gap-surfacing against an expected-document checklist.

The rule is documented in the wiki's `CONVENTIONS.md` and applied case-by-case in the artifact map. Adding a fourth compiled artifact requires explicit justification under one of those three categories. The default remains Dataview; pre-computation is the named exception, not a permission slip. When in doubt, start as a Dataview dashboard — promoting a dashboard to a compiled artifact later is additive; the reverse is more work.

### The three named exceptions

`compiled/this-week.md` — priority reasoning across domains. Dataview can list the seven things that have a date in the next seven days; it cannot reason about which of those genuinely warrant a heads-up given everything else going on, or rank them, or fold in a flag from the anomalies output. Daily refresh.

`compiled/anomalies.md` — pattern detection from history. Computing a 3-month rolling average, flagging deviations, and detecting expectation gaps ("the recurring statement that should have arrived by the 20th hasn't") sit outside Dataview's aggregation primitives. The notification engine already does this work for the digest; v2.5 captures the same output as a compiled artifact so it persists in the vault and feeds the daily this-week pass. Monthly refresh.

`compiled/tax-prep.md` — gap surfacing against an explicit checklist. Dataview can show what's in `tax/2025/received/`; it cannot reason about a 14-item expected-documents list and flag what's still missing with rationale for what to chase. Weekly during tax season, monthly otherwise.

### What this changed concretely

The wiki gains a folder layout split. `source/` holds entity records and raw documents (canonical, untouched by automation except for the worker's frontmatter merges). `compiled/` holds the three artifacts above (regenerated by scheduled Claude Code passes). `dashboards/` holds Dataview query files (rendered live in Obsidian). The split is structural, not cosmetic — it preserves the v2 commitment that entity bodies are never written by automation, because compiled artifacts and dashboards live in their own folders rather than being injected into entity pages.

The wiki also gains a `CONVENTIONS.md` document that holds the routing decision rule, the merge resolution rule, the frontmatter contract, and naming conventions. `CLAUDE.md` becomes development guidance only and references `CONVENTIONS.md` for any "how does the system actually decide X" question. The split lets agent-facing development guidance and architectural rules evolve independently.

The runtime gains scheduled compile passes that run inside the existing Claude Code subscription. Atomic writes (write-and-rename) are required so partial state never appears to a reader. Compiled artifacts are allowed to read each other's outputs — `this-week.md` reads `anomalies.md` to fold flagged items into the day's priorities — which means scheduling matters: monthly anomalies first, then daily this-week.

The architecture gains audit passes. Each compiled artifact's frontmatter declares the source paths it read; an audit pass compares declared sources to actual paths the artifact references and flags any claim without a backing source. This catches drift between what the prompt was told and what the prompt actually read, and it catches synthesis that smuggles in conclusions without provenance.

### What didn't change

M3's spirit is preserved. Entity bodies are still never written by automation; the worker still merges only into frontmatter; manual edits to entity prose are always safe. The compiled folder is structurally separate from entity records — compiled artifacts are not injected into entity pages, not written as AUTO sections, and not subject to integrity checks against tampering, because they live somewhere where tampering is meaningless. The class of bugs AUTO sections introduced cannot recur in v2.5.

Vault-canonical, SQLite-as-sidecar still holds. The freshness resolution rule, `locked_fields:`, `corrections.md`, the worker's refusal to autonomously create entity files, the anomaly heuristics in the digest — all carry over unchanged. The MVP timeline holds. The cost model holds.

The phased build shifts subtly: Phase 2's demo is now a Dataview dashboard reading from frontmatter the worker wrote, which is a more visible end-to-end loop than "watch the frontmatter update" and a lower-cost first deliverable than the full notification stack. Phase 4 introduces `this-week.md` alongside the existing Claude Code session workflow. Phase 5 adds the remaining two compiled artifacts.

### The lesson

The v2 → v2.5 shift adds one to the lessons above. **Rules of thumb and principles aren't the same thing, and conflating them costs flexibility.** M3 was the right rule of thumb — pre-computation had been overused in v1, and pulling sharply away from it was the right correction. But the principle underneath was something more nuanced: *prefer view-time when it works, and use pre-computation only where synthesis genuinely requires it*. Stating M3 as a hard rule rather than a default-with-named-exceptions made v2 cleaner to specify, but it also made it harder to admit that a small number of cases really did need pre-computation. v2.5 doesn't repudiate M3; it states the principle behind M3 more precisely. The next time a load-bearing simplification gets made, it's worth asking: *is this the principle, or is this the rule of thumb that approximates the principle? And what are the cases where the rule of thumb breaks?*

---

## What this document does not claim

Two clarifications worth stating directly.

This isn't a confession that v1 was wrong. v1 was internally coherent and would have produced a working system. The shift to v2 is not a correction of errors — it's a reframing once new constraints (portfolio purpose, privacy boundary, realistic maintenance budget) became visible. v1's decisions log preserved its rationale carefully, and that rationale isn't invalidated retroactively. It just stopped being load-bearing once the goals shifted. The same applies to the v2 → v2.5 shift: v2 was coherent and would have worked; v2.5 refines a load-bearing rule into a load-bearing principle, and the work v2 did is preserved in v2.5 unchanged.

This isn't a final architecture. v2.5 will face its own pressure as the system gets built and used. If a v3 emerges from real usage data, this document gets a new section. The point of recording iteration is to make the next iteration easier, not to declare the current one finished.

---

## Implementation reality — assumptions corrected during build

Architecture documents are written before the code runs. Some assumptions hold; others meet the vendor stack and lose. This section records corrections made during build so the design and the running system stay honest with each other.

### The "no Redis" assumption did not survive contact with current Paperless-ngx

The original substrate intent (carried in the docker-compose comment header through Phase 1's first commit) was *"single container, SQLite backend, in-process broker. No Redis, no Postgres."* That framing was load-bearing for the "subtraction over addition" principle: every additional moving part has to earn its keep, and a cache server for a one-household document pipeline reads as overkill.

It turned out to be wrong about Paperless. Current Paperless-ngx (2.x and later) requires Redis unconditionally — Django's cache backend, Celery's task broker, and the post-migrate signal handlers in upstream dependencies all hit `localhost:6379` during boot, with no flag to disable or substitute an in-process alternative. The container fails to finish migrations without a reachable Redis. This was discovered during Phase 1 verification, not during design.

The fix preserves the spirit of the original constraint while accepting the vendor reality: a small `redis:7-alpine` sidecar is added to docker-compose, with no auth, no published port, and no persistent volume — cache and broker state are intentionally ephemeral. From PLOS's perspective Paperless remains one logical component; the Redis container is an implementation detail of *running* Paperless, not a thing PLOS code interacts with. Postgres is still excluded — SQLite is sufficient for one household, and that part of the original intent does hold up.

The lesson is small but worth naming. *Vendor stacks have hard requirements that aren't always visible in their docs until you boot them.* "Subtraction over addition" works as a design principle, but it can't be enforced against requirements you don't control. The right response is to absorb the new component as a named exception (which is what `ARCHITECTURE.md` and the docker-compose comment header now do), not to fight the upstream project or pin to an end-of-life version.
