# VacationPlanner Development Guidelines

## CRITICAL: Data Safety

**NEVER delete `trips.db` or any user data without explicit user confirmation.**

- When schema changes are needed, use `ALTER TABLE ADD COLUMN` to migrate — never drop and recreate.
- If a migration is truly destructive (dropping a column, changing a type), ask the user before proceeding.
- The `vacation.db` (VacationMap) is read-only — never write to it.
- Before any `rm`, `DROP`, `DELETE`, or destructive git operation, confirm with the user.

## Architecture

- **Trip Planner Chatbot** — FastAPI backend (port 8000) + Vue.js 3 frontend (CDN, no build step)
- **VacationMap** — Separate app at `~/Documents/VacationMap` (port 9000)
- Two SQLite databases: `trips.db` (read-write, trip plans) + `vacation.db` (read-only, VacationMap scores)
- Stable lookup key pattern: `country_code:region_name` (e.g., `PT:Algarve`)

## Tech Stack

- Python 3.14, FastAPI, SQLAlchemy 2.x, Pydantic 2.x, Anthropic SDK
- Vue.js 3 via CDN, static HTML/CSS/JS (no npm/build)
- SQLite for both databases

## Key Files

| File | Purpose |
|------|---------|
| `profile.md` | Travel profile — user-editable, read by chatbot each turn |
| `instructions.md` | Chatbot behavior — user-editable, read by chatbot each turn |
| `backend/app/chat.py` | Claude API integration, system prompt assembly |
| `backend/app/tools.py` | Tool definitions and handlers for Claude function calling |
| `backend/app/vacationmap.py` | Read-only VacationMap access with scoring algorithms |

## Commands

```bash
# Start the app
./start.sh
# Or manually:
cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000
```

## Code Style

- Python: standard conventions, type hints where helpful
- Frontend: plain Vue.js 3 Composition API, no build tooling
