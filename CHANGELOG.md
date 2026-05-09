# Changelog

All notable changes to this repo are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows
[Semantic Versioning](https://semver.org/) once a release tag is cut.

Substantive entries land starting with Phase 1. The initial scaffold commit
is the baseline and is not enumerated below.

## [Unreleased]

### Added

- Phase 1 substrate: Paperless-ngx (Docker, SQLite backend, no Redis), the
  four-table SQLite sidecar schema, the post-consume hook that records
  ingested documents, and a worker skeleton that polls every 60 seconds and
  logs each new document.
- `scripts/init_db.py` for one-shot schema creation.
- `docker/docker-compose.yml` for a single-container Paperless setup with
  the host data tree under `G:\plos-data\`.
- Test suite covering the schema, the worker poll pass, and the hook contract.
- README "Quickstart" walks through the Phase 1 demo end-to-end.

### Changed

- Python package layout fixed to match `pyproject.toml`: code now lives at
  `src/plos/` so `pip install -e .` produces an importable `plos` package.
- `.gitignore` now excludes `.claude/settings.local.json` per the user's
  global standards.
