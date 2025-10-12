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
