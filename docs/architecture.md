# Architecture

## Process model

A single `uvicorn` process serves both the JSON API and the static frontend on port 8000.

- `/api/*` → FastAPI routes
- `/` → `frontend/index.html`
- `/static/*` → `frontend/` directory

There is no separate frontend dev server, no build step, no service worker.

## Components

```
backend/app/
├── main.py            HTTP routes only — thin handlers, delegate to crud/chat
├── database.py        Two SQLAlchemy engines + session dependencies
├── models.py          ORM models for trips.db
├── schemas.py         Pydantic request/response models
├── crud.py            All trips.db read/write
├── chat.py            Claude integration: prompt assembly + tool-use loop
├── tools.py           Tool definitions + handlers + region resolver
└── vacationmap.py     Read-only access to vacation.db + scoring formulas
```

### Two-database boundary

`database.py` defines two engines:

- `trips_engine` → `./trips.db` (the app's own data)
- `vacationmap_engine` → `~/Documents/VacationMap/backend/vacation.db` (read-only)

Each request can depend on either or both via `get_trips_db` / `get_vacationmap_db`. The dependency for `vacationmap_engine` only ever yields a session for `SELECT` queries — there is no `Base.metadata.create_all` and no models registered against it.

`vacationmap.py` accesses the foreign DB exclusively via raw SQL (`sqlalchemy.text`) to avoid mirroring VacationMap's 80+ column ORM model. This makes the companion app resilient to VacationMap schema additions, as long as the columns we name still exist.

### Stable cross-DB references

Trips reference VacationMap regions through `region_lookup_key` strings of the form `country_code:region_name` (e.g., `PT:Algarve`). We never store VacationMap's internal `region.id` because re-imports of VacationMap may renumber rows.

When scores need to survive VacationMap changes (for the trip dashboard), we snapshot them into `scores_snapshot` (a JSON blob on each suggested/shortlisted destination) at the moment the destination is suggested.

## Request lifecycle: chat message

```
User types message
        │
        ▼
POST /api/conversations/{conv_id}/messages
        │
        ▼
crud.add_message(role="user")          ← persisted before Claude is called,
        │                                so messages survive AI failures
        ▼
chat._build_system_prompt()
   reads instructions.md
   reads profile.md
   formats trip state (pending/shortlisted/excluded)
   formats visit history
        │
        ▼
chat._build_messages()                 ← full conversation history as Anthropic format
        │
        ▼
┌───── Tool-use loop (max 10 iterations) ─────┐
│   client.messages.create(...)               │
│        │                                    │
│        ▼                                    │
│   stop_reason == "tool_use"?                │
│        │                                    │
│   YES: for each tool_use block:             │
│        execute_tool(name, input, ...)       │
│        append assistant + tool_result       │
│        loop back to client.messages.create  │
│                                             │
│   NO: extract text, exit loop               │
└─────────────────────────────────────────────┘
        │
        ▼
chat._try_set_target_month()           ← first-message heuristic
        │
        ▼
crud.add_message(role="assistant")
        │
        ▼
return ChatResponse(user_msg, assistant_msg, trip_state_changed)
        │
        ▼
Frontend: if trip_state_changed, GET /api/trips/{id} to refresh sidebar
```

Key properties:
- The user message is persisted **before** Claude is called. If Claude fails, the user can retry without losing their input.
- `system_prompt` is rebuilt fresh on every turn, so edits to `profile.md` / `instructions.md` apply immediately.
- Tool calls within a single user turn happen in the same loop and feed back into the same conversation. The loop has a hard cap of 10 iterations as a safety stop.
- `trip_state_changed` is set only by `suggest_for_review` (the only state-mutating tool).

## Frontend architecture

`frontend/app.js` is a single Vue 3 Composition API component (~590 lines) mounted on `#app` from `index.html`. It maintains:

- View state (`list` vs `planning`)
- The current trip + active conversation
- Local message buffer (optimistic user message → replaced when API returns)
- Modal/popup state (destination details, region linking, message zoom)

Routing is hash-based: `#trip/{id}` opens a trip; clearing the hash returns to the list. No router library — `onMounted` reads the hash, `goHome` / `openTrip` write it.

All API calls go through a single `api(path, opts)` helper that handles JSON, 204, and error extraction.

Styling is plain CSS in `frontend/styles.css`. There is no component library. The full UI fits in three files.

## Persistence model

```
TripPlan ─┬─ SuggestedDestination*    (review queue between Claude and user)
          ├─ ShortlistedDestination*  (the user's working set)
          ├─ ExcludedDestination*     (with reasons that influence future suggestions)
          └─ Conversation*
                └─ ConversationMessage*
```

Cascade deletes: deleting a TripPlan removes all child destinations and conversations; deleting a Conversation removes its messages. Deleting a Conversation does NOT remove destinations — those belong to the trip, not the conversation.

`updated_at` on `TripPlan` is bumped on any state change so the trip list can sort by recency.

## What's intentionally absent

- **No authentication.** The app runs on localhost or a trusted private network. See constitution Principle V.
- **No real-time sync.** Both partners can use the app, but if they edit simultaneously, last write wins. The frontend re-fetches state after each user action.
- **No background jobs.** All work happens in the request thread. The longest operation is the Claude call (typically 5–15s).
- **No streaming responses.** The frontend waits for the full Claude response before rendering. Streaming was deferred — a typing indicator is shown instead.
- **No client-side bundler.** Vue 3 + marked are loaded via CDN.
