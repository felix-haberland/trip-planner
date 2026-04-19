# VacationPlanner Development Guidelines

## Workflow: native, not spec-kit

This project does **not** use the spec-kit workflow. Do not create new `specs/NNN-*/` folders, do not update `.specify/memory/constitution.md`, and do not add Constitution Check sections. The existing `specs/001..007/` folders are historical record — leave them untouched (including `specs/007-yearly-vacation-planner/`, even after it's superseded).

Instead:

- **For non-trivial changes**, sketch a short plan + tradeoffs, ask targeted questions, wait for the user's "go", then implement. The conversation itself is the spec.
- **For each feature**, add a short entry to `docs/features.md` (the feature log). One paragraph max — name, date, status, summary, pointer to the main touched paths. Update the entry (or mark it `superseded`) when it evolves.
- **For small fixes / clear directives**, just act.

## CRITICAL: Keep Documentation in Sync

**`docs/`, `instructions.md`, and `CLAUDE.md` itself must always reflect current reality. Update them in the same change as the code — never let them rot.**

When you make any change that affects how the system works, ask: "Does this contradict something in `docs/`, `instructions.md`, or `CLAUDE.md`?" If yes, update them in the same commit.

| Change type | Update |
|-------------|--------|
| New feature, behavior change, or architectural shift | Add or amend the entry in `docs/features.md`. Mark superseded features `Status: superseded by FNNN`. |
| New runtime convention, command, file layout, or learning that future Claude sessions need to know | Update this file (`CLAUDE.md`). |
| New HTTP endpoint, tool, or schema field | Update `docs/api-reference.md` and `docs/data-model.md`. |
| Change to AI behavior | Update `instructions.md` first; only touch code if a new tool/field is required. |

If you find documentation that is already wrong (you didn't cause it but you spotted it), fix it. Stale docs are technical debt that compounds.

`CLAUDE.md` itself is a living document — when you learn something non-obvious about this codebase that future Claude sessions would benefit from, add it under "Recent Learnings" or the appropriate section.

## CRITICAL: Data Safety

**NEVER delete `trips.db` or any user data without explicit user confirmation.**

- When schema changes are needed, use `ALTER TABLE ADD COLUMN` to migrate — never drop and recreate.
- If a migration is truly destructive (dropping a column, changing a type), ask the user before proceeding.
- The `vacation.db` (VacationMap) is **read-only** — never write to it. Only SELECT queries via `vacationmap.py`.
- Before any `rm`, `DROP`, `DELETE`, or destructive git operation, confirm with the user.

## Architecture

- **Trip Planner Chatbot** — FastAPI backend (port 8000) + Vue.js 3 frontend (CDN, no build step)
- **VacationMap** — Separate app at `~/Documents/VacationMap` (port 9000)
- Two SQLite databases:
  - `backend/trips.db` (read-write, owns trip plans, suggested/shortlisted/excluded destinations, conversations, messages)
  - `~/Documents/VacationMap/backend/vacation.db` (read-only, VacationMap regions/scores/visits)
- Stable lookup key pattern: `country_code:region_name` (e.g., `PT:Algarve`)
- The chatbot does NOT directly mutate destination state. Claude calls `suggest_for_review`, which queues a destination for the user to triage. The user clicks Shortlist/Exclude/Link in the UI.

## Tech Stack

- Python 3.14, FastAPI, SQLAlchemy 2.x, Pydantic 2.x, Anthropic SDK (Claude Sonnet 4)
- Vue.js 3 via CDN, static HTML/CSS/JS (no npm/build), `marked` for markdown rendering
- SQLite for both databases
- `httpx` for server-side URL fetching with SSRF guardrails (added by spec 006)
- Anthropic server-side `web_search_20250305` tool for name-only extraction (spec 006)

## Key Files

| File | Purpose |
|------|---------|
| `profile.md` | Travel profile — user-editable, read by chatbot each turn |
| `instructions.md` | Chatbot behavior — user-editable, read by chatbot each turn |
| `backend/app/main.py` | FastAPI app + router mounting + static file serving. Thin. Also hosts the global exception handler that appends tracebacks to `backend/errors.log`. |
| `backend/app/database.py` | SQLAlchemy engines + `init_trips_db()` (including the **spec 007 conversations polymorphic rebuild**). |
| `backend/app/trips/*.py` | Per-domain package: models, schemas, crud, routes, tools, chat, vacationmap. Conversation lives here (polymorphic owner_type/owner_id). |
| `backend/app/golf/*.py` | Golf library package (spec 006): models (`GolfResort`, `GolfCourse`, `EntityImage`), crud dedup + prevent-delete, `fetcher.safe_get`, `extraction`, tools `search_golf_resorts` / `search_golf_courses`. |
| `backend/app/yearly/*.py` | **Yearly planner package (F009)**: `YearPlan → YearOption → Slot` hierarchy. YearPlan owns `windows` (JSON soft anchors) + intent; each YearOption is a candidate whole-year arrangement; each Slot is a trip intent inside one Option with optional `window_index` and `trip_plan_id` bridge. CRUD: year plan + option (including `fork_option`, `mark_option_chosen`) + slot (overlap check is per-option; across options is allowed by design). Tools: `list_options`, `list_slots_in_option`, `list_linked_trips`, `get_visit_history`, `generate_year_option` (full-option AI generation), `propose_slot_in_option`. Chat is a year-options advisor that does NOT pick destinations. |
| `backend/app/seed_data/golf_library_seed.yaml` | Curated ~120-entry seed list for the golf library — spec 006. |
| `backend/scripts/seed_golf_library.py` | Seed script that runs extraction on the seed YAML, idempotent, rate-limited — spec 006. |
| `frontend/index.html` + `app.js` + `styles.css` | Single-page Vue 3 app. Top-level tabs: Trips, Year (spec 007), Golf Library (spec 006). |
| `docs/` | Architecture, API reference, chatbot behavior docs. `docs/features.md` is the live feature log (read this to see what's been built). |
| `specs/` | **Historical** spec-kit folders (001–007). Kept for reference; do not add new ones — use `docs/features.md` instead. |

## Domain Concepts (read before editing chat/tools logic)

### Destination lifecycle

`Claude → suggest_for_review` → **Suggested** (user reviews) → **Shortlisted** OR **Excluded**.

Backend never moves a destination directly to shortlisted/excluded from a tool call. The user owns those decisions.

Reverse moves are supported: shortlisted → suggested (`/unreview`), excluded → shortlisted (`/reconsider`), shortlisted → excluded (`/exclude`).

### Visit history filtering (3-tier)

VacationMap's `region_visits` table has a `visit_again` column. Behavior:

| visit_again | search_destinations behavior |
|-------------|------------------------------|
| `never` | hard-filtered, never returned |
| `not_soon` | filtered out of `results`, but high-scoring ones surface in `excluded_due_to_recent_visit` for the AI to mention |
| `few_years` | included in `results` with a `visit_again` annotation; AI should only suggest if exceptional |
| `anytime` (or null) | included normally |

The system prompt also includes the full visit history so Claude can reason about geographic/timing patterns.

### Region linking & fuzzy matching

Claude often suggests destinations using vague names ("Ireland", "Costa del Sol, Spain"). `tools._resolve_lookup_key()` runs a 6-step fallback chain:

1. Exact region name match
2. Treat region_name as a country → pick best region by golf_score (avoids "Ireland" matching "Northern Ireland")
3. country + region_name word cross-match
4. country_name → pick best region
5. Fuzzy LIKE on region name
6. For multi-word names, try each word as a country, then remaining words against its regions

When fuzzy matching changes the destination, `suggest_for_review` returns `fuzzy_matched: true` + `matched_region` + `other_regions_in_country` so the AI explains the resolution to the user.

The frontend also has a manual region linker (`/api/vacationmap/regions/search` autocomplete + `/api/trips/{id}/{section}/{dest_id}/link`) for cases where automatic resolution is wrong.

### Conversations

Each trip has 1+ conversations (active or archived). Each conversation has its own message history. The "Main" conversation is always pinned first. Users can create follow-up conversations (e.g., "October alternatives") that share the same trip state but have isolated chat history.

### System prompt assembly

`chat._build_system_prompt()` concatenates:
1. `instructions.md` (behavioral rules)
2. `profile.md` (traveler profile)
3. Current trip state (pending review / shortlisted / excluded with reasons)
4. Visit history with `visit_again` annotations
5. Trip `activity_weights` dict (spec 006 — drives which activity-specific tools Claude prioritizes; empty dict falls back to free-text inference)

All five are read fresh on every message. Edit `.md` files in place — changes apply on the next message, no restart needed.

### Golf library (spec 006)

- Two new user-facing pages under `Golf Library`: **Resorts** tab and **Courses** tab, each with mode-specific filters (price/hotel_type vs course_type/difficulty/green_fee) and a shared filter-sidebar pattern.
- The **Add** flow lets the user pick entity type (Resort or Course), then submit either a URL (→ `fetcher.safe_get` + Claude extract) or a name only (→ Claude + server-side `web_search_20250305` tool). Failures come back as structured `{status, message, partial_data?}` with `status ∈ {api_error, no_match, fetch_error, ambiguous}`.
- `fetcher.safe_get` enforces SSRF guardrails (http/https only, post-DNS private-IP blocking, 10 s timeout, 5 MB cap, redirect re-validation) on every URL fetch — including user-supplied image URLs.
- Name dedup uses a derived `name_norm` column (lowercase + NFKD-ASCII + `& → and` + collapsed whitespace + stripped punctuation). Matched on `(name_norm, country_code, entity_type)` as a soft warning, not a hard constraint.
- Deletes are prevented if any attached courses or shortlist references exist; the API returns a structured blocker list the UI renders inline.
- Courses can be standalone (no `resort_id`). Resort-attached courses inherit country/region at query time.
- The chatbot has two new tools (`search_golf_resorts`, `search_golf_courses`) that both accept an optional fuzzy `name_query`. When the user asks about a specific named entity, `instructions.md` directs Claude to call the search tool first, label hits "from your library", and prefix misses with "not in your curated library yet" while still answering from general knowledge.
- `search_destinations` responses are annotated with `curated_resort_count` / `resort_names` / `curated_course_count` / `course_names` for regions that have library content.
- `scripts/seed_golf_library.py` runs the same extraction pipeline over `backend/app/seed_data/golf_library_seed.yaml` (~100 European resorts + ~20 iconic standalone courses). Idempotent via dedup. Explicit user invocation only — never auto-runs.

## Error log

Unhandled exceptions from any route are appended to `backend/errors.log` (format: `timestamp LEVEL METHOD /path\n<traceback>`). Gitignored via `*.log`. When the user asks "check latest error" or similar, `tail` this file. The handler is in `main.py` and also returns a JSON 500 to the client so the frontend still gets a response shape.

## Recent Learnings

- **Excluded reasons matter**: The system prompt now flags excluded destinations as "RESPECT THESE DECISIONS" because Claude was previously re-suggesting them. Reasons like "too touristy" or "visited recently" reveal patterns that apply to similar destinations.
- **Suggest, don't decide**: An earlier design had Claude directly shortlist/exclude. We changed this because it removed user agency. Now Claude only queues suggestions; the user owns the triage step.
- **Region names must be specific**: Claude tends to say "Scotland" but VacationMap stores "Scotland Lowlands" / "Scotland Highlands". The fuzzy resolver handles this but the AI should learn to use specific names from search results — `instructions.md` enforces this.
- **Pre-commit runs black + ruff**: `git commit` will reformat on commit; if it fails, run `black backend/app/<file>.py` and re-stage before re-committing.
- **SSRF matters even locally**: the golf library's URL extraction fetches arbitrary user-supplied URLs. `fetcher.safe_get` must re-validate the resolved IP on every redirect hop — a single-check-at-start pattern is bypassable via a 302 to `127.0.0.1`.
- **Polymorphic FK is acceptable here**: `entity_images` links to either `golf_resorts` or `golf_courses` via `(entity_type, entity_id)`. SQLite doesn't enforce this at the DB level; it's enforced in `crud.py`. Worth the simplification over two parallel tables.
- **Seed script costs money**: the ~120 curated entries run through real Claude + web search calls. Document cost/runtime in the script's docstring; rate-limit between calls to stay under Anthropic API limits.
- **Polymorphic conversation owner (spec 007)**: `conversations` was rebuilt from `trip_id` FK to `(owner_type, owner_id)`. No DB-level FK — different owners live in different tables. Cascade-on-delete must be hand-rolled in each owner's `delete_*` function (see `trips.crud.delete_trip` + `yearly.crud.delete_year_plan`). `conversation_messages.trip_id` is a nullable legacy column; keep populating it for trip-owned messages so older tooling still has the join.
- **SQLite schema rebuilds are sometimes the only path**: SQLite can't `ALTER COLUMN` to drop NOT NULL or drop an FK. Spec 007's `conversations` rebuild uses an `INSERT-SELECT / DROP / RENAME` inside a single transaction with FKs disabled. Guarded by column presence — idempotent. Document any such rebuild clearly; it's OK under Constitution I as long as every row is preserved.
- **Slot overlap validation lives in crud, not DB**: SQLite can't express "no overlap within year_plan_id" as a constraint. `yearly.crud._check_no_overlap` uses a packed month index (`year * 12 + month - 1`) and falls back to date comparison when both slots supply exact dates. The month-index approach handles year-crossing (Dec 2026 → Jan 2027) naturally.
- **Slot-as-trip-intent (F008, supersedes spec 007's placements)**: a slot carries the trip idea (`theme`, label, timing, `activity_weights`); destination discovery happens inside a linked `trip_plan` via `slots.trip_plan_id`. The trip chat reads `yearly.crud.slot_for_trip(trip.id)` and injects the slot intent into the system prompt when present.
- **Year Options hierarchy (F009)**: the real user need is *comparable* whole-year arrangements, not a single editable plan. Model is now `YearPlan → YearOption → Slot`. A YearPlan holds the user's stable intent + `windows` (JSON); YearOptions are siblings representing candidate years; slots live inside one Option. Overlap validation is per-Option (two Options can both place a June trip — they're alternatives). The AI's `generate_year_option` tool creates a whole new Option in one shot; `propose_slot_in_option` refines an existing one. `fork_option` clones slots but not `trip_plan_id` — the forked Option starts with fresh destination discovery per slot. `mark_option_chosen` is purely informational (no cascade delete of siblings; user keeps them as reference).
- **Shared messages endpoint dispatches on owner_type**: `POST /api/conversations/{id}/messages` lives in `trips/routes.py` but inspects `conversation.owner_type` and forwards to either `trips.chat.handle_chat_message` or `yearly.chat.handle_year_plan_chat_message`. The response shape differs (`trip_state_changed` vs `year_plan_state_changed`) so the endpoint declares no `response_model` — the handler returns serialize directly.
- **`conftest.py` purges `app.*` modules**: tests depend on re-reading `TRIPS_DB_PATH` per test. The fixture removes every `app` / `app.*` entry from `sys.modules` (not just `app.database`) — otherwise Python's package cache keeps `app.database` bound to the old path. A handful of pre-existing tests (`test_crud_golf.py`, `test_tools_golf.py`, `test_seed.py`) have stale imports from before the domain restructure and fail independently of this fixture.

## Commands

```bash
# Start the app (kills existing process on :8000, starts uvicorn with reload)
./start.sh

# Or manually
cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000

# Run linter / formatter manually
cd backend && source venv/bin/activate && black app/ && ruff check app/

# Seed the golf library (spec 006) — ~10–20 min runtime, ~$20–$40 Anthropic spend, idempotent
cd backend && source venv/bin/activate && python scripts/seed_golf_library.py
```

## Code Style

- Python: standard conventions, type hints where helpful, black + ruff (enforced by pre-commit)
- Frontend: plain Vue.js 3 Composition API, no build tooling, no TypeScript
- API routes: thin — delegate to `crud.py` (DB) or `chat.py` (AI). `main.py` should not contain business logic.
