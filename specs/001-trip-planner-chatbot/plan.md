# Implementation Plan: Trip Planner Chatbot

**Branch**: `feat/001-trip-planner-chatbot` | **Date**: 2026-04-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-trip-planner-chatbot/spec.md`

## Summary

Build a companion chatbot app to VacationMap that helps plan trips through AI-powered conversation. The chatbot reads a transparent travel profile and behavioral instructions from user-editable markdown files, queries VacationMap's database for destination scores and visit history, and suggests destinations with detailed reasoning. Users iteratively refine trips by shortlisting or excluding destinations. All trip state (shortlists, exclusions, conversations) is persisted in a separate SQLite database, enabling both partners to resume planning sessions asynchronously.

## Technical Context

**Language/Version**: Python 3.11+ (aligned with VacationMap)  
**Primary Dependencies**: FastAPI 0.109.0, SQLAlchemy 2.0.25, Pydantic 2.5.3, Anthropic SDK, Uvicorn 0.27.0  
**Frontend**: Vue.js 3 via CDN (static HTML/CSS/JS, no build step — aligned with VacationMap)  
**Storage**: SQLite — `trips.db` (read-write, own data) + VacationMap's `vacation.db` (read-only)  
**Testing**: pytest  
**Target Platform**: Local macOS, accessed via browser  
**Project Type**: Web application (FastAPI backend + Vue.js frontend)  
**Performance Goals**: <15s first AI response, <3s trip load, <200ms non-AI endpoints  
**Constraints**: Local/private network only, no authentication, no public deployment  
**Scale/Scope**: 2 users, dozens of trips, ~50 messages per conversation

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution is a blank template — no project-specific gates defined. No violations possible. **PASS**.

Post-Phase 1 re-check: No new violations introduced. Data model is straightforward (4 tables), no unnecessary abstractions. **PASS**.

## Project Structure

### Documentation (this feature)

```text
specs/001-trip-planner-chatbot/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0: research decisions
├── data-model.md        # Phase 1: entity definitions
├── quickstart.md        # Phase 1: setup guide
├── contracts/           # Phase 1: API contracts
│   └── api-endpoints.md # REST + Claude tool definitions
├── checklists/
│   └── requirements.md  # Quality checklist
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── main.py              # FastAPI entry point, routes
│   ├── database.py          # SQLAlchemy engines (trips.db + vacation.db)
│   ├── models.py            # TripPlan, ShortlistedDestination, ExcludedDestination, ConversationMessage
│   ├── schemas.py           # Pydantic request/response models
│   ├── crud.py              # CRUD operations for trips, destinations, messages
│   ├── chat.py              # Claude API integration, system prompt assembly, tool execution
│   ├── vacationmap.py       # Read-only access to VacationMap database (regions, scores, visits)
│   └── tools.py             # Tool handler implementations (search, details, shortlist, exclude)
├── requirements.txt         # Python dependencies
├── trips.db                 # Trip plan database (auto-created)
└── tests/
    ├── test_crud.py         # Trip/destination CRUD tests
    ├── test_chat.py         # Chat integration tests (mocked Claude)
    ├── test_vacationmap.py  # VacationMap read-only access tests
    └── test_tools.py        # Tool handler tests

frontend/
├── index.html               # Main page: trip list + chat + dashboard
├── app.js                   # Vue.js application
└── styles.css               # Styling

profile.md                   # User-editable travel profile
instructions.md              # User-editable chatbot behavioral instructions
```

**Structure Decision**: Web application with backend/frontend split, matching VacationMap's structure. Config markdown files at project root for maximum visibility and editability.

## Complexity Tracking

No constitution violations — table not needed.

## Design Decisions Summary

| Decision | Choice | Reference |
|----------|--------|-----------|
| AI integration | Anthropic SDK with tool use | [research.md#R1](research.md) |
| Context management | Full history, summarize on overflow | [research.md#R2](research.md) |
| Trip storage | Separate SQLite (trips.db) | [research.md#R3](research.md) |
| Claude tools | 6 tools: search, details, visits, shortlist, exclude, state | [research.md#R4](research.md) |
| Frontend | Vue.js 3 CDN, static files | [research.md#R5](research.md) |
| Config files | profile.md + instructions.md at project root | [research.md#R6](research.md) |

## Implementation Phases

### Phase 1: Backend Foundation (P1 stories dependency)

- Database setup: dual SQLAlchemy engines, trip models, migrations
- VacationMap read-only access layer (regions, scores, visits)
- Trip CRUD endpoints (create, list, get, update, delete)
- Basic message persistence

### Phase 2: AI Chat Core (User Stories 1 + 2)

- Claude API integration with Anthropic SDK
- System prompt assembly (profile.md + instructions.md + trip state)
- Tool definitions and handlers (search, details, visits, shortlist, exclude, state)
- Chat endpoint: send message → Claude → tool calls → response → persist
- Conversation history management

### Phase 3: Frontend Chat UI (User Stories 1 + 2 + 3)

- Trip list view (create new, select existing)
- Chat interface (message input, message history, typing indicator)
- Shortlisted/excluded destination indicators in chat
- Trip resume: load existing trip with full state

### Phase 4: Dashboard & Management (User Stories 4 + 5)

- Trip dashboard: side-by-side destination comparison with scores
- Excluded destinations collapsed section
- Trip management: rename, archive, delete
- Trip metadata display (created, modified, counts)

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Claude API latency varies | First response may exceed 15s target | Show typing indicator, stream response if possible |
| Long conversations exceed token limits | AI loses context | Implement conversation summarization fallback |
| VacationMap DB schema changes | Companion app reads break | Use stable `country_code:region_name` keys, handle missing fields gracefully |
| Concurrent writes from both partners | Data inconsistency | "Last write wins" with updated_at timestamps; display refresh on focus |
