# PLOS — Personal Life Operating System

> Self-hosted document pipeline that turns physical mail, email attachments, and digital files into a structured, searchable, interlinked knowledge base in Obsidian. Built for a single household. Not a product, not a SaaS.

**Status:** Pre-implementation. Architecture and design docs complete; codebase is stubbed.

## Read this first

This repo is the public reference for PLOS. Three documents at the root tell you everything:

1. **[BRIEF.md](./BRIEF.md)** — what this is and why it exists *(start here)*
2. **[ARCHITECTURE.md](./ARCHITECTURE.md)** — the v2.5 reference architecture
3. **[EVOLUTION.md](./EVOLUTION.md)** — how the architecture got to its current shape *(the most distinctive doc in the repo)*

## What's in this repo

- **Reference docs** — `BRIEF.md`, `ARCHITECTURE.md`, `EVOLUTION.md`, eventually `METHODOLOGY.md`.
- **Supporting docs** — `docs/` holds reference material: recurring-question inventory, artifact templates, source-layer entity shapes.
- **Sample vault** — `examples/sample-vault/` holds the fictional household used for demos and tests. Currently structural only; populated incrementally during Phases 2–5.
- **Codebase** — `src/`, `scripts/`, `tests/`. Stubbed; implementation begins from Phase 1.

## Quickstart — Phase 1 substrate demo

End-to-end loop: drop a PDF into Paperless, see it OCR'd, see the row land in SQLite, see the worker log it. No vault writes yet — that's Phase 2.

### Prerequisites

- Windows 11 with **Docker Desktop running**.
- **Drive `G:` enabled in Docker Desktop file sharing** (Settings → Resources → File sharing). The runtime data tree lives there. If you'd rather use a different drive, change every `G:\plos-data\` path in `docker\docker-compose.yml` to match.
- Python 3.11+ on `PATH`.
- A PowerShell window. All commands below are PowerShell.
- ~5 minutes.

### One-time setup

Do these steps in order. Run them all from a **single PowerShell window** — the working directory and the activated virtualenv carry forward from one step to the next.

Some steps are easier in Windows Explorer than the terminal. Look for the **Or in Explorer:** notes under each step where there's a clean GUI alternative. The terminal commands are still given as the primary path because they're copy-pasteable and let you do the whole setup in one window.

#### Step 1 — Clone the repo

**Where:** any folder you keep code in (e.g. `C:\Users\<you>\Desktop\`).

```powershell
git clone https://github.com/<you>/plos-reference.git
cd plos-reference
```

**Or in Explorer:** clone with GitHub Desktop or any Git GUI, then open the resulting `plos-reference` folder in Explorer, hold **Shift** and right-click an empty area inside the folder, and pick **Open in Terminal** (Windows 11) or **Open PowerShell window here** (Windows 10). That gives you a PowerShell window already at the repo root — no `cd` needed.

**Why:** Every later step assumes your working directory is the repo root (`...\plos-reference`). The `cd` puts you there.

#### Step 2 — Create the runtime data tree

**Where:** doesn't matter — the paths are absolute.

```powershell
mkdir G:\plos-data\paperless\data, G:\plos-data\paperless\media, `
      G:\plos-data\paperless\consume, G:\plos-data\paperless\export, `
      G:\plos-data\plos
```

**This is a single PowerShell command.** The backticks (`` ` ``) at the end of lines are line continuations. Paste the whole three-line block at once.

**Or in Explorer:** open `G:\` in Explorer and create the folder tree by hand — `plos-data\paperless\data`, `plos-data\paperless\media`, `plos-data\paperless\consume`, `plos-data\paperless\export`, and `plos-data\plos`. End state is identical; the terminal command is just faster to type.

**Why:** Paperless and the worker write constantly — OCR'd PDFs, thumbnails, a search index, the Paperless DB, and the PLOS SQLite sidecar. Keeping all of that on `G:\plos-data\` (outside the repo) means `git status` stays clean and household documents never get committed by accident.

#### Step 3 — Create your environment file

**Where:** repo root.

```powershell
copy .env.template .env
```

**Stick with the terminal here.** Explorer hides dotfiles by default and renaming a copy to start with a `.` is fiddly — the `copy` command is genuinely the easier path for this one.

**Why:** `.env` holds secrets — Paperless admin credentials and a signing key. It is gitignored. `.env.template` lists the required keys with empty values; copying it gives you a starting `.env` without exposing secrets to git.

#### Step 4 — Edit `.env`

Open `.env` in any text editor — Notepad, Notepad++, VS Code, whatever you have. It's a plain key=value file, no special syntax. Set values for:

- `PAPERLESS_ADMIN_USER` — pick a username for the Paperless admin account.
- `PAPERLESS_ADMIN_PASSWORD` — pick a password.
- `PAPERLESS_SECRET_KEY` — 50+ random characters. Paperless uses it to sign session cookies.

**Optional but common:**

- `PAPERLESS_HOST_PORT` — host port Paperless is published on. Defaults to `8000`. Change it (e.g. to `8888`) if `8000` is already in use on your machine. If you change it, also update `PAPERLESS_URL_PUBLIC` to match (e.g. `http://localhost:8888`) so Paperless's CSRF protection accepts requests from the browser URL.

**Why:** Paperless reads these on first boot to create your admin login. The container will fail to start if `PAPERLESS_SECRET_KEY` is missing or trivially short. The host-port knob lets you avoid collisions with anything else already bound to `8000`.

#### Step 5 — Install Python dependencies and initialize the SQLite schema

**Where:** repo root.

