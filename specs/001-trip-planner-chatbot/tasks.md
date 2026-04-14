# Tasks: Trip Planner Chatbot

**Input**: Design documents from `/specs/001-trip-planner-chatbot/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-endpoints.md, quickstart.md

**Tests**: Not explicitly requested — test tasks omitted.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, directory structure, and configuration files

- [x] T001 Create project directory structure: `backend/app/`, `backend/tests/`, `frontend/` per plan.md project structure
- [x] T002 [P] Create `backend/requirements.txt` with dependencies: fastapi==0.109.0, uvicorn==0.27.0, sqlalchemy==2.0.25, pydantic==2.5.3, anthropic
- [x] T003 [P] Create `profile.md` at project root with initial travel profile template (fit couple from Munich, nature/hiking lovers, temperature preferences 20-28°C, golf interest) per FR-017 and research.md R6
- [x] T004 [P] Create `instructions.md` at project root with initial chatbot behavioral instructions template (how to reason about destinations, structure suggestions with pros/cons, use scores, handle safety constraints) per FR-018 and research.md R6

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database layer, models, schemas, VacationMap access, and FastAPI skeleton. MUST complete before any user story.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T005 Implement dual SQLAlchemy engine setup in `backend/app/database.py`: trips engine (read-write, `trips.db`) + VacationMap engine (read-only, path from `VACATIONMAP_DB_PATH` env var defaulting to `../VacationMap/backend/vacation.db`). Include session factories for both. Auto-create trips.db tables on startup. Per research.md R3
- [x] T006 [P] Create SQLAlchemy models in `backend/app/models.py`: TripPlan (name, description, target_month, status, timestamps), ShortlistedDestination (trip_id FK, region_lookup_key, destination_name, ai_reasoning, scores_snapshot JSON, user_note, added_at), ExcludedDestination (trip_id FK, region_lookup_key, destination_name, reason, ai_reasoning, excluded_at), ConversationMessage (trip_id FK, role, content, created_at). Cascade deletes from TripPlan. Per data-model.md
- [x] T007 [P] Create Pydantic request/response schemas in `backend/app/schemas.py`: TripCreate (name, description), TripUpdate (name, status), TripSummary (with shortlisted_count, excluded_count), TripDetail (with shortlisted list, excluded list), MessageCreate (content), MessageResponse (role, content, created_at), ChatResponse (user_message, assistant_message, trip_state_changed). Per contracts/api-endpoints.md
- [x] T008 Implement VacationMap read-only access layer in `backend/app/vacationmap.py`: functions to query regions with scores for a given month (replicating VacationMap's composite score calculation from its crud.py), get region details by lookup key, get all visit records with ratings/revisit preferences. Use the read-only engine from database.py. Per research.md R1
- [x] T009 Implement trip CRUD operations in `backend/app/crud.py`: create_trip, list_trips, get_trip (with shortlisted/excluded counts and full details), update_trip, delete_trip (cascade), add_shortlisted_destination, add_excluded_destination, list_messages, add_message. Per data-model.md and contracts/api-endpoints.md
- [x] T010 Set up FastAPI app skeleton in `backend/app/main.py`: create app instance, configure CORS (allow all origins), mount `frontend/` as static files, add startup event to initialize both databases. Serve `frontend/index.html` at root. Per quickstart.md

**Checkpoint**: Foundation ready — database layer, models, schemas, CRUD, and FastAPI skeleton operational. User story implementation can now begin.

---

## Phase 3: User Story 1 — Start a New Trip Plan (Priority: P1) 🎯 MVP

**Goal**: User creates a trip, describes what they want (e.g., "golf trip in June"), and receives AI-generated destination suggestions with scores and pro/con reasoning.

**Independent Test**: Open browser, create a new trip, type a description, and receive at least 3 destination suggestions with scores from VacationMap data.

### Implementation for User Story 1

- [x] T011 [P] [US1] Implement `search_destinations` tool handler in `backend/app/tools.py`: query VacationMap regions for a given month, apply optional filters (activity_focus adjusts score weights, max_flight_hours, min_safety_score, exclude regions with visit_again="never"), return top N results with composite scores, weather, cost, busyness, attractiveness, golf, safety, flight info, and tips. Per contracts/api-endpoints.md tool definitions and research.md R4
- [x] T012 [P] [US1] Implement `get_destination_details` tool handler in `backend/app/tools.py`: given a region_lookup_key and month, return full details — all score types (weather, cost_relative, cost_absolute, busyness_relative, busyness_absolute, attractiveness, golf, safety), temp_day, temp_night, rain_days, tips, flight_time_hours, flight_transfers, nature_score, hiking_score, city_access, hotel_quality, tourism_level, and visit history if visited. Per contracts/api-endpoints.md
- [x] T013 [P] [US1] Implement `get_visit_history` tool handler in `backend/app/tools.py`: return all region_visits from VacationMap with region name, country, rating, rating_summary, visit_again preference, and visited month/year. Per contracts/api-endpoints.md
- [x] T014 [P] [US1] Implement `shortlist_destination` and `exclude_destination` tool handlers in `backend/app/tools.py`: shortlist adds to trip's shortlisted_destinations with name, lookup_key, ai_reasoning, scores_snapshot, user_note; exclude adds to excluded_destinations with name, lookup_key, reason, ai_reasoning. Both write to trips.db via crud.py. Per contracts/api-endpoints.md
- [x] T015 [P] [US1] Implement `get_trip_state` tool handler in `backend/app/tools.py`: return current shortlisted destinations (names, scores, notes) and excluded destinations (names, reasons) for the active trip. Per contracts/api-endpoints.md
- [x] T016 [US1] Implement Claude API integration in `backend/app/chat.py`: read `profile.md` and `instructions.md` from project root at each turn, build system prompt combining instructions + profile + trip description + current trip state (shortlisted/excluded), send full conversation history as messages, register all 6 tool definitions, execute tool calls in a loop until Claude produces a final text response, persist both user and assistant messages. Use Anthropic Python SDK. Per research.md R1, R2, R6
- [x] T017 [US1] Implement trip and chat API endpoints in `backend/app/main.py`: POST /api/trips (create trip, return TripSummary), POST /api/trips/{trip_id}/messages (accept MessageCreate, call chat.py, return ChatResponse with both messages and trip_state_changed flag). Per contracts/api-endpoints.md
- [x] T018 [US1] Create frontend chat interface in `frontend/index.html`, `frontend/app.js`, and `frontend/styles.css`: Vue.js 3 app via CDN with two views — (1) trip creation form (name + description input, submit button), (2) chat view (message history with user/assistant bubbles, text input, send button, loading/typing indicator while waiting for AI response). Wire to POST /api/trips and POST /api/trips/{trip_id}/messages. Per research.md R5

**Checkpoint**: User Story 1 fully functional — user can create a trip, chat with the AI, and receive scored destination suggestions from VacationMap data.

---

## Phase 4: User Story 2 — Refine Trip by Adding or Excluding Destinations (Priority: P1)

**Goal**: User iteratively refines the trip by adding destinations to shortlist, excluding others, and requesting more suggestions. All decisions are persisted with reasoning.

**Independent Test**: Continue a conversation from US1, say "add Algarve to the list," verify it appears in shortlist panel. Say "not Tenerife — too far," verify it appears in excluded panel. Ask "what else?", verify new suggestions exclude already-listed destinations.

### Implementation for User Story 2

- [x] T019 [US2] Add shortlisted destinations sidebar panel to chat view in `frontend/app.js`: display current shortlisted destinations with name, key scores for the trip month, user notes, and "unscored" label for non-VacationMap destinations. Auto-refresh after each AI response by checking trip_state_changed flag. Per spec.md US2 acceptance scenarios
- [x] T020 [US2] Add excluded destinations collapsed section below shortlist panel in `frontend/app.js`: display dismissed destinations with name and short reason. Collapsed by default, expandable. Auto-refresh after each AI response. Per spec.md US2 acceptance scenarios

**Checkpoint**: User Stories 1 AND 2 fully functional — users can create trips, get suggestions, and iteratively refine by adding/excluding destinations with visible state panels.

---

## Phase 5: User Story 3 — Resume an Existing Trip Plan (Priority: P1)

**Goal**: User opens the app, sees a list of existing trip plans, selects one, and immediately sees the full state (shortlisted, excluded, conversation history). They can continue the conversation.

**Independent Test**: Create a trip in US1, add/exclude destinations in US2, close the browser, reopen, verify the trip appears in the list, select it, verify all shortlisted/excluded destinations and conversation history are intact, send a new message.

### Implementation for User Story 3

- [x] T021 [P] [US3] Implement GET /api/trips (list all trips with metadata) and GET /api/trips/{trip_id} (full details with shortlisted, excluded) endpoints in `backend/app/main.py`. Per contracts/api-endpoints.md
- [x] T022 [P] [US3] Implement GET /api/trips/{trip_id}/messages endpoint in `backend/app/main.py`: return all conversation messages ordered by created_at ASC. Per contracts/api-endpoints.md
- [x] T023 [US3] Create trip list view in `frontend/app.js`: show all trips as cards with name, description snippet, creation date, last modified, shortlisted count, and status badge. Add "New Trip" button. On card click, navigate to chat view with full state loaded (shortlist panel, excluded panel, conversation history). Per spec.md US3 acceptance scenarios

**Checkpoint**: All P1 user stories complete — full trip creation, AI suggestions, refinement, and resume flow working.

---

## Phase 6: User Story 4 — Trip Dashboard with Scores and Comparisons (Priority: P2)

**Goal**: User views a summary dashboard showing shortlisted destinations side by side with key scores, AI reasoning, and user notes. Excluded destinations shown in a collapsed section.

**Independent Test**: Create a trip with 4+ shortlisted and 2+ excluded destinations, switch to dashboard view, verify all destinations display with comparable scores and notes.

### Implementation for User Story 4

- [x] T024 [US4] Create trip dashboard view in `frontend/app.js`: a tab or toggle alongside the chat view showing a comparison table — rows for each shortlisted destination, columns for weather, cost, busyness, attractiveness, golf (if relevant), safety, total score for the trip month. Include AI reasoning summary and user notes per destination. Per spec.md US4 acceptance scenarios
- [x] T025 [US4] Add excluded destinations collapsed section to dashboard view in `frontend/app.js`: below the comparison table, a collapsible panel listing dismissed destinations with name and short dismissal reason. Per spec.md US4 acceptance scenarios

**Checkpoint**: User Story 4 complete — dashboard provides at-a-glance comparison of all shortlisted destinations.

---

## Phase 7: User Story 5 — Manage Trip Plans (Priority: P3)

**Goal**: User can rename, archive, and delete trip plans. Trip list shows metadata (created, modified, destination counts, status).

**Independent Test**: Create multiple trips, rename one, archive one, delete one, verify the trip list reflects all changes correctly.

### Implementation for User Story 5

- [x] T026 [P] [US5] Implement PUT /api/trips/{trip_id} (update name and/or status to "archived"/"active") and DELETE /api/trips/{trip_id} (cascade delete all associated data) endpoints in `backend/app/main.py`. Per contracts/api-endpoints.md
- [x] T027 [US5] Add trip management controls to trip list view in `frontend/app.js`: rename button (inline edit), archive/unarchive toggle, delete button with confirmation dialog. Show trip metadata (created date, last modified, shortlisted count, excluded count, status). Per spec.md US5 acceptance scenarios

**Checkpoint**: All user stories complete — full CRUD lifecycle for trips.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Error handling, UX polish, and validation

- [x] T028 [P] Add error handling for Claude API failures in `backend/app/chat.py` (catch API errors, timeout, rate limits) and display user-friendly error messages with retry option in `frontend/app.js`
- [x] T029 [P] Add edge case handling: vague trip descriptions (chatbot asks clarifying questions — handled by instructions.md), all matching destinations visited (inform user), and "unscored" destination labeling for non-VacationMap suggestions in `backend/app/chat.py` and `frontend/app.js`
- [x] T030 Run quickstart.md validation: verify end-to-end setup (venv, requirements install, env vars, profile.md, instructions.md, start server, open browser, create trip, get suggestions)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup (T001, T002) — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational (Phase 2) — no dependencies on other stories
- **US2 (Phase 4)**: Depends on US1 (Phase 3) — extends the chat UI from US1
- **US3 (Phase 5)**: Depends on Foundational (Phase 2) — can run parallel with US1/US2 but benefits from US1 being done
- **US4 (Phase 6)**: Depends on US1 (Phase 3) — needs shortlisted destinations to display
- **US5 (Phase 7)**: Depends on Foundational (Phase 2) — can run parallel with other stories
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (P1)**: After Foundational — standalone, no story dependencies
- **US2 (P1)**: After US1 — extends US1's chat view with refinement panels
- **US3 (P1)**: After Foundational — mostly independent, but best after US1 for full testing
- **US4 (P2)**: After US1 — needs shortlisted/excluded data to display
- **US5 (P3)**: After Foundational — independent backend, but frontend extends trip list from US3

### Within Each User Story

- Tool handlers (T011-T015) before chat integration (T016)
- Chat integration (T016) before API endpoints (T017)
- API endpoints (T017) before frontend (T018)
- Backend before frontend within each story

### Parallel Opportunities

- T002, T003, T004 can run in parallel (Setup phase)
- T006, T007 can run in parallel (models and schemas are independent files)
- T011, T012, T013, T014, T015 can ALL run in parallel (each tool handler is independent)
- T021, T022 can run in parallel (different endpoints)
- T028, T029 can run in parallel (different concerns)

---

## Parallel Example: User Story 1

```bash
# Launch all tool handlers together (all [P] tasks, independent files):
Task T011: "Implement search_destinations tool handler in backend/app/tools.py"
Task T012: "Implement get_destination_details tool handler in backend/app/tools.py"
Task T013: "Implement get_visit_history tool handler in backend/app/tools.py"
Task T014: "Implement shortlist_destination and exclude_destination tool handlers in backend/app/tools.py"
Task T015: "Implement get_trip_state tool handler in backend/app/tools.py"

