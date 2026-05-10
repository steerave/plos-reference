# Changelog

All notable changes to this repo are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows
[Semantic Versioning](https://semver.org/) once a release tag is cut.

Substantive entries land starting with Phase 1. The initial scaffold commit
is the baseline and is not enumerated below.

## [Unreleased]

### Added

- **Phase 4 Slice 1 — `compiled/this-week.md` compile pass.** First
  compiled artifact in PLOS. New `python -m plos.compile_this_week`
  command builds a manifest of every entity index.md, every dashboard,
  and the previous compile output (if any), then shells out to the
  `claude` CLI (`--print` non-interactive mode) for priority reasoning,
  and atomically writes the rendered `this-week.md` per the format
  spec in `docs/artifact-templates.md`. Pure-AI implementation: Claude
  reads the whole manifest and produces the full markdown. Format-
  validation gate refuses to write if the response doesn't start with
  YAML frontmatter or is missing a required section heading — the
  existing artifact is preserved on bad output.
- Two demo deadline fields seeded in the sample vault:
  `insurance_renewal_date: 2026-05-22` on `123-main-davenport` and
  `drivers_license_expiry: 2026-05-15` on `joe`. Without these, the
  compile pass had nothing to surface; with them, the demo produces a
  cross-domain "this week" prioritisation.
- README quickstart gains a "Phase 4 Slice 1 (this-week compile pass)"
  section.

- **Phase 3 Slice 3 — Beacon Software pay stub extractor.** Fourth
  graduated extractor (`src/plos/extractors/graduated/paystub_beacon_software.py`)
  recognises a Beacon Software bi-weekly pay stub and routes it to the
  matching person entity by a (legal_name, employer_current) pair —
  the first composite routing key in the registry. Introduces the
  first **person** entity in the sample vault
  (`examples/sample-vault/source/people/joe/index.md`) and a new
  dashboard at `examples/sample-vault/dashboards/income.md` showing
  the latest pay stub + YTD gross per person. Sample fixture lands at
  `tests/fixtures/sample_bills/paystub_beacon_2026_04.pdf`.
- New entity matcher `entities.find_person_by_employer_and_name()`.
- README quickstart gains a "Phase 3 Slice 3 (pay stub)" section plus
  a closing "End of Phase 3" note that summarises the three-entity-type
  end-state demo.
- Pay-stub sensitivity classification (full/summary/metadata-only
  sidecar modes) is **deliberately deferred to Phase 4+**, per the
  architecture's deferred-features list. The Phase 3 extractor treats
  pay stubs like any other document; body redaction lands later.

- **Phase 3 Slice 2 — First Davenport Bank statement extractor.** Third
  graduated extractor (`src/plos/extractors/graduated/bank_statement_first_davenport.py`)
  recognises a First Davenport Bank monthly checking statement and routes
  it to the matching account entity via `account_number`. Introduces the
  first **account** entity in the sample vault
  (`examples/sample-vault/source/accounts/first-davenport-checking-4521/index.md`)
  and a new dashboard at `examples/sample-vault/dashboards/account-balances.md`
  showing the latest statement per account. Sample fixture lands at
  `tests/fixtures/sample_bills/bank_first_davenport_2026_04.pdf`.
- New entity matcher `entities.find_account_by_account_number()`.
- README quickstart gains a "Phase 3 Slice 2 (bank statement)" section.

- **Phase 3 Slice 1 — Mr. Cooper mortgage statement extractor.** Second
  graduated extractor (`src/plos/extractors/graduated/mortgage_statement_mr_cooper.py`)
  recognises a Mr. Cooper monthly statement and routes it to the matching
  property via a new `mortgage_loan_number` frontmatter field. The
  property dashboard at `examples/sample-vault/dashboards/properties.md`
  gains a second table for the latest mortgage statement per property.
  A new sample fixture (`tests/fixtures/sample_bills/mortgage_mrcooper_2026_04.pdf`)
  ships with the demo bundle.
- New entity matcher `entities.find_property_by_mortgage_loan_number()`
  alongside the existing electric-account matcher. Both go through a
  small shared `_find_in()` helper.
- README quickstart gains a "Phase 3 Slice 1 (mortgage statement)"
  section walking the demo end-to-end.

### Changed

- **Worker dispatch is now generic over extractor + routing key.** Every
  extractor module under `src/plos/extractors/graduated/` now exports
  both `extract(text, doc) -> dict | None` and
  `route(fields, vault_root) -> RouteResult`. The worker calls
  `module.route(...)` instead of any hardcoded matcher. A new
  `RouteResult(path, missing_key)` named tuple distinguishes
  "extractor matched but routing key wasn't extracted" from
  "routing key extracted but no entity in the vault matches it".
- `EXTRACTORS` is now a list of `(handler_name, module)` tuples;
  `dispatch` returns `(handler, module, fields)`. Adding a new extractor
  is still one import + one tuple entry; the only widening is that the
  module must now expose `route` alongside `extract`.
- The "no_account_in_extraction" review reason was generalised to
  `no_routing_key_in_extraction` since the registry now covers more
  than electric-account routing.
- The worker's `_ensure_property_entity` is now `_ensure_entity(conn,
  entity_type, domain, slug, wiki_path)`. Entity type and domain are
  derived from the matched index.md path via a small `_ENTITY_TYPE_FROM_DIR`
  mapping (`properties` -> property/properties, `accounts` -> account/finance,
  etc.) — Slice 2 and Slice 3 plug into this without further worker change.
- `tests/fixtures/sample_bills/build.py` now passes `invariant=1` to
  reportlab so regenerated PDFs are byte-deterministic across runs and
  `git diff` stays quiet between fixture rebuilds.
- The reference repo's sample property gains a `mortgage_loan_number`
  frontmatter field so the demo can route the new fixture against it.

### Fixed

- **Phase 4-1 hotfix:** `compile_this_week.run()` now passes
  `encoding="utf-8"` to `subprocess.run`. Without it, Windows defaults
  the stdin pipe to `cp1252`, which can't encode the `→` source-
  provenance arrow embedded in the prompt preamble (and likely in
  Claude's response too). Surfaced the first time the live demo
  ran on Windows: `UnicodeEncodeError: 'charmap' codec can't encode
  character '\\u2192'`. The wiring tests on Linux/macOS would not
  have caught it because their default codec is already UTF-8.

- **Phase 3-0:** worker now refreshes `documents.document_date` from the
  Paperless API at the start of each processing pass. Paperless's date
  detection runs asynchronously after consume, so the post-consume hook
  inserts the row with `document_date = NULL`. The previous worker fell
  back to `date.today()`, which made the merge contract's freshness rule
  ineffective for any field updated more than once on the same calendar
  day. The worker now calls `paperless.get_document(id)` once per
  document, pulls both `content` and `created_date` from the same
  response, and writes the date back to SQLite if the API has one.

### Added

- **Phase 2 substrate end-to-end:** graduated-extractor framework
  (`src/plos/extractors/registry.py` with the `extract(text, document)
  -> dict | None` contract), the first extractor for Acme Power & Light
  electric bills, an entity matcher that routes a bill to its property
  via `electric_account`, an atomic YAML-frontmatter merge writer, the
  first Dataview dashboard at `examples/sample-vault/dashboards/properties.md`,
  and a populated sample property (`123-main-davenport`) plus a
  reportlab-built sample bill PDF fixture (`tests/fixtures/sample_bills/`).
- Paperless REST client (`src/plos/paperless.py`) for fetching OCR'd
  document text — `get_document_text(paperless_id)` and `get_document(id)`.
- `DocumentMeta` dataclass — the lightweight bundle the worker passes to
  every extractor (paperless_id, paperless_url, document_date, correspondent).
- New env vars in `.env.template`: `PAPERLESS_API_TOKEN` (generate via
  Paperless UI → My Profile → API Auth Token) and `PLOS_VAULT_ROOT`
  (defaults to `examples/sample-vault`).
- `reportlab` and `responses` dev dependencies.
- `.gitattributes` binary marks for `*.pdf`, `*.png`, `*.jpg`, `*.jpeg`,
  `*.gif`, `*.zip` so autocrlf on Windows can't corrupt the test
  fixtures on a fresh clone.
- Phase 1 substrate: Paperless-ngx (Docker, SQLite backend) plus a
  `redis:7-alpine` sidecar, the four-table SQLite sidecar schema, the
  post-consume hook that records ingested documents, and a worker skeleton
  that polls every 60 seconds and logs each new document.
- `python-dotenv` dependency. `scripts/init_db.py` and `python -m plos.worker`
  now load `.env` at startup so `PLOS_DB_PATH` and friends populate
  `os.environ` automatically — no need to export them per shell.
- `PAPERLESS_HOST_PORT` env var lets you publish Paperless on a host port
  other than `8000` (e.g. `8888`) without editing `docker-compose.yml`.
  Defaults to `8000`; pair with a matching `PAPERLESS_URL_PUBLIC`.
- `scripts/init_db.py` for one-shot schema creation.
- `docker/docker-compose.yml` for a single-container Paperless setup with
  the host data tree under `G:\plos-data\`.
- Test suite covering the schema, the worker poll pass, and the hook contract.
- README "Quickstart" walks through the Phase 1 demo end-to-end.

### Changed

- `worker.run_one_pass(conn, vault_root)` now drains documents through
  the full Phase 2 pipeline — fetch OCR text, dispatch to extractors,
  match the entity, atomically merge into vault frontmatter, record one
  `extracted_fields` row per field, mark `documents.status`. Previously
  it only logged each new row.
- Document status taxonomy expanded:
  - `done` — extractor + entity match, vault written.
  - `pending_claude` — no graduated extractor recognized the document.
  - `needs_review` — extractor matched but no entity could be routed
    (sets `review_reason` to `no_account_in_extraction` or
    `unmatched_entity`).
  - `new` — left untouched on transient processing failure so the next
    poll cycle retries.
- Phase 1 substrate now includes a Redis sidecar. The original "no Redis"
  intent did not survive contact with current Paperless-ngx, which hard-
  requires Redis for the Django cache and Celery broker. `ARCHITECTURE.md`
  records Redis as a named exception; `EVOLUTION.md` gains an
  "Implementation reality" section explaining the correction.
- Paperless consumer switched from default inotify watching to polling
  (`PAPERLESS_CONSUMER_POLLING=10`). Inotify events do not propagate
  through Windows + Docker Desktop bind mounts, so files dropped on the
  host were never noticed. Polling visits the consume folder every 10s.

### Fixed

- `scripts/post_consume_hook.py` now starts with `#!/usr/bin/env python3`.
  Without the shebang, Paperless's exec of the hook returned
  `OSError: [Errno 8] Exec format error` and aborted the consume task
  before the SQLite row was inserted, so the worker never saw new
  documents. The unit tests imported the module directly and so missed
  the bug.
- New `.gitattributes` enforces LF line endings for `*.py` and `*.sh` so
  that git's default `core.autocrlf` on Windows can't silently revert
  the hook's shebang to CRLF on a fresh clone — that would reintroduce
  the same `Exec format error` inside the Linux container.
- Python package layout fixed to match `pyproject.toml`: code now lives at
  `src/plos/` so `pip install -e .` produces an importable `plos` package.
- `.gitignore` now excludes `.claude/settings.local.json` per the user's
  global standards.
- README Quickstart rewritten as numbered steps with explicit working
  directory ("Where:") and rationale ("Why:") for each step, including
  notes on which commands are single multi-line statements vs. one-at-a-time.
- README Quickstart now leads with the simplest path for each step and
  adds **Or in Explorer:** notes where a Windows GUI alternative is
  genuinely easier (folder creation, opening a terminal at the repo root,
  dragging the PDF into the consume folder, browsing the SQLite sidecar
  with DB Browser). The demo now requires only one terminal — the worker
  — instead of two.
