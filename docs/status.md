# Project Status Log

## 2026-05-11

**Done:**

*Phase 4 housekeeping:*
- fa42385: renamed `tests/fixtures/sample_bills/` → `sample_documents/`; broadened `.gitignore` to cover whole `.obsidian/`, whole `.claude/`, and generated `examples/sample-vault/compiled/`.

*Phase 5 — MVP marker complete:*
- Phase 5-1 (2294edf): `compile_anomalies.py` percentage-deviation heuristic; `ELIGIBLE_FIELDS` allowlist; empty-deviation short-circuit; three historical Acme bill fixtures so April's $142.37 fires at +29% against Jan–Mar baseline.
- Phase 5-2 (8af579c): expectation-gaps section in `anomalies.md` (no statement in currently-due calendar month); `EXPECTATION_FIELDS` allowlist; `PLOS_ANOMALIES_AS_OF` env override; combined short-circuit only when both lists empty.
- Phase 5-3 (3b44dfb): `compile_tax_prep.py` reads `source/tax/<year>/expected-documents.md` and partitions received/missing by the `received:` flag; tax-year auto-detect from US filing calendar; `PLOS_TAX_YEAR` env override; sample vault seeded with 2026 inventory.
- Phase 5-4 (b468c8c): `audit_pass.py` flags drift between `sources_read:` frontmatter and body `→ /source/...` arrows across all three v1 artifacts; categories undeclared/unused/nonexistent citation; writes `_review/audit-report.md`.
- Phase 5-5 (aee8911): `notifications.py` weekly-digest delivery layer via stdlib `smtplib` over STARTTLS; dry-run by default; v1 ships one section (recent activity over past 7 days with routing entity + status).
- Phase 5-6 (ce220ef): `indexer.py` review-queue self-cleaner + `_review/queue.md` renderer; new `'resolved'` status flips when proposed entity gets created in `source/`.
- Phase 5-7 (ec8a2f7, f530ad2, 3166678): `scripts/scheduled_run.py` wrapper + new `scheduled_runs` SQLite table; `install_schedules.ps1` registers 6 PLOS_* tasks via Schedule.Service COM API; companion `uninstall_schedules.ps1` and `enable_logged_off.ps1`.

*Live verification:*
- All 6 PLOS_* Windows Task Scheduler tasks registered and in Ready state; fired PLOS_audit_pass through Start-ScheduledTask and confirmed a `scheduled_runs` row landed with `exit_status='success'`.
- Demoed each compile pass against the user's real Paperless instance: this-week (12s), anomalies (+29% utility deviation + bank-statement May gap), tax-prep (2-of-5 received).
- Cleaned the real MidAmerican bill (paperless_id=3) from Paperless via API DELETE + SQLite row removed; `_review/queue.md` re-rendered empty.

*Tests:*
- 167 (start of day) → 307 (+140 across Phase 5 slices). Suite still under 2s.

**Next:**
- Decide deployment path: (A) iterate further on the public reference repo with the sample vault; (B) stand up the private operating-instance repo with a real-household vault, point `.env` at it; (C) plan the basement-server deployment for long-term hosting.
- `.env.template` needs the SMTP env-var keys added — permission-denied to Claude, user applies manually.
- `enable_logged_off.ps1` ready but not yet run; flip to unattended only when basement / operating instance picture is settled.
- Anomalies Slice 3 (unexpected charges) deferred from Phase 5 — needs transaction-level ingestion (bank extractor emits only summary fields today).

**Notes:**
- Phase 5 (MVP marker) is complete. The v1 architecture ships end-to-end: hot-path extractors → Claude long-tail drain + corrections → three compiled artifacts → audit pass → weekly digest → review-queue self-cleaner → scheduling. 7 commits today.
- The public reference repo and the private operating-instance repo are deliberately separate (per top-level CLAUDE.md). The fictional sample vault is the only vault here; real household data routing requires standing up the operating instance, which doesn't yet exist.
- Two parser traps fixed today: schtasks.exe CLI doesn't round-trip embedded quotes through PowerShell when the repo path contains spaces (fixed by switching install_schedules.ps1 to Schedule.Service COM API — `RegisterTaskDefinition` takes structured objects, no CLI reparsing); em-dash chars in .ps1 files break PowerShell's parser via cp1252 misread (same trap as Phase 4-1's arrow). Standardised on ASCII hyphens in all .ps1 files.
- Real personal data hygiene precedent: when test runs land actual household docs in Paperless, the cleanup path is Paperless API DELETE + matching SQLite row delete + indexer re-render. All three need to happen for the data to be fully gone.

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
