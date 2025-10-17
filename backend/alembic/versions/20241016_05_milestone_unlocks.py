"""Add milestone unlock metadata and queue."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20241016_05_milestone_unlocks"
down_revision = "20241016_04_milestone_requirements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "curriculum_schedules",
        sa.Column(
            "milestone_queue",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "curriculum_schedule_items",
        sa.Column("requirement_advisor_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "curriculum_schedule_items",
        sa.Column(
            "requirement_progress",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "curriculum_schedule_items",
        sa.Column("unlock_notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("curriculum_schedules", "milestone_queue", server_default=None)
    op.alter_column("curriculum_schedule_items", "requirement_progress", server_default=None)


def downgrade() -> None:
    op.drop_column("curriculum_schedule_items", "unlock_notified_at")
    op.drop_column("curriculum_schedule_items", "requirement_progress")
    op.drop_column("curriculum_schedule_items", "requirement_advisor_version")
    op.drop_column("curriculum_schedules", "milestone_queue")
