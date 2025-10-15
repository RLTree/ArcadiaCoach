"""Add launch metadata fields to curriculum schedule items.

Revision ID: 20241015_02_schedule_launch_metadata
Revises: 20241015_01_initial_persistence
Create Date: 2025-10-15 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "20241015_02_schedule_launch_metadata"
down_revision = "20241015_01_initial_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extend alembic_version.version_num to accommodate longer revision identifiers.
    with op.batch_alter_table("alembic_version") as batch_op:
        batch_op.alter_column(
            "version_num",
            type_=sa.String(length=64),
            existing_type=sa.String(length=32),
        )

    with op.batch_alter_table("curriculum_schedule_items") as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending")
        )
        batch_op.add_column(
            sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("active_session_id", sa.String(length=64), nullable=True)
        )
    with op.batch_alter_table("curriculum_schedule_items") as batch_op:
        batch_op.alter_column("status", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("curriculum_schedule_items") as batch_op:
        batch_op.drop_column("active_session_id")
        batch_op.drop_column("last_completed_at")
        batch_op.drop_column("last_started_at")
        batch_op.drop_column("status")

    with op.batch_alter_table("alembic_version") as batch_op:
        batch_op.alter_column(
            "version_num",
            type_=sa.String(length=32),
            existing_type=sa.String(length=64),
        )
