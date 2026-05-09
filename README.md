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

- Windows 11 with Docker Desktop running
- Python 3.11+
- ~5 minutes

### One-time setup

```powershell
git clone https://github.com/<you>/plos-reference.git
cd plos-reference

# Create the runtime data tree (lives outside the repo on purpose).
mkdir G:\plos-data\paperless\data, G:\plos-data\paperless\media, `
      G:\plos-data\paperless\consume, G:\plos-data\paperless\export, `
      G:\plos-data\plos

# Configure environment.
copy .env.template .env
# Edit .env: set PAPERLESS_ADMIN_USER, PAPERLESS_ADMIN_PASSWORD,
# PAPERLESS_SECRET_KEY (50+ random chars).

# Install Python deps and initialize the SQLite schema.
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python scripts\init_db.py

# Start Paperless.
docker compose -f docker\docker-compose.yml --env-file .env up -d
# Open http://localhost:8000 and log in with the admin credentials from .env.
```

### Run the demo

In one terminal, start the worker:

```powershell
.venv\Scripts\activate
python -m plos.worker
```

In another terminal, drop any PDF into the consume folder:

```powershell
copy C:\path\to\some.pdf G:\plos-data\paperless\consume\
```

Within ~30 seconds:

1. **In Paperless** — the document appears in the document list, OCR'd.
2. **In SQLite** — a row in `documents` with `status='new'`, then `'done'`.
3. **In the worker terminal** — a log line of the form `new document id=1 paperless_id=1 title='some.pdf'`.

That's the Phase 1 demo. Phase 2 adds the first extractor and writes to the vault.

## License

See [LICENSE](./LICENSE).

---

*This is a portfolio reference repo. The actual operating instance and the real household vault are separate private repos and not present here.*
