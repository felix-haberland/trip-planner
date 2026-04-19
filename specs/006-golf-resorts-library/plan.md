# Implementation Plan: Golf Courses & Resorts Library

**Branch**: `main` (specs developed in-place; see CLAUDE.md pattern for specs 001–005) | **Date**: 2026-04-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/006-golf-resorts-library/spec.md`

## Summary

Introduce a first-class curated library of **golf resorts** and **golf courses** that the user populates via AI-assisted extraction (URL or name → Claude extract → review → save) and consumes via a two-tab browse UI and two new chatbot tools (`search_golf_resorts`, `search_golf_courses` — both with fuzzy `name_query`). Courses are first-class and may be standalone (no parent resort). Entities include a gallery (external image URLs) and are optionally linked to VacationMap regions via the existing `country_code:region_name` stable key. A seed script populates ~120 curated entries via the same extraction pipeline. Trips gain an `activity_weights` dict so the chatbot can pick golf tools deterministically when the trip is golf-heavy.

Technical approach: extend the existing FastAPI + SQLAlchemy backend with new tables (`golf_resorts`, `golf_courses`, `entity_images`) + new columns on existing tables (`trips.activity_weights`, `suggested/shortlisted/excluded_destinations.resort_id` / `.course_id`). Server-side URL fetching via `httpx` with strict SSRF guardrails. AI extraction calls Claude with either `WebFetch`-style URL context or the Anthropic server-side `web_search_20250305` tool for name-only queries. Frontend adds two new views and an extraction form to the existing Vue 3 CDN app — no build step.

## Technical Context

**Language/Version**: Python 3.14 (runtime; constitution floor 3.11+), ES2020 JS for frontend
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x, Pydantic 2.x, Anthropic SDK (web_search_20250305 server tool + standard messages API), httpx (new — for server-side URL fetch with strict timeouts / size caps), Vue 3 via CDN, marked.js
**Storage**: `trips.db` (read-write — new tables + column additions), `vacation.db` (read-only — no change)
**Testing**: pytest (existing pattern)
**Target Platform**: Linux/macOS server on localhost or trusted LAN; served to desktop browsers
**Project Type**: Web application (existing backend + frontend monorepo)
**Performance Goals**: Browse page renders 100 entities in < 500 ms (SC-002); AI extraction completes within 20 s for URL-based, 30 s for name-only; chatbot tool call round-trip ≤ 2 s against a library of ≤ 500 entities
**Constraints**: No auth; SQLite-only; server-side URL fetch must enforce SSRF guardrails (FR-005a); no new build step on the frontend; Anthropic SDK `web_search_20250305` assumed available (assumption in spec)
**Scale/Scope**: ≤ 500 resorts + ≤ 1000 courses in realistic single-user use; ≥ 120 entries present after seed; 2 new Claude tools; 1 modified Claude tool (`search_destinations` annotations); 1 new frontend view with two tabs; 1 new extraction form; 1 new seed script

## Constitution Check

*GATE: Must pass before Phase 0. Re-checked after Phase 1 design.*

| Principle | Evaluation | Verdict |
|-----------|------------|---------|
| I. User Data is Sacred | Only additive schema changes: `CREATE TABLE IF NOT EXISTS` for `golf_resorts` / `golf_courses` / `entity_images`, `ALTER TABLE ADD COLUMN` for `trips.activity_weights` and for `resort_id` / `course_id` on the three destination tables. `name_norm` is a derived column, added via `ALTER TABLE ADD COLUMN` and backfilled non-destructively. Prevent-delete on user-initiated deletes (FR-020a) is scoped strictly to the parent, matching the constitution's "cascade deletes scoped to the parent" rule. `vacation.db` remains read-only. | PASS |
| II. Transparent AI Configuration | The new tool descriptions, the library-first-then-general-knowledge policy (FR-015b), and the activity-weight rules (FR-017a) go into `instructions.md`, not into Python. Tool schemas live in `tools.py` (data, not behavior). Prompt assembly in `chat._build_system_prompt()` still only concatenates `instructions.md` + `profile.md` + trip state + visit history + (new) activity weights. No hardcoded behavioral text. | PASS |
| III. User Owns Decisions | `suggest_for_review` gains optional `resort_id` / `course_id` (FR-018) but remains a queue-only operation; user still triages Shortlist / Exclude / Link. Library edits and deletes are user-initiated. The new tools are read-only from the chatbot's point of view. | PASS |
| IV. Stable Identifiers Across Boundaries | Resorts/courses reference VacationMap via `vacationmap_region_key` (the `country_code:region_name` stable key). No VacationMap PKs stored. The new shortlist columns `resort_id` / `course_id` reference `trips.db` locally and do not cross DB boundaries. | PASS |
| V. Living Documentation | Spec 006 exists and is registered in `specs/README.md`. Implementation will update `CLAUDE.md` (new files, commands, learnings), `docs/api-reference.md` (new endpoints), `docs/data-model.md` (new tables + columns), and `instructions.md` (new behavior) in the same PR. | PASS (with implementation obligation) |
| VI. Simple by Default, Justify Complexity | One new dependency: `httpx` (justified — stdlib `urllib` lacks clean timeout + redirect re-validation ergonomics, and Anthropic SDK's HTTP client is httpx-based already, so no new transport). No frontend build step. SQLite only. No new service, no auth change, no real-time. `entity_images` is a polymorphic table — an acceptable simplification over two parallel tables given the single consumer (the gallery UI). | PASS |

**Gate result**: all principles pass. No Complexity Tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/006-golf-resorts-library/
├── spec.md                # Existing — feature specification (Status: Draft)
├── plan.md                # This file
├── research.md            # Phase 0 — unknowns resolved
├── data-model.md          # Phase 1 — SQL schema + entity semantics
├── quickstart.md          # Phase 1 — setup + smoke test walkthrough
└── contracts/
    └── openapi.yaml       # Phase 1 — new HTTP endpoints (golf library + extract)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── main.py                  # ADD routes for /api/golf-library/* and extract endpoint
│   ├── models.py                # ADD GolfResort, GolfCourse, EntityImage models;
│   │                            # ALTER Trip (+activity_weights),
│   │                            # Suggested/Shortlisted/Excluded (+resort_id, +course_id)
│   ├── crud.py                  # ADD CRUD for resorts, courses, images; dedup + prevent-delete
│   ├── chat.py                  # EXTEND _build_system_prompt (activity_weights, library presence);
│   │                            # EXTEND tool-use loop to expose the new tools
│   ├── tools.py                 # ADD search_golf_resorts, search_golf_courses with name_query;
│   │                            # EXTEND search_destinations response with curated_* annotations
│   ├── vacationmap.py           # No change (still read-only)
│   ├── fetcher.py               # NEW — server-side URL fetch with SSRF guardrails (FR-005a)
│   ├── extraction.py            # NEW — AI extraction pipeline (URL or name → structured JSON)
│   │                            # wraps Claude + web_search_20250305 tool
│   └── seed_data/
│       └── golf_library_seed.yaml  # NEW — curated list of resorts (~100) and courses (~20)
├── scripts/
│   └── seed_golf_library.py     # NEW — iterates golf_library_seed.yaml, calls extraction.py,
│                                # saves via crud.py with dedup; idempotent; rate-limited
└── tests/
    ├── test_fetcher.py          # NEW — SSRF guardrails (scheme allowlist, IP blocklist, timeout, size)
    ├── test_extraction.py       # NEW — extraction success paths + sub-statused errors
    ├── test_crud_golf.py        # NEW — dedup, prevent-delete, cascade of images
    ├── test_tools_golf.py       # NEW — search_golf_resorts, search_golf_courses, name_query
    └── test_seed.py             # NEW — seed script idempotence + dedup

frontend/
├── index.html                   # ADD nav entry "Golf Library", Add flow, detail modals
├── app.js                       # ADD views: LibraryListResorts, LibraryListCourses,
│                                # LibraryDetail(Resort|Course), AddToLibrary; PATCH trip
│                                # creation/edit for activity_weights input
└── styles.css                   # ADD thumbnail grid, carousel, filter sidebar styles

docs/
├── api-reference.md             # EXTEND with new endpoints
└── data-model.md                # EXTEND with new tables + ALTER'd columns

profile.md                       # (no change unless user wants golf preferences pre-populated)
instructions.md                  # EXTEND with tool selection rules, library-first-then-fallback
                                 # policy, activity_weights interpretation, labelling conventions
CLAUDE.md                        # EXTEND "Key Files" table + "Recent Learnings"
specs/README.md                  # Already updated in spec-drafting phase; verify at commit time
```

**Structure Decision**: Extend the existing web-app layout. No new top-level directory is warranted — the library is a set of new routes + new tables inside the existing backend, and a new view inside the existing Vue 3 CDN frontend. This matches the "Simple by Default" constitution principle and keeps the monorepo shape consistent with specs 001–005.

## Complexity Tracking

No constitutional violations. No entries.
