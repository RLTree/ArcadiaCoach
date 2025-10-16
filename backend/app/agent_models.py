"""Pydantic models mirroring the Swift agent payloads."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class Widget(BaseModel):
    type: Literal["Card", "List", "StatRow", "MiniChatbot", "ArcadiaChatbot"]
    props: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _merge_specialized_props(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        if values.get("props"):
            return values
        for key in ("propsCard", "propsList", "propsStat", "propsMiniChatbot", "propsArcadiaChatbot"):
            if key in values and values[key] is not None:
                values["props"] = values[key]
                break
        return values


class WidgetEnvelope(BaseModel):
    display: Optional[str] = None
    widgets: List[Widget] = Field(default_factory=list)
    citations: Optional[List[str]] = None


class EndLearn(BaseModel):
    intent: str
    display: str
    widgets: List[Widget] = Field(default_factory=list)
    citations: Optional[List[str]] = None


class QuizMetadata(BaseModel):
    topic: Optional[str] = None
    score: Optional[float] = None


class EndQuiz(BaseModel):
    intent: str
    display: Optional[str] = None
    widgets: List[Widget] = Field(default_factory=list)
    elo: Dict[str, int] = Field(default_factory=dict)
    last_quiz: Optional[QuizMetadata] = None


class EndMilestone(BaseModel):
    intent: str
    display: str
    widgets: List[Widget] = Field(default_factory=list)


class LearnerMemoryItemPayload(BaseModel):
    note_id: str
    note: str
    tags: List[str] = Field(default_factory=list)
    created_at: datetime


class EloRubricBandPayload(BaseModel):
    level: str
    descriptor: str


class EloCategoryDefinitionPayload(BaseModel):
    key: str
    label: str
    description: str
    focus_areas: List[str] = Field(default_factory=list)
    weight: float = Field(default=1.0)
    rubric: List[EloRubricBandPayload] = Field(default_factory=list)
    starting_rating: int = 1100


class EloCategoryPlanPayload(BaseModel):
    generated_at: datetime
    source_goal: Optional[str] = None
    strategy_notes: Optional[str] = None
    categories: List[EloCategoryDefinitionPayload] = Field(default_factory=list)


class CurriculumModulePayload(BaseModel):
    module_id: str
    category_key: str
    title: str
    summary: str
    objectives: List[str] = Field(default_factory=list)
    activities: List[str] = Field(default_factory=list)
    deliverables: List[str] = Field(default_factory=list)
    estimated_minutes: Optional[int] = None
    tier: Optional[int] = Field(default=None, ge=1)
    prerequisite_module_ids: List[str] = Field(default_factory=list)


class MilestonePrerequisitePayload(BaseModel):
    item_id: str
    title: str
    kind: Literal["lesson", "quiz", "milestone"]
    status: Literal["pending", "in_progress", "completed"] = "pending"
    required: bool = Field(default=True)
    recommended_day_offset: Optional[int] = None


class MilestoneBriefPayload(BaseModel):
    headline: str
    summary: Optional[str] = None
    objectives: List[str] = Field(default_factory=list)
    deliverables: List[str] = Field(default_factory=list)
    success_criteria: List[str] = Field(default_factory=list)
    external_work: List[str] = Field(default_factory=list)
    capture_prompts: List[str] = Field(default_factory=list)
    prerequisites: List[MilestonePrerequisitePayload] = Field(default_factory=list)
    elo_focus: List[str] = Field(default_factory=list)
    resources: List[str] = Field(default_factory=list)


class MilestoneProgressPayload(BaseModel):
    recorded_at: datetime
    notes: Optional[str] = None
    external_links: List[str] = Field(default_factory=list)
    attachment_ids: List[str] = Field(default_factory=list)


class SequencedWorkItemPayload(BaseModel):
    item_id: str
    kind: Literal["lesson", "quiz", "milestone"]
    category_key: str
    title: str
    summary: Optional[str] = None
    objectives: List[str] = Field(default_factory=list)
    prerequisites: List[str] = Field(default_factory=list)
    recommended_minutes: int = Field(default=45, ge=5)
    recommended_day_offset: int = Field(default=0, ge=0)
    effort_level: Literal["light", "moderate", "focus"] = "moderate"
    focus_reason: Optional[str] = None
    expected_outcome: Optional[str] = None
    user_adjusted: bool = False
    scheduled_for: Optional[datetime] = None
    launch_status: Literal["pending", "in_progress", "completed"] = "pending"
    last_launched_at: Optional[datetime] = None
    last_completed_at: Optional[datetime] = None
    active_session_id: Optional[str] = None
    launch_locked_reason: Optional[str] = None
    milestone_brief: Optional[MilestoneBriefPayload] = None
    milestone_progress: Optional[MilestoneProgressPayload] = None


class ScheduleWarningPayload(BaseModel):
    code: str
    message: str
    detail: Optional[str] = None
    generated_at: datetime


class CategoryPacingPayload(BaseModel):
    category_key: str
    planned_minutes: int = Field(default=0, ge=0)
    target_share: float = Field(default=0.0, ge=0.0)
    deferral_pressure: Literal["low", "medium", "high"]
    deferral_count: int = Field(default=0, ge=0)
    max_deferral_days: int = Field(default=0, ge=0)
    rationale: Optional[str] = None


class ScheduleRationaleEntryPayload(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    headline: str
    summary: str
    related_categories: List[str] = Field(default_factory=list)
    adjustment_notes: List[str] = Field(default_factory=list)


class ScheduleSlicePayload(BaseModel):
    start_day: int
    end_day: int
    day_span: int
    total_items: int
    total_days: int
    has_more: bool = False
    next_start_day: Optional[int] = None


class CurriculumSchedulePayload(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    time_horizon_days: int = Field(default=14, ge=1)
    timezone: Optional[str] = None
    anchor_date: Optional[date] = None
    cadence_notes: Optional[str] = None
    is_stale: bool = False
    warnings: List[ScheduleWarningPayload] = Field(default_factory=list)
    items: List[SequencedWorkItemPayload] = Field(default_factory=list)
    pacing_overview: Optional[str] = None
    category_allocations: List[CategoryPacingPayload] = Field(default_factory=list)
    rationale_history: List[ScheduleRationaleEntryPayload] = Field(default_factory=list)
    sessions_per_week: int = Field(default=4, ge=1)
    projected_weekly_minutes: int = Field(default=0, ge=0)
    long_range_item_count: int = Field(default=0, ge=0)
    extended_weeks: int = Field(default=0, ge=0)
    long_range_category_keys: List[str] = Field(default_factory=list)
    slice: Optional[ScheduleSlicePayload] = None


class ScheduleLaunchContentPayload(BaseModel):
    kind: Literal["lesson", "quiz", "milestone"]
    session_id: str
    lesson: Optional[EndLearn] = None
    quiz: Optional[EndQuiz] = None
    milestone: Optional[EndMilestone] = None


class ScheduleLaunchResponsePayload(BaseModel):
    schedule: CurriculumSchedulePayload
    item: SequencedWorkItemPayload
    content: ScheduleLaunchContentPayload


class OnboardingCurriculumPayload(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    overview: str
    success_criteria: List[str] = Field(default_factory=list)
    modules: List[CurriculumModulePayload] = Field(default_factory=list)


class OnboardingAssessmentTaskPayload(BaseModel):
    task_id: str
    category_key: str
    section_id: Optional[str] = None
    title: str
    task_type: Literal["concept_check", "code"]
    prompt: str
    guidance: str
    rubric: List[str] = Field(default_factory=list)
    expected_minutes: int = Field(default=20, ge=1)
    starter_code: Optional[str] = None
    answer_key: Optional[str] = None


class FoundationModuleReferencePayload(BaseModel):
    module_id: str
    category_key: str
    priority: Literal["core", "reinforcement", "extension"] = "core"
    suggested_weeks: Optional[int] = Field(default=None, ge=1)
    notes: Optional[str] = None


class FoundationTrackPayload(BaseModel):
    track_id: str
    label: str
    priority: Literal["now", "up_next", "later"] = "now"
    confidence: Literal["low", "medium", "high"] = "medium"
    weight: float = Field(default=1.0)
    technologies: List[str] = Field(default_factory=list)
    focus_areas: List[str] = Field(default_factory=list)
    prerequisites: List[str] = Field(default_factory=list)
    recommended_modules: List[FoundationModuleReferencePayload] = Field(default_factory=list)
    suggested_weeks: Optional[int] = Field(default=None, ge=1)
    notes: Optional[str] = None


class GoalParserInferencePayload(BaseModel):
    generated_at: datetime
    summary: Optional[str] = None
    target_outcomes: List[str] = Field(default_factory=list)
    tracks: List[FoundationTrackPayload] = Field(default_factory=list)
    missing_templates: List[str] = Field(default_factory=list)


class AssessmentSectionPayload(BaseModel):
    section_id: str
    title: str
    description: str = ""
    intent: Literal["concept", "coding", "data", "architecture", "tooling", "custom"] = "concept"
    expected_minutes: int = Field(default=45, ge=0)
    tasks: List[OnboardingAssessmentTaskPayload] = Field(default_factory=list)


class OnboardingAssessmentPayload(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: Literal["pending", "in_progress", "completed"] = "pending"
    tasks: List[OnboardingAssessmentTaskPayload] = Field(default_factory=list)
    sections: List[AssessmentSectionPayload] = Field(default_factory=list)


class AssessmentTaskResponsePayload(BaseModel):
    task_id: str
    response: str
    category_key: str
    task_type: Literal["concept_check", "code"]
    word_count: int = Field(default=0, ge=0)


class AssessmentRubricEvaluationPayload(BaseModel):
    criterion: str
    met: bool
    notes: Optional[str] = None
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class AssessmentTaskGradePayload(BaseModel):
    task_id: str
    category_key: str
    task_type: Literal["concept_check", "code"]
    score: float = Field(ge=0.0, le=1.0)
    confidence: Literal["low", "medium", "high"] = "medium"
    feedback: str
    strengths: List[str] = Field(default_factory=list)
    improvements: List[str] = Field(default_factory=list)
    rubric: List[AssessmentRubricEvaluationPayload] = Field(default_factory=list)


class AssessmentCategoryOutcomePayload(BaseModel):
    category_key: str
    average_score: float = Field(ge=0.0, le=1.0)
    initial_rating: int = Field(ge=0)
    starting_rating: int = Field(default=1100, ge=0)
    rating_delta: int = 0
    rationale: Optional[str] = None


class AssessmentGradingPayload(BaseModel):
    submission_id: str
    evaluated_at: datetime
    overall_feedback: str
    strengths: List[str] = Field(default_factory=list)
    focus_areas: List[str] = Field(default_factory=list)
    task_results: List[AssessmentTaskGradePayload] = Field(default_factory=list)
    category_outcomes: List[AssessmentCategoryOutcomePayload] = Field(default_factory=list)


class AssessmentSubmissionAttachmentPayload(BaseModel):
    attachment_id: Optional[str] = None
    name: str
    kind: Literal["file", "link", "note"] = "file"
    url: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = Field(default=None, ge=0)


class AssessmentSubmissionPayload(BaseModel):
    submission_id: str
    username: str
    submitted_at: datetime
    responses: List[AssessmentTaskResponsePayload] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)
    grading: Optional[AssessmentGradingPayload] = None
    attachments: List[AssessmentSubmissionAttachmentPayload] = Field(default_factory=list)


class OnboardingPlanPayload(BaseModel):
    profile_summary: str
    curriculum: OnboardingCurriculumPayload
    categories: List[EloCategoryDefinitionPayload] = Field(default_factory=list)
    assessment: List[OnboardingAssessmentTaskPayload] = Field(default_factory=list)


class SkillRatingPayload(BaseModel):
    category: str
    rating: int


class LearnerProfilePayload(BaseModel):
    username: str
    goal: str = ""
    use_case: str = ""
    strengths: str = ""
    timezone: Optional[str] = None
    knowledge_tags: List[str] = Field(default_factory=list)
    recent_sessions: List[str] = Field(default_factory=list)
    memory_records: List[LearnerMemoryItemPayload] = Field(default_factory=list)
    skill_ratings: List[SkillRatingPayload] = Field(default_factory=list)
    memory_index_id: str
    last_updated: datetime
    elo_category_plan: Optional[EloCategoryPlanPayload] = None
    curriculum_plan: Optional[OnboardingCurriculumPayload] = None
    curriculum_schedule: Optional[CurriculumSchedulePayload] = None
    onboarding_assessment: Optional[OnboardingAssessmentPayload] = None
    onboarding_assessment_result: Optional[AssessmentGradingPayload] = None
    goal_inference: Optional[GoalParserInferencePayload] = None
    foundation_tracks: List[FoundationTrackPayload] = Field(default_factory=list)
    assessment_submissions: List[AssessmentSubmissionPayload] = Field(default_factory=list)


class LearnerProfileGetResponse(BaseModel):
    found: bool
    profile: Optional[LearnerProfilePayload] = None


class LearnerProfileUpdateResponse(BaseModel):
    profile: LearnerProfilePayload


class LearnerMemoryWriteResponse(BaseModel):
    note_id: str
    vector_store_id: str
    status: Literal["queued", "stored"]


class LearnerEloCategoryPlanResponse(BaseModel):
    username: str
    plan: EloCategoryPlanPayload
