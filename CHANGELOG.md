# Changelog

All notable changes to this repo are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows
[Semantic Versioning](https://semver.org/) once a release tag is cut.

Substantive entries land starting with Phase 1. The initial scaffold commit
is the baseline and is not enumerated below.

## [Unreleased]

### Added

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
