"""Add milestone requirements to schedule items."""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20241016_04_milestone_requirements"
down_revision = "20241016_03_milestone_projects"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "curriculum_schedule_items",
        sa.Column("milestone_requirements", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.alter_column("curriculum_schedule_items", "milestone_requirements", server_default=None)


def downgrade():
    op.drop_column("curriculum_schedule_items", "milestone_requirements")