# NOTE: T011-T015 all write to the same file (tools.py) — mark as [P] since they implement
# independent functions, but coordinate to avoid merge conflicts if truly parallel.
# Sequential within the file is safer; parallel across files is clean.

# Then sequentially:
Task T016: "Claude API integration in backend/app/chat.py" (depends on T011-T015)
Task T017: "API endpoints in backend/app/main.py" (depends on T016)
Task T018: "Frontend chat interface" (depends on T017)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Create a trip, chat with AI, receive suggestions
5. Demo if ready — this alone delivers the core value

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 → Test → **MVP!** (create trip, get AI suggestions)
3. Add US2 → Test → Refinement loop (add/exclude destinations with visible state)
4. Add US3 → Test → Resume trips (persistence and multi-session planning)
5. Add US4 → Test → Dashboard (at-a-glance comparison)
6. Add US5 → Test → Trip management (rename, archive, delete)
7. Polish → Error handling, edge cases, quickstart validation

---

## Notes

- [P] tasks = different files or independent functions, no dependencies
- [Story] label maps task to specific user story for traceability
- T011-T015 are marked [P] as independent functions but all in tools.py — sequential execution avoids conflicts
- All tool handlers available from US1 onward (shortlist/exclude tools needed for AI to act on suggestions)
- profile.md and instructions.md are read fresh each turn — changes take immediate effect
- VacationMap data is read-only — never write to vacation.db
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
