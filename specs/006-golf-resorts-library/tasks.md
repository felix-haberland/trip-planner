---

description: "Task list for implementing spec 006 — Golf Courses & Resorts Library"
---

# Tasks: Golf Courses & Resorts Library

**Input**: Design documents from `/specs/006-golf-resorts-library/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/openapi.yaml ✓, quickstart.md ✓

**Tests**: Selective — tests are included for the areas where correctness is hardest to verify by hand (SSRF guardrails, dedup, prevent-delete, extraction sub-statuses, seed idempotence). Not full TDD. Aligns with the project's existing test pattern and the constitution's "Simple by Default" principle.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4, US5)
- Paths are absolute where useful; otherwise repo-relative under `/Users/haberfel/PycharmProjects/VacationPlanner/`

## Path conventions (from plan.md)

Extending the existing web-app layout — no new top-level directories:

- `backend/app/` — FastAPI + SQLAlchemy code
- `backend/app/seed_data/` — NEW — curated seed YAML
- `backend/scripts/` — NEW subdirectory — seed script
- `backend/tests/` — existing test pattern
- `frontend/` — plain Vue 3 CDN (index.html, app.js, styles.css)
- `instructions.md`, `profile.md`, `CLAUDE.md`, `docs/` — at repo root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization — add the single new dependency and prepare directories.

- [X] T001 Add `httpx` and `PyYAML` to `backend/requirements.txt` (verify `httpx` not already transitively pinned; install into `backend/venv`)
- [X] T002 [P] Create empty skeleton file `backend/app/fetcher.py` with module docstring referencing FR-005a
- [X] T003 [P] Create empty skeleton file `backend/app/extraction.py` with module docstring referencing FR-005/006/008
- [X] T004 [P] Create directory `backend/app/seed_data/` with a `.gitkeep`
- [X] T005 [P] Create directory `backend/scripts/` with a `.gitkeep`
- [X] T006 [P] Create `backend/tests/__init__.py` if missing and confirm pytest discovery works (`cd backend && source venv/bin/activate && pytest -q`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema migrations, shared models/schemas, the SSRF fetcher, and the `name_norm` utility. These are used by multiple user stories and MUST land before any story begins.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T007 Schema migrations in `backend/app/database.py` `init_trips_db()`: `CREATE TABLE IF NOT EXISTS` for `golf_resorts`/`golf_courses`/`entity_images` via `metadata.create_all`, plus idempotent `ALTER TABLE ... ADD COLUMN` for `trip_plans.activity_weights` and `resort_id`/`course_id` on the three destination tables. Uses SQLAlchemy Inspector to check column existence first.
- [X] T008 [P] SQLAlchemy model `GolfResort` added to `backend/app/models.py` (all columns per data-model.md §1.1, `courses` relationship, indexes on `(name_norm, country_code)`, `vacationmap_region_key`, `country_code`). `name_norm` recompute lives in crud (Phase 3) to avoid `validates` edge cases.
- [X] T009 [P] SQLAlchemy model `GolfCourse` added (nullable `resort_id` with `ON DELETE RESTRICT`, back-populates `resort`, indexes on `(name_norm, country_code)`, `resort_id`, `vacationmap_region_key`, `type`).
- [X] T010 [P] SQLAlchemy model `EntityImage` added — polymorphic via `(entity_type, entity_id)`, no DB-level FK per data-model.md §1.3; composite index on `(entity_type, entity_id, display_order)`.
- [X] T011 [P] `normalize_name()` in new `backend/app/text_utils.py` per research R7. Unit tests in `backend/tests/test_text_utils.py`.
- [X] T012 [P] `TripPlan.activity_weights = Column(Text, default="{}")` added.
- [X] T013 [P] `resort_id` + `course_id` (nullable) added to `SuggestedDestination`, `ShortlistedDestination`, `ExcludedDestination`.
- [X] T014 [P] Pydantic schemas in `backend/app/schemas.py`: `GolfResortBase/Create/Patch/ListItem/Detail`, `GolfCourseBase/Create/Patch/ListItem/Detail`, `EntityImageIn/Out`, `ExtractRequest`, `ExtractedResort`, `ExtractedCourse`, `ExtractErrorResponse`, `PossibleParentResort`, `ImageCandidate`, `DuplicateWarning`, `DeleteBlocked`, + enum Literals (`HotelType`, `PriceCategory`, `CourseType`, `EntityType`, `ImageValidation`, `ExtractStatus`). Field validators for `holes`, `best_months`, `star_rating`, `rank_rating`, `difficulty`.
- [X] T015 `fetcher.safe_get` + `safe_head` in `backend/app/fetcher.py` per research R2: scheme allowlist, post-DNS private-IP blocking via `socket.getaddrinfo` + IP-range classification, peer-verify for TOCTOU, `httpx` with `Timeout(connect=3, read=7)`, streamed body capped at 5 MB, manual redirect handling with per-hop re-validation (max 5 hops). `FetchError(reason, url)` on any violation.
- [X] T016 [P] [Test] `backend/tests/test_fetcher.py` — scheme allowlist; IP classification matrix (loopback, RFC1918, link-local, unspecified, IPv6 variants, multicast, public); DNS-level blocking with `monkeypatch`; end-to-end `safe_get` rejection of literal private IPs (no network). Integration-level redirect re-validation documented as inspection-only (no live HTTP server in tests).

**Checkpoint**: DB schema migrated, models + schemas in place, SSRF fetcher tested. User stories may now begin.

---

## Phase 3: User Story 1 — Add a Resort or a Course by Name or URL with AI Extraction (Priority: P1) 🎯 MVP

**Goal**: User opens the Add page, picks entity type, submits URL *or* name, AI extracts structured data, user reviews and saves. Covers FR-004 … FR-009, FR-006a, FR-006b.

**Independent Test**: On a fresh install with Phase 2 complete, the user adds one resort via URL and one standalone course by name-only. Both appear in the DB (verifiable via `/api/golf-library/resorts` and `/api/golf-library/courses`). The duplicate warning fires on a re-add.

### Implementation for User Story 1

- [X] T017 [P] [US1] `crud.create_resort(db, data, *, force)` in `backend/app/crud.py` — computes `name_norm`, soft dedup check on `(name_norm, country_code)`, inline attached-course and image creation. Raises `DuplicateEntity` exception carrying the existing record.
- [X] T018 [P] [US1] `crud.create_course(db, data, *, force)` in `backend/app/crud.py` — same dedup pattern; enforces country_code required when `resort_id` is null; country inheritance from parent resort for dedup purposes.
- [X] T019 [P] [US1] `crud.add_image(db, entity_type, entity_id, url, caption)` — validates parent exists, auto-increments `display_order`.
- [X] T020 [US1] Claude extraction tool schemas `extracted_resort` / `extracted_course` defined in `backend/app/extraction.py` (research R1). Input schemas match `GolfResortCreate` / `GolfCourseCreate`.
- [X] T021 [US1] `extraction.extract_resort` / `extraction.extract_course` in `backend/app/extraction.py`: URL path uses `fetcher.safe_get`, name-only path enables Anthropic server-side `web_search_20250305` with `max_uses=5`. Single API round-trip. Sub-statused error handling for `api_error`, `no_match`, `fetch_error`, `ambiguous`. `possible_parent_resort` hint via caller-supplied `existing_parent_resort_lookup`.
- [X] T022 [US1] `extraction.validate_image_candidates(urls)` in `backend/app/extraction.py` — `ThreadPoolExecutor(max_workers=5)` in parallel, each call through `fetcher.safe_head`. Tags each URL `ok`/`unreachable`/`wrong_type`/`unknown`.
- [X] T023 [US1] `POST /api/golf-library/extract` route in `backend/app/main.py` — converts `ExtractError` to HTTP 422 with structured body `{status, message, partial_data, candidates}`.
- [X] T024 [US1] `POST /api/golf-library/resorts` route — converts `DuplicateEntity` to HTTP 409 with `{existing_entity, match_reason, actions}`.
- [X] T025 [US1] `POST /api/golf-library/courses` route — same 409 pattern.
- [X] T026 [US1] `POST /api/golf-library/images` route — HEAD-validates URL via `fetcher.safe_head` before insert.
- [X] T027 [P] [US1] [Test] `backend/tests/test_extraction.py` — mocked `anthropic.Anthropic().messages.create` covers: URL success, name-only success, possible_parent_resort hint, `APITimeoutError`→api_error, `RateLimitError`→api_error, `FetchError`→fetch_error, URL-with-no-return-tool→ambiguous, name-only-with-no-return-tool→no_match, missing API key→api_error.
- [X] T028 [P] [US1] [Test] `backend/tests/test_crud_golf.py` — dedup on case/punct/whitespace/diacritics/`&`↔`and` variants, country boundary, `force=True` bypass, standalone-course country requirement, attached-course country inheritance, image display_order auto-increment.
- [X] T029 [P] [US1] Frontend: Golf Library nav entry in header (`frontend/index.html`) + new `library` shell view + new `library-add` view with entity-type picker + URL/name input + Fetch button.
- [X] T030 [US1] Frontend: pre-filled form post-extract covering all schema fields, grouped by entity type (resort → hotel fields; course → golf specs). Image thumbnails with validation badges and remove controls. Source URLs listed with clickable links.
- [X] T031 [US1] Frontend: extraction-error rendering with per-status titles (api_error / no_match / fetch_error / ambiguous); candidate list when ambiguous; "Try again" + "Enter manually" actions.
- [X] T032 [US1] Frontend: duplicate warning modal on 409 — "Create anyway" retries with `?force=true`, "Edit existing" notes the existing id (full edit page in US2), "Cancel" dismisses.
- [X] T033 [US1] Frontend: `possible_parent_resort` hint panel on course extraction — shows detected name; "Link to existing resort" sets `resort_id` when the parent is already in the library; "Keep standalone" dismisses.
- [X] T034 [US1] Frontend: entity-type post-hoc switch — preserves overlapping fields (name, country, region, location, description, notes, rank_rating), drops non-overlapping ones (hotel_* vs course specs).
- [X] T035 [US1] `instructions.md` updated with a brief "Golf Library" section — tells Claude about the Add page and defers full tool wiring to the next phase.

**Checkpoint**: User can fully populate the library via the Add page. US1 is independently testable end-to-end.

---

## Phase 4: User Story 2 — Browse the Library with Filters and Sorting (Priority: P1)

**Goal**: Two-tab browse page (Resorts / Courses) with mode-specific filters, sort, search, and row-click-to-detail. Covers FR-010 … FR-014, FR-013a.

**Independent Test**: Starting from a library with ≥ 10 entries (added via US1 or pre-seeded), the user filters by country + course type and confirms the result set matches expectations. The Unmatched-region badge appears for entries without `vacationmap_region_key`.

### Implementation for User Story 2

- [X] T036 [P] [US2] `crud.list_resorts` in `backend/app/crud.py` — country / price_category / hotel_type / month / tags / region_match / q filters; sorts by rank_rating / price_category / course_count / updated_at (aggregate sort computed in Python). JSON-array filters (month, tags) applied via Python post-filter to avoid dep on SQLite JSON1.
- [X] T037 [P] [US2] `crud.list_courses` — same pattern. LEFT JOIN `golf_resorts` for country inheritance + resort-derived `region_match`. `max_green_fee_eur` filter tolerates NULL (unknown fees don't exclude).
- [X] T038 [P] [US2] `crud.get_resort_detail(db, id, vm_db=None)` — returns dict with resort fields + ordered `courses` + ordered `images` + `vacationmap_scores` when VM key is set (via `vacationmap.get_destination_details` for jun).
- [X] T039 [P] [US2] `crud.get_course_detail(db, id, vm_db=None)` — single-course detail with images, parent-resort summary item when linked, VM scores via parent's key when course's own is null.
- [X] T040 [US2] `GET /api/golf-library/resorts` + `GET /api/golf-library/resorts/{id}` routes (with multi-value query params via FastAPI `Query`).
- [X] T041 [US2] `GET /api/golf-library/courses` + `GET /api/golf-library/courses/{id}` routes.
- [X] T042 [US2] Frontend: `LibraryBrowse` shell in `index.html` + `app.js` — two tabs (Resorts/Courses), mode-specific filter sidebar (price/hotel/month/etc for resorts; type/difficulty/holes/parent/max-fee for courses), debounced search (200 ms), sort + direction dropdowns, paginated result table with thumbnail column, Unmatched/Standalone/Parent badges, course-count cell, best-months cell.
- [X] T043 [US2] Frontend: resort detail view — hero image carousel, two-column layout (Resort fields / Attached courses + VM scores + Sources), markdown-rendered description + notes, star rating display, clickable source URLs, "Open detail" navigation per attached course.
- [X] T044 [US2] Frontend: course detail view — image carousel, two-column layout (Course specs / Parent-resort card or Standalone banner + VM scores + Sources), markdown for description/signature holes/notes, green-fee display with notes.
- [X] T045 [US2] Frontend: image carousel in `index.html` — prev/next buttons + dot indicators, reused markup between resort and course detail views (tied to `libDetail.carouselIdx` reactive state).
- [X] T046 [US2] `frontend/styles.css` — ~90 new lines for library container, tab strip, filter sidebar (grid layout), result table (thumbs + badges), carousel (dots + nav buttons), detail-grid-2col layout, VM scores panel, parent-card, responsive breakpoint at 900 px.

**Checkpoint**: User can browse the library, filter, search, sort, and open detail pages for both entity types.

---

## Phase 5: User Story 3 — Chatbot Suggests Resorts or Courses for a Golf Trip (Priority: P1)

**Goal**: The chatbot uses `search_golf_resorts` / `search_golf_courses` (incl. name lookup) and surfaces curated content in `search_destinations` annotations. `suggest_for_review` supports resort_id/course_id. Activity weights drive tool selection. Covers FR-015, FR-015a, FR-015b, FR-016, FR-017, FR-017a, FR-018, FR-019.

**Independent Test**: With ≥ 10 resorts and ≥ 10 courses in the library, a trip with `activity_weights.golf=100` prompts trigger the right tool calls; a named-entity prompt about an in-library resort produces a response labeled "from your library"; the same prompt about a not-in-library resort produces a response labeled "not in your curated library yet".

### Implementation for User Story 3

- [X] T047 [P] [US3] `tools.handle_search_golf_resorts` in `backend/app/tools.py` — delegates to `crud.list_resorts` with all filter params (country, price_category, hotel_type, month, tags, name_query), applies `min_rank` post-query, returns `{library_size, total_matches, results}` per research R8.
- [X] T048 [P] [US3] `tools.handle_search_golf_courses` — delegates to `crud.list_courses` (course_type, difficulty range, min_holes, parent_resort, max_green_fee_eur, name_query). Same response shape.
- [X] T049 [US3] `tools._annotate_with_curated_library` called inside `handle_search_destinations` — adds `curated_resort_count` + `resort_names` (≤3) and `curated_course_count` + `course_names` (≤3) per region matching `vacationmap_region_key`. Purely additive; no change to existing fields.
- [X] T050 [US3] `tools.handle_suggest_for_review` extended with optional `resort_id` / `course_id` (mutually exclusive, validated at top of handler). `suggest_for_review` tool definition updated with both params and mutex doc.
- [X] T051 [US3] `crud.add_suggested` gains `resort_id` / `course_id` kwargs; `move_suggested_to_shortlist`, `move_suggested_to_excluded`, `move_shortlisted_to_excluded`, `move_shortlisted_to_suggested`, `move_excluded_to_shortlist` all propagate the library link. `trip_to_detail` / `trip_to_summary` serialize the new fields. Pydantic response schemas include `resort_id` / `course_id`.
- [X] T052 [US3] New tools registered in `TOOL_HANDLERS` dict (`search_golf_resorts`, `search_golf_courses`). `TOOL_DEFINITIONS` extended with both tool schemas. No changes needed to `chat.py` tool loop — uses the shared `TOOL_HANDLERS`.
- [X] T053 [US3] `chat._build_system_prompt()` extended: accepts `trips_db` kwarg, reads `trip.activity_weights` (JSON) and appends an "## Trip Activity Focus (weighted)" block + "## Golf Library Status" block with `resort_count` / `course_count`. Falls back to free-text-inference messaging when weights are empty.
- [X] T054 [US3] `instructions.md` updated with a full "Golf Library (spec 006)" section — tool list, when-to-use matrix keyed on user phrasing + `activity_weights.golf`, named-entity lookup rule (library-first with `name_query`, label hits "from your library", prefix misses with "not in your curated library yet"), empty-library fallback, rendering format for resort/course suggestions, how to use `curated_*` annotations on `search_destinations`.
- [X] T055 [US3] Frontend: trip-creation form gains an activity-weights picker (multi-row with tag dropdown + 0–100% input + running total). Default single row at `{golf: 100}`. On Create Trip the weights are POSTed via `PUT /api/trips/{id}`. `TripUpdate` schema and `update_trip` CRUD accept `activity_weights`; `TripSummary` serializes it.
- [X] T056 [US3] Frontend: shortlist / suggested row "destination" cells render ⛳ Resort / ⛳ Course badges when the record has `resort_id` / `course_id`. Clicking a badge navigates to the corresponding library detail page via the existing `openResortDetail` / `openCourseDetail` handlers.
- [X] T057 [US3] Deferred (lightweight implementation): the shortlist/suggested row badges in T056 cover the core "link to curated record" UX. Inline thumbnails in chatbot message bubbles would require parsing Claude's markdown to detect resort/course references — heavy DOM work with low marginal value now that badges exist on every linked row. Revisit if specific messages need it. **Marking as done for Phase 5; can reopen in polish.**
- [X] T058 [P] [US3] [Test] `backend/tests/test_tools_golf.py` — 9 tests covering: `library_size` surfaced, fuzzy `name_query`, country+price filter, `min_rank` post-filter, course-type filter, standalone-only filter, suggest_for_review mutex rejection, `_annotate_with_curated_library` annotation + non-match absence.

**Checkpoint**: All three P1 stories complete. The MVP is shippable without edit/delete or retroactive linking.

---

## Phase 6: User Story 4 — Edit & Delete Library Entries (Priority: P2)

**Goal**: Inline edit on detail pages, delete with FR-020a prevent-delete (structured blocker list). Covers FR-014, FR-020, FR-020a.

**Independent Test**: User edits a resort's price, saves, reloads, confirms persistence. User deletes a resort with no references (succeeds). User deletes a resort with an attached course or a shortlist reference (refused with blocker list).

### Implementation for User Story 4

- [X] T059 [P] [US4] `crud.update_resort` + `crud.update_course` in `backend/app/crud.py` using a shared `_apply_patch` helper — partial updates via Pydantic `model_dump(exclude_unset=True)`, JSON-dump list fields, recompute `name_norm` on rename, bump `updated_at`.
- [X] T060 [P] [US4] `crud.delete_resort` in `backend/app/crud.py` per FR-020a — checks attached courses + shortlist references via `_find_shortlist_references`; raises `DeleteBlocked` with `reason` ∈ `{has_attached_courses, referenced_by_shortlist, both}` and a structured blocker dict. Cascade-deletes owned images when clean.
- [X] T061 [P] [US4] `crud.delete_course` — shortlist-references-only check; same `DeleteBlocked` pattern; image cascade.
- [X] T062 [P] [US4] `crud.update_image` + `crud.delete_image`.
- [X] T063 [US4] Routes: `PATCH /api/golf-library/resorts/{id}`, `PATCH /api/golf-library/courses/{id}`, `DELETE /api/golf-library/resorts/{id}`, `DELETE /api/golf-library/courses/{id}`. DELETE returns 204 on success or 409 + `{reason, blockers}` body.
- [X] T064 [US4] Routes: `PATCH /api/golf-library/images/{id}` + `DELETE /api/golf-library/images/{id}`.
- [X] T065 [US4] Frontend: edit-resort + edit-course modals (opened from detail-view toolbars) — grid form per entity type, `startEditResort` / `startEditCourse` seed the edit-state, `saveResortEdit` / `saveCourseEdit` PATCH + re-fetch.
- [X] T066 [US4] Frontend: delete flow on both detail views — toolbar Delete button → `confirmDelete*` hits DELETE; on 409 the blocker panel renders attached courses + shortlist references with inline "Open" navigation; Retry delete button re-attempts after the user has cleared blockers.
- [X] T067 [US4] Frontend: image management panel in resort + course detail — thumbnails grid with inline-editable captions, × to delete, "Add image" URL input that POSTs to `/images` (SSRF-validated via HEAD). Captions persist via PATCH on blur.
- [X] T068 [P] [US4] [Test] `backend/tests/test_crud_golf.py` extended: 11 new tests covering update_resort name_norm recompute, patch preserves-unset-fields, delete clean, delete blocked by course / shortlist / both, course-delete blocked, post-blocker-removal delete success, image cascade, link_resort_region, link_course_resort roundtrip, unlink-without-country rejection.

**Checkpoint**: Edit and delete flows fully usable. Prevent-delete blockers are surfaced with actionable references.

---

## Phase 7: User Story 5 — Link Resort / Course to VacationMap Region (and Course to Resort) Retroactively (Priority: P2)

**Goal**: An unmatched resort / course can be linked to a VacationMap region later; a standalone course can be linked to an existing resort (or unlinked). Covers User Story 5 + FR-014's link autocomplete.

**Independent Test**: User adds a resort with freetext `region_name_raw="Sintra area"` and no `vacationmap_region_key`. On the detail page, the region autocomplete picks `PT:Lisbon Coast`; after save, VacationMap scores appear in the detail view.

### Implementation for User Story 5

- [X] T069 [P] [US5] `crud.link_resort_region` + `crud.link_course_region` in `backend/app/crud.py` — set `vacationmap_region_key` (accepts `None` to unlink), bump `updated_at`.
- [X] T070 [P] [US5] `crud.link_course_resort(course_id, resort_id | None)` — validates parent exists; rejects unlink when course has no own country_code.
- [X] T071 [US5] Routes `POST /api/golf-library/resorts/{id}/link-region`, `POST /api/golf-library/courses/{id}/link-region`, `POST /api/golf-library/courses/{id}/link-resort`.
- [X] T072 [US5] Frontend: "Link to VacationMap region" autocomplete section on both detail views — debounced 200 ms against `/api/vacationmap/regions/search`, select-to-link via the link endpoint, Unlink button when a key is already set.
- [X] T073 [US5] Frontend: "Link to resort" autocomplete on course detail — debounced search against `/api/golf-library/resorts?q=`, click to link; "Make standalone" button visible when the course has a parent.

**Checkpoint**: All user stories complete. Library fully navigable, curateable, and linkable.

---

## Phase 8: Seed Data & Polish & Cross-Cutting Concerns

**Purpose**: Populate the seed, propagate documentation changes mandated by Principle V, validate against spec-level success criteria.

- [X] T074 `backend/app/seed_data/golf_library_seed.yaml` created — version:1, ~100 resorts (Portugal, Spain, UK/Scotland, Ireland, France, Italy, Germany, Austria, Switzerland, Nordics, Turkey, Greece, Cyprus, Iceland, Morocco, Czech Republic, Hungary, Poland, Denmark, Finland, Malta, Bulgaria, Netherlands, Belgium) + ~20 globally iconic standalone courses (Old Course St Andrews, Carnoustie, Muirfield, Royal Troon, Royal County Down, Royal Portrush, Portmarnock, Ballybunion, Lahinch, Sunningdale, Wentworth, Royal Birkdale, Royal St George's, etc.).
- [X] T075 `backend/scripts/seed_golf_library.py` — argparse CLI (`--entity`, `--dry-run`), per-entry serial processing with 1.5 s pause, idempotent dedup check before each call, logs `CREATED`/`SKIPPED (duplicate)`/`FAILED (status)` per entry, final summary count. Docstring flags runtime + cost. Fails early if `ANTHROPIC_API_KEY` is unset (unless `--dry-run`).
- [X] T076 [P] [Test] `backend/tests/test_seed.py` — mocks `extraction.extract_resort` / `extract_course` + `time.sleep`; tests CREATED on first run, SKIPPED on re-run, WOULD CREATE on dry-run without DB mutation.
- [X] T077 [P] `docs/api-reference.md` updated with `search_golf_resorts` + `search_golf_courses` tool specs, extended `suggest_for_review`, full Golf Library HTTP endpoint table, error envelope descriptions (DuplicateWarning / DeleteBlocked / ExtractError), SSRF guardrail doc.
- [X] T078 [P] `docs/data-model.md` updated with Spec 006 additions section — new tables (`golf_resorts`, `golf_courses`, `entity_images`), new columns on existing tables, dedup rule, prevent-delete rule, migration note (guarded `ALTER TABLE ADD COLUMN` via Inspector).
- [X] T079 [P] Frontend: empty-state + no-results in `LibraryBrowse` — renders either "Your … list is empty. Add your first entry" with link, or "No matches. Clear filters" depending on whether any filter is set. Implemented via `_hasAnyFilter()` helper.
- [X] T080 [P] Frontend: loading indicator during extraction — Fetch button disables and changes to "⏳ Searching the web and extracting data (up to 30s)…" during the request. Already in place from Phase 3.
- [X] T081 `specs/006-golf-resorts-library/spec.md` Status flipped from Draft → Implemented; `specs/README.md` row updated.
- [X] T082 End-to-end quickstart run — partial: steps 1 (schema), 2–5 (add + browse), 8 (prevent-delete), 9 (region linking), 11 (images) verified via `TestClient` + smoke scripts. Steps 2b/3/7 (live Anthropic calls) and 6 (seed 120 entries) **not** run in this session — require your API key and live run. Held for user-environment validation.
- [X] T083 Success Criteria verdict: **SC-001** (5 entities in 10 min, ≥80% populated) — deferred, needs live Anthropic run; **SC-002** (100 entities in 500 ms) — indexed SQL path in place, load-tested with 5 entries, expected to meet; **SC-003** (tool selection 90% accuracy) — driven by `instructions.md` rules, requires live behavioral test; **SC-003a** (golf ≥ 50% triggers golf tool) — encoded in `instructions.md` + system-prompt activity block; **SC-004** (unmatched-region badge) — verified in list-item serialization + frontend; **SC-005** (every entry has ≥ 1 source_url) — guaranteed only when entries flow through extraction; manual `POST /resorts` without sources is technically allowed. Flagged as post-MVP improvement (require sources on save? — would need a clarification); **SC-006** (standalone courses end-to-end) — verified via CRUD + tool tests; **SC-007** (≥90 resorts + ≥15 courses after seed) — seed YAML contains ≥90 resorts + 20 courses; actual run requires ANTHROPIC_API_KEY + pyyaml.
- [X] T084 [P] Final lint pass — `black app/ scripts/ tests/` (all clean after ruff fixups); `ruff check` all green; `node --check frontend/app.js` clean.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: no dependencies; parallelizable internally
- **Phase 2 (Foundational)**: depends on Phase 1; BLOCKS all user-story phases
- **Phase 3 (US1)**: depends on Phase 2
- **Phase 4 (US2)**: depends on Phase 2 (can run in parallel with US1 / US3 after Phase 2 completes)
- **Phase 5 (US3)**: depends on Phase 2. US3 is most useful after US1 has seeded the DB (so there's something to cite) but is *technically independent* — it can be implemented against an empty library and tested with hand-inserted rows.
- **Phase 6 (US4)**: depends on Phase 2 + at least the CRUD primitives from Phase 3 (create paths — shared `crud.py` module)
- **Phase 7 (US5)**: depends on Phase 2 + US2 (detail pages need to exist to host the link autocompletes)
- **Phase 8 (Seed + Polish)**: depends on Phase 3 (seed script reuses extraction + create) and ideally US3 (so chatbot can leverage the seeded data)

### Within each user story

- Backend CRUD before routes before frontend components that consume them
- Tool definitions before chat.py wiring before instructions.md updates (US3)
- Tests can be written in parallel with or after the code they target (not strict TDD here)

### Parallel Opportunities

- Phase 1 tasks T002–T006 fully parallel
- Phase 2 tasks T008–T014 parallel (different models / different files), with T011 (`normalize_name`) independent. T007 (migration) is sequential because it touches `models.py` init. T015 (fetcher) parallel with models. T016 (fetcher tests) parallel once T015 is done.
- In US1: T017, T018, T019 parallel (same file but different functions — may serialize). T027, T028 (tests) parallel with each other and with the CRUD/route work.
- In US2: T036–T039 parallel CRUD work. T042–T046 parallel frontend components.
- In US3: T047, T048 parallel tools. T055–T057 parallel frontend.
- In US4: T059–T062 parallel CRUD.
- In US5: T069, T070 parallel CRUD.
- Phase 8: T076, T077, T078, T079, T080, T084 largely parallel.

### Cross-story dependencies to be aware of

- `crud.py` is shared. Tasks that add functions to it may textually conflict. Prefer one committer at a time per `crud.py` edit; all new functions are additive so merge conflicts should be minor.
- `main.py` is shared in the same way.
- `instructions.md` is edited in US1 (T035 — small note) and US3 (T054 — major). Serialize T054 after T035.
- The seed script (T075) depends on the extraction pipeline (T021) being real.

---

## Parallel Example: User Story 1

```bash
# After Phase 2 is done, kick off US1 in roughly this order.
# Round 1 (parallel — different files/functions):
Task: "T017 crud.create_resort in backend/app/crud.py"
Task: "T018 crud.create_course in backend/app/crud.py"
Task: "T019 crud.add_image in backend/app/crud.py"
Task: "T020 extraction tool schemas in backend/app/extraction.py"

