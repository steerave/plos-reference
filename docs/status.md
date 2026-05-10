# Project Status Log

## 2026-05-14

**Done:**
- Verified Phase 4b end-to-end on the live MidAmerican bill at
  `paperless_id=3`. Drain extracted a clean
  `utility_bill_combined` doc_type with 11 fields including per-
  utility breakdown ($102.70 electric + $74.99 gas), kWh and therms,
  the routing keys (account 31630-76026, both providers), and a
  proposed property entity with slug `2835-west-ct-bettendorf`.
  Real-world bill, real-world OCR, real-world Claude — and the
  field-naming convention proved flexible enough that Claude
  invented two new domain-appropriate field names
  (`last_utility_bill_electric_amount`,
  `last_utility_bill_gas_amount`) without violating the contract.
- Closed Phase 4c (corrections override workflow):
  - Added `examples/sample-vault/corrections.md` — YAML-frontmatter
    file with a `corrections:` list of `{slug, field, value, source,
    reason}` entries; prose body documents the format.
  - Added `src/plos/vault.py:apply_correction()` — atomic write that
    sets a field AND appends to `locked_fields:`. Bypasses the
    freshness rule by design (corrections are orthogonal to
    freshness).
  - Added `src/plos/entities.py:find_by_slug()` — generic any-
    entity-type lookup.
  - Added `src/plos/import_corrections.py` —
    `python -m plos.import_corrections` reads the file, locates each
    entity by slug via `find_by_slug`, calls `apply_correction`, and
    inserts/updates a row in the SQLite `corrections` audit table
    (DELETE + INSERT for update semantics — keeps one row per
    entity+field). Counts outcomes as
    `{'applied': N, 'no_entity': M, 'errored': K}`.
  - 25 new tests across `test_vault.py` (5 new for
    `apply_correction`), `test_entities.py` (5 new for
    `find_by_slug`), and the new `test_import_corrections.py` (15
    tests covering parse / apply_one / multi-entry run / error
    paths / env handling).
  - Updated CHANGELOG, README (new "Phase 4c (corrections override)"
    quickstart), CLAUDE.md (new "Phase 4c conventions" section
    documenting the YAML format, the freshness-bypass discipline,
    the locked_fields piggyback design, the v1 append-only
    semantics, and the audit-row shape).
- Test count: 167 passing in 1.05s (was 142 at end of Phase 4b).

**Next:**
- Live demo of Phase 4c: edit `corrections.md` to add an entry,
  run `python -m plos.import_corrections`, confirm the entity
  frontmatter updates, the field shows in `locked_fields:`, and the
  SQLite audit row lands.
- Phase 5: scheduling (Windows Task Scheduler or a Claude Code
  remote agent for the daily `this-week` compile pass), the
  remaining two compiled artifacts (`anomalies.md`, `tax-prep.md`),
  the audit pass that verifies `sources_read:` declarations match
  in-body `→ /source/...` arrows. **MVP marker.**

**Notes:**
- Phase 4 is now feature-complete per the original phasing in
  ARCHITECTURE.md. Three Slices landed: 4-1 (compile pass), 4b
  (drain), 4c (corrections). Each follows a similar shape — a
  `python -m plos.<thing>` entry point, a manifest or input file
  per call, atomic vault writes, structured audit in SQLite. The
  Claude Code CLI is now invoked from two places (compile pass +
  drain); corrections.md is human-driven, no AI involved.
- The locked_fields piggyback for corrections is the most
  interesting design choice in Phase 4c. It avoids passing a
  database connection into the merge writer and lets the existing
  contract handle override automatically. The trade-off is that
  the entity file alone can't tell "hand-locked" from
  "correction-locked"; that distinction lives in SQLite and a
  Phase 5 audit pass would surface it.
- `corrections.entity_id` is FK-constrained, so corrections for
  entities the worker hasn't seen yet apply to the vault but skip
  the audit row. This is logged but quiet otherwise. If the audit
  gap turns out to matter, a small SQLite migration drops the FK.

## 2026-05-13

