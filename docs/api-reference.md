# API Reference

Base URL: `http://localhost:8000`

All requests/responses are JSON. CORS is open (`*`) — the app is intended for local/private network use only.

## Trips

### `GET /api/trips`
List all trips, ordered by `updated_at DESC`.

**Response** `200 OK`: `TripSummary[]`
```json
[{
  "id": 1,
  "name": "Golf Trip June 2026",
  "description": "golf trip in June, prefer short flights",
  "target_month": "jun",
  "status": "active",
  "suggested_count": 2,
  "shortlisted_count": 4,
  "excluded_count": 2,
  "created_at": "...",
  "updated_at": "..."
}]
```

### `POST /api/trips`
Create a trip.

**Request**: `{ "name": "...", "description": "..." }`
**Response** `201`: `TripSummary`

### `GET /api/trips/{trip_id}`
Full trip detail with all destinations and conversations.

**Response** `200`: `TripDetail` (extends `TripSummary` with `conversations[]`, `suggested[]`, `shortlisted[]`, `excluded[]`).

### `PUT /api/trips/{trip_id}`
Update name, description, or status.

**Request**: `{ "name"?: "...", "description"?: "...", "status"?: "active"|"archived" }`
**Response** `200`: `TripSummary`

### `DELETE /api/trips/{trip_id}`
Delete a trip and all child data (cascade).
**Response** `204`

---

## Suggested destinations (the review queue)

Suggested destinations are queued by Claude via `suggest_for_review`. The user triages them via these endpoints.

### `POST /api/trips/{trip_id}/suggested/{suggested_id}/shortlist`
Move from Suggested → Shortlisted.

**Request**: `{ "user_note"?: "..." }`
**Response** `200`: `{ "status": "shortlisted", "id": <int> }`

### `POST /api/trips/{trip_id}/suggested/{suggested_id}/exclude`
Move from Suggested → Excluded.

**Request**: `{ "reason": "..." }` (required)
**Response** `200`: `{ "status": "excluded", "id": <int> }`

### `PUT /api/trips/{trip_id}/suggested/{dest_id}/note`
Update the optional note on a suggested destination.

**Request**: `{ "user_note": "..." | null }`

### `POST /api/trips/{trip_id}/suggested/{dest_id}/link`
Link a suggested destination to a VacationMap region. Resolves real scores from `vacation.db` for the trip's `target_month`.

**Request**: `{ "lookup_key": "PT:Algarve" }`
**Response** `200`: `{ "status": "linked", "scores_resolved": true }`

---

## Shortlisted destinations

### `POST /api/trips/{trip_id}/shortlisted/{shortlisted_id}/exclude`
Move from Shortlisted → Excluded.

**Request**: `{ "reason": "..." }`
**Response** `200`: `{ "status": "excluded", "id": <int> }`

### `POST /api/trips/{trip_id}/shortlisted/{shortlisted_id}/unreview`
Move back from Shortlisted → Suggested (re-queue).

**Response** `200`: `{ "status": "moved_to_review", "id": <int> }`

### `PUT /api/trips/{trip_id}/shortlisted/{dest_id}/note`
Update note.

### `POST /api/trips/{trip_id}/shortlisted/{dest_id}/link`
Link to a VacationMap region (same semantics as suggested/link).

---

## Excluded destinations

### `POST /api/trips/{trip_id}/excluded/{excluded_id}/reconsider`
Move from Excluded → Shortlisted. Drops the exclusion reason.

**Request**: `{ "user_note"?: "..." }`
**Response** `200`: `{ "status": "shortlisted", "id": <int> }`

### `PUT /api/trips/{trip_id}/excluded/{dest_id}/note`
Update note (note is separate from exclusion reason).

---

## Conversations

A trip has 1+ conversations. The "Main" conversation is created on first open. Each conversation has independent message history but shares the trip's destination state.

### `POST /api/trips/{trip_id}/conversations`
**Request**: `{ "name": "..." }`
**Response** `201`: `{ "id": <int>, "name": "..." }`

### `POST /api/conversations/{conv_id}/archive` / `unarchive`
Toggle archival status. Archived conversations are hidden by default.

### `PUT /api/conversations/{conv_id}/rename`
**Request**: `{ "name": "..." }`

### `DELETE /api/conversations/{conv_id}`
Permanently delete a conversation and all its messages. **Does not** delete the trip's destination state.
**Response** `204`

---

## Messages

### `GET /api/conversations/{conv_id}/messages`
List messages in a conversation, ordered by `created_at ASC`.

**Response** `200`: `MessageResponse[]`

### `POST /api/conversations/{conv_id}/messages` *(the chat endpoint)*
Send a user message and receive Claude's response.

