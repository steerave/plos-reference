# Project Status Log

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
