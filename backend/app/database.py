import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# === Trips database (read-write, own data) ===
# Contains both trip-planning tables (trip_plans, conversations, etc.) and
# the golf library tables (golf_resorts, golf_courses, entity_images). Code
# is organized into separate modules (`app/` for trips, `app/golf/` for the
# library), but both use this single engine + `TripsBase`.
TRIPS_DB_PATH = os.environ.get("TRIPS_DB_PATH", "./trips.db")
trips_engine = create_engine(
    f"sqlite:///{TRIPS_DB_PATH}",
    connect_args={"check_same_thread": False},
)
TripsSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=trips_engine)
TripsBase = declarative_base()

# === VacationMap database (read-only) ===
VACATIONMAP_DB_PATH = os.environ.get(
    "VACATIONMAP_DB_PATH",
    os.path.expanduser("~/Documents/VacationMap/backend/vacation.db"),
)
vacationmap_engine = create_engine(
    f"sqlite:///{VACATIONMAP_DB_PATH}",
    connect_args={"check_same_thread": False},
)


VacationMapSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=vacationmap_engine
)


def init_trips_db():
    """Create trips.db tables if they don't exist and run idempotent migrations.

    Migrations use `ALTER TABLE ADD COLUMN` only (per constitution Principle I).
    Each migration is guarded by a column-existence check so re-running is safe.
    """
    from sqlalchemy import inspect as sqla_inspect, text

    from .trips import models as _trip_models  # noqa: F401 — register trip models
    from .golf import models as _golf_models  # noqa: F401 — register golf models
    from .yearly import models as _yearly_models  # noqa: F401 — spec 007

    # Spec 007: rebuild the legacy `conversations` table (trip_id NOT NULL FK)
    # into the polymorphic (owner_type, owner_id) shape if needed. SQLite
    # can't ALTER a column's NOT NULL/FK, so an INSERT-SELECT-rename is the
    # only safe path. Guarded by column presence — no-op on fresh DBs.
    _migrate_conversations_to_polymorphic()
    # Spec 007 follow-up: the old `conversation_messages.trip_id` column was
    # NOT NULL. Year-plan-owned conversations have no trip, so make it
    # nullable via the same INSERT-SELECT-rename pattern.
    _migrate_conversation_messages_trip_id_nullable()
    # F008 yearly redesign: drop the option/placement tables (superseded) and
    # add slots.trip_plan_id / slots.theme. Idempotent — guarded by existence.
    _migrate_yearly_to_slot_as_trip_intent()
    # F009: introduce YearOption layer between YearPlan and Slot. Adds
    # year_plans.windows, creates year_options table, rebuilds slots under
    # year_option_id. Idempotent — guarded by column presence. Slot rows
    # are discarded on rebuild (authorized: yearly data is test-grade).
    _migrate_yearly_to_year_options()
    # F010: simplification — every trip idea must sit in a window
    # (`slots.window_index` NOT NULL) and at most one per (option, window).
    # Rebuild slots if the old nullable window_index is still there.
    _migrate_slot_window_required()
    # F011: relax back to allow multiple trip ideas per (option, window) —
    # users can sketch alternatives inside a single option cell. Drops the
    # UNIQUE constraint from F010 by rebuilding the slots table.
    _migrate_slot_drop_unique_option_window()
    # F012: add `excluded_reason` to year_options and slots so users can
    # exclude a candidate with a note, and the chatbot learns from it.
    _migrate_yearly_excluded_reason()

    # 1. Create any missing tables (idempotent, never drops).
    TripsBase.metadata.create_all(bind=trips_engine)
    inspector = sqla_inspect(trips_engine)

    def _cols(table: str) -> set[str]:
        if table not in inspector.get_table_names():
            return set()
        return {c["name"] for c in inspector.get_columns(table)}

    migrations: list[tuple[str, str]] = []  # (sentinel_column, DDL)

    # trip_plans.activity_weights (FR-017a)
    if "trip_plans" in inspector.get_table_names():
        if "activity_weights" not in _cols("trip_plans"):
            migrations.append(
                (
                    "trip_plans.activity_weights",
                    "ALTER TABLE trip_plans ADD COLUMN activity_weights TEXT NOT NULL DEFAULT '{}'",
                )
            )

    # resort_id + course_id on the three destination tables (FR-018/FR-019)
    for dest_table in (
        "suggested_destinations",
        "shortlisted_destinations",
        "excluded_destinations",
    ):
        if dest_table not in inspector.get_table_names():
            continue
        existing = _cols(dest_table)
        if "resort_id" not in existing:
            migrations.append(
                (
                    f"{dest_table}.resort_id",
                    f"ALTER TABLE {dest_table} ADD COLUMN resort_id INTEGER",
                )
            )
        if "course_id" not in existing:
            migrations.append(
                (
                    f"{dest_table}.course_id",
                    f"ALTER TABLE {dest_table} ADD COLUMN course_id INTEGER",
                )
            )

    if migrations:
        with trips_engine.begin() as conn:
            for sentinel, ddl in migrations:
                conn.execute(text(ddl))