**Done:**
- Verified Phase 4 Slice 1 end-to-end on the live `claude` CLI:
  `python -m plos.compile_this_week` produced a valid
  `examples/sample-vault/compiled/this-week.md` in 12s with both
  seeded deadline items prioritised correctly (Joe's drivers license
  in **Must do**, State Farm renewal in **Should do**), each with a
  `→ /source/...` provenance arrow, and the conventional footer.
  One integration-only bug surfaced and got fixed in commit
  `69b9e62` (`encoding="utf-8"` on `subprocess.run` — Windows
  defaults to cp1252 which can't encode the `→` character).
- Closed Phase 4b (pending_claude drain workflow):
  - Added `src/plos/drain_pending_claude.py` —
    `python -m plos.drain_pending_claude` walks every
    `documents.status='pending_claude'` row, shells out to
    `claude --print` per document with the OCR text + every entity
    index.md as context, parses the JSON response (tolerating
    \`\`\`json ... \`\`\` fencing), and dispatches:
    - `route_status=matched` → `vault.merge_frontmatter` + status
      `done` + `extracted_fields` audit rows tagged
      `handler='claude'`.
    - `route_status=unmatched_entity` → status `needs_review`,
      JSON-encoded proposal (rationale + fields + proposed_entity
      block) stored in `documents.review_reason` for a Phase 5+
      review-queue renderer to consume.
    - `route_status=unrecognized` → status `needs_review` with
      reason `claude_unrecognized`.
    - Invalid JSON / hallucinated entity / empty OCR / subprocess
      crash all have explicit handling and tests.
  - 14 unit tests cover all paths (matched / unmatched / unrecognized
    / invalid JSON / empty OCR / hallucinated entity slug / multi-doc
    loop / subprocess failure).
  - Updated CHANGELOG, README (new "Phase 4b (pending_claude drain)"
    quickstart), CLAUDE.md (new "Phase 4b conventions" section
    documenting the structured JSON contract, `handler='claude'`,
    the JSON-in-review_reason workaround for unmatched audit, and
    the no-auto-creation invariant).
- Test count: 142 passing in 0.85s (was 128 at end of Phase 4
  Slice 1).

**Next:**
- Live demo of Phase 4b: run `python -m plos.drain_pending_claude`
  on the user's machine. The MidAmerican bill at `paperless_id=3`
  has been waiting in `pending_claude` since the Phase 2 demo and
  is the live test case. Expected outcome: Claude extracts the gas
  fields, fails to match an existing entity (the sample vault has
  only 123-main-davenport, keyed to ACCT-12345 / Acme), and stores
  the proposal in `review_reason`. Status flips
  `pending_claude → needs_review`.
- Phase 4c: `corrections.md` + `import_corrections.py`. Vault-edit-
  then-import flow that lets a human override Claude's or a
  graduated extractor's output for a specific entity+field.
  Architecture pairs it with the drain under "the same session
  pattern."
- Phase 5: scheduling, the other two compiled artifacts
  (`anomalies.md`, `tax-prep.md`), the audit pass against
  `sources_read:`. MVP marker.

**Notes:**
- Phase 4b is the second place `subprocess.run([claude_cmd, "--print"])`
  appears in the codebase. The pattern is now established enough
  that further compile passes (`anomalies.md`, `tax-prep.md`) and
  ad-hoc-question handlers will plug into the same shape:
  build manifest → shell to claude → validate response → write
  back atomically.
- The schema's `extracted_fields.entity_id IS NOT NULL` constraint
  forced a small architectural compromise in the unmatched-entity
  branch — Claude's proposal lives in `documents.review_reason` as
  a JSON blob rather than as proper audit-trail rows. Phase 5+
  formalisation (when the audit-pass story lands) will likely drop
  the NOT NULL via a small SQLite table-rebuild migration. Flagged
  in the deferral list.

## 2026-05-12

**Done:**
- Verified Phase 3 end-to-end on the live Paperless instance: dropped
  all four sample-bill PDFs (Phase 2 electric + Phase 3 mortgage /
  bank / pay stub) into the live consume folder, watched the worker
  route each through real OCR, all four reached `status='done'`.
  `extracted_fields` recorded 23 rows across the four expected
  handlers; three entity types instantiated in the `entities` table
  (property, account, person). One integration-only bug surfaced and
  was self-fixed: the worker process had been started before the
  Phase 3 commits landed, so only the electric extractor was loaded
  in the running registry — restart resolved it. The freshness rule
  fired exactly as designed when mortgage's Paperless-detected date
  (2026-05-01) ran ahead of electric's (2026-03-15) — the audit
  trail still recorded every extraction even when the merge skipped.
- Closed Phase 4 Slice 1 (compile pass for `this-week.md`):
  - Added `src/plos/compile_this_week.py` — `python -m plos.compile_this_week`
    builds a manifest of every entity index.md + every dashboard +
    the previous compile output, shells out to the `claude` CLI in
    `--print` non-interactive mode, validates the response shape
    (must start with `---`, must contain `Must do` / `Should do` /
    `Watching` section headings), and atomically writes the result
    to `examples/sample-vault/compiled/this-week.md`.
  - Seeded the sample vault with two fictional deadline fields so
    the compile pass has cross-domain content to prioritise:
    `insurance_renewal_date: '2026-05-22'` on the property,
    `drivers_license_expiry: '2026-05-15'` on Joe.
  - 12 unit tests cover manifest building (entity files, dashboards,
    previous output, today's date), atomic write (no temp leak,
    overwrite of stale output), format-validation gate (rejects
    response without frontmatter or missing sections), subprocess
    failure propagation, and `PLOS_VAULT_ROOT` env handling. All
    Claude invocations mocked.
  - Updated CHANGELOG, README (new "Phase 4 Slice 1" quickstart
    section), CLAUDE.md (new "Phase 4 conventions" section
    documenting the compile-pass invocation contract, manifest
    shape, format-validation gate, atomic-write discipline, source
    provenance rules).
- Test count: 128 passing in 0.8s (was 116 at end of Phase 3 — added
  12 tests for the compile pass).

**Next:**
- Phase 4 Slice 1 demo verification: run `python -m plos.compile_this_week`
  on the live machine, open `compiled/this-week.md` in Obsidian,
  confirm both seeded items appear with `→ /source/...` provenance
  arrows.
- Begin Phase 4b: `pending_claude` drain workflow. The MidAmerican
  bill at `paperless_id=3` has been sitting since the Phase 2 demo
  and is exactly what Phase 4b is designed to handle. Architecture
  pairs it with the compile pass under "the same session pattern."
- Phase 4c: `corrections.md` + `import_corrections.py` — the vault-
  wide override file with provenance.

**Notes:**
- The compile-pass invocation contract is the new architectural
  delta in Phase 4. The pattern (build manifest → shell to claude
  CLI → validate response shape → atomic write) is the template
  every future compiled artifact follows: `anomalies.md` and
  `tax-prep.md` in Phase 5 plug into the same shape with their own
  manifest builder + section-heading set.
- Source provenance is the contract that makes Phase 5+ audit passes
  possible. The artifact's `sources_read:` frontmatter list and the
  `→ /source/...` arrows in the body must agree; the audit pass
  walks the artifact and flags any drift. This is why the
  format-validation gate at write time is non-negotiable — a corrupt
  artifact would silently break the audit pass too.

## 2026-05-11

**Done:**
- Closed Phase 3 (mortgage / bank / pay stub) end-to-end. Four atomic
  feature commits, all pushed:
  - **Phase 3-0** (`628b7d4`): worker refreshes `documents.document_date`
    from the Paperless API at the start of each pass — `documents.document_date`
    is `NULL` at hook time because Paperless's date detection is
    asynchronous. The worker shifted from `paperless.get_document_text(id)`
    to `paperless.get_document(id)`, pulls both `content` and
    `created_date` from the same response, and writes the date back
    to SQLite when the API has one.
  - **Phase 3-1** (`6343956`): Mr. Cooper mortgage statement extractor
    plus a small worker routing generalisation. Each extractor module
    now exports both `extract` and `route(fields, vault_root)`;
    `EXTRACTORS` holds `(handler, module)` tuples; a new
    `RouteResult(path, missing_key)` named tuple distinguishes
    `no_routing_key_in_extraction` from `unmatched_entity`. Property
    dashboard gets a second Dataview table for mortgage data.
  - **Phase 3-2** (`4b104fd`): First Davenport Bank statement extractor
    + first account entity in the sample vault
    (`accounts/first-davenport-checking-4521/`) + new
    `dashboards/account-balances.md`. Worker upserts new entity types
    via a small `_ENTITY_TYPE_FROM_DIR` dict
    (`accounts → (account, finance)`, etc.) — no per-type branches.
  - **Phase 3-3** (`64e679a`): Beacon Software pay stub extractor +
    first person entity (`people/joe/`) + new `dashboards/income.md`.
    First composite routing key in the registry — pay stubs route on
    `(legal_name, employer_current)` together. One subtle regex bug
    surfaced and got fixed in the same commit: the original
    `_employee_name` pattern was greedy enough to bleed past the name
    when adjacent OCR text started with a capitalised word, so the
    name capture is now anchored on the literal colon and limited to
    exactly two Capitalized words.
- Updated project CLAUDE.md with a "Phase 3 conventions" section
  capturing the extractor `route()` contract, the `RouteResult`
  semantics, the composite-routing-key pattern, the entity-type-from-
  directory mapping, the `document_date` refresh decision, the Phase 3
  fictional providers, and the deferrals.
- README and CHANGELOG updated per slice — three new "Quickstart" demo
  walk-throughs (Phase 3 Slice 1, Slice 2, Slice 3) plus a closing
  "End of Phase 3" note.
- Reportlab now called with `invariant=1` so regenerated sample PDFs
  are byte-deterministic across runs (`git diff` stays quiet between
  fixture rebuilds).
- Test count: 116 passing in 0.6s (was 56 at end of Phase 2 — added
  60 tests covering three new extractors, three new entity matchers,
  the composite routing key, the date-refresh path, the worker's
  generalised dispatch, and an end-to-end "three documents → three
  entity types" Phase 3 demo test).

**Next:**
- Begin Phase 4: first compiled artifact (`compiled/this-week.md`),
  scheduled daily, plus the Claude Code session workflow that drives
  it. Phase 4 also brings the long-tail extraction path that drains
  `pending_claude` documents (real-world bills not matching our four
  fictional providers route there today and wait).
- Pick up the deferred Phase 4 housekeeping items if convenient:
  rename `tests/fixtures/sample_bills/` to something less misleading
  (it holds mortgages and pay stubs too now); start populating
  `examples/sample-vault/source/people/joe/` with the richer shape
  documented in `docs/source-layer-shapes.md` (identity, medical,
  account-access).

**Notes:**
- The architecture's "one extractor file + one tuple entry" claim now
  has three more receipts. The worker hasn't grown a per-doc-type
  branch since Phase 2.
- The Phase 3 demo at end-state: drop four PDFs (Phase 2 electric +
  Phase 3 mortgage/bank/paystub) into `consume/`, watch four
  extractors route four documents onto three different entity types
  (property, account, person) through one generic worker, then open
  three Dataview dashboards in Obsidian and see the rows render live.
- The extractor route() contract is the largest architectural delta
  in Phase 3. It absorbed both the simple-key cases (electric_account,
  mortgage_loan_number, account_number) and the composite-key case
  (employee_name + employer) without further worker changes — which
  is the right test for whether the abstraction is at the right level.

## 2026-05-10

**Done:**
- Brainstormed and locked the Phase 2 design (electric utility bill end-to-end), captured in `~/.claude/plans/b-electric-smooth-sparrow.md`.
- Built sample data fixtures: populated `examples/sample-vault/source/properties/123-main-davenport/index.md` and added a deterministic reportlab PDF generator at `tests/fixtures/sample_bills/build.py` plus the generated `electric_acme_2026_04.pdf`.
- Added `reportlab` and `responses` as dev dependencies; added `*.pdf`/`*.png`/`*.jpg`/`*.zip` binary marks to `.gitattributes` so autocrlf can't corrupt fixtures.
- Wrote the Paperless REST client at `src/plos/paperless.py` (`get_document_text`, `get_document`) with HTTP-mocked tests; added `PAPERLESS_API_TOKEN` env var.
- Defined the graduated-extractor contract in `src/plos/extractors/registry.py` — `DocumentMeta` frozen dataclass + `dispatch()` over a plain `EXTRACTORS` list (no auto-discovery).
- Wrote the Acme Power & Light electric-bill extractor at `src/plos/extractors/graduated/utility_bill_electric.py` with whitespace-tolerant regex and 10 unit tests.
- Wrote the entity matcher at `src/plos/entities.py` (`find_property_by_electric_account`); added `PLOS_VAULT_ROOT` env var.
- Wrote the atomic frontmatter merge writer at `src/plos/vault.py` honoring `locked_fields:` skip + `data_effective_date` freshness rule + temp-then-rename atomic write.
- Rewrote `src/plos/worker.py` to drain documents through extractor → entity matcher → vault writer → `extracted_fields` audit trail; expanded status taxonomy to `done` / `pending_claude` / `needs_review` / `new` (retry on transient failure).
- Created the first Dataview dashboard at `examples/sample-vault/dashboards/properties.md`.
- Updated CHANGELOG, README (new "Quickstart — Phase 2 demo" section), and project CLAUDE.md (decision-capture for extractor interface, registry pattern, vault merge order, status taxonomy).
- Verified Phase 2 demo end-to-end on Windows: dropped the sample bill PDF, worker picked it up, extracted, wrote to vault frontmatter (`last_utility_bill_amount: 142.37`, `_kwh: 850`, `_date: 2026-04-30`, `_url: paperless link`), and the property's `index.md` reflects the new fields.
- Pushed all 9 Phase 2 commits to <https://github.com/steerave/plos-reference>.

**Next:**
- Begin Phase 3: graduated extractors for gas, water, internet (utility bills), plus mortgage statements and pay stubs per `ARCHITECTURE.md` phasing. Each new extractor is one module + one tuple entry in `registry.EXTRACTORS`.
- Fix the `data_effective_date` regression: when Paperless's date-detection runs after the post-consume hook fires, `documents.document_date` is `NULL` and the worker falls back to `date.today()`. Right fix is for the worker to refresh `document_date` from Paperless's API before processing.

**Notes:**
- Total today: 9 atomic feature/docs commits + 1 prior `docs/status.md` from 2026-05-09. Full test suite: 54 passed in 0.41s.
- Two real bugs surfaced during the session: existing test_worker.py imports the worker module directly, so the missing `vault_root` parameter was caught by tests; reportlab fixture generates clean PDFs whose embedded text Paperless's OCR pipeline preserves verbatim, so the regex-based extractor matched on first run.
- The Phase 2 worker only recognizes the fictional `Acme Power & Light` provider — real-utility bills correctly route to `status='pending_claude'` until Phase 6+ adds the Claude-fallback extractor.

## 2026-05-09

**Done:**
- Scaffolded the public reference repo (BRIEF, ARCHITECTURE, EVOLUTION, sample-vault skeleton, stubbed `src/`/`scripts/`/`tests/`).
- Committed Phase 1 substrate: Paperless-ngx, four-table SQLite sidecar schema, post-consume hook, worker skeleton with 60s poll loop.
- Relocated runtime data tree from `C:\plos-data\` to `G:\plos-data\` across `docker-compose.yml`, `.env.template`, and the README.
- Added `python-dotenv` and wired `load_dotenv()` into `scripts/init_db.py` and `python -m plos.worker` so `.env` actually populates `os.environ`.
- Made the Paperless host port configurable via `PAPERLESS_HOST_PORT` (default 8000); local instance runs on 8888.
- Added a Redis sidecar to docker-compose; recorded as a named exception in `ARCHITECTURE.md` and added an "Implementation reality" section to `EVOLUTION.md` explaining why the original "no Redis" intent didn't survive current Paperless-ngx.
- Fixed `scripts/post_consume_hook.py` shebang (`#!/usr/bin/env python3`) — without it Paperless's exec returned `OSError: [Errno 8] Exec format error` and aborted the consume task.
- Switched Paperless consumer to polling (`PAPERLESS_CONSUMER_POLLING=10`) because inotify events don't propagate through Windows + Docker Desktop bind mounts.
- Added `.gitattributes` pinning `*.py`/`*.sh` to LF so git's `core.autocrlf` on Windows can't reintroduce the shebang bug on a fresh clone.
- Rewrote the README Quickstart as numbered steps with explicit **Where:** (working directory) and **Why:** (purpose) per step; added **Or in Explorer:** alternatives where the GUI is genuinely easier; reduced the demo from two terminals to one.
- **Verified Phase 1 demo end-to-end:** PDF dropped via Explorer → Paperless OCR → SQLite row → worker log line.

**Next:**
- Set up the GitHub remote (`gh repo create steerave/plos-reference --public --source=. --remote=origin --push`) and push the 10-commit history.
- Begin Phase 2: one document type end-to-end (utility bill → frontmatter update → first Dataview dashboard) per `ARCHITECTURE.md` phasing.

**Notes:**
- Phase 1 verification surfaced two defects the unit tests couldn't catch (missing shebang masked by pytest importing the module directly; inotify-on-Windows-bind-mounts is environment-specific) plus one architectural assumption corrected (Redis is unavoidable with current Paperless-ngx).
- All 10 commits are local; remote setup happens immediately after this status entry.
