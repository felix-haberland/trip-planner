# Trip Planner Chatbot — Documentation

The Trip Planner Chatbot is a companion app to [VacationMap](../README-VacationMap.md) that helps a couple plan vacations through conversational AI. Claude reads a transparent travel profile, queries VacationMap's destination database, considers visit history, and suggests destinations for the user to triage.

## Documentation index

| Doc | What's in it |
|-----|--------------|
| [architecture.md](architecture.md) | High-level system architecture, components, data flow |
| [chatbot-behavior.md](chatbot-behavior.md) | How prompts are assembled, the tool-use loop, fuzzy resolution, visit-history filtering |
| [api-reference.md](api-reference.md) | All HTTP endpoints + Claude tool definitions |
| [data-model.md](data-model.md) | Current SQLAlchemy schema for `trips.db` |
| [development.md](development.md) | Local setup, running, testing, contributing |

For project rules and principles see [`/.specify/memory/constitution.md`](../.specify/memory/constitution.md).
For day-to-day development guidance see [`/CLAUDE.md`](../CLAUDE.md).
For per-feature design specs see [`/specs/`](../specs/).

## Quick mental model

```
            ┌──────────────────────────────┐
            │       Vue 3 Frontend         │
            │  (trip list, chat, triage)   │
            └──────────────┬───────────────┘
                           │ HTTP/JSON
            ┌──────────────▼───────────────┐
            │      FastAPI Backend         │
            │  main.py · chat.py · tools   │
            └──┬─────────────────────┬─────┘
               │                     │
   read-write  │                     │ read-only
               ▼                     ▼
        ┌─────────────┐       ┌─────────────┐
        │  trips.db   │       │ vacation.db │
        │ (own data)  │       │(VacationMap)│
        └─────────────┘       └─────────────┘
                           ▲
                           │ tool use
            ┌──────────────┴───────────────┐
            │     Claude (Anthropic API)   │
            └──────────────────────────────┘
```

The user types a message → backend persists it → Claude is called with the assembled system prompt + full conversation history + tool definitions → Claude calls tools (search, get details, suggest_for_review, etc.) → backend executes them, persisting any new "pending review" suggestions → Claude returns final text → backend persists and returns to frontend.

The user then triages the pending suggestions (Shortlist / Exclude / Link region) — these are explicit user actions, never AI mutations.

## Where data lives

- **`trips.db`** — owned by this app, read-write. Trips, suggested/shortlisted/excluded destinations, conversations, messages.
- **`vacation.db`** — owned by VacationMap, read-only. Countries, regions (with monthly weather/cost/busyness/attractiveness scores plus static golf/nature/hiking/safety scores), and `region_visits` (the couple's visit history with ratings).
- **`profile.md`** + **`instructions.md`** — at the project root, user-editable. Read on every chat turn. The user owns the AI's character and rules.

## Where to start reading code

1. [`backend/app/main.py`](../backend/app/main.py) — every HTTP route in one file.
2. [`backend/app/chat.py`](../backend/app/chat.py) — `handle_chat_message` orchestrates the Claude tool-use loop.
3. [`backend/app/tools.py`](../backend/app/tools.py) — tool definitions Claude sees + their handlers.
4. [`backend/app/vacationmap.py`](../backend/app/vacationmap.py) — read-only access + scoring formulas.
5. [`frontend/app.js`](../frontend/app.js) — single Vue component with all UI logic.
