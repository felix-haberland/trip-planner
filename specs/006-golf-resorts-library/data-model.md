# Data Model: Golf Courses & Resorts Library

Phase 1 output. SQL schemas, relationships, and validation rules derived from spec 006. Implemented in `backend/app/models.py` (SQLAlchemy) and migrated via `ALTER TABLE ADD COLUMN` / `CREATE TABLE IF NOT EXISTS` at startup.

## 1. New tables

### 1.1 `golf_resorts`

```sql
CREATE TABLE IF NOT EXISTS golf_resorts (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  name                  TEXT    NOT NULL,
  name_norm             TEXT    NOT NULL,       -- derived: lower + collapse ws + strip punct + NFKD + & -> and
  url                   TEXT,
  source_urls           TEXT    NOT NULL DEFAULT '[]',  -- JSON array of strings
  country_code          TEXT    NOT NULL,       -- ISO 3166-1 alpha-2, e.g., "PT"
  region_name_raw       TEXT,                   -- freetext from extraction
  vacationmap_region_key TEXT,                  -- "country_code:region_name" stable key; nullable
  town                  TEXT,
  latitude              REAL,
  longitude             REAL,
  hotel_name            TEXT,
  hotel_type            TEXT,                   -- CHECK in ('luxury','boutique','golf_hotel','none') OR NULL
  star_rating           INTEGER,                -- 0..5, nullable
  price_category        TEXT,                   -- '€','€€','€€€','€€€€' OR NULL
  best_months           TEXT    NOT NULL DEFAULT '[]',  -- JSON array of ints 1..12
  description           TEXT,                   -- markdown
  amenities             TEXT    NOT NULL DEFAULT '[]',  -- JSON array of tag strings
  rank_rating           INTEGER,                -- 0..100, nullable
  tags                  TEXT    NOT NULL DEFAULT '[]',  -- JSON array
  personal_notes        TEXT,                   -- markdown
  source_checked_at     TIMESTAMP,
  created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_golf_resorts_name_norm_country
  ON golf_resorts (name_norm, country_code);
CREATE INDEX IF NOT EXISTS ix_golf_resorts_vm_region_key
  ON golf_resorts (vacationmap_region_key);
CREATE INDEX IF NOT EXISTS ix_golf_resorts_country
  ON golf_resorts (country_code);
```

**Required on save**: `name`, `country_code`. Everything else optional.
**Validation**: `name_norm` is computed server-side; users cannot set it directly. `best_months` values must be 1..12 or rejected. `star_rating` 0..5. `rank_rating` 0..100. `price_category` restricted to the four allowed strings.
**Constitution alignment**: append-or-modify (Principle I); `vacationmap_region_key` uses the stable cross-DB identifier (Principle IV).

### 1.2 `golf_courses`

```sql
CREATE TABLE IF NOT EXISTS golf_courses (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  resort_id             INTEGER REFERENCES golf_resorts(id) ON DELETE RESTRICT,  -- nullable (standalone)
  name                  TEXT    NOT NULL,
  name_norm             TEXT    NOT NULL,
  url                   TEXT,
  source_urls           TEXT    NOT NULL DEFAULT '[]',
  country_code          TEXT,                   -- NULLABLE when resort_id is set (inherited);
                                                -- NOT NULL enforced in app code when resort_id IS NULL
  region_name_raw       TEXT,
  vacationmap_region_key TEXT,
  town                  TEXT,
  latitude              REAL,
  longitude             REAL,
  holes                 INTEGER,                -- 9, 18, 27, 36
  par                   INTEGER,
  length_yards          INTEGER,
  type                  TEXT,                   -- 'links','parkland','heathland','desert','coastal','mountain','other'
  architect             TEXT,
  year_opened           INTEGER,
  difficulty            INTEGER,                -- 1..5
  signature_holes       TEXT,                   -- markdown
  description           TEXT,                   -- markdown
  green_fee_low_eur     INTEGER,                -- nullable
  green_fee_high_eur    INTEGER,                -- nullable
  green_fee_notes       TEXT,                   -- freetext, nullable
  best_months           TEXT    NOT NULL DEFAULT '[]',
  rank_rating           INTEGER,
  tags                  TEXT    NOT NULL DEFAULT '[]',
  personal_notes        TEXT,
  display_order         INTEGER NOT NULL DEFAULT 0,   -- order within a resort
  source_checked_at     TIMESTAMP,
  created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_golf_courses_name_norm_country
  ON golf_courses (name_norm, country_code);
CREATE INDEX IF NOT EXISTS ix_golf_courses_resort_id
  ON golf_courses (resort_id);
CREATE INDEX IF NOT EXISTS ix_golf_courses_vm_region_key
  ON golf_courses (vacationmap_region_key);
CREATE INDEX IF NOT EXISTS ix_golf_courses_type
  ON golf_courses (type);
```

**Required on save**: `name`; `country_code` required when `resort_id IS NULL`.
**Inheritance**: when `resort_id` is set and `country_code`/`region_name_raw`/`vacationmap_region_key`/`latitude`/`longitude`/`town` are null on the course, the browse/chatbot read paths resolve them from the parent resort at query time.
**Referential integrity**: `ON DELETE RESTRICT` at the SQL level is defensive; the real enforcement is in `crud.delete_resort()` per FR-020a (application-level prevent-delete with structured blocker response).

### 1.3 `entity_images`

