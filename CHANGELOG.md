# Changelog

All notable changes to this repo are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows
[Semantic Versioning](https://semver.org/) once a release tag is cut.

Substantive entries land starting with Phase 1. The initial scaffold commit
is the baseline and is not enumerated below.

## [Unreleased]

### Fixed

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
