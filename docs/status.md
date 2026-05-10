# Project Status Log

## 2026-05-10

**Done:**

*Phase 2 (early session):*
- Locked Phase 2 design (electric utility bill end-to-end) in `~/.claude/plans/b-electric-smooth-sparrow.md`.
- Wrote Paperless REST client (`src/plos/paperless.py`), graduated-extractor registry, the Acme Power & Light extractor, the entity matcher, the atomic frontmatter merge writer, and the worker pipeline.
- Built deterministic reportlab PDF fixture at `tests/fixtures/sample_bills/build.py` + first Dataview dashboard at `examples/sample-vault/dashboards/properties.md`.
- Verified Phase 2 demo end-to-end on Windows and pushed all 9 Phase 2 commits.

*Phase 3 (mid session):*
- Phase 3-0 (628b7d4): worker refreshes `documents.document_date` from Paperless API at start of each pass — fixes the merge-contract freshness regression.
- Phase 3-1 (6343956): Mr. Cooper mortgage extractor + worker routing generalization (each extractor now exports `extract` + `route`; new `RouteResult` tuple).
- Phase 3-2 (4b104fd): First Davenport Bank statement extractor + first account entity + `dashboards/account-balances.md`.
- Phase 3-3 (64e679a): Beacon Software paystub extractor + first person entity + `dashboards/income.md` (composite routing key).
- Phase 3 docs close (e7f1b21): project CLAUDE.md "Phase 3 conventions" section.
- Verified Phase 3 live on Paperless: 4 PDFs through, all `status=done`, 23 `extracted_fields` rows, three entity types instantiated.

*Phase 4 (late session):*
- Phase 4-1 (544f437): `compile_this_week.py` — first compiled artifact in PLOS, shells out to `claude --print`, validates response shape, atomic write.
- Phase 4-1 hotfix (69b9e62): pass `encoding="utf-8"` to `subprocess.run` — Windows cp1252 codec couldn't encode the `→` source-provenance arrow.
- Phase 4b (f308ee3): `drain_pending_claude.py` — second use of `claude` CLI, structured JSON contract, `handler='claude'` for matched audit rows.
- Phase 4c (1d4a818): `corrections.md` + `import_corrections.py` + new `vault.apply_correction` + `entities.find_by_slug`.
- Verified all three Phase 4 demos live: `this-week.md` rendered (~12s), MidAmerican drain → 11 fields + proposed entity skeleton, Joe's birthdate locked via corrections (audit row landed cleanly).

*Tests:*
- Test count: 56 (start of day) → 167 (+111 across Phases 3 and 4). Suite under 1.1s.

**Next:**
- Phase 5 (MVP marker): `compiled/anomalies.md`, `compiled/tax-prep.md`, audit pass (verifies `sources_read:` matches body `→ /source/...` arrows), scheduling, `notifications.py` weekly digest, `indexer.py` vault indexer.

**Notes:**
- Claude Code CLI is now invoked from two places (compile pass + drain). The pattern: build manifest → shell `claude --print` with `encoding="utf-8"` → validate response → atomic write. Phase 5+ compile passes plug into this same shape.
- The corrections workflow piggybacks on `locked_fields:` — `vault.merge_frontmatter`'s existing skip logic handles them without a database lookup. SQLite `corrections` table is the source of truth for hand-lock vs correction-lock.
- `corrections.entity_id` is FK-constrained, so corrections for entities not yet seen by the worker apply to the vault but skip the audit row (logged at INFO).
- Two integration-only bugs found and fixed during live verification today: stale worker process holding old extractor registry (Phase 3), Windows cp1252 choking on `→` (Phase 4-1). The kind of thing pytest doesn't catch.

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
