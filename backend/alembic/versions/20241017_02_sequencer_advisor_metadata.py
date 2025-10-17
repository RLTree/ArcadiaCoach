"""Add sequencer advisor metadata columns"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20241017_02_sequencer_advisor_metadata"
down_revision = "20241017_01_milestone_requirement_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "curriculum_schedules",
        sa.Column(
            "dependency_targets",
            sa.JSON(),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "curriculum_schedules",
        sa.Column("sequencer_advisor_summary", sa.JSON(), nullable=True),
    )
    op.add_column(
        "curriculum_schedule_items",
        sa.Column(
            "dependency_targets",
            sa.JSON(),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.execute(
        "UPDATE curriculum_schedules SET dependency_targets = '[]'::jsonb WHERE dependency_targets IS NULL"
    )
    op.execute(
        "UPDATE curriculum_schedule_items SET dependency_targets = '[]'::jsonb WHERE dependency_targets IS NULL"
    )
    op.alter_column("curriculum_schedules", "dependency_targets", server_default=None)
    op.alter_column("curriculum_schedule_items", "dependency_targets", server_default=None)


def downgrade() -> None:
    op.drop_column("curriculum_schedule_items", "dependency_targets")
    op.drop_column("curriculum_schedules", "sequencer_advisor_summary")
    op.drop_column("curriculum_schedules", "dependency_targets")
