"""Add milestone brief and progress columns.

Revision ID: 20241016_01_milestone_briefs
Revises: 20241015_02_schedule_launch_metadata
Create Date: 2025-10-16 09:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "20241016_01_milestone_briefs"
down_revision = "20241015_02_schedule_launch_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("curriculum_schedule_items") as batch_op:
        batch_op.add_column(sa.Column("milestone_brief", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("milestone_progress", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("curriculum_schedule_items") as batch_op:
        batch_op.drop_column("milestone_progress")
        batch_op.drop_column("milestone_brief")
