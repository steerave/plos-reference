# Project Status Log

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
