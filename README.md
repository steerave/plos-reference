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
- **Unexpected-charges section.** Slice 3.

## License

See [LICENSE](./LICENSE).

---

*This is a portfolio reference repo. The actual operating instance and the real household vault are separate private repos and not present here.*