def _migrate_conversations_to_polymorphic():
    """One-time rebuild of the `conversations` table to (owner_type, owner_id).

    No-op if already migrated or if the table does not yet exist. Preserves
    every row: INSERT-SELECT copies all existing trip conversations with
    owner_type='trip' and owner_id=trip_id. Safe to re-run (guarded by the
    `owner_type` column presence check).
    """
    from sqlalchemy import inspect as sqla_inspect, text

    inspector = sqla_inspect(trips_engine)
    if "conversations" not in inspector.get_table_names():
        return  # fresh DB — create_all will build the new shape directly
    existing_cols = {c["name"] for c in inspector.get_columns("conversations")}
    if "owner_type" in existing_cols:
        return  # already migrated

    with trips_engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        conn.execute(text("""
                CREATE TABLE conversations_new (
                    id INTEGER PRIMARY KEY,
                    owner_type TEXT NOT NULL,
                    owner_id INTEGER NOT NULL,
                    name TEXT NOT NULL DEFAULT 'Main',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at DATETIME NOT NULL
                )
                """))
        conn.execute(text("""
                INSERT INTO conversations_new
                    (id, owner_type, owner_id, name, status, created_at)
                SELECT id, 'trip', trip_id, name, status, created_at
                FROM conversations
                """))
        conn.execute(text("DROP TABLE conversations"))
        conn.execute(text("ALTER TABLE conversations_new RENAME TO conversations"))
        conn.execute(
            text(
                "CREATE INDEX ix_conversations_owner ON conversations(owner_type, owner_id)"
            )
        )
        conn.execute(text("PRAGMA foreign_keys = ON"))


def _migrate_conversation_messages_trip_id_nullable():
    """Rebuild `conversation_messages` so `trip_id` is nullable.

    The original schema declared `trip_id INTEGER NOT NULL`. After spec 007
    made conversations polymorphic, year-plan-owned messages legitimately
    have no trip, and the old NOT NULL constraint blocks inserts. SQLite
    can't drop NOT NULL via ALTER, so rebuild the table. Idempotent: guarded
    by a nullability check; no-op once the column is already nullable.
    Preserves every row via INSERT-SELECT.
    """
    from sqlalchemy import inspect as sqla_inspect, text

    inspector = sqla_inspect(trips_engine)
    if "conversation_messages" not in inspector.get_table_names():
        return  # fresh DB — create_all will build the correct shape
    cols = {c["name"]: c for c in inspector.get_columns("conversation_messages")}
    trip_col = cols.get("trip_id")
    if trip_col is None or trip_col.get("nullable", True):
        return  # already nullable (or column missing — nothing to do)

    with trips_engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        conn.execute(text("""
                CREATE TABLE conversation_messages_new (
                    id INTEGER PRIMARY KEY,
                    conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
                    trip_id INTEGER REFERENCES trip_plans(id) ON DELETE CASCADE,
                    role VARCHAR NOT NULL,
                    content TEXT NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """))
        conn.execute(text("""
                INSERT INTO conversation_messages_new
                    (id, conversation_id, trip_id, role, content, created_at)
                SELECT id, conversation_id, trip_id, role, content, created_at
                FROM conversation_messages
                """))
        conn.execute(text("DROP TABLE conversation_messages"))
        conn.execute(
            text(
                "ALTER TABLE conversation_messages_new RENAME TO conversation_messages"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX ix_conversation_messages_id ON conversation_messages (id)"
            )
        )
        conn.execute(text("PRAGMA foreign_keys = ON"))


def _migrate_yearly_to_slot_as_trip_intent():
    """F008: reshape the yearly planner.

    - Add `slots.trip_plan_id` (FK → trip_plans, nullable, ON DELETE SET NULL).
    - Add `slots.theme` (TEXT NOT NULL DEFAULT '').
    - Drop `slot_option_placements` and `trip_options` tables if present.

    Idempotent: each step is guarded by a presence check. The table drops are
    pre-authorized by the user for F008 (the old placement/option feature is
    superseded and its test-grade data is intentionally discarded).
    """
    from sqlalchemy import inspect as sqla_inspect, text

    inspector = sqla_inspect(trips_engine)
    existing_tables = set(inspector.get_table_names())

    if "slots" in existing_tables:
        slot_cols = {c["name"] for c in inspector.get_columns("slots")}
        with trips_engine.begin() as conn:
            if "trip_plan_id" not in slot_cols:
                conn.execute(
                    text(
                        "ALTER TABLE slots ADD COLUMN trip_plan_id INTEGER "
                        "REFERENCES trip_plans(id) ON DELETE SET NULL"
                    )
                )
            if "theme" not in slot_cols:
                conn.execute(
                    text("ALTER TABLE slots ADD COLUMN theme TEXT NOT NULL DEFAULT ''")
                )

    # Drop the superseded tables. SQLite can't do this inside the same
    # `inspector` snapshot's transaction, so use a fresh begin.
    with trips_engine.begin() as conn:
        if "slot_option_placements" in existing_tables:
            conn.execute(text("DROP TABLE slot_option_placements"))
        if "trip_options" in existing_tables:
            conn.execute(text("DROP TABLE trip_options"))