Run these **one line at a time** — each depends on the previous one finishing:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python scripts\init_db.py
```

**Why each line:**

- `python -m venv .venv` creates an isolated Python environment in `.venv\` so project deps don't pollute system Python.
- `.venv\Scripts\activate` switches the shell into that environment. Your prompt will gain a `(.venv)` prefix — that's how you know it worked.
- `pip install -e ".[dev]"` installs the project as an editable package plus dev tools (pytest, etc.).
- `python scripts\init_db.py` creates the four-table SQLite sidecar at `G:\plos-data\plos\plos.db`.

#### Step 6 — Start Paperless

**Where:** repo root.

```powershell
docker compose -f docker\docker-compose.yml --env-file .env up -d
```

This brings up two containers: `plos-paperless` and `plos-redis`. After this first `up -d` creates them, you can start/stop them later from the Docker Desktop UI (Containers tab) — no need to retype the command unless you change the compose file or `.env`.

**Why:** Starts the Paperless-ngx container plus its required Redis sidecar in the background. `-f docker\docker-compose.yml` points at the compose file in the `docker\` subfolder; `--env-file .env` feeds the admin/secret values into the container; `-d` runs it detached so your shell is free.

#### Step 7 — Verify Paperless is up

Open `http://localhost:<PAPERLESS_HOST_PORT>` in a browser — `http://localhost:8000` if you kept the default, or whatever port you set in Step 4. Log in with the credentials you set in Step 4. You should see an empty document list.

**Why:** Confirms Paperless booted, the secret key is valid, and your admin account exists. If the page won't load, check `docker compose -f docker\docker-compose.yml logs paperless`.

### Run the demo

You only need **one PowerShell window** (for the worker, so you can watch its log output). The "drop a PDF" half is just a file landing in a folder — Explorer is the natural way to do it.

#### Action 1 — start the worker (PowerShell)

**Where:** repo root. If you closed the setup window, open a new PowerShell at the repo root (Shift+Right-click in the folder → **Open in Terminal**) and run **one line at a time**:

```powershell
.venv\Scripts\activate
python -m plos.worker
```

Leave this window open. The worker polls every 60 seconds and prints a log line for each new document.

**Why:** The worker watches the SQLite `documents` table for rows the post-consume hook adds when Paperless ingests a file. In Phase 1 it just logs them; later phases will route them to extractors.

#### Action 2 — drop a PDF into the consume folder (Explorer)

