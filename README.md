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

#### Step 1 — Clone the repo

**Where:** any folder you keep code in (e.g. `C:\Users\<you>\Desktop\`).

```powershell
git clone https://github.com/<you>/plos-reference.git
cd plos-reference
```

**Why:** Every later step assumes your working directory is the repo root (`...\plos-reference`). The `cd` puts you there.

#### Step 2 — Create the runtime data tree

**Where:** doesn't matter — the paths are absolute.

```powershell
mkdir G:\plos-data\paperless\data, G:\plos-data\paperless\media, `
      G:\plos-data\paperless\consume, G:\plos-data\paperless\export, `
      G:\plos-data\plos
```

**This is a single PowerShell command.** The backticks (`` ` ``) at the end of lines are line continuations. Paste the whole three-line block at once.

**Why:** Paperless and the worker write constantly — OCR'd PDFs, thumbnails, a search index, the Paperless DB, and the PLOS SQLite sidecar. Keeping all of that on `G:\plos-data\` (outside the repo) means `git status` stays clean and household documents never get committed by accident.

#### Step 3 — Create your environment file

**Where:** repo root.

```powershell
copy .env.template .env
```

**Why:** `.env` holds secrets — Paperless admin credentials and a signing key. It is gitignored. `.env.template` lists the required keys with empty values; copying it gives you a starting `.env` without exposing secrets to git.

#### Step 4 — Edit `.env`

Open `.env` in any text editor and set values for:

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

**Why:** Starts the Paperless-ngx container in the background. `-f docker\docker-compose.yml` points at the compose file in the `docker\` subfolder; `--env-file .env` feeds the admin/secret values into the container; `-d` runs it detached so your shell is free.

#### Step 7 — Verify Paperless is up

Open `http://localhost:<PAPERLESS_HOST_PORT>` in a browser — `http://localhost:8000` if you kept the default, or whatever port you set in Step 4. Log in with the credentials you set in Step 4. You should see an empty document list.

**Why:** Confirms Paperless booted, the secret key is valid, and your admin account exists. If the page won't load, check `docker compose -f docker\docker-compose.yml logs paperless`.

### Run the demo

You'll need **two PowerShell windows**, both `cd`'d into the repo root.

#### Terminal A — start the worker

**Where:** repo root.

Run **one line at a time**:

```powershell
.venv\Scripts\activate
python -m plos.worker
```

Leave this window open. The worker polls every 60 seconds and prints a log line for each new document.

**Why:** The worker watches the SQLite `documents` table for rows the post-consume hook adds when Paperless ingests a file. In Phase 1 it just logs them; later phases will route them to extractors.

#### Terminal B — drop a PDF into the consume folder

**Where:** doesn't matter — the paths are absolute.

```powershell
copy C:\path\to\some.pdf G:\plos-data\paperless\consume\
```

Replace `C:\path\to\some.pdf` with the path to any real PDF on your machine.

**Why:** Paperless watches `consume\`. When a file appears, it OCRs and files it, then runs the post-consume hook that writes a row into the PLOS SQLite sidecar.

### What success looks like

Within ~30 seconds, all three should be true:

1. **In Paperless (browser at `http://localhost:<PAPERLESS_HOST_PORT>`)** — the document appears in the document list, OCR'd.
2. **In SQLite (`G:\plos-data\plos\plos.db`)** — a new row in the `documents` table with `status='new'`, then `'done'`.
3. **In Terminal A (the worker)** — a log line of the form `new document id=1 paperless_id=1 title='some.pdf'`.

That's the Phase 1 demo. Phase 2 adds the first extractor and writes to the vault.

## License

See [LICENSE](./LICENSE).

---

*This is a portfolio reference repo. The actual operating instance and the real household vault are separate private repos and not present here.*