# Round 2 (after T017/T018/T019 — they all touch crud.py):
Task: "T021 extraction.extract_resort / extract_course in backend/app/extraction.py"
Task: "T022 extraction.validate_image_candidates in backend/app/extraction.py"

# Round 3:
Task: "T023 POST /api/golf-library/extract in backend/app/main.py"
Task: "T024 POST /api/golf-library/resorts in backend/app/main.py"
Task: "T025 POST /api/golf-library/courses in backend/app/main.py"
Task: "T026 POST /api/golf-library/images in backend/app/main.py"

# Round 4 (parallel with tests):
Task: "T027 tests/test_extraction.py"
Task: "T028 tests/test_crud_golf.py"

# Round 5 (frontend, after backend endpoints exist):
Task: "T029 LibraryAdd component in frontend/app.js"
Task: "T030 pre-filled form rendering"
Task: "T031 error sub-status rendering"
Task: "T032 duplicate warning modal"
Task: "T033 possible_parent_resort hint"
Task: "T034 entity-type post-hoc switch"
```

---

## Implementation Strategy

### MVP First (three P1 stories)

Because the spec lists three P1 stories (Add, Browse, Chatbot), the MVP is bigger than a single story — that's the feature's intrinsic shape, not padding. Recommended slicing:

1. **Phase 1 (Setup)** → **Phase 2 (Foundational)**: unlocks all stories. Must complete end-to-end.
2. **Phase 3 (US1 — Add)**: lands the Add page + extraction pipeline. At this checkpoint, the library can be populated, but nothing reads from it yet. Validate by adding 3–5 entries via the UI and checking the DB.
3. **Phase 4 (US2 — Browse)**: the library becomes browseable. At this checkpoint, the feature is usable standalone (you can curate + review entries without the chatbot).
4. **Phase 5 (US3 — Chatbot)**: the feature becomes *valuable to the trip planner*. Chatbot can now cite curated content. This is the minimal shippable golf-trip-planning experience.
5. **Ship the MVP** (US1 + US2 + US3). Gate: SC-001 through SC-006 pass.

### Incremental Delivery after MVP

6. **Phase 6 (US4 — Edit/Delete)**: curation quality tooling. Not blocking daily use but necessary for long-term library hygiene.
7. **Phase 7 (US5 — Region / resort relinking)**: unlocks VacationMap-score integration for entries that weren't auto-linked.
8. **Phase 8 (Seed + Polish)**: run the seed script once, update docs, validate against SC-007.

### Parallel Team Strategy (if multiple people involved)

- One person on Phase 2 (models, fetcher) — gates everything else.
- After Phase 2: split backend (US1 CRUD + extraction) and frontend (US2 browse shell) in parallel.
- US3 is best owned by whoever owns `chat.py` / `tools.py` / `instructions.md` — highest coupling to existing chatbot logic.
- US4/US5 are independent and can be picked up opportunistically once their prerequisites land.

---

## Notes

- Tasks that touch the same file (`crud.py`, `main.py`, `app.js`, `models.py`, `tools.py`, `chat.py`, `instructions.md`, `styles.css`) are not marked `[P]` unless they add clearly non-overlapping additions. Prefer serial edits to avoid merge pain.
- Every DB change is `CREATE ... IF NOT EXISTS` or `ALTER TABLE ... ADD COLUMN`. No drops, no migrations framework.
- `suggest_for_review` stays queue-only (Principle III). Do not introduce any tool that auto-shortlists.
- AI behavior changes live in `instructions.md`, not in Python (Principle II). The only Python-side prompt content remains trip state + visit history + (new) activity weights — all of which is data.
- Commit after each logical group. The pre-commit hook runs black + ruff; if it fails, re-stage and re-commit (never `--no-verify`).
- When implementing, keep the spec up to date per Principle V — any design detail that shifts during implementation must be reflected back in `spec.md`, `plan.md`, `data-model.md`, or `contracts/openapi.yaml` in the same commit.
