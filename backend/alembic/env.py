"""Alembic environment for the Trip Planner.

Key differences from the default scaffold:

* `sqlalchemy.url` is pulled from the runtime config via the `-x url=...`
  override OR from `app.database.TRIPS_DATABASE_URL` (which respects
  `DATABASE_URL` for Postgres and `TRIPS_DB_PATH` for SQLite).
* `target_metadata` is `TripsBase.metadata` after all ORM modules have been
  imported — so `alembic revision --autogenerate` sees every table.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the backend package importable when running `alembic` from backend/.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Import all model modules so TripsBase.metadata is fully populated.
from app.database import TripsBase, TRIPS_DATABASE_URL  # noqa: E402
from app.trips import models as _trip_models  # noqa: E402,F401
from app.golf import models as _golf_models  # noqa: E402,F401
from app.yearly import models as _yearly_models  # noqa: E402,F401

config = context.config

# Prefer runtime URL over the stub in alembic.ini.
_runtime_url = (
    context.get_x_argument(as_dictionary=True).get("url")
    or os.environ.get("ALEMBIC_DATABASE_URL")
    or TRIPS_DATABASE_URL
)
config.set_main_option("sqlalchemy.url", _runtime_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = TripsBase.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite-friendly DDL ops for local dev
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # `render_as_batch` = safe on SQLite, no-op on Postgres.
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