Open `G:\plos-data\paperless\consume\` in Windows Explorer and drag any PDF into it. Save-from-browser, scan-to-folder, or right-click → Send To also work — Paperless watches the folder for any new file regardless of how it arrives.

**Or in a terminal**, if you'd rather script it:

```powershell
copy C:\path\to\some.pdf G:\plos-data\paperless\consume\
```

**Why:** Paperless watches `consume\`. When a file finishes writing, it OCRs and files it, then runs the post-consume hook that writes a row into the PLOS SQLite sidecar.

### What success looks like

Within ~30 seconds, all three should be true:

1. **In Paperless (browser at `http://localhost:<PAPERLESS_HOST_PORT>`)** — the document appears in the document list, OCR'd.
2. **In SQLite (`G:\plos-data\plos\plos.db`)** — a new row in the `documents` table with `status='new'`, then `'done'`. Open the `.db` file with [DB Browser for SQLite](https://sqlitebrowser.org/) (free, point-and-click) to peek inside without writing any SQL — easier than the `sqlite3` CLI for one-off checks.
3. **In the worker window** — a log line of the form `new document id=1 paperless_id=1 title='some.pdf'`.

That's the Phase 1 demo. Phase 2 adds the first extractor and writes to the vault.

## Quickstart — Phase 2 demo

End-to-end loop: drop a fictional electric bill into Paperless, watch the worker pull the OCR text, recognize the bill, look up the matching property, atomically write the extracted fields into the property's `index.md` frontmatter, then open a Dataview dashboard in Obsidian and see the new value rendered live.

This builds on Phase 1 — Paperless, Redis, and the SQLite sidecar from the Phase 1 demo are still required.

### Prerequisites (in addition to Phase 1)

- A Paperless API token. Generate one in the Paperless UI: top-right avatar → **My Profile** → next to *API Auth Token*, click *Show* (or *Regenerate* if needed). Copy the value.
- Obsidian, with the [Dataview plugin](https://blacksmithgu.github.io/obsidian-dataview/) installed and enabled, opened on `examples/sample-vault/` as the vault. The dashboard renders as a live table inside Obsidian; without Dataview it shows as a code block.

### One-time setup

#### Step 1 — Add the new env vars to `.env`

Open `.env` in any text editor and set:

- `PAPERLESS_API_TOKEN` — paste the token from the Prerequisites step.
- `PLOS_VAULT_ROOT` — leave as `examples/sample-vault` for the demo, or point at your own vault.

**Why:** The worker uses the API token to fetch each document's OCR'd text. `PLOS_VAULT_ROOT` tells the worker which vault to write into.

#### Step 2 — Pull the new dependencies

**Where:** repo root, with `(.venv)` active.

```powershell
pip install -e ".[dev]"
```

**Why:** Phase 2 added `python-dotenv` (already wired in Phase 1) plus dev-only `reportlab` (for the sample-bill builder) and `responses` (HTTP mocking in tests).

#### Step 3 — Restart the worker

If you have a Phase 1 worker running, stop it (`Ctrl+C` in its terminal) and start the Phase 2 one:

```powershell
.venv\Scripts\activate
python -m plos.worker
```

You should see a startup line like `worker started — polling every 60s, vault_root=...`. The vault_root tells you exactly which folder the worker will write into.

### Run the demo

#### Action 1 — drop the sample electric bill

Drag `tests\fixtures\sample_documents\electric_acme_2026_04.pdf` into `G:\plos-data\paperless\consume\`. (Or run `python tests\fixtures\sample_documents\build.py` first to regenerate it from scratch.) The bill is for Acme Power & Light, account `ACCT-12345`, $142.37 due 2026-04-30, 850 kWh — the same account number the sample property at `examples/sample-vault/source/properties/123-main-davenport/index.md` already declares.

#### Action 2 — watch the worker pick it up

Within ~30 seconds the worker prints:

```
extracted id=N paperless_id=M extractor=graduated:utility_bill_electric property=123-main-davenport changed=['data_effective_date', 'electric_account', 'last_utility_bill_amount', 'last_utility_bill_date', 'last_utility_bill_kwh', 'last_utility_bill_url'] status=done
```

(Field names will be in alphabetical order.)

### What success looks like

Three places to check:

1. **In the property's `index.md`** — open `examples/sample-vault/source/properties/123-main-davenport/index.md`. The frontmatter now has:
   - `last_utility_bill_amount: 142.37`
   - `last_utility_bill_date: 2026-04-30`
   - `last_utility_bill_kwh: 850`
   - `last_utility_bill_url: http://localhost:8888/documents/<M>/`
   - `data_effective_date: 2026-04-30`
2. **In Obsidian, on `examples/sample-vault/dashboards/properties.md`** — the Dataview table renders one row for the property, with the bill amount, kWh, and a clickable Source link back to Paperless.
3. **In SQLite** — `extracted_fields` has five rows for the bill (one per extracted field), each with `handler='graduated:utility_bill_electric'`. The `entities` table has a row for `123-main-davenport`.

That's the Phase 2 demo. Phase 3 adds mortgage statements, bank statements, and pay stubs — each in its own vertical slice with its own demo. Phase 4 introduces the first compiled artifact (`this-week.md`).

## Quickstart — Phase 3 Slice 1 (mortgage statement)

Same setup as Phase 2 — Paperless + Redis + worker + the sample vault. The new extractor is wired into the registry alongside the electric one, so the running worker picks it up automatically (restart not required if it was started after the slice landed).

#### Action — drop the sample mortgage statement

Drag `tests\fixtures\sample_documents\mortgage_mrcooper_2026_04.pdf` into `G:\plos-data\paperless\consume\`. (Or run `python tests\fixtures\sample_documents\build.py` to regenerate it from scratch — output is byte-deterministic so re-running is safe.) The statement is for Mr. Cooper, loan number `LN-9912345`, principal balance $284,237.18, total amount due $2,452.72, statement date 2026-04-15 — the same loan number the sample property declares as `mortgage_loan_number` in its frontmatter.

### What success looks like

1. **In the property's `index.md`** — `examples/sample-vault/source/properties/123-main-davenport/index.md` frontmatter now also has:
   - `last_mortgage_statement_amount: 2452.72`
   - `last_mortgage_statement_principal_balance: 284237.18`
   - `last_mortgage_statement_date: 2026-04-15`
   - `last_mortgage_statement_url: http://localhost:8888/documents/<M>/`
   - `data_effective_date` advances to 2026-04-15 (or stays at the most recent ingested document's date, whichever is later — see the merge contract in `CONVENTIONS.md`).
2. **In Obsidian, on `examples/sample-vault/dashboards/properties.md`** — the dashboard now has two tables. The mortgage table renders a row for `123-main-davenport` with the servicer, total due, principal balance, and a Source link back to Paperless.
3. **In SQLite** — `extracted_fields` gains five new rows for the mortgage statement, each with `handler='graduated:mortgage_statement_mr_cooper'`.

Drop both the electric bill and the mortgage statement and the property's frontmatter accumulates both sets of fields without conflict — they target different keys, both extractors share one entity, and the merge contract orders them by document date.

## Quickstart — Phase 3 Slice 2 (bank statement)

This slice introduces the first **account** entity and the second new dashboard. Same Paperless + worker substrate as Phase 2; no env-var changes.

#### Action — drop the sample bank statement

Drag `tests\fixtures\sample_documents\bank_first_davenport_2026_04.pdf` into `G:\plos-data\paperless\consume\`. The statement is for First Davenport Bank, account `ACCT-4521` (the checking account at `examples/sample-vault/source/accounts/first-davenport-checking-4521/index.md`), statement period 2026-03-16 → 2026-04-15, ending balance $16,529.74.

### What success looks like

1. **In the account's `index.md`** — `examples/sample-vault/source/accounts/first-davenport-checking-4521/index.md` frontmatter gains:
   - `last_statement_balance: 16529.74`
   - `last_statement_end_date: 2026-04-15`
   - `last_statement_deposits: 5420.0`
   - `last_statement_withdrawals: 3128.66`
   - `last_statement_url: http://localhost:8888/documents/<M>/`
2. **In Obsidian, on `examples/sample-vault/dashboards/account-balances.md`** — a Dataview table renders the row for the checking account with the latest balance and a Source link back to Paperless.
3. **In SQLite** — `extracted_fields` gains six new rows for the statement, each with `handler='graduated:bank_statement_first_davenport'`. The `entities` table gains a row for `first-davenport-checking-4521` with `type='account'`, `domain='finance'`.

## Quickstart — Phase 3 Slice 3 (pay stub)

This slice introduces the first **person** entity — `examples/sample-vault/source/people/joe/index.md` — and the third new dashboard. Same Paperless + worker substrate; no env-var changes.

#### Action — drop the sample pay stub

Drag `tests\fixtures\sample_documents\paystub_beacon_2026_04.pdf` into `G:\plos-data\paperless\consume\`. The stub is for *Joe Sample* employed at *Beacon Software*, period ending 2026-04-14, gross $4,615.38, net $3,145.28, YTD gross $36,923.04. The same `legal_name` + `employer_current` pair appears on the new sample person record.

### What success looks like

1. **In Joe's `index.md`** — `examples/sample-vault/source/people/joe/index.md` frontmatter gains:
   - `last_paystub_gross: 4615.38`
   - `last_paystub_net: 3145.28`
   - `last_paystub_ytd_gross: 36923.04`
   - `last_paystub_period_end: 2026-04-14`
   - `last_paystub_url: http://localhost:8888/documents/<M>/`
2. **In Obsidian, on `examples/sample-vault/dashboards/income.md`** — a Dataview table renders one row showing the latest pay stub plus YTD gross.
3. **In SQLite** — `extracted_fields` gains seven new rows (gross, net, period end, url, employee name, employer, YTD gross) with `handler='graduated:paystub_beacon_software'`. The `entities` table gains a row for `joe` with `type='person'`, `domain='family'`.

### End of Phase 3

Drop all three Phase 3 PDFs (mortgage, bank, paystub) plus the Phase 2 electric bill in `consume/` and watch four extractors route four documents onto three different entity types — property, account, person — through one generic worker. The architecture's "one extractor file + one entry" claim now has three more receipts.

## Quickstart — Phase 4 Slice 1 (this-week compile pass)

The first **compiled artifact** lands here. Phase 4 Slice 1 adds `python -m plos.compile_this_week` — a Python script that builds a manifest of every entity index.md, every dashboard, and the previous compile output, then shells out to the `claude` CLI for priority reasoning and atomically writes `compiled/this-week.md` answering the cross-cutting question "What needs my attention this week?"

### Prerequisites (in addition to Phase 2)

- The `claude` CLI on `PATH` (you're using Claude Code already, so this is just `where.exe claude` returning a path).
- The sample vault has two seeded deadline fields: `insurance_renewal_date: 2026-05-22` on `123-main-davenport`, `drivers_license_expiry: 2026-05-15` on `joe`. These give the compile pass cross-domain content to prioritise. The actual operating instance would carry many more such fields per entity.

### Run the compile pass

**Where:** repo root, with the venv active.

```powershell
python -m plos.compile_this_week
```

The script prints two log lines (`invoking claude --print (manifest length: N chars)` and `wrote ...this-week.md`) and exits in 5–15s.

### What success looks like

1. **`examples/sample-vault/compiled/this-week.md` exists** with valid YAML frontmatter (`type: compiled`, `artifact: this-week`, `refreshed: <ISO timestamp>`, `sources_read:` listing every cited path, `compile_pass_version: 1`).
2. **Four sections present:** `Must do`, `Should do`, `Watching`, and (if any dates are within 7 days) `Birthdays / dates this week`.
3. **Both seeded items appear, prioritised:**
   - Joe's drivers license expiring May 15 (4 days from compile time today) → **Must do**.
   - 123 Main's State Farm renewal on May 22 (11 days out) → **Should do** or **Watching**.
4. **Each item has a `→ /source/...` provenance arrow** that resolves to a real file in the sample vault.
5. **Footer line:** `*Generated by daily compile pass. To regenerate: \`compile this-week\`.*`
6. **Re-running** advances the `refreshed` timestamp; content is qualitatively similar (pure AI means it won't be byte-identical, and that's fine).

### What this does *not* do (deferred)

- Compile-pass scheduling. Cron/Task Scheduler integration is Phase 5.
- `corrections.md` + `import_corrections.py` flow. Phase 4c.
- The other two compiled artifacts (`anomalies.md`, `tax-prep.md`). Phase 5.

## Quickstart — Phase 4b (pending_claude drain)

The graduated extractors (Phases 2-3) handle four fictional providers — Acme Power & Light, Mr. Cooper, First Davenport Bank, Beacon Software. Real-world bills that don't match any of them route to `documents.status='pending_claude'` and wait. Phase 4b drains the queue.

#### Action — run the drain

```powershell
python -m plos.drain_pending_claude
```

The script walks every `pending_claude` row in SQLite, shells out to `claude --print` per document with the OCR text plus every entity index.md as context, and asks for structured JSON back. It then either:

- **Matched:** merges Claude's extracted fields into the matched entity's `index.md` via the standard merge contract; sets `documents.status='done'`; records the audit trail in `extracted_fields` with `handler='claude'`.
- **Unmatched entity:** marks `needs_review` and JSON-encodes Claude's full proposal (extracted fields + proposed entity skeleton + rationale) into `documents.review_reason` for later human triage. The vault is not touched.
- **Unrecognized:** marks `needs_review` with `review_reason='claude_unrecognized'`.

Per ARCHITECTURE.md, this script never autonomously creates new entity files — entity creation always remains a human-reviewed step. Claude *proposes*; a human applies.

### What success looks like

Pre-existing `pending_claude` rows in SQLite get processed. The MidAmerican bill from Phase 2 (`paperless_id=3` in the user's local instance) is the natural live test: Claude extracts the gas/electric fields, but since the sample vault doesn't have a property the bill belongs to, it lands as `needs_review` with the proposal recorded. A summary line at exit reports counts (`{'done': N, 'needs_review': M, 'errored': 0}`).

### What this does *not* do (deferred)

- Auto-create new entity files from Claude's proposals. Phase 5+ stands up the formal review-queue surface and the human-in-the-loop apply step.
- Render `_review/queue.md` in the vault. Phase 5.

## Quickstart — Phase 4c (corrections override)

The merge contract says **corrections always win** — they outrank both fresh extractions and the freshness rule itself. Phase 4c gives you the surface to add them: `examples/sample-vault/corrections.md` carries a YAML list of `{slug, field, value, source, reason}` entries; `python -m plos.import_corrections` applies them.

#### Action — add a correction and import

Edit `examples/sample-vault/corrections.md` and add an entry to the `corrections:` frontmatter list. Example:

```yaml
---
type: corrections
corrections:
  - slug: 123-main-davenport
    field: last_utility_bill_amount
    value: 142.99
    source: 'http://localhost:8888/documents/4/'
    reason: 'OCR misread the cents column on the April Acme bill.'
---
```

Then run:

```powershell
python -m plos.import_corrections
```

The script logs one line per applied entry and a final summary like `import_corrections complete: {'applied': 1, 'no_entity': 0, 'errored': 0}`.

### What success looks like

1. **Entity frontmatter updated.** Open `examples/sample-vault/source/properties/123-main-davenport/index.md`; `last_utility_bill_amount` is now 142.99 (or whatever you chose).
2. **Field locked.** The same file's `locked_fields:` list now contains the field name. Future Acme bill processing will *not* overwrite it — `vault.merge_frontmatter` skips locked fields by design.
3. **SQLite audit row.** The `corrections` table has one row per `(entity_id, field_name)` pair with the corrected value and timestamp.
4. **Idempotent.** Re-running the script produces the same state — no duplicate audit rows, no unnecessary file writes.

### What this does *not* do (deferred)

- **Sync mode (remove corrections).** v1 is append-only — removing an entry from `corrections.md` does not undo the correction. To remove it manually: edit the entity's `index.md` to remove the field from `locked_fields:` and reset its value, then `DELETE FROM corrections WHERE entity_id=? AND field_name=?` in SQLite. Phase 5+ may automate.
- **Cross-correction conflict detection.** Adding two corrections for the same entity+field with different values applies them in file order (the second overwrites the first on import). No warning is emitted.
- **Auto-validation that the field name is sensible** (e.g. "did you typo `electic_account`?"). The script writes whatever you ask.

## Quickstart — Phase 5 Slice 1 (anomalies compile pass)

The second **compiled artifact** lands here. `python -m plos.compile_anomalies` walks the SQLite audit trail, identifies recurring numeric fields whose latest value deviates by more than 20% from a baseline of their prior three values, and shells out to the `claude` CLI to render a human-readable `compiled/anomalies.md`. **Statistics in Python, prose in Claude** — the deviation math is deterministic; Claude only renders the resulting list.

This slice ships only the percentage-deviation heuristic. The full anomalies spec (expectation gaps + unexpected charges) lands in Slices 2–3 under the same artifact.

### Prerequisites (in addition to Phase 4)

- `tests\fixtures\sample_documents\` now emits four Acme bills (Jan/Feb/Mar/Apr 2026) instead of one. Re-run `python tests\fixtures\sample_documents\build.py` to materialise them; the existing April PDF is byte-identical to before.
- The sample property `123-main-davenport` is already wired for Acme; no entity-level changes are needed.

### Action — regenerate fixtures, consume, and compile

```powershell
# 1. Materialise the historical Acme bills (idempotent; the April one is unchanged).
python tests\fixtures\sample_documents\build.py

# 2. Drop all four Acme bills into Paperless consume/
copy tests\fixtures\sample_documents\electric_acme_2026_*.pdf G:\plos-data\paperless\consume\

# 3. Run the worker until all four lines show status=done (one pass usually catches them all).
python -m plos.worker

# 4. Run the anomalies compile pass.
python -m plos.compile_anomalies
```

The script logs two lines (`invoking claude --print (N deviations, manifest length: M chars)` and `wrote ...anomalies.md`) and exits in 5–15s.

### What success looks like

1. **SQLite has four rows for `last_utility_bill_amount`** on the `123-main-davenport` entity in `extracted_fields`, each with a distinct `source_document_date` spanning Jan–Apr 2026.
2. **`examples/sample-vault/compiled/anomalies.md` exists** with valid YAML frontmatter (`type: compiled`, `artifact: anomalies`, `refresh_cadence: monthly`, `compile_pass_version: 1`, `sources_read:` listing the cited path).
3. **A `## Spending deviations` section** with one bullet citing `123-main-davenport`'s utility bill amount, the current value (~$142.37), the 3-month baseline mean (~$110.07), and a percentage delta of ~+29%.
4. **A `→ /source/properties/123-main-davenport/index.md` arrow** under the bullet pointing to the entity.
5. **Re-running with no new data** is safe — the deterministic empty-deviation short-circuit only fires when nothing crosses the 20% threshold; otherwise Claude re-renders the same fact-set in qualitatively similar prose.

### What this does *not* do (deferred)

- **Unexpected-charges section** (transaction with no matching subscription). Slice 3.
- **Audit pass** against `sources_read:` vs body `→ /source/...` arrows. Still deferred until all three artifacts ship.
- **Compile-pass scheduling.** Still manual via `python -m plos.compile_anomalies`. Phase 5 plumbing slice.

## Quickstart — Phase 5 Slice 2 (expectation gaps)

Slice 2 adds the second heuristic to `compiled/anomalies.md`: **expectation gaps** — recurring monthly statements that didn't arrive for the currently-due calendar month. Same compile pass, new section.

Cadence is implicit: any `(entity, field)` pair in `EXPECTATION_FIELDS` (`last_utility_bill_amount`, `last_mortgage_statement_amount`, `last_statement_balance`) with at least one historical `extracted_fields` row is treated as "expected to keep arriving monthly." No new entity frontmatter required.

A gap fires when:
- The `GRACE_DAY` (20th) of a calendar month has passed.
- That month is the "currently due" month — the most recent month whose 20th has elapsed.
- No row exists for the `(entity, field)` pair with `source_document_date` in that month.

### Prerequisites (in addition to Slice 1)

- The four Slice 1 Acme bills already in SQLite (Jan/Feb/Mar/Apr → April-current at `2026-05-10`).
- The Phase 3 mortgage + bank fixtures already consumed (most-recent rows at `2026-05-01` for mortgage, `2026-03-16` for bank).

### Action — override "today" via env var, run the compile pass

```powershell
# Pin "today" to 2026-05-21 so May 20 has passed → May is the currently-due month.
$env:PLOS_ANOMALIES_AS_OF = "2026-05-21"
python -m plos.compile_anomalies

# Clear the override when you're done so subsequent runs use the real date.
Remove-Item Env:PLOS_ANOMALIES_AS_OF
```

The log line now reports `(N deviations, M gaps, manifest length: K chars)`.

### What success looks like

With `PLOS_ANOMALIES_AS_OF=2026-05-21`:

1. **`compiled/anomalies.md` has two populated sections.**
2. **`## Spending deviations`** — same +29% bullet from Slice 1 (April Acme bill vs Jan/Feb/Mar baseline).
3. **`## Expectation gaps`** — one bullet citing the **First Davenport checking account**, last seen `2026-03-16`, expected month `2026-05`, 1 day overdue. Utility (last seen 2026-05-10) and mortgage (last seen 2026-05-01) both have May rows, so they don't gap.
4. **Provenance arrows** under both bullets point to the cited entity index.md files.
5. **`sources_read:`** lists both cited paths.

### Empty-state behaviour

When both lists are empty (no deviations, no gaps), `run` short-circuits and writes a deterministic "no deviations / no missing statements" artifact without invoking Claude. Cheap, reproducible, still emits the full frontmatter contract and both section headings.

### What this does *not* do (deferred)

- **Per-entity expected-cadence frontmatter.** Slice 2 infers cadence from history. Slice 2+ may add an explicit override (e.g., `expected_statements:` list, or `not_expected: [field, ...]` opt-out).
- **Biweekly cadences.** Paystubs (Beacon) don't participate in gap detection; they'd require a non-monthly heuristic. Future slice if it matters.
- **Multi-month gap accumulation.** Slice 2 flags only the currently-due month per `(entity, field)`. Older missed months that were flagged in earlier passes and never resolved are not re-flagged. The audit-pass story (later Phase 5) is the right place for that history.
- **Unexpected-charges section** for `anomalies.md`. Requires transaction-level ingestion + a subscription registry. Future slice.

## Quickstart — Phase 5 Slice 3 (tax-prep compile pass)

The **third and final v1 compiled artifact** lands here. `python -m plos.compile_tax_prep` reads a per-year inventory file at `source/tax/<year>/expected-documents.md`, partitions its entries into received vs. missing by the `received: bool` flag, and shells out to the `claude` CLI to render a human-readable `compiled/tax-prep.md`. Same statistics-in-Python / prose-in-Claude split as `anomalies.md`.

### Prerequisites

- The sample vault now ships `examples/sample-vault/source/tax/2026/expected-documents.md` with five demo entries (W-2, 1098, 1099-INT, property tax, charitable receipts). Two are marked `received: true`; three are missing.
- Two stub `received/` files at `examples/sample-vault/source/tax/2026/received/` so the artifact's provenance arrows point to real files.

### Tax-year resolution

The compile pass auto-detects the active tax year from today's UTC date:

- **Jan–Apr** → previous calendar year (the filing window).
- **May–Dec** → current calendar year (the collection window).

Override with the `PLOS_TAX_YEAR` env var (`YYYY`). Malformed values raise.

### Action — run the compile pass

```powershell
# Today is 2026-05-10 → active tax year auto-resolves to 2026.
python -m plos.compile_tax_prep

# Or pin to a specific year:
$env:PLOS_TAX_YEAR = "2026"
python -m plos.compile_tax_prep
Remove-Item Env:PLOS_TAX_YEAR
```

The log line reports `(tax_year=YYYY, received=N, missing=M, manifest length: K chars)`.

### What success looks like

1. **`examples/sample-vault/compiled/tax-prep.md` exists** with frontmatter declaring `artifact: tax-prep`, `tax_year: 2026`, `refresh_cadence: monthly (weekly Jan-Apr)`, `sources_read:` listing every cited path.
2. **`Status:`** line: `2 of 5 expected documents received.`
3. **`## Received` section** — two bullets (1098 from Mr. Cooper, property tax statement), each with a `→ /source/tax/2026/received/...` arrow.
4. **`## Missing` section** — three bullets (W-2, 1099-INT, charitable receipts), each citing the inventory file as provenance.
5. **No `.tmp` leak** in `examples/sample-vault/compiled/`.

### Empty-state behaviour

If `source/tax/<year>/expected-documents.md` doesn't exist for the resolved tax year, `run` short-circuits and writes a deterministic "no inventory configured for <year>" artifact without invoking Claude. Both section headings are still emitted with placeholder bullets, so downstream readers (audit pass, notifications) see a stable contract.

### What this does *not* do (deferred)

- **`## For the accountant`** section — running totals (charitable contributions, rental income, estimated tax payments) aggregated from `extracted_fields`. Adds cross-table joins; defer until real tax-prep workflow drives the requirement.
- **`## Outstanding actions`** section — a chase-list derived from the missing list. The missing list already implies the chase; an explicit Outstanding section would be Claude synthesis on top of Claude synthesis.
- **File-presence-based received detection.** v1 trusts the inventory's `received: bool` flag. A future slice could cross-check by globbing `received/` and warning when a `received: true` entry's `received_path` doesn't exist.
- **Per-document linking back to Paperless.** Each `received_path` currently points to a vault file, not a Paperless URL. A future slice may add `paperless_url:` per entry.
- **Audit pass** verifying `sources_read:` matches body `→ /source/...` arrows. Now ready to land — all three v1 compiled artifacts ship. Next slice.

## Quickstart — Phase 5 Slice 4 (audit pass)

The audit pass is the meta-layer that keeps the AI-synthesized artifacts honest. For each of the three v1 compiled artifacts (`this-week.md`, `anomalies.md`, `tax-prep.md`), it parses the body's `→ /source/...` arrow citations and the frontmatter's `sources_read:` list, then flags drift in three categories:

- **undeclared_citation** — body cites a path but `sources_read:` doesn't list it. The AI synthesized from a source it didn't declare reading.
- **unused_declaration** — `sources_read:` lists a path but the body never cites it. The AI read but didn't surface anything. Mild.
- **nonexistent_citation** — body or frontmatter references a path that doesn't exist on disk. Catches AI path hallucination. Highest-value finding.

The audit is pure deterministic Python; no Claude involvement.

### Action — run the audit

```powershell
python -m plos.audit_pass
```

The report writes to `examples/sample-vault/_review/audit-report.md` (gitignored, regenerated each run).

### What success looks like

With the three demo artifacts the previous slices wrote:

1. **`_review/audit-report.md` exists** with frontmatter declaring `artifact: audit-report`, `audited_count: 3`, all four `findings_*` counts at 0, `audit_pass_version: 1`.
2. **Summary line:** `**All 3 audited artifacts passed.** Every → /source/... arrow is declared in sources_read:, every declared path is cited at least once, and every path resolves to an existing file in the vault.`
3. **One section per artifact**, each with a `_(clean — N declared, M cited, no drift)_` marker.
4. **No `.tmp` leak** in `_review/`.

### What it looks like when drift exists

If you manually edit `compiled/this-week.md` and either:
- add an `→ /source/people/jane/index.md` arrow (where `jane` doesn't exist),
- or remove an entry from `sources_read:` that the body still cites,

the next `audit_pass` run produces a report with `findings_total: 1+`, the affected artifact gets its own section with bullet findings naming the drifting path, and the summary line counts the breakdown by category.

### What this does *not* do (deferred)

- **Strict-mode non-zero exit.** v1 always exits 0; findings live in the report. A `--strict` flag (or `PLOS_AUDIT_STRICT=1`) could promote findings to a non-zero exit for CI/cron pipelines. Defer until scheduling lands and the notifier hooks in.
- **Glob-pattern path support.** Cited paths must be concrete (`/source/properties/123-main/index.md`); a path like `/source/properties/*/tax/` would be flagged as nonexistent. Future slice if the artifact templates start using globs.
- **Cross-artifact provenance check.** Doesn't verify that `compiled/anomalies.md` cites paths whose timestamps make sense (e.g., extracted_fields rows that match its `refreshed:`). Out of v1.
- **Auto-fix.** No "rewrite the artifact to make sources_read match body" command. The fix is to regenerate the artifact via its compile pass.

## Quickstart — Phase 5 Slice 5 (weekly digest notifications)

The delivery layer. `python -m plos.notifications` reads SQLite, renders a plain-text digest summarising the past 7 days of pipeline activity, and (when explicitly opted-in) sends it to your inbox via SMTP. Without this slice, the system writes artifacts the user has to remember to go look at. With it, "PLOS as a thing in your inbox" exists.

v1 ships ONE section — **Recent activity** — listing every `documents` row created in the past 7 days, with the routing entity (slug + type) and final processing status per row. Later slices fold in deadlines, anomalies/gaps/audit summaries, and review-queue counts.

### One-time setup — SMTP env vars

Add to your `.env` (or `.env.template` if you want to track the keys; **never** commit a real password):

```
# Required to actually send (omit to keep dry-run only):
PLOS_SMTP_USERNAME=
PLOS_SMTP_PASSWORD=
PLOS_NOTIFY_TO=

# Optional (defaults below):
PLOS_SMTP_HOST=smtp.gmail.com
PLOS_SMTP_PORT=587
PLOS_NOTIFY_FROM=        # defaults to PLOS_SMTP_USERNAME
PLOS_NOTIFY_SEND=        # unset/empty = dry-run; "1"/"true"/"yes"/"TRUE" = send
PLOS_DIGEST_AS_OF=       # YYYY-MM-DD to pin "today" for testing
```

For Gmail, `PLOS_SMTP_PASSWORD` must be a **Gmail App Password** (16-char value from `https://myaccount.google.com/apppasswords`), not your Google account password. 2-factor authentication has to be enabled to generate App Passwords.

### Action — dry-run first

```powershell
# Default behaviour: render to stdout, no network call.
python -m plos.notifications
```

The output:
- A subject line: `PLOS digest — week ending YYYY-MM-DD`
- The window: `YYYY-MM-DD – YYYY-MM-DD (7-day lookback, end-inclusive)`
- A `Recent activity` section listing each document with status + routing entity, or `No documents processed this week.` when the window is empty.

### Then actually send

```powershell
$env:PLOS_NOTIFY_SEND = "1"
python -m plos.notifications
Remove-Item Env:PLOS_NOTIFY_SEND
```

The digest lands in your inbox. SMTP errors (auth fail, network) raise; the dry-run / log line tells you what was attempted.

### What success looks like

- **Dry-run mode** (`PLOS_NOTIFY_SEND` unset) prints the rendered email to stdout, no SMTP call, exit 0.
- **Send mode** (`PLOS_NOTIFY_SEND=1`) connects to `PLOS_SMTP_HOST:PLOS_SMTP_PORT`, STARTTLS, login, send, exit 0. An email lands in `PLOS_NOTIFY_TO`'s inbox.
- **Missing required env var in send mode** raises `RuntimeError` listing every missing var; no SMTP call happens.

### What this does *not* do (deferred)

- **Deadlines section** — date-typed entity frontmatter within a lookahead window. Overlaps with `this-week.md` but the digest is the push channel.
- **Anomalies + gaps + audit-findings summary** — parse `compiled/anomalies.md` and `_review/audit-report.md`, surface counts.
- **Review-queue summary** — counts of `documents.status='needs_review'` by reason.
- **Segmentation by owning_entity** (tax/legal isolation per ARCHITECTURE.md). v1 has one flat activity list.
- **HTML body.** v1 is plain-text only; markdown-ish structure renders fine in any client.
- **Bounce / delivery monitoring.** Send + log + done. SMTP errors raise, but post-delivery state isn't tracked.

## Quickstart — Phase 5 Slice 6 (vault indexer + review queue)

The indexer closes the Phase 4b loop. When the `pending_claude` drain leaves a document in `needs_review` with a JSON-encoded `claude_unmatched_entity` proposal (Claude couldn't find an entity to route to, so it proposed one), the user reads the proposal, decides if it's right, and creates the entity in `source/<type>/<slug>/index.md`. `python -m plos.indexer` is what notices that the user did the work — it detects the new entity file, flips the document's status from `needs_review` to `resolved`, and re-renders `_review/queue.md` without that row.

Two responsibilities, one module:

1. **Self-clean.** Scan `documents.status='needs_review'`. For rows whose `review_reason` is a JSON proposal with a `proposed_entity.slug`, check if `entities.find_by_slug(slug)` returns a real file. If yes → flip status to `resolved`. The user's action (creating the entity) is the trigger; no manual mark-as-resolved step.
2. **Render `_review/queue.md`.** Walk every remaining `needs_review` row, group by reason, write a markdown page. Stable shape — empty queue still renders the page with a "nothing queued" marker.

### Action — run the indexer

```powershell
python -m plos.indexer
```

The log line reports `queued_before=N, resolved=M, queued_after=K` and writes the page to `examples/sample-vault/_review/queue.md` (gitignored alongside `compiled/` and `audit-report.md`).

### What success looks like

With the user's existing demo state (one Phase 4b leftover — the MidAmerican bill):

1. **`_review/queue.md` exists** with frontmatter (`type: review`, `artifact: queue`, `queued: 1`, `resolved_this_run: 0`, `by_reason:` count map, `indexer_version: 1`).
2. **One `## Unmatched entity (Claude proposed)` section** with one bullet:
   - `doc 2 — 2026-05-09 MidAmericanBill.pdf`
   - `Proposed: 2835-west-ct-bettendorf (property)`
   - The rationale Claude gave at drain time
   - The Paperless URL

### Demoing the resolution loop

```powershell
# 1. Inspect the queue page to see the proposed slug + type.
notepad examples\sample-vault\_review\queue.md

# 2. Create the entity at the proposed path.
#    Edit examples\sample-vault\source\properties\2835-west-ct-bettendorf\index.md
#    with at least YAML frontmatter (---\n---\n is enough for the indexer's existence check).

# 3. Re-run the indexer.
python -m plos.indexer
```

The log line now reports `resolved=1, queued_after=0`. The queue page renders empty.

### The `resolved` status

The indexer adds `'resolved'` to the `documents.status` taxonomy:

- `done` — extractor matched, entity routed, vault written
- `pending_claude` — no graduated extractor recognized the document
- `needs_review` — extraction matched but entity is missing/unparseable
- **`resolved` (new)** — was needs_review; user has since created the proposed entity. The original extracted fields were **not** auto-applied — the user can apply them manually if they want by reading the JSON in `review_reason` and editing the entity.
- `new` — unchanged

### What this does *not* do (deferred)

- **Apply Claude's `fields:` block to the now-existing entity.** Resolution marks `done` but doesn't write the proposed extraction. The user might have created the entity for reasons that differ from Claude's interpretation; auto-apply should be opt-in once a separate "apply queue proposal" command lands.
- **Preserve the proposed slug** when the drain stored a plain-string `claude_unmatched_entity` (the edge case from `drain_pending_claude.py:415` where Claude said "matched" but the slug didn't resolve). Those rows have no JSON proposal; they stay queued until a future fix preserves the proposed slug at drain time too.
- **Action hints per reason in the queue page.** Each section has a heading but no "what to do next" prose. Could be added once real review-queue traffic shapes what hints are useful.
- **Resolution via fuzzy slug match.** v1 is exact-match-only. If Claude proposes `123-main` but the user creates `123-main-street`, the indexer doesn't notice.

## Quickstart — Phase 5 Slice 7 (scheduling — MVP marker)

Wire all six recurring PLOS passes into Windows Task Scheduler. With this slice the system runs unattended — `python -m ...` invocations stop being a thing you have to remember.

### What gets scheduled

| Task | Frequency | Time | Module |
|------|-----------|------|--------|
| `PLOS_compile_this_week` | Daily | 06:00 | `plos.compile_this_week` |
| `PLOS_compile_anomalies` | Monthly (1st) | 03:00 | `plos.compile_anomalies` |
| `PLOS_compile_tax_prep`  | Monthly (1st) | 04:00 | `plos.compile_tax_prep` |
| `PLOS_audit_pass`        | Weekly (Sun)  | 05:00 | `plos.audit_pass` |
| `PLOS_notifications`     | Weekly (Sun)  | 08:00 | `plos.notifications` |
| `PLOS_indexer`           | Every 10 min  | 08:05 start | `plos.indexer` |

Times are local. Ordering matters within the day: anomalies before this-week (so the daily Watching section sees fresh anomaly state), audit before notifications (so the digest can later surface drift findings — Slice 6 deferral). The Phase 1 worker (`python -m plos.worker`) is NOT scheduled — it's a long-running poll loop and you start it yourself (e.g., on login via a shortcut, or as a Windows service).

### One-time setup

```powershell
# Register all six tasks. Run from the repo root.
.\scripts\install_schedules.ps1

# Dry-run first if you want to see exactly what gets registered:
.\scripts\install_schedules.ps1 -WhatIf

# View the registered tasks:
schtasks /Query /FO LIST /V | findstr PLOS_
```

### What the wrapper does

Each scheduled task invokes `scripts/scheduled_run.py <task-name>` rather than `python -m plos.<module>` directly. The wrapper:

1. Pins working directory to the repo root so `.env` loads consistently regardless of how the scheduler launches it.
2. Records the run in a new `scheduled_runs` SQLite table with `task_name`, `started_at`, `completed_at`, `exit_status` (`success` / `error`), and `error_summary` if anything raised.
3. Imports the module and calls its `main()`.
4. Exits 0 on clean success, 1 on a wrapped exception, 2 on an unknown task name (so Task Scheduler can distinguish "task ran and failed" from "the schedule itself is misconfigured").

You can run it manually anytime: `python scripts/scheduled_run.py audit_pass`. Useful for verifying the wrapper before committing to the schedule.

### Inspect run history

```powershell
sqlite3 G:\plos-data\plos\plos.db "SELECT task_name, started_at, exit_status, error_summary FROM scheduled_runs ORDER BY id DESC LIMIT 20;"
```

Every scheduled run lands a row. Useful when something didn't fire as expected — Task Scheduler's own logs are in Event Viewer (`Applications and Services Logs → Microsoft → Windows → TaskScheduler`).

### Caveats

- Tasks run **only when the user is logged on** by default. To run while logged off, edit each task in Task Scheduler → Properties → Security options → "Run whether user is logged on or not"; you'll have to supply the account password (Windows stores it encrypted per-machine).
- The `MINUTE` schedule for `PLOS_indexer` uses `/MO 10` — every 10 minutes. Task Scheduler still honours the laptop's sleep state; if the laptop sleeps, the task waits for wake.
- The PowerShell scripts use literal task names (`PLOS_*`). If you rename them, update both `install_schedules.ps1` and `uninstall_schedules.ps1`.

### Remove

```powershell
.\scripts\uninstall_schedules.ps1
```

### What this does *not* do (deferred)

- **Auto-start the long-running worker** (`python -m plos.worker`). Different beast — a continuous poll loop, not a one-shot. A Windows service / NSSM wrapper is the right pattern; out of v1.
- **Failure notifications.** A failed scheduled run records `exit_status='error'` in SQLite. The `notifications.py` digest doesn't yet surface those failures (Slice 5 deferred this). Manual `SELECT` against `scheduled_runs` is the workaround for now.
- **Schedule history viewer.** No `python -m plos.schedules` command to show recent runs. Use sqlite3 (or the future Phase 6+ Dataview dashboard over `scheduled_runs`).
- **Backfill / catch-up runs.** If the laptop is off when a task should fire, schtasks doesn't retroactively run it. Per-task "run if scheduled time was missed" is a Task Scheduler property you can flip manually.
- **Cross-platform support.** Windows Task Scheduler only. macOS launchd / Linux cron equivalents are mechanical to write but out of v1.

### Phase 5 (MVP marker) complete

With scheduling registered, Phase 5 is complete:

- ✅ `compiled/anomalies.md` (Slice 1: deviations, Slice 2: expectation gaps)
- ✅ `compiled/tax-prep.md` (Slice 3)
- ✅ Audit pass (Slice 4)
- ✅ `notifications.py` weekly digest (Slice 5)
- ✅ `indexer.py` + `_review/queue.md` (Slice 6)
- ✅ Scheduling (Slice 7)

What's not in v1 / Phase 5: Anomalies Slice 3 (unexpected charges) — needs transaction-level ingestion. The rest of the architecture's "what is deliberately not in v1" list still applies.

## License

See [LICENSE](./LICENSE).

---

*This is a portfolio reference repo. The actual operating instance and the real household vault are separate private repos and not present here.*
