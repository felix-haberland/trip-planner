# Feature Specification: Golf Courses & Resorts Library

**Feature Branch**: `feat/006-golf-resorts-library`
**Created**: 2026-04-18
**Status**: Implemented
**Input**: User description: "Curated library of golf courses and resorts with rich metadata (location, courses, hotel, price, source, etc.), browseable with filters/sorting, AI-assisted entry from name or URL, surfaced by the chatbot during golf trip planning."

## Clarifications

### Session 2026-04-18

- Q: Data entry — just URL, or also name-only? → A: Both. Name-only triggers AI web search; URL triggers AI page fetch + extraction.
- Q: Chatbot integration approach? → A: Separate golf-specific tools, with a light hint from `search_destinations` that curated content exists in a region. Golf-trip ranking differs fundamentally from broad regional scoring.
- Q: Region matching — require VacationMap link? → A: No. Allow unmatched entries and clearly indicate them. User can link later via the existing autocomplete pattern.
- Q: Multi-user / sharing? → A: Single-user, single-library for v1. No export.
- Q: Are courses first-class entities or only children of resorts? → A: **Both are first-class.** Typical user prompts include "show me the best golf courses at [location]" (course-centric, resort may be irrelevant) as well as "golf resorts for June" (resort-centric). The library must support adding, browsing, filtering, and searching both entities independently. A course can belong to a resort, or exist standalone (no resort at all — e.g., a public championship course).
- Q: Server-side URL fetch safety posture (SSRF)? → A: **Strict.** Allow only `http`/`https`; block private IP ranges (RFC1918, loopback, link-local, 169.254/16); 10s timeout; cap response body at 5 MB.
- Q: Deduplication rule when saving a new resort/course? → A: **Normalize** — lowercase + collapse whitespace + strip punctuation on name, then exact match on `(name_norm, country_code, entity_type)`. Warn the user before saving; let them proceed, edit the existing entry, or cancel.
- Q: `rank_rating` model — single AI-derived score, per-source breakdown, both, or tags? → A: **Single AI-derived 0–100 score only.** Keeps filtering/sorting simple. Per-source provenance is not persisted as structured data; the AI may mention notable rankings in the `description` field during extraction, but the canonical signal for filters and sorts is the single scalar.
- Q: How should AI-extraction failures be surfaced to the user? → A: **Sub-statused errors, no auto-retry.** The backend returns one of `api_error`, `no_match`, `fetch_error`, or `ambiguous` with a human-readable message. The UI renders a specific message per status. The form stays blank unless partial extraction succeeded (in which case partial fields are filled and flagged). The user can retry manually or enter fields by hand.
- Q: How does the chatbot know a trip is golf-themed? → A: **Weighted activity tags on the trip + free-text fallback.** Trips gain a structured `activity_weights` field — a dict mapping activity tag (e.g., `golf`, `hiking`, `beach`, `city`, `culture`, `relaxation`, `food`, `nature`) to an integer 0–100 representing relative focus (e.g., `{golf: 70, hiking: 30}`). Weights should sum to ~100 but are not strictly enforced. The system prompt includes the weights and instructs Claude to prioritize tools/content matching the highest-weighted activities, giving proportional airtime to secondary ones. When `activity_weights` is empty or absent, Claude falls back to free-text inference from the user's prompt (today's behavior).

### Session 2026-04-18 (round 2)

