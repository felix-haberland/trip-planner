# Data Model

This is the **current** schema for `trips.db`. The original spec ([specs/001-trip-planner-chatbot/data-model.md](../specs/001-trip-planner-chatbot/data-model.md)) shows the initial design; this doc reflects what's actually live.

## Schema overview

```
TripPlan (+ activity_weights JSON dict — spec 006)
  ├─ SuggestedDestination*    (review queue — Claude → user triage; + resort_id / course_id — spec 006)
  ├─ ShortlistedDestination*  (user's working set; + resort_id / course_id)
  ├─ ExcludedDestination*     (with reasons; + resort_id / course_id)
  └─ Conversation*
        └─ ConversationMessage*

GolfResort  (spec 006)
  ├─ GolfCourse*              (resort_id nullable — courses may be standalone)
  └─ EntityImage* (polymorphic via entity_type='resort')
GolfCourse  (spec 006; may be standalone or resort-attached)
  └─ EntityImage* (polymorphic via entity_type='course')
```

## Spec 006 additions — Golf library

See [specs/006-golf-resorts-library/data-model.md](../specs/006-golf-resorts-library/data-model.md) for full column-level detail.

**New tables**:

- `golf_resorts` — name, name_norm (derived), url, source_urls, country_code, region_name_raw, vacationmap_region_key (stable cross-DB key), town/lat/lng, hotel_name, hotel_type, star_rating, price_category, best_months, description, amenities, rank_rating (0–100), tags, personal_notes, source_checked_at. Indexed on (name_norm, country_code) + vacationmap_region_key + country_code.
- `golf_courses` — same core fields plus resort_id (nullable FK `ON DELETE RESTRICT`), holes/par/length_yards, type (links/parkland/…), architect, year_opened, difficulty (1–5), signature_holes, green_fee_low_eur/high/notes, display_order. Courses with a resort_id may leave country/region null — they inherit from the parent at query time.
- `entity_images` — polymorphic via (entity_type, entity_id). `entity_type ∈ {resort, course}`. No DB-level FK (SQLite can't express polymorphic refs); enforced in `crud.py`. Cascade-deletes when the parent is deleted.

**New columns on existing tables** (all `ALTER TABLE ADD COLUMN`, guarded by inspector checks in `init_trips_db`):

- `trip_plans.activity_weights` (TEXT, default `'{}'`) — JSON dict of `{tag: 0..100}` per FR-017a
- `suggested_destinations.resort_id`, `.course_id` (INTEGER nullable)
- `shortlisted_destinations.resort_id`, `.course_id` (INTEGER nullable)
- `excluded_destinations.resort_id`, `.course_id` (INTEGER nullable)

**Dedup rule (FR-003a)**: `name_norm` is derived as `NFKD → ASCII → lowercase → & → "and" → strip ASCII punctuation → collapse whitespace`. Dedup check matches `(name_norm, country_code, entity_type)` as a soft warning — not a DB-level unique constraint, so the user can always override with `?force=true`.

**Prevent-delete (FR-020a)**: application-level enforcement in `crud.delete_resort` / `crud.delete_course`. A resort with attached courses OR a resort/course referenced by any suggested/shortlisted/excluded row cannot be deleted; the API returns 409 with a structured blocker list.

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

## Yearly planner (F009)

`YearPlan → YearOption → Slot`. A YearPlan owns the user's intent, activity targets, and the list of **open windows** (calendar availability). Each YearPlan holds many YearOptions — candidate whole-year arrangements the user can compare and pick between. Each Slot is a single trip intent inside one Option. When the user is ready to pick a destination for a slot, `slots.trip_plan_id` bridges to a concrete `trip_plans` row where the existing Trip Planner chat drives destination discovery.

Multiple YearPlans per calendar year are allowed (genuinely different contexts like "Conservative 2027" vs "Wild 2027"). Multiple Options inside one plan are the primary comparison mechanism.

```
year_plans ───< year_options ───< slots ──(optional 1:1)──> trip_plans
  windows[]                       window_index              trip_plan_id
  (JSON)
```

### `year_plans`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| year | INTEGER NOT NULL | Indexed; not unique (multiple plans per year allowed). |
| name | TEXT NOT NULL | "My 2027", "Wild 2027 experiment". |
| intent | TEXT NOT NULL DEFAULT '' | Free-text yearly narrative. |
| activity_weights | TEXT NOT NULL DEFAULT '{}' | JSON, same shape as `trip_plans.activity_weights`. |
| windows | TEXT NOT NULL DEFAULT '[]' | JSON list of `{label?, start_date, end_date, duration_hint?, constraints?}`. Soft anchors — Options may propose shifted exact dates per slot. |
| status | TEXT NOT NULL DEFAULT 'draft' | `'draft'` \| `'archived'`. |
| created_at / updated_at | DATETIME | |

### `year_options`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| year_plan_id | INTEGER NOT NULL | FK → `year_plans.id` ON DELETE CASCADE. |
| name | TEXT NOT NULL | "Adventurous mix", "Golf-heavy", "Something different". |
| summary | TEXT NOT NULL DEFAULT '' | One-line description of the option's theme. |
| created_by | TEXT NOT NULL DEFAULT 'user' | `'ai'` (via `generate_year_option`) or `'user'` (manual/fork). |
| status | TEXT NOT NULL DEFAULT 'draft' | `'draft'` \| `'chosen'` (the user's pick; informational) \| `'archived'`. |
| position | INTEGER NOT NULL DEFAULT 0 | Display order. |
| created_at / updated_at | DATETIME | |

### `slots`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| year_option_id | INTEGER NOT NULL | FK → `year_options.id` ON DELETE CASCADE. |
| window_index | INTEGER NOT NULL | Points into the parent YearPlan's `windows` list (not a DB-level FK). Multiple slots per (option, window) are allowed — users sketch alternative ideas inside one cell. |
| label | TEXT NULL | Short friendly name ("Safari", "Christmas escape"). |
| theme | TEXT NOT NULL DEFAULT '' | Prose description of the trip intent; avoids locking in a destination. |
| start_year, start_month | INTEGER NOT NULL | `CHECK(month BETWEEN 1 AND 12)`. |
| end_year, end_month | INTEGER NOT NULL | Year-crossing allowed. |
| exact_start_date, exact_end_date | DATE NULL | Optional precise override (may shift from the parent window). |
| duration_days | INTEGER NULL | |
| climate_hint | TEXT NULL | |
| constraints_note | TEXT NULL | |
| activity_weights | TEXT NOT NULL DEFAULT '{}' | Slot-level activity mix. Fed into the linked trip's `activity_weights` on `start-trip`. |
| status | TEXT NOT NULL DEFAULT 'open' | `'open'` \| `'proposed'` (AI-suggested, awaiting user accept) \| `'archived'`. |
| position | INTEGER NOT NULL DEFAULT 0 | |
| trip_plan_id | INTEGER NULL | FK → `trip_plans.id` ON DELETE SET NULL. Populated when the user starts destination discovery. |

Overlap between siblings in the same option is allowed by design (alternatives inside one cell, e.g. "Golf or Beach in June"). The application no longer date-overlap-checks within an option.

Reverse lookup `yearly.crud.slot_for_trip(trip_id)` returns the slot (if any) linked to a trip — used by `trips/chat.py` to inject slot intent into the destination-discovery system prompt.

`fork_option(option_id, name)` clones the option's slots but intentionally does **not** copy `trip_plan_id` — the forked option starts fresh so destination discovery can diverge per-option.

## Polymorphic conversations (spec 007)

`conversations` was rebuilt from `trip_id` FK to `(owner_type, owner_id)`:

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| owner_type | TEXT NOT NULL | `'trip'` \| `'year_plan'` \| (future: `'trip_option'`). Indexed with owner_id. |
| owner_id | INTEGER NOT NULL | |
| name | TEXT NOT NULL DEFAULT 'Main' | |
| status | TEXT NOT NULL DEFAULT 'active' | |
| created_at | DATETIME NOT NULL | |

No DB-level FK — owners live in different tables. Cascade-on-delete is hand-rolled in each owner's `delete_*` function. `conversation_messages.trip_id` remains as a nullable legacy column (populated only for trip-owned conversations) so older tooling still sees its join.

## Migrations

`backend/app/database.py:init_trips_db()` calls `Base.metadata.create_all(bind=trips_engine)` on startup. SQLAlchemy creates missing tables but does NOT alter existing ones.

For schema additions on existing databases:
- `init_trips_db()` runs idempotent `ALTER TABLE ADD COLUMN` statements guarded by SQLAlchemy Inspector column-existence checks (spec 006). Safe to re-run on any startup; a column is added at most once.
- Spec 007 adds a **one-time table rebuild** of `conversations` when the legacy `trip_id` column is still present. The rebuild is non-destructive: `INSERT INTO conversations_new SELECT id, 'trip', trip_id, name, status, created_at FROM conversations` preserves every row before the old table is dropped inside the same transaction. Guarded by `owner_type not in inspector.get_columns('conversations')`.
- For other destructive changes, ask the user first (constitution principle I).

There is no migration framework (alembic, etc.) — the app is small enough that the guarded inline migrations beat the abstraction overhead.