```sql
CREATE TABLE IF NOT EXISTS entity_images (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_type    TEXT    NOT NULL,              -- 'resort' | 'course'
  entity_id      INTEGER NOT NULL,              -- FK to golf_resorts.id OR golf_courses.id (polymorphic)
  url            TEXT    NOT NULL,
  caption        TEXT,
  display_order  INTEGER NOT NULL DEFAULT 0,
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_entity_images_lookup
  ON entity_images (entity_type, entity_id, display_order);
```

**Polymorphic FK**: not enforced at the DB level because SQLite doesn't support polymorphic FKs cleanly. Enforced in `crud.py`: every write validates `(entity_type, entity_id)` points to an existing row; every parent-delete path removes `entity_images` rows in the same transaction.
**Lifecycle**: images are owned children of their parent entity; when the parent is hard-deleted (after passing FR-020a checks), the corresponding `entity_images` rows are deleted in the same transaction.

## 2. Altered tables

### 2.1 `trips` — add `activity_weights`

```sql
ALTER TABLE trips ADD COLUMN activity_weights TEXT NOT NULL DEFAULT '{}';
```

- JSON dict of `{activity_tag: 0..100}` where `activity_tag ∈ {golf, hiking, beach, city, culture, relaxation, food, nature, wellness, adventure}`.
- Empty `'{}'` preserves today's free-text-inference behavior (FR-017a).
- Values SHOULD sum to ≈100 but not enforced.

### 2.2 `suggested_destinations`, `shortlisted_destinations`, `excluded_destinations` — add `resort_id` / `course_id`

For each of the three destination tables:

```sql
ALTER TABLE <table> ADD COLUMN resort_id INTEGER REFERENCES golf_resorts(id) ON DELETE RESTRICT;
ALTER TABLE <table> ADD COLUMN course_id INTEGER REFERENCES golf_courses(id) ON DELETE RESTRICT;
CREATE INDEX IF NOT EXISTS ix_<table>_resort_id ON <table>(resort_id);
CREATE INDEX IF NOT EXISTS ix_<table>_course_id ON <table>(course_id);
```

- `resort_id` and `course_id` are mutually exclusive by convention (enforced in application code, not a SQL `CHECK`).
- `ON DELETE RESTRICT` reinforces FR-020a's prevent-delete policy.

## 3. Derived / computed fields

- **`name_norm`** (on `golf_resorts` and `golf_courses`): computed server-side via
  `normalize(s) = strip_punct(collapse_ws(lower(nfkd_ascii(s.replace("&", " and ")))))`.
  Recomputed on every insert/update in the SQLAlchemy model's `__init__` / setter. Never user-editable.

- **Inherited location fields on courses**: resolved in the read path (SELECT-time COALESCE with the parent resort's columns), never persisted. This avoids a denormalization hazard where a resort's country changes and the attached courses drift.

## 4. Relationships (ER summary)

```
golf_resorts (1) ---- (0..n) golf_courses        via golf_courses.resort_id (nullable)
golf_resorts (1) ---- (0..n) entity_images       via (entity_type='resort', entity_id=resort.id)
golf_courses (1) ---- (0..n) entity_images       via (entity_type='course', entity_id=course.id)
golf_resorts (1) ---- (0..n) suggested/shortlisted/excluded_destinations.resort_id
golf_courses (1) ---- (0..n) suggested/shortlisted/excluded_destinations.course_id
trips        (1) ---- (1)    trips.activity_weights (JSON)
```

## 5. State transitions

Entities have no lifecycle states (no Draft/Published/Archived flag). Creation and deletion are the only transitions:

- **Create**: Insert row; `name_norm` computed; `created_at` / `updated_at` set.
- **Update**: Recompute `name_norm` if `name` changed. Bump `updated_at`.
- **Delete**: User-initiated. Blocked per FR-020a if any referencing rows exist. When unblocked, the parent row and its owned `entity_images` are removed in one transaction; no cascade touches referenced destination rows (they are the blockers).
- **Link to VacationMap region** (FR-009 + User Story 5): `UPDATE golf_resorts SET vacationmap_region_key = 'PT:Lisbon Coast' WHERE id = ?;`. Same for courses.
- **Link course to resort** / unlink: `UPDATE golf_courses SET resort_id = ? WHERE id = ?;`. When unlinking (`resort_id = NULL`), `country_code` must be non-null on the course (enforced by app code before the update).

## 6. Data volume

- Expected after seed run: ~100 resorts + ~20–40 courses (resort-attached + standalone).
- Expected ceiling for realistic single-user use: ≤ 500 resorts, ≤ 1000 courses, ≤ 7500 images (5 per entity × 1500 entities).
- SQLite comfortably handles this. All filter/sort paths are indexed.

## 7. Cross-references to spec FRs

| FR | Table / Column |
|----|----------------|
| FR-001 | `golf_resorts` full row |
| FR-002 | `golf_courses` full row |
| FR-002a | nullable country/region on course when `resort_id IS NOT NULL` |
| FR-002b | `green_fee_low_eur`, `green_fee_high_eur`, `green_fee_notes` |
| FR-003 | All migrations are `CREATE TABLE IF NOT EXISTS` / `ALTER ... ADD COLUMN` |
| FR-003a | `name_norm` on both library tables + composite index with `country_code` |
| FR-003b | `entity_images` table |
| FR-017a | `trips.activity_weights` |
| FR-018 / FR-019 | `resort_id` + `course_id` on the three destination tables |
| FR-020a | `ON DELETE RESTRICT` at SQL + application-level blocker enumeration |
