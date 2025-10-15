"""Initial PostgreSQL persistence schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20241015_01_initial_persistence"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learner_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False, server_default=""),
        sa.Column("use_case", sa.Text(), nullable=False, server_default=""),
        sa.Column("strengths", sa.Text(), nullable=False, server_default=""),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("knowledge_tags", sa.JSON(), nullable=False),
        sa.Column("recent_sessions", sa.JSON(), nullable=False),
        sa.Column("memory_index_id", sa.String(length=64), nullable=False),
        sa.Column("elo_snapshot", sa.JSON(), nullable=False),
        sa.Column("elo_category_plan", sa.JSON(), nullable=True),
        sa.Column("curriculum_plan", sa.JSON(), nullable=True),
        sa.Column("schedule_adjustments", sa.JSON(), nullable=False),
        sa.Column("onboarding_assessment", sa.JSON(), nullable=True),
        sa.Column("onboarding_assessment_result", sa.JSON(), nullable=True),
        sa.Column("goal_inference", sa.JSON(), nullable=True),
        sa.Column("foundation_tracks", sa.JSON(), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_learner_profiles_username", "learner_profiles", ["username"], unique=True)

    op.create_table(
        "learner_memory_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("learner_id", sa.String(length=36), sa.ForeignKey("learner_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("note_id", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("note_id", name="uq_memory_note_id"),
    )
    op.create_index("ix_learner_memory_records_learner", "learner_memory_records", ["learner_id"])

    op.create_table(
        "curriculum_schedules",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("learner_id", sa.String(length=36), sa.ForeignKey("learner_profiles.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_horizon_days", sa.Integer(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("cadence_notes", sa.Text(), nullable=True),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pacing_overview", sa.Text(), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("category_allocations", sa.JSON(), nullable=False),
        sa.Column("rationale_history", sa.JSON(), nullable=False),
        sa.Column("sessions_per_week", sa.Integer(), nullable=True),
        sa.Column("projected_weekly_minutes", sa.Integer(), nullable=True),
        sa.Column("long_range_item_count", sa.Integer(), nullable=True),
        sa.Column("extended_weeks", sa.Integer(), nullable=True),
        sa.Column("long_range_category_keys", sa.JSON(), nullable=False),
    )

    op.create_table(
        "assessment_submissions",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("learner_id", sa.String(length=36), sa.ForeignKey("learner_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("submission_id", sa.String(length=64), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responses", sa.JSON(), nullable=False),
        sa.Column("attachments", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("grading", sa.JSON(), nullable=True),
    )
    op.create_index("ix_assessment_submissions_learner", "assessment_submissions", ["learner_id"])
    op.create_index("ix_assessment_submissions_created", "assessment_submissions", ["submitted_at"])
    op.create_unique_constraint("uq_assessment_submission_id", "assessment_submissions", ["submission_id"])

    op.create_table(
        "assessment_attachments",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("attachment_id", sa.String(length=64), nullable=False),
        sa.Column("learner_id", sa.String(length=36), sa.ForeignKey("learner_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("stored_path", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("is_consumed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_assessment_attachments_learner", "assessment_attachments", ["learner_id"])
    op.create_index("ix_assessment_attachments_consumed", "assessment_attachments", ["is_consumed"])
    op.create_unique_constraint("uq_assessment_attachment_id", "assessment_attachments", ["attachment_id"])

    op.create_table(
        "curriculum_schedule_items",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("schedule_id", sa.String(length=36), sa.ForeignKey("curriculum_schedules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.String(length=128), nullable=False),
        sa.Column("category_key", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("objectives", sa.JSON(), nullable=False),
        sa.Column("prerequisites", sa.JSON(), nullable=False),
        sa.Column("recommended_minutes", sa.Integer(), nullable=False),
        sa.Column("recommended_day_offset", sa.Integer(), nullable=False),
        sa.Column("focus_reason", sa.Text(), nullable=True),
        sa.Column("expected_outcome", sa.Text(), nullable=True),
        sa.Column("effort_level", sa.String(length=16), nullable=False),
        sa.Column("user_adjusted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_schedule_items_day_offset",
        "curriculum_schedule_items",
        ["recommended_day_offset"],
    )

    op.create_table(
        "persistence_audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("learner_id", sa.String(length=36), sa.ForeignKey("learner_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    op.drop_table("persistence_audit_events")
    op.drop_index("ix_schedule_items_day_offset", table_name="curriculum_schedule_items")
    op.drop_table("curriculum_schedule_items")
    op.drop_constraint("uq_assessment_attachment_id", "assessment_attachments", type_="unique")
    op.drop_index("ix_assessment_attachments_consumed", table_name="assessment_attachments")
    op.drop_index("ix_assessment_attachments_learner", table_name="assessment_attachments")
    op.drop_table("assessment_attachments")
    op.drop_constraint("uq_assessment_submission_id", "assessment_submissions", type_="unique")
    op.drop_index("ix_assessment_submissions_created", table_name="assessment_submissions")
    op.drop_index("ix_assessment_submissions_learner", table_name="assessment_submissions")
    op.drop_table("assessment_submissions")
    op.drop_table("curriculum_schedules")
    op.drop_index("ix_learner_memory_records_learner", table_name="learner_memory_records")
    op.drop_table("learner_memory_records")
    op.drop_index("ix_learner_profiles_username", table_name="learner_profiles")
    op.drop_table("learner_profiles")
