"""drop_legacy_golf_tables_from_trips_db

Revision ID: 73c63fed419d
Revises: 1a3a938d3713
Create Date: 2026-04-19 18:18:26.250688

Before this commit the golf library shared the trips database. We've
split it out into its own SQLite (`backend/data/golf.db`). This migration
drops the orphaned `golf_resorts`, `golf_courses`, and `entity_images`
tables from the trips engine if they exist there.

No-op on fresh deploys (the new baseline never created those tables).
Runs exactly once on existing SQLite installs.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "73c63fed419d"
down_revision: Union[str, Sequence[str], None] = "1a3a938d3713"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LEGACY_TABLES = ("entity_images", "golf_courses", "golf_resorts")


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    for name in _LEGACY_TABLES:
        if name in existing:
            op.drop_table(name)


def downgrade() -> None:
    # Re-creating the legacy golf shape in the trips DB is intentionally
    # not supported — the golf library lives in its own engine now.
    raise NotImplementedError("Legacy golf tables are not re-creatable.")
