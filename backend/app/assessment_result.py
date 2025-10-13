"""Data models for onboarding assessment grading results (Phase 5)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


ConfidenceLevel = Literal["low", "medium", "high"]


class RubricCriterionResult(BaseModel):
    """Outcome for a single rubric criterion."""

    criterion: str
    met: bool
    notes: Optional[str] = None
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class TaskGradingResult(BaseModel):
    """Detailed grading feedback for a single assessment task."""

    task_id: str
    category_key: str
    task_type: Literal["concept_check", "code"]
    score: float = Field(ge=0.0, le=1.0)
    confidence: ConfidenceLevel = "medium"
    feedback: str
    strengths: List[str] = Field(default_factory=list)
    improvements: List[str] = Field(default_factory=list)
    rubric: List[RubricCriterionResult] = Field(default_factory=list)


class AssessmentCategoryOutcome(BaseModel):
    """Aggregated outcome for an assessment category, including initial rating."""

    category_key: str
    average_score: float = Field(ge=0.0, le=1.0)
    initial_rating: int = Field(ge=0)
    starting_rating: int = Field(default=1100, ge=0)
    rating_delta: int = 0
    rationale: Optional[str] = None


class AssessmentGradingResult(BaseModel):
    """Top-level grading report persisted for onboarding completions."""

    submission_id: str
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    overall_feedback: str
    strengths: List[str] = Field(default_factory=list)
    focus_areas: List[str] = Field(default_factory=list)
    task_results: List[TaskGradingResult] = Field(default_factory=list)
    category_outcomes: List[AssessmentCategoryOutcome] = Field(default_factory=list)


__all__ = [
    "AssessmentCategoryOutcome",
    "AssessmentGradingResult",
    "ConfidenceLevel",
    "RubricCriterionResult",
    "TaskGradingResult",
]