**Request**: `{ "content": "..." }`
**Response** `200`: `ChatResponse`
```json
{
  "user_message":      { "id":..., "role":"user",      "content":"...", "created_at":"..." },
  "assistant_message": { "id":..., "role":"assistant", "content":"...", "created_at":"..." },
  "trip_state_changed": true
}
```

When `trip_state_changed` is `true`, the frontend re-fetches `/api/trips/{id}` to refresh the destination sidebar.

This endpoint:
1. Persists the user message.
2. Reads `instructions.md` and `profile.md`.
3. Builds the system prompt with current trip state and visit history.
4. Sends conversation history + tool definitions to Claude.
5. Runs the tool-use loop (max 10 iterations).
6. Persists the assistant response.

If `ANTHROPIC_API_KEY` is not set, returns a synthesized error message instead of calling Claude.

### `PUT /api/messages/{message_id}`
Edit message content (works for both user and assistant messages).

**Request**: `{ "content": "..." }`
**Response** `200`: `MessageResponse`

### `DELETE /api/messages/{message_id}`
Delete a message.
**Response** `204`

---

## VacationMap region lookup (read-only)

These endpoints expose VacationMap data for the frontend's region-linking UI and destination-detail popup.

### `GET /api/vacationmap/regions/search?q=<query>`
Autocomplete-style region search. Requires `q.length >= 2`.

**Response** `200`: `[{ "lookup_key": "PT:Algarve", "label": "Algarve, Portugal" }]` (max 20)

### `GET /api/vacationmap/regions/{lookup_key:path}/details?month=<month>`
Full details for one region for a given month. `month` defaults to `"jun"`.

**Response** `200`:
```json
{
  "destination": "Algarve, Portugal",
  "lookup_key": "PT:Algarve",
  "total_score": 7.8,
  "weather_score": 9.2,
  "temp_day": 24.5,
  "temp_night": 17.0,
  "rain_days": 2,
  "cost_relative": 6.0,
  "cost_absolute": 65,
  "busyness_relative": 5.0,
  "busyness_absolute": 4500,
  "attractiveness": 8.5,
  "golf_score": 8.0,
  "nature_score": 7.0,
  "hiking_score": 6.0,
  "safety": 8.0,
  "city_access": 7.5,
  "hotel_quality": 8.0,
  "tourism_level": 7.0,
  "flight_hours": 3.5,
  "flight_transfers": 0,
  "tips": "...",
  "visit": null
}
```

If the region exists but the couple has visited, `visit` contains `{ summary, rating, rating_summary, visit_again, visited_month, visited_year }`.

---

## Claude tool definitions (internal)

These are not HTTP endpoints — they are passed to the Claude API as tool definitions. Claude calls them via tool-use blocks; the backend executes them and returns the result. Source: [`tools.py`](../backend/app/tools.py).

### `search_destinations`
Score-ranked destination search.
```json
{
  "month":               "jan|...|dec|christmas|easter",   // required
  "activity_focus":      "golf|hiking|nature|city|beach|general",
  "max_flight_hours":    8,
  "min_safety_score":    6.0,
  "exclude_visited_never": true,
  "limit":               10
}
```
Returns top results plus `excluded_due_to_recent_visit` for high-scoring `not_soon` destinations.

### `get_destination_details`
```json
{ "region_lookup_key": "PT:Algarve", "month": "jun" }   // both required
```

### `get_visit_history`
No parameters. Returns all visited regions.

### `suggest_for_review` *(state-mutating)*
Queues a destination into the user's review list.
```json
{
  "destination_name":           "Algarve, Portugal",            // required
  "ai_reasoning":               "Excellent golf (8/10)...",     // required
  "region_lookup_key":          "PT:Algarve",                   // optional — fuzzy resolved if absent
  "scores_snapshot":            { ... },                        // optional — DB lookup preferred
  "pre_filled_exclude_reason":  "Visited recently — revisit in a few years"
}
```

Returns:
- On success: `{ "status": "suggested_for_review", "id": <int>, "scores_resolved": true|false, "lookup_key_resolved": "..." }`
  - Plus `fuzzy_matched`, `matched_region`, `other_regions_in_country` if a fuzzy resolution changed the destination.
- On rejection (already in trip): `{ "status": "rejected", "reason": "Already in shortlisted list", "destination": "..." }`

### `get_trip_state`
No parameters. Returns `{ pending_review[], shortlisted[], excluded[] }` for the active trip.

### `search_golf_resorts` (spec 006)
Search the curated golf-resorts library (read-only).

Optional params: `name_query` (fuzzy), `country` (ISO alpha-2), `price_category` (list of `€`/`€€`/`€€€`/`€€€€`), `hotel_type` (list), `month` (1–12), `tags` (list), `min_rank` (0–100), `limit` (default 10).

