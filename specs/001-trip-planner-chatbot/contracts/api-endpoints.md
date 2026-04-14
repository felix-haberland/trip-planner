# API Contracts: Trip Planner Chatbot

**Date**: 2026-04-14  
**Base URL**: `http://localhost:8000`

## Trip Management

### GET /api/trips

List all trip plans.

**Response** `200 OK`:
```json
[
  {
    "id": 1,
    "name": "Golf Trip June 2026",
    "description": "golf trip in June, prefer short flights",
    "target_month": "jun",
    "status": "active",
    "shortlisted_count": 4,
    "excluded_count": 2,
    "created_at": "2026-04-14T10:30:00Z",
    "updated_at": "2026-04-14T14:22:00Z"
  }
]
```

### POST /api/trips

Create a new trip plan.

**Request**:
```json
{
  "name": "Golf Trip June 2026",
  "description": "golf trip in June, prefer short flights"
}
```

**Response** `201 Created`:
```json
{
  "id": 1,
  "name": "Golf Trip June 2026",
  "description": "golf trip in June, prefer short flights",
  "target_month": null,
  "status": "active",
  "shortlisted_count": 0,
  "excluded_count": 0,
  "created_at": "2026-04-14T10:30:00Z",
  "updated_at": "2026-04-14T10:30:00Z"
}
```

### GET /api/trips/{trip_id}

Get full trip details including shortlisted and excluded destinations.

**Response** `200 OK`:
```json
{
  "id": 1,
  "name": "Golf Trip June 2026",
  "description": "golf trip in June, prefer short flights",
  "target_month": "jun",
  "status": "active",
  "created_at": "2026-04-14T10:30:00Z",
  "updated_at": "2026-04-14T14:22:00Z",
  "shortlisted": [
    {
      "id": 1,
      "destination_name": "Algarve, Portugal",
      "region_lookup_key": "PT:Algarve",
      "ai_reasoning": "Excellent golf facilities (8/10), warm June weather...",
      "scores_snapshot": {
        "golf": 8.0,
        "weather": 9.2,
        "cost_relative": 6.0,
        "busyness_relative": 5.0,
        "attractiveness": 8.5,
        "safety": 8.0,
        "total": 7.8
      },
      "user_note": "Great golf courses, Lisa's top pick",
      "added_at": "2026-04-14T11:05:00Z"
    }
  ],
  "excluded": [
    {
      "id": 1,
      "destination_name": "Tenerife, Spain",
      "region_lookup_key": "ES:Tenerife",
      "reason": "Too touristy in June",
      "excluded_at": "2026-04-14T11:10:00Z"
    }
  ]
}
```

### PUT /api/trips/{trip_id}

Update trip name or status.

**Request**:
```json
{
  "name": "Updated Trip Name",
  "status": "archived"
}
```

**Response** `200 OK`: Updated trip object.

### DELETE /api/trips/{trip_id}

Delete a trip and all associated data.

**Response** `204 No Content`

---

## Conversation

### GET /api/trips/{trip_id}/messages

Get conversation history for a trip.

**Response** `200 OK`:
```json
[
  {
    "id": 1,
    "role": "user",
    "content": "I want a golf trip in June, preferably under 5 hours flight",
    "created_at": "2026-04-14T10:31:00Z"
  },
  {
    "id": 2,
    "role": "assistant",
    "content": "Great! Based on your profile and preferences, here are my top suggestions for a golf trip in June...",
    "created_at": "2026-04-14T10:31:12Z"
  }
]
```

### POST /api/trips/{trip_id}/messages

Send a user message and receive an AI response. This is the core chat endpoint.

**Request**:
```json
{
  "content": "What about Portugal? I've heard the Algarve is great for golf."
}
```

**Response** `200 OK`:
```json
{
  "user_message": {
    "id": 5,
    "role": "user",
    "content": "What about Portugal? I've heard the Algarve is great for golf.",
    "created_at": "2026-04-14T11:00:00Z"
  },
  "assistant_message": {
    "id": 6,
    "role": "assistant",
    "content": "The Algarve is an excellent choice! Here's what the data says...",
    "created_at": "2026-04-14T11:00:08Z"
  },
  "trip_state_changed": true
}
```

The backend:
1. Persists the user message
2. Reads `profile.md` and `instructions.md`
3. Builds the system prompt with profile, instructions, and current trip state
4. Sends full conversation history to Claude with tool definitions
5. Executes any tool calls Claude makes (search destinations, shortlist, exclude, etc.)
6. Persists the assistant response
7. Returns both messages

---

## Tool Definitions (Internal — Claude API)

These are not HTTP endpoints. They are tool definitions passed to the Claude API for function calling during conversations.

### search_destinations

```json
{
  "name": "search_destinations",
  "description": "Search VacationMap destinations for a given month with optional filters. Returns scored results.",
  "input_schema": {
    "type": "object",
    "properties": {
      "month": { "type": "string", "enum": ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec","christmas","easter"] },
      "activity_focus": { "type": "string", "enum": ["golf", "hiking", "nature", "city", "beach", "general"] },
      "max_flight_hours": { "type": "number" },
      "min_safety_score": { "type": "number", "default": 6.0 },
      "exclude_visited_never": { "type": "boolean", "default": true },
      "limit": { "type": "integer", "default": 10 }
    },
    "required": ["month"]
  }
}
```

### get_destination_details

```json
{
  "name": "get_destination_details",
  "description": "Get full details for a specific destination including all scores for a month, tips, flight info, and visit history.",
  "input_schema": {
    "type": "object",
    "properties": {
      "region_lookup_key": { "type": "string", "description": "Format: CC:RegionName (e.g., PT:Algarve)" },
      "month": { "type": "string" }
    },
    "required": ["region_lookup_key", "month"]
  }
}
```

### get_visit_history

```json
{
  "name": "get_visit_history",
  "description": "Get all visited regions with ratings and revisit preferences.",
  "input_schema": {
    "type": "object",
    "properties": {}
  }
}
```

### shortlist_destination

```json
{
  "name": "shortlist_destination",
  "description": "Add a destination to the current trip's shortlist.",
  "input_schema": {
    "type": "object",
    "properties": {
      "destination_name": { "type": "string" },
      "region_lookup_key": { "type": "string", "description": "Null if not in VacationMap" },
      "ai_reasoning": { "type": "string" },
      "scores_snapshot": { "type": "object" },
      "user_note": { "type": "string" }
    },
    "required": ["destination_name", "ai_reasoning"]
  }
}
```

### exclude_destination

```json
{
  "name": "exclude_destination",
  "description": "Mark a destination as excluded from the current trip.",
  "input_schema": {
    "type": "object",
    "properties": {
      "destination_name": { "type": "string" },
      "region_lookup_key": { "type": "string" },
      "reason": { "type": "string" }
    },
    "required": ["destination_name", "reason"]
  }
}
```

### get_trip_state

```json
{
  "name": "get_trip_state",
  "description": "Get current shortlisted and excluded destinations for the active trip.",
  "input_schema": {
    "type": "object",
    "properties": {}
  }
}
```
