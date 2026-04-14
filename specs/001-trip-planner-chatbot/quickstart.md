# Quickstart: Trip Planner Chatbot

**Date**: 2026-04-14

## Prerequisites

- Python 3.11+ with pip
- VacationMap's `vacation.db` accessible on the same machine
- A Claude API key from Anthropic

## Project Setup

```bash
# From the VacationPlanner project root
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration

1. Set the Claude API key:
   ```bash
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```

2. Set the path to VacationMap's database:
   ```bash
   export VACATIONMAP_DB_PATH="/Users/haberfel/Documents/VacationMap/backend/vacation.db"
   ```

3. Edit the travel profile and chatbot instructions:
   - `profile.md` — describe the travelers, preferences, and constraints
   - `instructions.md` — define how the chatbot should behave and reason

## Running

```bash
# Start the backend (default port 8000)
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Then open `http://localhost:8000` in a browser.

## Key Files

| File | Purpose |
|------|---------|
| `profile.md` | Travel profile — who the travelers are, their preferences |
| `instructions.md` | Chatbot behavior — how the AI reasons and suggests |
| `backend/app/main.py` | FastAPI entry point, routes |
| `backend/app/models.py` | SQLAlchemy models (TripPlan, destinations, messages) |
| `backend/app/chat.py` | Claude API integration, tool execution |
| `backend/app/vacationmap.py` | Read-only access to VacationMap database |
| `frontend/index.html` | Chat UI + trip dashboard |
| `frontend/app.js` | Vue.js application logic |

## Architecture

```
Browser (Vue.js)
    │
    ▼
FastAPI Backend (:8000)
    ├── trips.db (read-write) — trip plans, messages, destinations
    ├── vacation.db (read-only) — VacationMap scores, visits
    ├── profile.md (read) — travel profile
    ├── instructions.md (read) — chatbot behavior
    └── Claude API — AI conversation with tool use
```

## Port Assignment

| App | Port |
|-----|------|
| VacationMap | 9000 |
| Trip Planner Chatbot | 8000 |

Both can run simultaneously.
