# Development

## Prerequisites

- Python 3.11+ (3.14 in current dev env)
- A working VacationMap install at `~/Documents/VacationMap` (the app reads its `vacation.db`)
- An Anthropic API key

## First-time setup

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env
# Edit ../.env and set ANTHROPIC_API_KEY
```

The `trips.db` file is created automatically on first startup in `backend/`.

If your VacationMap database is somewhere else, set:
```bash
export VACATIONMAP_DB_PATH=/path/to/vacation.db
```

## Running

```bash
./start.sh
# or:
cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000` in a browser.

`start.sh` kills any process already bound to port 8000 before starting, so it's safe to re-run.

## Editing the AI's behavior

You don't need to restart anything to change how the AI behaves:

- Edit `profile.md` — changes the couple's profile.
- Edit `instructions.md` — changes the chatbot's rules.

Both files are re-read on every chat message.

## Tests

```bash
cd backend && source venv/bin/activate
pytest
```

Tests live in `backend/tests/`. Coverage today is light — focused on the chat flow and CRUD operations.

## Code style

Pre-commit hooks run **black** (formatter) and **ruff** (linter) on commit. If a commit fails:

```bash
cd backend && source venv/bin/activate
black app/
ruff check app/
git add backend/app/<file>.py
git commit ...   # re-create commit; do not amend after a hook failure
```

Important: when the pre-commit hook fails, the commit was NOT created. Fix the issue and create a NEW commit. Do not use `--amend` (it would modify the previous commit, not create the one you intended).

## Common tasks

### Add a new Claude tool

1. Add a `TOOL_DEFINITIONS` entry in `tools.py` describing the schema.
2. Implement `handle_<tool_name>(params, trips_db, vm_db, trip_id)`.
3. Register the handler in `TOOL_HANDLERS`.
4. If the tool mutates trip state, set `trip_state_changed = True` in `chat.handle_chat_message()` for that tool name (currently only `suggest_for_review` does this).
5. Update `docs/api-reference.md` and the relevant spec.

Constitution check: state-mutating tools require justification (principle III).

### Add a new HTTP endpoint

1. Add the route in `main.py` (keep handlers thin — delegate to `crud` or `chat`).
2. If it touches `trips.db`, add the operation in `crud.py`.
3. If it touches `vacation.db`, add the read in `vacationmap.py` (SELECT only).
4. Add request/response schemas in `schemas.py` if non-trivial.
5. Update `docs/api-reference.md`.

### Add a column to an existing table

```bash
sqlite3 backend/trips.db
> ALTER TABLE <table> ADD COLUMN <col> <type>;
> .quit
```

Then add the column to the SQLAlchemy model in `models.py`. **Do not** delete and recreate the table.

### Migrate a destructive schema change

Ask the user first (constitution principle I). If approved:

1. Backup: `cp backend/trips.db backend/trips.db.bak`
2. Write a migration script that copies data into a new shape.
3. Run it manually.
4. Update the model.

## Project structure

```
.
├── CLAUDE.md                  Day-to-day dev guidance (read this in Claude Code)
├── docs/                      This documentation
├── specs/                     Spec-kit feature folders (NNN-feature-slug/)
├── .specify/                  Spec-kit toolchain (constitution, templates, workflows)
├── profile.md                 User-editable AI profile
├── instructions.md            User-editable AI instructions
├── start.sh                   Convenience launcher
├── backend/
│   ├── app/                   FastAPI app (see docs/architecture.md)
│   ├── tests/
│   ├── trips.db               (auto-created)
│   └── requirements.txt
└── frontend/
    ├── index.html
    ├── app.js                 Single Vue 3 component
    └── styles.css
```
