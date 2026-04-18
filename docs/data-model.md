# Data Model

This is the **current** schema for `trips.db`. The original spec ([specs/001-trip-planner-chatbot/data-model.md](../specs/001-trip-planner-chatbot/data-model.md)) shows the initial design; this doc reflects what's actually live.

## Schema overview

```
TripPlan
  ├─ SuggestedDestination*    (review queue — Claude → user triage)
  ├─ ShortlistedDestination*  (user's working set)
  ├─ ExcludedDestination*     (with reasons)
  └─ Conversation*
        └─ ConversationMessage*
```

All tables are in `trips.db`. VacationMap entities (`countries`, `regions`, `region_visits`) live in `vacation.db` and are accessed read-only.

## TripPlan

`trip_plans`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK, autoincrement | |
| name | TEXT | NOT NULL | User-given trip name |
| description | TEXT | NOT NULL | Initial trip description, also editable later |
| target_month | TEXT | NULL | `jan`..`dec`, `christmas`, `easter`. Set by `_try_set_target_month` heuristic on first message, or by AI/UI. |
| status | TEXT | NOT NULL, default `"active"` | `active` or `archived` |
| created_at | DATETIME | NOT NULL, auto | |
| updated_at | DATETIME | NOT NULL, auto, updates on any state change | Drives trip-list sort order |

Cascade deletes: deleting a TripPlan removes all destinations and conversations.

## SuggestedDestination *(added since 001)*

`suggested_destinations`

The "review queue" between Claude and the user. Claude's `suggest_for_review` tool inserts here; the user moves them to shortlisted or excluded via UI.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | PK |
| trip_id | INTEGER | FK → trip_plans.id, CASCADE |
| region_lookup_key | TEXT | NULL if not in VacationMap |
| destination_name | TEXT | NOT NULL — display name |
| ai_reasoning | TEXT | NOT NULL — Claude's pros/cons |
| scores_snapshot | TEXT | NULL — JSON of scores at suggestion time |
| user_note | TEXT | NULL — optional user note |
| pre_filled_exclude_reason | TEXT | NULL — Claude can pre-fill an exclusion reason (e.g., "Visited recently") so the user can exclude with one click |
| suggested_at | DATETIME | NOT NULL, auto |

## ShortlistedDestination

`shortlisted_destinations`

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | PK |
| trip_id | INTEGER | FK → trip_plans.id, CASCADE |
| region_lookup_key | TEXT | NULL if not in VacationMap |
| destination_name | TEXT | NOT NULL |
| ai_reasoning | TEXT | NOT NULL — preserved from suggestion |
| scores_snapshot | TEXT | NULL — JSON, preserved from suggestion |
| user_note | TEXT | NULL |
| added_at | DATETIME | NOT NULL, auto |

## ExcludedDestination

`excluded_destinations`

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | PK |
| trip_id | INTEGER | FK → trip_plans.id, CASCADE |
| region_lookup_key | TEXT | NULL if not in VacationMap |
| destination_name | TEXT | NOT NULL |
| reason | TEXT | NOT NULL — user's exclusion reason |
| ai_reasoning | TEXT | NULL — preserved from suggestion for context |
| user_note | TEXT | NULL — *added since 001* — separate from `reason`, free-form |
| excluded_at | DATETIME | NOT NULL, auto |

## Conversation *(added since 001)*

`conversations`

A trip can have multiple parallel conversations (e.g., "Main", "October alternatives"). All conversations share the trip's destination state but have independent message history.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | PK |
| trip_id | INTEGER | FK → trip_plans.id, CASCADE |
| name | TEXT | NOT NULL, default `"Main"` |
| status | TEXT | NOT NULL, default `"active"` — `active` or `archived` |
| created_at | DATETIME | NOT NULL, auto |

The "Main" conversation is auto-created when a trip is first opened.

## ConversationMessage

`conversation_messages`

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | PK |
| conversation_id | INTEGER | FK → conversations.id, CASCADE, NULLABLE for legacy data |
| trip_id | INTEGER | FK → trip_plans.id, CASCADE, NULLABLE — kept for backward compat with pre-conversation data |
| role | TEXT | NOT NULL — `"user"` or `"assistant"` |
| content | TEXT | NOT NULL |
| created_at | DATETIME | NOT NULL, auto |

`trip_id` is intentionally redundant for older messages that predate the Conversation model. New writes always set `conversation_id`.

## scores_snapshot JSON shape

When `region_lookup_key` resolves to a VacationMap region, the snapshot is built by `tools._build_scores_from_db()`:

```json
{
  "total_score":         7.8,
  "weather_score":       9.2,
  "cost_relative":       6.0,
  "busyness_relative":   5.0,
  "attractiveness":      8.5,
  "golf_score":          8.0,
  "flight_hours":        3.5
}
```

When the destination is NOT in VacationMap, `scores_snapshot` is `NULL` and the UI shows "unscored" badges. AI-estimated scores are not persisted (they're discarded in favor of `NULL`).

## Cross-DB references

`region_lookup_key` is a string of the form `country_code:region_name` (e.g., `PT:Algarve`, `TH:Bangkok`). It joins to `vacation.db` via:

```sql
SELECT r.* FROM regions r
JOIN countries c ON r.country_id = c.id
WHERE c.code = :country_code AND r.name = :region_name
```

VacationMap's primary keys are intentionally **not** stored in `trips.db` — this makes the companion app resilient to VacationMap re-imports. See constitution principle IV.

## Migrations

`backend/app/database.py:init_trips_db()` calls `Base.metadata.create_all(bind=trips_engine)` on startup. SQLAlchemy creates missing tables but does NOT alter existing ones.

For schema additions on existing databases:
- Use `ALTER TABLE ADD COLUMN` manually via `sqlite3` CLI before deploying.
- For destructive changes, ask the user first (constitution principle I).

There is no migration framework (alembic, etc.) — the app is small enough that manual SQL is preferable to the abstraction overhead.
