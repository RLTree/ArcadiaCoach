"""Pydantic models mirroring the Swift agent payloads."""

from __future__ import annotations

from datetime import datetime, timezone
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


class OnboardingCurriculumPayload(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    overview: str
    success_criteria: List[str] = Field(default_factory=list)
    modules: List[CurriculumModulePayload] = Field(default_factory=list)


class OnboardingAssessmentTaskPayload(BaseModel):
    task_id: str
    category_key: str
    title: str
    task_type: Literal["concept_check", "code"]
    prompt: str
    guidance: str
    rubric: List[str] = Field(default_factory=list)
    expected_minutes: int = Field(default=20, ge=1)
    starter_code: Optional[str] = None
    answer_key: Optional[str] = None


class OnboardingAssessmentPayload(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: Literal["pending", "in_progress", "completed"] = "pending"
    tasks: List[OnboardingAssessmentTaskPayload] = Field(default_factory=list)


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
    knowledge_tags: List[str] = Field(default_factory=list)
    recent_sessions: List[str] = Field(default_factory=list)
    memory_records: List[LearnerMemoryItemPayload] = Field(default_factory=list)
    skill_ratings: List[SkillRatingPayload] = Field(default_factory=list)
    memory_index_id: str
    last_updated: datetime
    elo_category_plan: Optional[EloCategoryPlanPayload] = None
    curriculum_plan: Optional[OnboardingCurriculumPayload] = None
    onboarding_assessment: Optional[OnboardingAssessmentPayload] = None
    onboarding_assessment_result: Optional[AssessmentGradingPayload] = None
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
