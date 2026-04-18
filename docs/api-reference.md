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
