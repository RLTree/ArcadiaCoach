"""Add requirement summary to schedule items."""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20241017_01_milestone_requirement_summary"
down_revision = "20241016_05_milestone_unlocks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "curriculum_schedule_items",
        sa.Column("requirement_summary", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("curriculum_schedule_items", "requirement_summary")