Returns `{ library_size: int, total_matches: int, results: [ResortListItem] }` — `library_size` lets Claude distinguish "empty library" from "populated but no match".

### `search_golf_courses` (spec 006)
Search the curated golf-courses library. Supports resort-attached + standalone courses.

Optional params: `name_query`, `country`, `course_type` (list of links/parkland/heathland/desert/coastal/mountain/other), `min_difficulty`/`max_difficulty` (1–5), `min_holes` (9/18/27/36), `parent_resort` (`any`/`has_resort`/`standalone`), `max_green_fee_eur`, `tags`, `min_rank`, `limit` (default 10).

Returns `{ library_size, total_matches, results }`. Each result includes parent-resort name (or "Standalone"), country/region (inherited when course's own is null), par/length/architect/type/difficulty/rank/green_fee.

### `suggest_for_review` (extended in spec 006)
Adds two optional parameters, mutually exclusive (enforced at the top of the handler):

- `resort_id`: link the suggestion to a specific resort from `search_golf_resorts` results
- `course_id`: link the suggestion to a specific course from `search_golf_courses` results

Both IDs persist on the `suggested_destinations` row and propagate through shortlist/excluded transitions.

## Golf Library HTTP API (spec 006)

All paths are under `/api/golf-library`.

| Method | Path | Description |
|---|---|---|
| `POST` | `/extract` | Run AI extraction against `{entity_type, url? name?}`. 200 returns `ExtractSuccess*`; 422 returns `ExtractError`. |
| `GET` | `/resorts` | List resorts. Filters: `country`, `price_category[]`, `hotel_type[]`, `month`, `tags[]`, `region_match` (`any`/`matched`/`unmatched`), `q` (full-text). Sort: `rank_rating`/`price_category`/`course_count`/`updated_at`. Pagination via `limit` (≤200) + `offset`. |
| `GET` | `/resorts/{id}` | Full detail: resort + attached courses + images + VacationMap score snapshot (when linked). |
| `POST` | `/resorts` | Create. 409 returns `DuplicateWarning` (retry with `?force=true`). |
| `PATCH` | `/resorts/{id}` | Partial update. |
| `DELETE` | `/resorts/{id}` | 204 on success, 409 with `DeleteBlocked` body when attached courses or shortlist references exist (FR-020a). |
| `POST` | `/resorts/{id}/link-region` | Body: `{vacationmap_region_key}`. Use `null` to unlink. |
| `GET` | `/courses` | List courses. Filters: `country`, `course_type[]`, `min_difficulty`/`max_difficulty`, `min_holes`, `parent_resort`, `max_green_fee_eur`, `tags[]`, `region_match`, `q`. Sort: `rank_rating`/`length_yards`/`difficulty`/`green_fee_low_eur`/`updated_at`. |
| `GET` | `/courses/{id}` | Full detail: course + images + parent-resort summary + VacationMap scores. |
| `POST` | `/courses` | Create (standalone or attached). 409 dedup pattern same as resorts. |
| `PATCH` | `/courses/{id}` | Partial update. |
| `DELETE` | `/courses/{id}` | 204 on success, 409 with `DeleteBlocked` body when shortlist references exist. |
| `POST` | `/courses/{id}/link-region` | Same shape as resort link. |
| `POST` | `/courses/{id}/link-resort` | Body: `{resort_id}` (null = unlink — requires course's own country_code to be set). |
| `POST` | `/images` | Body: `{entity_type, entity_id, url, caption?}`. SSRF-validated via HEAD before insert. |
| `PATCH` | `/images/{id}` | Body: `{caption?, display_order?}`. |
| `DELETE` | `/images/{id}` | 204. |

### Error envelopes

- **DuplicateWarning** (409 on POST create): `{existing_entity, match_reason: "exact_name_norm_country", actions: ["create_anyway","edit_existing","cancel"]}`.
- **DeleteBlocked** (409 on DELETE): `{reason: "has_attached_courses"|"referenced_by_shortlist"|"both", blockers: {attached_courses: [...], shortlist_references: [...]}}`.
- **ExtractError** (422 on `/extract`): `{status: "api_error"|"no_match"|"fetch_error"|"ambiguous", message, partial_data?, candidates?}`.

### SSRF guardrails (FR-005a)

All server-side URL fetches (page fetch during extraction, image HEAD validation, user-supplied image URLs) go through `app.fetcher.safe_get` / `safe_head`:

- `http`/`https` schemes only
- Post-DNS IP filter: RFC1918, loopback, link-local (169.254/16), IPv6 equivalents, multicast, reserved, unspecified — all blocked
- 10 s total timeout (connect 3 s + read 7 s)
- 5 MB response body cap (streamed + truncated)
- Redirects re-validated on every hop, max 5
- `trust_env=False` — environment proxies are intentionally ignored

---

## Yearly planner (F009)

Base paths: `/api/year-plans`, `/api/year-options`, `/api/slots`. All bodies JSON. Hierarchy: **YearPlan → YearOption → Slot**. Conversation endpoints remain under `/api/conversations/*` and dispatch on `owner_type='year_plan'`.

### Year plans

| Method | Path | Notes |
|---|---|---|
| `GET`    | `/api/year-plans?year={y}&status={s}` | Both filters optional. Returns `YearPlanSummary[]` (includes `windows`, `option_count`, `linked_trip_count`). |
| `POST`   | `/api/year-plans` | Body `{year, name, intent?, activity_weights?, windows?}`. Seeds a "Main" conversation. Multiple YearPlans per calendar year are allowed. |
| `GET`    | `/api/year-plans/{id}` | Full detail: `windows[]`, `options[]` (each with its slots), conversations, `attachable_trip_ids`. |
| `PATCH`  | `/api/year-plans/{id}` | Body `{name?, intent?, activity_weights?, windows?, status?}`. Status must be `'draft'` or `'archived'`. Windows is a JSON list of `{label?, start_date, end_date, duration_hint?, constraints?}`. |
| `DELETE` | `/api/year-plans/{id}?confirm=true` | Cascades to options, slots, and conversations. Linked `trip_plans` are kept. |

### Year options

| Method | Path | Notes |
|---|---|---|
| `POST`   | `/api/year-plans/{id}/options` | Body `{name, summary?, created_by?}`. Returns `YearOptionDetail`. |
| `GET`    | `/api/year-options/{id}` | Full option with slots. |
| `PATCH`  | `/api/year-options/{id}` | Body `{name?, summary?, status?, position?}`. Status must be `'draft'`, `'chosen'`, or `'archived'`. |
| `DELETE` | `/api/year-options/{id}?confirm=true` | Cascades to its slots; linked trips are kept. |
| `POST`   | `/api/year-options/{id}/fork` | Body `{name}`. Clones the option (and its slots) as a new draft option. Slots' `trip_plan_id` is **not** carried over. |
| `POST`   | `/api/year-options/{id}/mark-chosen` | Sets `status='chosen'`. Informational — sibling options are left alone. |

### Slots

| Method | Path | Notes |
|---|---|---|
| `POST`   | `/api/year-options/{option_id}/slots` | `SlotCreate` body (includes `theme`, `window_index?`, optional `status='proposed'`). 400 on overlap within this option. Year-crossing allowed. Overlap across sibling options is allowed by design. |
| `PATCH`  | `/api/slots/{slot_id}` | Partial update; re-validates overlap (within the same option) if time fields change. |
| `DELETE` | `/api/slots/{slot_id}?confirm=true` | Deletes the slot only. Linked trip is kept. |
| `POST`   | `/api/slots/{slot_id}/accept` | `'proposed'` → `'open'`. |
| `POST`   | `/api/slots/{slot_id}/start-trip` | Creates a new `trip_plans` row seeded from the slot and sets `slots.trip_plan_id`. Idempotent. Response: `{trip_id, slot_id, trip}`. |
| `POST`   | `/api/slots/{slot_id}/link-trip` | Body `{trip_id}`. Links an existing trip. |
| `POST`   | `/api/slots/{slot_id}/unlink-trip` | Clears the link; trip is kept. |

### Conversations

| Method | Path | Notes |
|---|---|---|
| `GET`    | `/api/year-plans/{id}/conversations` | List conversations owned by this year plan. |
| `POST`   | `/api/year-plans/{id}/conversations` | Body `{name}`. Creates an owner-scoped conversation (`owner_type='year_plan'`). |

Cross-owner conversation endpoints (shared with trips):

| Method | Path | Notes |
|---|---|---|
| `POST`   | `/api/conversations/{conv_id}/messages` | **Dispatcher**: inspects `conversation.owner_type` and routes to the trip chat or the year-plan chat handler. Response shape matches the handler: trip → `{user_message, assistant_message, trip_state_changed}`, year plan → `{user_message, assistant_message, year_plan_state_changed}`. |
| `GET`    | `/api/conversations/{conv_id}/messages` | List messages (owner-agnostic). |
| `POST`   | `/api/conversations/{conv_id}/archive` / `unarchive` | |
| `DELETE` | `/api/conversations/{conv_id}` | |
| `PUT`    | `/api/conversations/{conv_id}/rename` | Body `{name}`. |
