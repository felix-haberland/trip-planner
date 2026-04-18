# VacationPlanner Development Guidelines

## CRITICAL: Keep Documentation in Sync

**Specs, constitution, and `CLAUDE.md` itself must always reflect current reality. Update them in the same change as the code — never let them rot.**

When you make any change that affects how the system works, ask: "Does this contradict something in `specs/`, `.specify/memory/constitution.md`, or `CLAUDE.md`?" If yes, update them in the same commit.

| Change type | Update |
|-------------|--------|
| New feature, behavior change, or architectural shift | Add or amend the relevant `specs/NNN-*/spec.md` (and `plan.md` if it exists). If the feature is new, create a new numbered folder. If superseded, mark the old spec `Status: Superseded by NNN`. |
| Change to a project rule, principle, or constraint | Amend `.specify/memory/constitution.md` and bump its version (semver). Re-evaluate Constitution Check sections in any open plan. |
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

## Key Files

| File | Purpose |
|------|---------|
| `profile.md` | Travel profile — user-editable, read by chatbot each turn |
| `instructions.md` | Chatbot behavior — user-editable, read by chatbot each turn |
| `backend/app/main.py` | FastAPI routes (trips, conversations, messages, region search/link) |
| `backend/app/chat.py` | Claude API integration, system prompt assembly, tool-use loop |
| `backend/app/tools.py` | Tool definitions, fuzzy region resolver, suggest_for_review handler |
| `backend/app/vacationmap.py` | Read-only VacationMap access, scoring algorithms (ported from VacationMap) |
| `backend/app/models.py` | SQLAlchemy models for trips.db |
| `backend/app/crud.py` | All trips.db read/write operations |
| `frontend/index.html` + `app.js` + `styles.css` | Single-page Vue 3 app |
| `docs/` | Architecture, API reference, chatbot behavior docs |
| `specs/` | Spec-kit feature specs (one folder per major feature) |

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

All four are read fresh on every message. Edit `.md` files in place — changes apply on the next message, no restart needed.

## Recent Learnings

- **Excluded reasons matter**: The system prompt now flags excluded destinations as "RESPECT THESE DECISIONS" because Claude was previously re-suggesting them. Reasons like "too touristy" or "visited recently" reveal patterns that apply to similar destinations.
- **Suggest, don't decide**: An earlier design had Claude directly shortlist/exclude. We changed this because it removed user agency. Now Claude only queues suggestions; the user owns the triage step.
- **Region names must be specific**: Claude tends to say "Scotland" but VacationMap stores "Scotland Lowlands" / "Scotland Highlands". The fuzzy resolver handles this but the AI should learn to use specific names from search results — `instructions.md` enforces this.
- **Pre-commit runs black + ruff**: `git commit` will reformat on commit; if it fails, run `black backend/app/<file>.py` and re-stage before re-committing.

## Commands

```bash
# Start the app (kills existing process on :8000, starts uvicorn with reload)
./start.sh

# Or manually
cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000

# Run linter / formatter manually
cd backend && source venv/bin/activate && black app/ && ruff check app/
```

## Code Style

- Python: standard conventions, type hints where helpful, black + ruff (enforced by pre-commit)
- Frontend: plain Vue.js 3 Composition API, no build tooling, no TypeScript
- API routes: thin — delegate to `crud.py` (DB) or `chat.py` (AI). `main.py` should not contain business logic.
