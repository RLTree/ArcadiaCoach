"""Add milestone project metadata and evaluation fields"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20241016_03_milestone_projects'
down_revision = '20241016_02_milestone_completions'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        'curriculum_schedule_items',
        sa.Column('milestone_project', sa.JSON(), nullable=True),
    )
    op.add_column(
        'milestone_completions',
        sa.Column('project_status', sa.String(length=32), nullable=False, server_default='completed'),
    )
    op.add_column(
        'milestone_completions',
        sa.Column('evaluation_outcome', sa.String(length=32), nullable=True),
    )
    op.add_column(
        'milestone_completions',
        sa.Column('evaluation_notes', sa.Text(), nullable=True),
    )
    op.add_column(
        'milestone_completions',
        sa.Column('elo_delta', sa.Integer(), nullable=False, server_default='12'),
    )
    op.execute("UPDATE milestone_completions SET project_status = 'completed' WHERE project_status IS NULL")
    op.execute("UPDATE milestone_completions SET elo_delta = 12 WHERE elo_delta IS NULL")
    op.alter_column('milestone_completions', 'project_status', server_default=None)
    op.alter_column('milestone_completions', 'elo_delta', server_default=None)


def downgrade():
    op.drop_column('milestone_completions', 'elo_delta')
    op.drop_column('milestone_completions', 'evaluation_notes')
    op.drop_column('milestone_completions', 'evaluation_outcome')
    op.drop_column('milestone_completions', 'project_status')
    op.drop_column('curriculum_schedule_items', 'milestone_project')