- Q: Cascade behavior when deleting a resort or course that other records reference? → A: **Prevent deletion.** If a resort has attached courses, or any trip's shortlisted/suggested/excluded destination record references the resort or course (`resort_id` or `course_id`), the delete is refused. The UI surfaces the blocking references and guides the user to detach first (delete or reassign the attached courses; remove the `resort_id` / `course_id` from each referencing shortlist entry). No soft-delete; deletion is always explicit and always preceded by manual cleanup.
- Q: Green fee data type — freetext, structured + notes, single number, or tiered enum? → A: **Structured + notes.** Split `green_fee_range` into `green_fee_low_eur` (int, nullable), `green_fee_high_eur` (int, nullable), and `green_fee_notes` (freetext, nullable) on `golf_courses`. AI extraction parses numeric amounts when the source is specific, otherwise leaves the numeric fields null and fills `green_fee_notes` with the raw phrase. Filters and sorts operate on the numeric fields; display combines both (e.g., "€120–180 (peak season)").
- Q: Photos / images support? → A: **Gallery (up to 5 per entity).** Introduce a separate `entity_images` table (id, entity_type, entity_id, url, caption, display_order, created_at). AI extraction captures up to 5 candidate images per resort/course (Open Graph, meta:image, hero banners, gallery thumbnails). Images are stored as external URLs only — no local download in v1. Browse list shows the first-by-`display_order` image as a thumbnail; detail pages show a carousel over all images. Images are owned children of their parent entity: when a resort or course is deleted (after passing the prevent-delete checks), its `entity_images` rows cascade-delete.
- Q: Seed / starter data strategy? → A: **Rich seed via the same extraction pipeline.** Ship a `scripts/seed_golf_library.py` that feeds the regular AI extraction pipeline with a curated list of ~100 European resorts (anchored on the Today's Golfer "100 best golf resorts in Continental Europe" list, cross-referenced with Top 100 Golf Courses and similar sources) plus ~20 globally iconic standalone courses (Old Course St Andrews, Royal County Down, Portmarnock, Pebble Beach equivalents where relevant). The script runs the same URL/name → Claude extraction flow used by the UI, so the seed data is dogfooded and dedup-safe (entries whose normalized name + country already exist are skipped). Not invoked automatically on startup — the user runs it explicitly, typically once on a fresh install. Runtime cost (Claude API tokens + web search) is flagged in the script's docstring.
- Q: AI extraction cost & concurrency guardrails on the UI Add flow? → A: **No guardrails.** Trust the user. The UI Add form triggers one extraction per Fetch click; no debounce, no server-side quota, no cost tracking, no concurrency cap. Claude API usage and spend are monitored via the Anthropic dashboard outside the app. The seed script's own rate-limiting (FR-S-004) is scoped to bulk runs only; on-demand UI extractions remain unthrottled.

### Session 2026-04-18 (round 3)

- Q: How does the chatbot look up a specific named resort/course (e.g., "what about Monte Rei?") — the search tools have country/price/tag filters but no name filter? → A: **Name filter on existing tools + fallback allowed to general knowledge.** Both `search_golf_resorts` and `search_golf_courses` gain an optional `name_query` parameter that runs a fuzzy match against the entity's `name_norm` (using the same lowercase/whitespace/punctuation normalization as dedup). No new tools are added. The system prompt is updated so that when the user asks about a specific named entity, Claude MUST first call the relevant search tool with `name_query` set. If the library has the entity, Claude presents curated data and cites it as "from your library". If the library does not have the entity, Claude MAY answer from general knowledge but MUST clearly label the response as "not in your curated library yet" and offer to add it (pointing at the Add page). The library is the primary source; general knowledge is an explicit fallback.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Add a Resort or a Course by Name or URL with AI Extraction (Priority: P1)

The user opens an "Add to Golf Library" page and first picks what they're adding: **a resort** (hotel + one or more courses) or **a single course** (may or may not belong to a resort). They either paste a URL or type just the name. The AI fetches relevant information — for URLs via direct page fetch, for names via web search — and populates a structured form appropriate to the entity type. The user reviews, edits if needed, and saves.

For resorts, the AI also extracts the courses on-property and creates them as attached course records. For standalone courses, the AI extracts course-level data only; if the course happens to belong to a resort that is not yet in the library, the AI surfaces a suggestion ("This course is part of Quinta do Lago resort — add the resort too?") but does not auto-create it.

**Why this priority**: Without a low-friction way to populate the library, it will never accumulate enough data to be useful. Manual entry of dozens of fields per entity is the single biggest barrier. Supporting both entity types from day one means the user can reflect the real-world mix — some great courses aren't part of a branded resort.

**Independent Test**: On a fresh install, the user adds one resort (URL) and one standalone course (name only), confirms both produce pre-filled forms with plausible values, and saves both. The library then shows 1 resort (with its attached courses) and 1 extra standalone course.

**Acceptance Scenarios**:

1. **Given** the user is on the Add page with entity type = Resort, **When** they paste the URL `https://www.monterei.com` and click "Fetch", **Then** within 20 seconds the form is populated with the resort name, country, region (auto-linked to VacationMap if matched), at least one attached course with name/par/length, hotel type, price category, and a source reference. The user can edit any field before saving.
2. **Given** the user is on the Add page with entity type = Course, **When** they type only "Old Course, St Andrews" and click "Fetch", **Then** the AI performs a web search, identifies the specific course, and populates the form with course-level data (par, length, type, architect, year, description) plus country and region. No resort is created; the resort link is left empty with an optional suggestion to also add the surrounding resort/links complex.
3. **Given** the user is on the Add page with entity type = Resort and types "Son Gual Mallorca", **When** they click "Fetch", **Then** the AI returns resort-level fields plus any courses found on-property, drawn from multiple sources. The `source_urls` field lists all URLs consulted.
4. **Given** the AI cannot resolve the name to a specific entity (ambiguous or not found), **When** extraction completes, **Then** the form surfaces a clear error ("No resort/course found for 'XYZ'") and the user can enter fields manually.
5. **Given** the AI returns data but the region cannot be auto-linked to a VacationMap region, **When** the user reviews the form, **Then** the region field shows "Unmatched — enter freetext or link manually" with an autocomplete dropdown to link retroactively.
6. **Given** the user adds a standalone course whose name implies a parent resort (AI detects e.g., "North Course, Monte Rei"), **When** extraction completes, **Then** the form flags "This course appears to belong to Monte Rei — link to an existing resort or add it?" with actions to (a) link to an existing resort in the library via autocomplete, (b) dismiss and keep the course standalone, or (c) open the Add Resort flow pre-filled.

---

### User Story 2 - Browse the Library with Filters and Sorting (Priority: P1)

The user opens a "Golf Library" page with two tabs/modes: **Resorts** and **Courses**. Each mode shows columns appropriate to the entity.

- Resorts list: name, country/region, hotel type, price category, number of courses, rating/rank, best months.
- Courses list: name, country/region, parent resort (if any) or "Standalone", type (links/parkland/…), par, length, architect, difficulty, rank/rating.

Filters differ by mode:

- Resort filters: country, price category, hotel type, best month, tags, matched/unmatched region.
- Course filters: country, course type (links/parkland/…), difficulty, min holes, parent-resort presence (has-resort / standalone / any), tags, matched/unmatched region.

Clicking a row opens the detail view for that entity.

**Why this priority**: Browse + filter is the primary direct consumption path. Supporting both modes means the user can answer both "which resorts are in my library" and "which courses are in my library" without conflation.

**Independent Test**: With 10+ resorts and 5+ standalone courses loaded, the user switches to Courses mode, filters to "Scotland, type = links", sorts by rank ascending, and verifies the result includes both resort-attached courses and standalone courses matching the criteria.

**Acceptance Scenarios**:

1. **Given** 15 resorts are in the library, **When** the user is in Resorts mode and applies filter `country = Portugal`, **Then** only Portuguese resorts are listed.
2. **Given** resorts have `best_months` lists, **When** the user filters by `month = June`, **Then** only resorts whose `best_months` include June are shown.
3. **Given** the library has resort-attached courses and standalone courses, **When** the user switches to Courses mode without applying filters, **Then** both types appear in a single list with a clear "Parent resort" column (name or "Standalone").
4. **Given** the user is in Courses mode, **When** they filter `type = links` and `country = Scotland`, **Then** all matching courses are shown regardless of whether they belong to a resort.
5. **Given** the user clicks a resort row, **When** the detail view opens, **Then** all courses attached to the resort are shown with their individual attributes (par, length, architect, difficulty, description), plus the resort-level description and source links.
6. **Given** the user clicks a course row, **When** the detail view opens, **Then** the course's full attributes are shown, plus a link to the parent resort (if any) or a clear "Standalone course" indicator with the course's own country/region.

---

### User Story 3 - Chatbot Suggests Resorts or Courses for a Golf Trip (Priority: P1)

The user starts a new trip. Depending on how they frame the question, the chatbot reaches for different data:

- **Resort-centric prompt**: "Golf trip in June, 5–7 days, luxury resorts in Europe." → chatbot queries curated resorts and returns resort-level suggestions (name, region, number of courses, price category, rank, best months, rationale).
- **Course-centric prompt**: "Show me the best golf courses in Scotland" / "Top links courses I could play on a 3-day trip". → chatbot queries curated courses directly and returns course-level suggestions (name, parent resort or standalone, type, par, length, architect, difficulty, rank, rationale). It may group courses by region to help with multi-course trips.
- **Mixed prompt**: "A golf week in Portugal with at least one top-ranked course." → chatbot may call both tools: resorts (to anchor accommodation) + courses (to surface play options regardless of resort).

**Why this priority**: This is the *ultimate goal* stated in the feature request — the library exists so trip planning can leverage curated golf-specific data rather than generic regional scoring, for both typical user phrasings.

**Independent Test**: With 10+ resorts and 10+ courses (mix of resort-attached and standalone), the user tries (a) "best golf resorts for June, luxury" and verifies resort-level suggestions, and (b) "best golf courses in Scotland" and verifies course-level suggestions including at least one standalone course.

**Acceptance Scenarios**:

1. **Given** the library has 20 resorts and the user describes a golf trip in June, **When** the chatbot responds, **Then** at least one tool call is made to `search_golf_resorts` with filters derived from the trip (month, activity=golf, possibly price tier), and the response cites specific resorts from the library by name.
2. **Given** the library has 30 courses and the user says "best links courses in the UK", **When** the chatbot responds, **Then** at least one call is made to `search_golf_courses` with filters (country, type=links), and the response cites specific courses by name — including standalone ones — with their par, length, architect, and rank if available.
3. **Given** the chatbot finds 5 matching resorts, **When** it presents suggestions, **Then** each suggestion includes: resort name, region (and VacationMap link status), number of courses, price category, rank/rating if available, best months, and a brief rationale tying resort attributes to the trip criteria.
4. **Given** the chatbot finds 5 matching courses, **When** it presents suggestions, **Then** each includes: course name, parent resort (or "Standalone"), country/region, type, par, length, architect (if known), difficulty, rank, and a brief rationale.
5. **Given** `search_destinations` returns a region that has curated content in the library, **When** Claude reads the response, **Then** the region entry includes both `curated_resort_count` / `resort_names` and `curated_course_count` / `course_names` hints so Claude can mention specific entities rather than generic "good for golf" phrasing.
6. **Given** the chatbot suggests a resort or a course via the existing `suggest_for_review` flow, **When** the backend resolves the suggestion, **Then** the resort_id *or* course_id is attached to the suggestion record alongside the region link, so the user's shortlist can point to a specific entity.

---

### User Story 4 - Edit & Delete Library Entries (Priority: P2)

The user opens a resort detail, edits any field (e.g., corrects the price category, adds notes about a recent visit, updates a course description), and saves. Optionally, they delete a resort entirely. All edits are persisted immediately.

**Why this priority**: Necessary for maintaining quality over time but not blocking the initial value loop.

**Independent Test**: User edits a resort's price category and personal_notes, saves, reloads the page, and confirms changes persisted.

**Acceptance Scenarios**:

1. **Given** a resort exists, **When** the user edits any field on the detail page and clicks Save, **Then** the change is persisted and reflected in the library list view.
2. **Given** a resort exists with no attached courses and no references from any trip's shortlist/suggested/excluded records, **When** the user clicks Delete and confirms, **Then** the resort is removed from the library.
3. **Given** a resort has 2 attached courses and 1 shortlist entry referencing it, **When** the user clicks Delete, **Then** the system refuses the delete and the UI lists the blockers (2 attached courses, 1 shortlist entry in trip "June Golf") with inline actions to detach or delete each reference. Only after all blockers are resolved can the resort be deleted.
4. **Given** a course is referenced by a shortlist entry, **When** the user clicks Delete on the course, **Then** the system refuses and surfaces the referencing shortlist entry (trip name + context) with a "Remove from shortlist" action.

---

### User Story 5 - Link Resort to VacationMap Region Retroactively (Priority: P2)

A resort was added with an unmatched region (e.g., "Sintra area" — not a VacationMap region). Later, VacationMap adds the region, or the user wants to link it to an existing one ("Lisbon Coast"). The user opens the resort detail, uses the region autocomplete (same component as the existing manual linker at `/api/vacationmap/regions/search`), picks a region, and the link is saved.

**Why this priority**: Unmatched resorts still add value, but linking unlocks regional-score integration in the chatbot.

**Independent Test**: User creates a resort with freetext region "Sintra area", then links it to VacationMap region `PT:Lisbon Coast`, and verifies the detail page now shows VacationMap scores for that region.

**Acceptance Scenarios**:

1. **Given** a resort has `country_code: PT` and freetext `region_name_raw: "Sintra area"` but no `vacationmap_region_key`, **When** the user uses the region linker and picks `PT:Lisbon Coast`, **Then** `vacationmap_region_key` is set and VacationMap scores become visible on the resort detail.

---

### Edge Cases

- **AI extraction partial success**: If the AI fetches a page but can only extract some fields (e.g., name + courses but no pricing), the form is populated with what's known and missing fields are clearly marked empty. The save is allowed.
- **Duplicate resort or course**: Before saving, the system computes `name_norm` (lowercase, whitespace collapsed to single spaces, ASCII punctuation stripped) and checks for existing entries where `(name_norm, country_code, entity_type)` matches. If a match is found, the user is presented with the existing entry and offered three actions: **Create anyway** (save a new record), **Edit existing** (discard the new input and open the existing entry), or **Cancel**. The match is a soft warning, not a DB-level unique constraint, so the user always has the final say.
- **URL that doesn't resolve to a single resort** (e.g., a listicle with 20 resorts): The AI returns a list of candidate resorts found on the page, and the user picks one to extract. Batch import is out of scope for v1.
- **Stale source**: Source URLs may 404 over time. A `source_checked_at` timestamp is stored; no automatic re-check in v1, but the field is visible so the user can spot old entries.
- **Course without a resort** (standalone public course, no hotel): Supported as a first-class standalone course record with `resort_id = null`. The course carries its own country_code and region fields — no resort wrapper is needed.
- **Resort added after its standalone course**: The user can retroactively link an existing standalone course to a newly-added resort via the course detail page's "Link to resort" autocomplete. The course's own country/region fields remain but the resort becomes the source of truth for those at query time.
- **Resort with unknown best months**: `best_months` is optional. If empty, month filters treat the resort as "any month" and the chatbot notes that seasonality info is missing.
- **Chatbot asks for something no resort matches**: Graceful fallback — chatbot returns no resort matches and defers to `search_destinations` (regional scoring) with a note that no curated resorts fit the criteria.

## Requirements *(mandatory)*

### Functional Requirements

#### Library data model

- **FR-001**: System MUST persist golf resorts in `trips.db` with attributes: id, name, url, source_urls (list), country_code, region_name_raw (freetext), vacationmap_region_key (nullable link to `country_code:region_name` pattern), town, latitude, longitude, hotel_name, hotel_type (`luxury` / `boutique` / `golf_hotel` / `none`), star_rating (0–5, nullable), price_category (`€` / `€€` / `€€€` / `€€€€`), best_months (list of month numbers 1–12), description (markdown), amenities (list of tags), rank_rating (0–100, nullable), tags (list), personal_notes (markdown), source_checked_at, created_at, updated_at.
- **FR-002**: System MUST persist golf courses in `trips.db` as a first-class entity. Each course MAY be linked to a resort (0..n courses per resort) or MAY be standalone (no parent resort). Attributes: id, resort_id (nullable foreign key to golf_resorts), name, url (nullable — for standalone courses with their own site), source_urls (list), country_code, region_name_raw (freetext), vacationmap_region_key (nullable), town, latitude, longitude, holes (9/18/27/36), par, length_yards, type (`links` / `parkland` / `heathland` / `desert` / `coastal` / `mountain` / `other`), architect, year_opened, difficulty (1–5), signature_holes (markdown), description (markdown), green_fee_low_eur (int, nullable), green_fee_high_eur (int, nullable), green_fee_notes (freetext, nullable — e.g., "peak season", "guest rate only"), best_months (list), rank_rating (0–100, nullable), tags (list), personal_notes (markdown), display_order (for multi-course resorts), source_checked_at, created_at, updated_at.
- **FR-002b** (green fee extraction): AI extraction MUST attempt to parse numeric amounts from the source into `green_fee_low_eur` and `green_fee_high_eur` (single-value sources fill both fields with the same amount). Non-EUR currencies SHOULD be converted to approximate EUR at extraction time (rounded to the nearest 5) with the original phrasing preserved in `green_fee_notes`. If no numeric amount can be determined, both numeric fields MUST remain null and the raw phrase goes into `green_fee_notes`.
- **FR-002a**: When a course has a `resort_id`, the course's country/region fields MAY be left null and are inherited from the resort at query time. Standalone courses (no `resort_id`) MUST provide their own country_code and optional region link.
- **FR-003**: System MUST migrate the schema via `ALTER TABLE ADD COLUMN` / `CREATE TABLE IF NOT EXISTS` — never drop existing tables. New tables are created alongside existing ones.
- **FR-003a** (dedup normalization): Both `golf_resorts` and `golf_courses` tables MUST persist a derived `name_norm` column alongside `name`. `name_norm` is computed as: lowercase → collapse runs of whitespace to a single space → strip ASCII punctuation (`.,;:!?'"/\\-_()[]{}`). The column is indexed together with `country_code` to make the dedup check cheap. `name_norm` is recomputed on every insert/update; it is derived data, not user-editable.
- **FR-003b** (images table): System MUST persist an `entity_images` table with attributes: id (PK), entity_type (`resort` / `course`), entity_id (FK to the corresponding table, not enforced at DB level since it's polymorphic — enforced in application code), url (external URL, not downloaded), caption (nullable), display_order (int), created_at. Indexed on `(entity_type, entity_id, display_order)` for ordered retrieval. When the parent resort or course is deleted (after passing FR-020a prevent-delete checks), its owned `entity_images` rows MUST be deleted by the application before or within the same transaction.

#### AI-assisted entry

- **FR-004**: System MUST provide an "Add to Golf Library" form where the user first selects entity type (Resort or Course), then submits either a URL or a name (not both required — either one). A "Fetch" action triggers AI extraction.
- **FR-005**: When a URL is submitted, the backend MUST fetch the page content (via server-side fetch, not via the user's browser) and pass it to Claude with a structured extraction prompt matching the selected entity type. Claude returns JSON — resort+courses schema for Resort, single-course schema for Course.
- **FR-005a** (URL fetch safety — SSRF guardrails): The server-side fetcher MUST enforce the following restrictions on every request:
  - Scheme allowlist: `http` and `https` only. All other schemes (`file`, `ftp`, `gopher`, `data`, etc.) rejected with a clear error.
  - Host resolution: after DNS resolution, reject addresses in private/reserved ranges — RFC1918 (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16), loopback (127.0.0.0/8), link-local (169.254.0.0/16), IPv6 equivalents (fc00::/7, ::1/128, fe80::/10), and `0.0.0.0`.
  - Timeout: total request duration capped at 10 seconds (connect + read).
  - Response size: response body capped at 5 MB; larger responses are truncated and flagged, or rejected, with a clear error.
  - Redirects MUST be re-validated against the same rules (a 302 to `http://127.0.0.1` must be blocked).
- **FR-006**: When a name is submitted without a URL, the backend MUST invoke Claude with web search enabled, instruct it to identify the specific entity and gather data from multiple sources, and return structured JSON plus the list of URLs consulted.
- **FR-006a**: For course-type extraction, the AI MUST additionally surface a "possible parent resort" hint if it detects that the course belongs to a branded resort. The hint includes the detected resort name and (if possible) whether a matching resort already exists in the library. The backend MUST NOT auto-create a parent resort.
- **FR-006b** (image extraction): AI extraction MUST return up to 5 candidate image URLs per entity, prioritizing in order: (1) Open Graph `og:image`, (2) schema.org `image` meta tags, (3) hero/banner images identifiable in the page structure, (4) gallery/slider thumbnails. Each candidate includes an optional caption when inferable from `alt` text or surrounding context. The extraction form displays the candidates as a thumbnail strip; the user can remove unwanted ones and reorder before saving. URLs that fail a lightweight HEAD validation (non-200, non-image content-type) are flagged in the form but still saved if the user chooses to keep them.
- **FR-007**: The extraction response MUST populate a form the user reviews before saving. No automatic persistence without user confirmation. The user can edit every field and can change the entity type post-hoc (e.g., "this is actually a full resort, not a single course") — the form re-renders to the other schema and preserves overlapping fields.
- **FR-008**: If extraction fails or is ambiguous, the backend MUST return a structured error response `{status, message, partial_data?}` where `status` is one of:
  - `api_error` — Claude API itself failed (timeout, rate limit, 5xx). Message suggests retrying in a moment.
  - `no_match` — Name-only web search returned no plausible candidate. Message suggests refining the name, supplying a URL, or entering manually.
  - `fetch_error` — URL fetch failed (non-200, non-HTML, SSRF-blocked, truncated at 5 MB, or timeout). Message includes the HTTP status or block reason.
  - `ambiguous` — Multiple candidates found and the AI could not confidently pick one. Message lists top candidates (where available) so the user can disambiguate on next attempt.
  The backend MUST NOT auto-retry. If partial data was extracted before the failure (e.g., name + URL but no scorecard), `partial_data` contains those fields and the UI pre-fills them with a "partial — review before saving" flag. The user can then retry, refine inputs, or complete the form manually.
- **FR-009**: Region resolution during extraction MUST use the existing fuzzy resolver (`tools._resolve_lookup_key`). If resolved, the form shows the matched region with a "Matched automatically" indicator. If not resolved, the form shows `region_name_raw` as freetext and prompts the user to link manually (optional).

#### Browse & detail

- **FR-010**: System MUST provide a "Golf Library" browse page with two modes/tabs: **Resorts** and **Courses**. Both modes share the same page shell and filter-panel pattern but render mode-specific columns and filters.
- **FR-010a**: Resorts mode list columns: hero thumbnail (first image by `display_order`, fallback placeholder if none), name, country/region, hotel type, price category, number of courses, rank/rating, best months badge.
- **FR-010b**: Courses mode list columns: hero thumbnail (first image by `display_order`, fallback placeholder if none), name, parent resort (or "Standalone"), country/region, type, par, length, architect, difficulty, rank/rating.
- **FR-011**: Filters MUST be mode-specific:
  - Resorts: country, price category, hotel type, month (from best_months), tags (multi-select), matched/unmatched region.
  - Courses: country, course type (links/parkland/heathland/desert/coastal/mountain/other), difficulty range, min holes, parent-resort presence (has-resort / standalone / any), tags, matched/unmatched region, green-fee max (€ numeric slider).
- **FR-012**: Sorting MUST be mode-specific:
  - Resorts: rank_rating, price_category, number of courses, updated_at.
  - Courses: rank_rating, length_yards, difficulty, green_fee_low_eur, updated_at.
- **FR-013**: Clicking a resort row MUST open a resort detail view showing an image carousel over all `entity_images` (if any), the full resort record, all attached courses with their full data (each with its own image carousel if present), source URLs (clickable), personal notes, and VacationMap scores for the linked region (if linked).
- **FR-013a**: Clicking a course row MUST open a course detail view showing an image carousel over all `entity_images` for the course (if any) and the full course record. If the course has a `resort_id`, the view MUST include a summary card linking to the parent resort. If standalone, the view MUST clearly indicate "Standalone course" and show the course's own country/region.
- **FR-014**: Both detail views MUST support inline editing of all fields, a Delete action with confirmation, a "Link to VacationMap region" autocomplete when `vacationmap_region_key` is null, and an image-management panel (add URL, remove, reorder, edit caption). Course detail additionally MUST support linking to an existing resort (autocomplete over resorts in the library) or unlinking to make the course standalone.

#### Chatbot integration

- **FR-015**: System MUST add a new Claude tool `search_golf_resorts` with input parameters: `name_query` (optional — fuzzy match against `name_norm`), country (optional), price_category (optional list), hotel_type (optional list), month (optional 1–12), tags (optional list), min_rank (optional), limit (default 10). The tool returns resort records with their top-ranked course summarized. When `name_query` is supplied, results are ordered by match quality.
- **FR-015a**: System MUST add a new Claude tool `search_golf_courses` with input parameters: `name_query` (optional — fuzzy match against `name_norm`), country (optional), course_type (optional list of links/parkland/…), min_difficulty (optional), max_difficulty (optional), min_holes (optional), parent_resort_filter (`any` / `has_resort` / `standalone`, default `any`), tags (optional list), month (optional 1–12), min_rank (optional), max_green_fee_eur (optional int), limit (default 10). The tool returns course records, each including parent resort name (if any), country/region, par, length, architect, type, difficulty, rank, and green-fee range (low/high EUR + notes). When `name_query` is supplied, results are ordered by match quality.
- **FR-015b** (named-entity lookup behavior): When the user's message references a specific named resort or course, the chatbot system prompt MUST direct Claude to first call the relevant search tool with `name_query` set to the named entity. Two branches:
  - **Library hit**: Claude presents the curated record and labels it "from your library" so the user knows the source.
  - **Library miss**: Claude MAY answer from general knowledge, but MUST prefix or clearly label the response with "not in your curated library yet" and offer to add it via the Add page. The library is the primary source; general knowledge is an explicit fallback, never silent.
- **FR-016**: The existing `search_destinations` tool MUST annotate each region in its response with `curated_resort_count` and up to 3 `resort_names` when resorts exist in the library for that region, AND `curated_course_count` with up to 3 `course_names` when courses exist (counting both resort-attached and standalone courses). No data duplication — derived at query time.
- **FR-017**: The chatbot system prompt (`instructions.md`) MUST be updated to describe both new tools, when to use each one (resort-centric vs course-centric user intent), and how to present resort suggestions vs course suggestions distinctly from regional suggestions. The AI should choose the right tool based on the user's phrasing ("resorts for June" → resorts tool; "best courses at X" → courses tool; golf-themed trip without specific framing → call both).
- **FR-017a** (trip activity weights — new schema on existing `trip` entity):
  - Trips MUST gain an `activity_weights` column (JSON dict). Keys are activity tags from an enumerated vocabulary: `golf`, `hiking`, `beach`, `city`, `culture`, `relaxation`, `food`, `nature`, `wellness`, `adventure`. Values are integers 0–100 representing relative focus. Weights should sum to ~100 but are not strictly enforced; the system prompt normalizes them for reasoning purposes.
  - The trip creation and edit UI MUST let the user add one or more activities with a percentage input (default: a single activity at 100%). An "untagged" trip is allowed (empty dict).
  - The system prompt MUST include `activity_weights` as structured context on every message. The prompt instructs Claude to:
    - Always consider the golf tools when `golf >= 30%`, giving them airtime proportional to the weight.
    - When `golf >= 50%`, treat the golf tools as the primary source for suggestions.
    - When `activity_weights` is empty, fall back to inferring intent from the user's free-text prompt (today's behavior — preserves backward compatibility for existing trips).
  - The same weighting convention is reserved for future activity-specific tools (hiking, culture, etc.); this feature only wires up the `golf` weight to the new golf tools.
- **FR-018**: When Claude calls `suggest_for_review`, the system MUST accept an optional `resort_id` or `course_id` parameter (mutually exclusive — a suggestion points to at most one library entity) so the suggestion record can point to a specific resort or specific course (not just a region).
- **FR-019**: The shortlisted/excluded/suggested destination records MUST support optional `resort_id` and `course_id` columns (both nullable, mutually exclusive by convention) linking the record to a specific entity in the library.

#### Seed data

- **FR-S-001** (seed script): System MUST ship `scripts/seed_golf_library.py` that populates the library with a curated starter set via the same AI extraction pipeline used by the UI. Scope:
  - ~100 European resorts anchored on the Today's Golfer "best resorts in Continental Europe" list, cross-checked against Top 100 Golf Courses and similar curated sources. Resorts are specified as a list of either URLs or `(name, country_code)` tuples.
  - ~20 globally iconic standalone courses (e.g., Old Course St Andrews, Royal County Down, Portmarnock, Muirfield) as course-type entries with `resort_id = null`.
- **FR-S-002** (idempotence & dedup): The seed script MUST be safe to re-run. For each candidate, it computes `name_norm` + `country_code` and skips entries that already exist (resort or course, per `entity_type`). Skipped entries are logged; newly-created entries are logged with their generated ids.
- **FR-S-003** (pipeline reuse): Each seed entry MUST flow through the same FR-005 (URL fetch) or FR-006 (name-only web search) → Claude extraction path used by the UI's Add form. No parallel/shortcut persistence path is allowed. This guarantees the seed data exercises the same code paths as user-entered data.
- **FR-S-004** (rate limiting): Because the seed runs ~120 extractions, it MUST serialize calls (no concurrency) and pause briefly between calls to stay within Anthropic API rate limits. Failures on individual entries are logged and skipped; the script reports a per-entry success/failure summary at the end.
- **FR-S-005** (not automatic): The seed script MUST NOT run automatically on startup or during migrations. The user invokes it explicitly. The script's docstring MUST flag the expected wall-clock time and approximate Claude API cost so the user can decide when to run it.
- **FR-S-006** (source list transparency): The curated resort + course list MUST live in a readable file (e.g., `backend/seed_data/golf_library_seed.yaml`) so the user can edit, append, or remove entries before running the seed. The file format is documented in the script's docstring.

#### Data safety & transparency

- **FR-020**: System MUST NOT delete any resort or course on schema migrations. Deletes are only user-initiated via the UI.
- **FR-020a** (cascade on user-initiated delete — prevent):
  - Deleting a **resort** MUST be refused if either (a) any `golf_courses` row has `resort_id = <this resort>`, or (b) any shortlisted / suggested / excluded destination record in any trip has `resort_id = <this resort>`.
  - Deleting a **course** MUST be refused if any shortlisted / suggested / excluded destination record in any trip has `course_id = <this course>`.
  - When a delete is refused, the API MUST return a structured response enumerating the blocking references: attached courses (for a resort) and/or referencing shortlist entries (for both). Each reference includes enough context for the UI to render a clickable item (trip name, section, etc.).
  - The UI MUST surface these blockers inline with actions to detach or delete each one. Only when all blockers are resolved can the user retry the delete.
  - This is application-level enforcement; no cascading foreign-key action is declared at the DB level (which would violate the prevent-delete contract).
- **FR-021**: Source URLs and `source_checked_at` MUST be visible in the detail view so the user can trace claims back to origin.

### Key Entities

- **Golf Resort**: A resort property that offers golf (hotel + one or more on-property courses). First-class entity. Has an optional link to a VacationMap region. Owns 0..n courses. Attributes capture hotel, pricing, seasonality, ranking, and provenance.
- **Golf Course**: A single 9/18/27/36-hole course. First-class entity. MAY belong to a resort (via `resort_id`) or be standalone (no parent resort — e.g., a public championship course or a famous links not tied to a hotel). Attributes capture technical golf data (par, length, type, architect) and qualitative data (difficulty, description, signature holes). Standalone courses carry their own country_code and region link; resort-attached courses inherit those from the parent when not explicitly set.
- **Entity Source**: The origin of a resort's or course's data (URL + timestamp). Stored on each entity via `source_urls` list and `source_checked_at`.
- **Entity Image**: An image associated with a resort or a course. Polymorphic link via `(entity_type, entity_id)`. Stored as an external URL (no local download in v1) with optional caption and display order. Up to 5 per entity in practice, though not strictly enforced. Owned child of the parent entity — deleted when the parent is deleted.
- **Shortlisted/Suggested Destination (extended)**: Existing entity gains optional `resort_id` and `course_id` links (mutually exclusive), so a shortlist entry can point to a specific resort or a specific course in the library, in addition to a region.
- **Trip (extended)**: Existing entity gains an `activity_weights` JSON dict (e.g., `{"golf": 70, "hiking": 30}`) expressing the relative focus of the trip across an enumerated activity vocabulary. Drives which activity-specific tools the chatbot prioritizes. Empty dict preserves today's free-text-inference behavior.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new user can add 5 entities via AI extraction (mix of resorts and courses, mix of URL and name-only) in under 10 minutes, with ≥80% of fields populated correctly without manual editing.
- **SC-002**: The library browse page renders 100 entities (in either mode) with filters applied in under 500ms.
- **SC-003**: For a resort-centric prompt ("golf resorts for June"), the chatbot uses `search_golf_resorts`; for a course-centric prompt ("best courses in Scotland"), it uses `search_golf_courses`. The correct tool is chosen on the first turn in at least 90% of test prompts.
- **SC-003a**: When a trip has `activity_weights.golf >= 50`, the chatbot calls at least one golf tool on the first turn of any destination-suggestion request, even if the user's free-text prompt does not mention golf.
- **SC-004**: Entities with an unmatched region still appear in browse and filter results, and are clearly flagged with an "Unmatched region" indicator in both the list and detail views.
- **SC-005**: 100% of entities have at least one `source_urls` entry (extraction must persist the sources used).
- **SC-006**: Standalone courses (no parent resort) can be added, browsed, filtered, and suggested by the chatbot end-to-end without any resort record existing.
- **SC-007**: After `scripts/seed_golf_library.py` completes on a fresh DB, the library contains ≥90 European resorts and ≥15 standalone iconic courses, with ≥80% of each entry's fields populated and 100% carrying at least one `source_urls` entry. Re-running the script adds 0 new entries.

## Assumptions

- Server-side URL fetching is allowed (no corporate proxy in the way). Implementation will use `httpx` against user-provided URLs with the SSRF guardrails in FR-005a (scheme allowlist, private-IP blocking, 10s timeout, 5 MB cap).
- Claude's web search tool is available and enabled for name-only extraction. If it is not available in the current SDK version, name-only entry degrades to requiring a URL (spec would need re-clarification).
- Resort quality rankings from sources like top100golfcourses.com are treated as editorial opinion, not ground truth. The `rank_rating` field is the sole structured quality signal — a single 0–100 score the AI derives from available signals (ranking position, ratings, editorial tone). No per-source rank breakdown is persisted; the AI may mention notable rankings (e.g., "#3 in Today's Golfer 2024 Europe list") inline in the `description` field, but filters and sorts use only `rank_rating`. No specific ranking authority is canonical.
- The curated library is supplementary to, not a replacement for, the regional VacationMap data. A golf trip plan may include both resort-level picks (from the library) and region-level picks (from VacationMap) in the same shortlist.
- Single-user scope: no sharing, export, or import of the library in v1. The library lives in `trips.db` alongside trip plans.
- AI extraction cost is the user's responsibility, monitored via the Anthropic dashboard outside the app. The UI Add flow imposes no debounce, quota, or cost tracking. The seed script (FR-S-001..S-006) is the only place where deliberate throttling is enforced, and only because it runs ~120 extractions in a batch.
- Schema changes follow CLAUDE.md data safety rules: `ALTER TABLE ADD COLUMN`, never drop.