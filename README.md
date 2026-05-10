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

Drag `tests\fixtures\sample_bills\electric_acme_2026_04.pdf` into `G:\plos-data\paperless\consume\`. (Or run `python tests\fixtures\sample_bills\build.py` first to regenerate it from scratch.) The bill is for Acme Power & Light, account `ACCT-12345`, $142.37 due 2026-04-30, 850 kWh — the same account number the sample property at `examples/sample-vault/source/properties/123-main-davenport/index.md` already declares.

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

That's the Phase 2 demo. Phase 3 will add gas, water, and internet extractors plus mortgage statements and pay stubs, and Phase 4 introduces the first compiled artifact (`this-week.md`).

## License

See [LICENSE](./LICENSE).

---

*This is a portfolio reference repo. The actual operating instance and the real household vault are separate private repos and not present here.*
