"""Add milestone completion history table.

Revision ID: 20241016_02_milestone_completions
Revises: 20241016_01_milestone_briefs
Create Date: 2025-10-16 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "20241016_02_milestone_completions"
down_revision = "20241016_01_milestone_briefs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "milestone_completions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("learner_id", sa.String(length=36), sa.ForeignKey("learner_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.String(length=128), nullable=False),
        sa.Column("category_key", sa.String(length=128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("headline", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("external_links", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("attachment_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("elo_focus", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("recommended_day_offset", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("learner_id", "item_id", name="uq_milestone_completion_item"),
    )
    op.create_index(
        "ix_milestone_completions_learner",
        "milestone_completions",
        ["learner_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_milestone_completions_learner", table_name="milestone_completions")
    op.drop_table("milestone_completions")