def _migrate_yearly_to_year_options():
    """F009: reshape the yearly planner to `YearPlan → YearOption → Slot`.

    - Add `year_plans.windows` (TEXT NOT NULL DEFAULT '[]').
    - Ensure `year_options` table exists (create_all handles the shape once
      the ORM model is registered).
    - Rebuild `slots`: drop the old table if it still has `year_plan_id`,
      letting `create_all` recreate it with the new `year_option_id` FK.
      **Discards existing slot rows** — pre-authorized by the user (the
      yearly feature data is test-grade). Linked `trip_plans` rows are
      preserved (they live in a separate table).

    Idempotent: guarded by column-presence checks.
    """
    from sqlalchemy import inspect as sqla_inspect, text

    inspector = sqla_inspect(trips_engine)
    existing = set(inspector.get_table_names())

    # Step 1 — windows column on year_plans.
    if "year_plans" in existing:
        year_plan_cols = {c["name"] for c in inspector.get_columns("year_plans")}
        if "windows" not in year_plan_cols:
            with trips_engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE year_plans ADD COLUMN windows TEXT NOT NULL DEFAULT '[]'"
                    )
                )

    # Step 2 — drop the old slots shape. create_all() (called next) will
    # recreate with the F009 shape. Guarded on the presence of the old FK
    # column `year_plan_id` to stay idempotent once migrated.
    if "slots" in existing:
        slot_cols = {c["name"] for c in inspector.get_columns("slots")}
        if "year_plan_id" in slot_cols and "year_option_id" not in slot_cols:
            with trips_engine.begin() as conn:
                conn.execute(text("DROP TABLE slots"))


def _migrate_yearly_excluded_reason():
    """F012: add `excluded_reason TEXT` to `year_options` and `slots`.

    Both columns are nullable and only populated when status='excluded'.
    Idempotent — guarded by column presence.
    """
    from sqlalchemy import inspect as sqla_inspect, text

    inspector = sqla_inspect(trips_engine)
    with trips_engine.begin() as conn:
        if "year_options" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("year_options")}
            if "excluded_reason" not in cols:
                conn.execute(
                    text("ALTER TABLE year_options ADD COLUMN excluded_reason TEXT")
                )
        if "slots" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("slots")}
            if "excluded_reason" not in cols:
                conn.execute(text("ALTER TABLE slots ADD COLUMN excluded_reason TEXT"))


def _migrate_slot_drop_unique_option_window():
    """F011: drop the UNIQUE(year_option_id, window_index) constraint.

    Users now sketch multiple alternative trip ideas inside one cell of the
    grid. SQLite can't drop a constraint without rebuilding the table.
    Idempotent — guarded by presence of the constraint.
    """
    from sqlalchemy import inspect as sqla_inspect, text

    inspector = sqla_inspect(trips_engine)
    if "slots" not in inspector.get_table_names():
        return
    uniq_names = {u.get("name") for u in inspector.get_unique_constraints("slots")}
    if "uq_slot_option_window" not in uniq_names:
        return
    with trips_engine.begin() as conn:
        conn.execute(text("DROP TABLE slots"))


def _migrate_slot_window_required():
    """F010: enforce that every trip idea (slot) sits in a window.

    Rebuilds the slots table when the existing `window_index` column is
    nullable. Create_all then rebuilds with `window_index NOT NULL` +
    `UNIQUE (year_option_id, window_index)`. Discards slot rows (authorized:
    yearly data is test-grade). Idempotent.
    """
    from sqlalchemy import inspect as sqla_inspect, text

    inspector = sqla_inspect(trips_engine)
    if "slots" not in inspector.get_table_names():
        return
    cols = {c["name"]: c for c in inspector.get_columns("slots")}
    win = cols.get("window_index")
    if win is None:
        return  # shouldn't happen — F009 guaranteed the column
    if win.get("nullable", True) is False:
        return  # already F010-shaped
    with trips_engine.begin() as conn:
        conn.execute(text("DROP TABLE slots"))


def get_trips_db():
    """Dependency: yields a trips database session."""
    db = TripsSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_vacationmap_db():
    """Dependency: yields a read-only VacationMap database session."""
    db = VacationMapSessionLocal()
    try:
        yield db
    finally:
        db.close()
