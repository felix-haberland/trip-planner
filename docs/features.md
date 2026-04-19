# Features Log

Lightweight, chronological record of what's been built (or is being built) in VacationPlanner. Replaces the spec-kit workflow for this project — see `CLAUDE.md` for why.

Add a new entry when starting or finishing a feature. Keep each entry short: name, date, status, a 1–3-sentence summary, and pointers to the main touched areas. Don't copy code into this file — link by path. Mark reworked features as `Superseded by ...`.

Status values: `planned` · `in-progress` · `shipped` · `superseded`.

---

## F001 — Trip Planner Chatbot (core)
**Date:** 2025-Q4 · **Status:** shipped
Single-trip planning flow: user chats with Claude, Claude calls `search_destinations` (VacationMap read-only lookup), queues `suggest_for_review`, user triages into shortlisted/excluded. FastAPI + SQLite + Vue 3 (CDN). Historical spec: `specs/001-trip-planner-chatbot/`.

## F002 — Suggest-for-review flow
**Date:** 2025-Q4 · **Status:** shipped
Claude never mutates trip state directly; it queues suggestions and the user owns the triage step. Historical spec: `specs/002-suggest-for-review-flow/`.

## F003 — Conversations & history
**Date:** 2025-Q4 · **Status:** shipped
Per-trip conversations with isolated message history; "Main" pinned first; follow-ups for side-threads. Historical spec: `specs/003-conversations-and-history/`.

## F004 — Region linking & fuzzy matching
**Date:** 2026-Q1 · **Status:** shipped
6-step fallback in `tools._resolve_lookup_key()` to map vague AI names ("Ireland", "Costa del Sol") to VacationMap regions, plus a manual linker in the UI. Historical spec: `specs/004-region-linking-and-fuzzy-matching/`.

## F005 — Visit history filtering (3-tier)
**Date:** 2026-Q1 · **Status:** shipped
`visit_again` column drives `never` / `not_soon` / `few_years` / `anytime` behavior in `search_destinations` + system prompt. Historical spec: `specs/005-visit-history-filtering/`.

## F006 — Golf library
**Date:** 2026-Q1 · **Status:** shipped
User-curated library of resorts + courses, seeded from YAML via Claude + web search. SSRF-hardened URL fetch (`fetcher.safe_get`), name-norm dedup, prevent-delete, two new search tools for the chatbot. Backend: `backend/app/golf/`. Historical spec: `specs/006-golf-resorts-library/`.

## F007 — Yearly planner (original)
**Date:** 2026-03 · **Status:** superseded by F008
Year-level plan with time-window Slots and year-plan-level TripOptions placed into slots via `SlotOptionPlacement`. Built but didn't match user intent — the year-level AI was picking destinations rather than composing the year's trip *themes*. Backend: `backend/app/yearly/`. Historical spec: `specs/007-yearly-vacation-planner/`.

## F008 — Yearly planner (redesign)
**Date:** 2026-04-19 · **Status:** superseded by F009
Slot = trip intent with `trip_plan_id` bridge. Shipped but didn't support comparing whole-year alternatives — you could only edit one plan at a time.

## F012 — Yearly planner: exclude with reason
**Date:** 2026-04-19 · **Status:** shipped
Added an `excluded` status + `excluded_reason` to both `year_options` and `slots`. Backend: `crud.exclude_option/exclude_slot` (reason required) + unexclude (clears reason on exit); new routes `POST /api/year-options/{id}/{exclude,unexclude}` and `POST /api/slots/{id}/{exclude,unexclude}`. Advisor prompt: excluded options and ideas are listed in a dedicated "RESPECT THESE DECISIONS" block with their reasons, with a role-prompt rule not to re-propose them. Frontend: per-option Exclude button (prompt for reason); excluded rows dim + show the reason inline; page-level toggle to hide/show excluded option rows. Per-cell Exclude on trip ideas; excluded ideas collapsed behind "Show N excluded ▾" toggle that reveals them with their reason + Un-exclude button.

## F010–F011 — Yearly planner: grid UX + alternatives per cell
**Date:** 2026-04-19 · **Status:** shipped
UX pass on F009. Renamed "slot" → "trip idea" in the UI. Every trip idea is anchored to one window (`slots.window_index NOT NULL`); dates are inherited from the window by default. Year-plan detail renders as a grid with options as rows and windows as columns — each cell can hold multiple alternative ideas (Golf or Beach in the same June cell of one option). Per-cell actions: "+ Add another" (manual) and "✨ Suggest more" (AI asks for count + guidance, then calls `propose_slot_in_option` for that cell). Top-level "Ask AI for options" nudges the AI to produce options meaningfully different from existing ones to avoid duplicate output. Dropped the per-option date-overlap check and the F010 `UNIQUE(option_id, window_index)` constraint.

## F009 — Yearly planner: Year Options (comparable year packages)
**Date:** 2026-04-19 · **Status:** shipped
Reshaped to `YearPlan → YearOption → Slot`. A YearPlan owns the user's intent, activity targets, and `windows` (calendar availability, JSON list of soft anchors). Each YearPlan holds many YearOptions — candidate whole-year arrangements ("Adventurous mix", "Golf-heavy", "Something different") — so the user can compare and pick. Slots live inside an Option with an optional `window_index` back-reference to the parent YearPlan's window. Multi-YearPlan-per-year still supported for genuinely different contexts ("Conservative 2027" vs "Wild 2027"). Slot → trip_plan bridge unchanged; trip chat still injects slot context. New tools: `generate_year_option` (full-option generation), `propose_slot_in_option` (iterative refinement), `list_options`, `list_slots_in_option`, `list_linked_trips`. `fork_option` clones an Option with its slots (trip links intentionally not copied). `mark_option_chosen` tags the winner without destroying siblings. New endpoints under `/api/year-options/{id}/...` + `/api/slots/{id}/...`. Dropped F008's `propose_slot` tool and the old `slots.year_plan_id` FK. Backend: `backend/app/yearly/`. Frontend: `frontend/{app.js,index.html,styles.css}` (Options list + compare modal). Tests: 33 across `test_yearly_{crud,tools}.py`.

## Error log (ops)
**Date:** 2026-04-19 · **Status:** shipped
Global FastAPI exception handler in `backend/app/main.py` appends tracebacks to `backend/errors.log` (gitignored via `*.log`). Clients still get a JSON 500. Used for "check latest error" debugging.
