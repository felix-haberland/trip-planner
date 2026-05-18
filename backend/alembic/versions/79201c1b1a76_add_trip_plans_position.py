"""add_trip_plans_position

Revision ID: 79201c1b1a76
Revises: 73c63fed419d
Create Date: 2026-05-17 21:40:56.188784

Adds `trip_plans.position` (Integer NOT NULL default 0) for user-driven
drag-and-drop ordering (F011). Backfill assigns `0..N-1` to existing rows
ordered by `updated_at DESC` so the post-migration default order matches
the previous pre-position behaviour.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "79201c1b1a76"
down_revision: Union[str, Sequence[str], None] = "73c63fed419d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("trip_plans") as batch:
        batch.add_column(
            sa.Column("position", sa.Integer(), nullable=False, server_default="0")
        )

    # Backfill so the post-migration display order matches the pre-position
    # behaviour (ORDER BY updated_at DESC). New rows append via app code; the
    # `server_default = 0` stays on the column so bulk imports without
    # `position` (e.g. the bundled seed loader) still succeed and tie-break
    # on `id` in `list_trips`.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id FROM trip_plans ORDER BY updated_at DESC, id ASC")
    ).fetchall()
    for idx, row in enumerate(rows):
        bind.execute(
            sa.text("UPDATE trip_plans SET position = :p WHERE id = :id"),
            {"p": idx, "id": row[0]},
        )


def downgrade() -> None:
    with op.batch_alter_table("trip_plans") as batch:
        batch.drop_column("position")
