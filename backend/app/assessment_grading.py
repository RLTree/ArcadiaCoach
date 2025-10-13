"""Automated grading pipeline for onboarding assessment submissions (Phase 5)."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from statistics import mean
from typing import Any, Dict, List, Literal, Optional, Tuple, cast

from agents import ModelSettings, RunConfig, Runner
from chatkit.types import ThreadMetadata
from openai.types.shared.reasoning import Reasoning
from openai.types.shared.reasoning_effort import ReasoningEffort
from pydantic import BaseModel, Field, ValidationError

from .assessment_result import (
    AssessmentCategoryOutcome,
    AssessmentGradingResult,
    RubricCriterionResult,
    TaskGradingResult,
)
from .assessment_submission import AssessmentSubmission, AssessmentTaskResponse, submission_payload
from .arcadia_agent import ArcadiaAgentContext, get_arcadia_agent
from .config import Settings
from .learner_profile import AssessmentTask, LearnerProfile
from .memory_store import MemoryStore


logger = logging.getLogger(__name__)


ConfidenceLiteral = Literal["low", "medium", "high"]


class RubricFeedbackPayload(BaseModel):
    criterion: str
    met: bool
    notes: Optional[str] = None
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class TaskGradePayload(BaseModel):
    task_id: str
    score: float = Field(ge=0.0, le=1.0)
    confidence: ConfidenceLiteral = "medium"
    feedback: str
    strengths: List[str] = Field(default_factory=list)
    improvements: List[str] = Field(default_factory=list)
    rubric: List[RubricFeedbackPayload] = Field(default_factory=list)


class GradingAgentResponse(BaseModel):
    overall_feedback: str
    strengths: List[str] = Field(default_factory=list)
    focus_areas: List[str] = Field(default_factory=list)
    tasks: List[TaskGradePayload] = Field(default_factory=list)


def _reasoning_effort(value: str) -> ReasoningEffort:
    allowed = {"minimal", "low", "medium", "high"}
    effort = value if value in allowed else "medium"
    return cast(ReasoningEffort, effort)


def _coerce_agent_response(payload: Any) -> GradingAgentResponse:
    if isinstance(payload, GradingAgentResponse):
        return payload
    if isinstance(payload, BaseModel):
        return GradingAgentResponse.model_validate(payload.model_dump())
    if isinstance(payload, dict):
        return GradingAgentResponse.model_validate(payload)
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Agent returned malformed JSON for grading: {exc}") from exc
        return GradingAgentResponse.model_validate(data)
    raise TypeError(f"Unexpected grading payload type: {type(payload).__name__}")


def _payload_for_agent(
    profile: LearnerProfile,
    submission: AssessmentSubmission,
    tasks: Dict[str, AssessmentTask],
) -> Dict[str, Any]:
    categories: List[Dict[str, Any]] = []
    if profile.elo_category_plan:
        for entry in profile.elo_category_plan.categories:
            categories.append(
                {
                    "key": entry.key,
                    "label": entry.label,
                    "weight": entry.weight,
                    "focus_areas": entry.focus_areas,
                    "rubric": [
                        {"level": band.level, "descriptor": band.descriptor}
                        for band in entry.rubric
                    ],
                    "starting_rating": entry.starting_rating,
                }
            )

    responses: List[Dict[str, Any]] = []
    for response in submission.responses:
        task = tasks.get(response.task_id)
        responses.append(
            {
                "task_id": response.task_id,
                "category_key": task.category_key if task else response.category_key,
                "task_type": task.task_type if task else response.task_type,
                "title": task.title if task else "",
                "prompt": task.prompt if task else "",
                "guidance": task.guidance if task else "",
                "rubric": list(task.rubric) if task else [],
                "answer_key": task.answer_key,
                "expected_minutes": task.expected_minutes if task else None,
                "response": response.response,
            }
        )

    submission_view = submission_payload(submission)
    attachments_payload = [
        {
            "attachment_id": item.attachment_id,
            "name": item.name,
            "kind": item.kind,
            "url": item.url,
            "description": item.description,
            "content_type": item.content_type,
            "size_bytes": item.size_bytes,
            "source": item.source,
        }
        for item in submission_view.attachments
    ]

    return {
        "learner": {
            "username": profile.username,
            "goal": profile.goal,
            "use_case": profile.use_case,
            "strengths": profile.strengths,
        },
        "categories": categories,
        "submission": {
            "submission_id": submission.submission_id,
            "submitted_at": submission.submitted_at.isoformat(),
            "metadata": submission.metadata,
            "attachments": attachments_payload,
        },
        "responses": responses,
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serialisable")


def _grading_instructions() -> str:
    return (
        "You are grading an onboarding assessment for Arcadia Coach. "
        "For each task, evaluate the learner's response against the supplied rubric, guidance, and answer key. "
        "Score each task between 0.0 and 1.0 (inclusive) where 1.0 is exceptional and 0.0 is incorrect or missing. "
        "Return STRICT JSON with keys: overall_feedback (string <= 140 words), "
        "strengths (array of strings), focus_areas (array of strings), and tasks (array). "
        "Each tasks entry must include task_id, score (float), confidence ('low'|'medium'|'high'), "
        "feedback (string), strengths (array of strings), improvements (array of strings), "
        "and rubric (array of {criterion, met, notes?, score?}). "
        "Do not include any additional keys. "
        "Ensure rubric notes stay concise (<=35 words) and avoid markdown."
    )


def _map_confidence(value: str) -> ConfidenceLiteral:
    options: Dict[str, ConfidenceLiteral] = {"low": "low", "medium": "medium", "high": "high"}
    return options.get(value.lower(), "medium")


def _sanitize_score(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return round(value, 4)


def _fallback_result(
    submission: AssessmentSubmission,
    tasks: Dict[str, AssessmentTask],
) -> AssessmentGradingResult:
    task_results: List[TaskGradingResult] = []
    for response in submission.responses:
        task = tasks.get(response.task_id)
        task_results.append(
            TaskGradingResult(
                task_id=response.task_id,
                category_key=task.category_key if task else response.category_key,
                task_type=task.task_type if task else response.task_type,
                score=0.5,
                confidence="low",
                feedback="Automated grading was unavailable; provisional score recorded.",
                strengths=[],
                improvements=["Review rubric items manually and adjust score once grading succeeds."],
                rubric=[],
            )
        )

    outcomes: List[AssessmentCategoryOutcome] = []
    grouped: Dict[str, List[float]] = defaultdict(list)
    for result in task_results:
        grouped[result.category_key].append(result.score)
    for category_key, scores in grouped.items():
        avg = mean(scores)
        rating = max(int(round(1100 + (avg - 0.5) * 200)), 0)
        outcomes.append(
            AssessmentCategoryOutcome(
                category_key=category_key,
                average_score=round(avg, 4),
                initial_rating=rating,
                starting_rating=1100,
                rating_delta=rating - 1100,
                rationale="Fallback result; replace once automated grading completes.",
            )
        )

    return AssessmentGradingResult(
        submission_id=submission.submission_id,
        overall_feedback="Automated grading temporarily unavailable. Scores have been provisionally set to 0.5.",
        strengths=[],
        focus_areas=["Trigger a developer regrade once the grading agent is reachable."],
        task_results=task_results,
        category_outcomes=outcomes,
    )


def _convert_tasks(
    payload: GradingAgentResponse,
    submission: AssessmentSubmission,
    tasks: Dict[str, AssessmentTask],
) -> List[TaskGradingResult]:
    lookup: Dict[str, AssessmentTask] = tasks
    fallback_types: Dict[str, AssessmentTaskResponse] = {response.task_id: response for response in submission.responses}
    converted: List[TaskGradingResult] = []

    for item in payload.tasks:
        task_model = lookup.get(item.task_id)
        fallback = fallback_types.get(item.task_id)
        category_key = task_model.category_key if task_model else (fallback.category_key if fallback else "general")
        task_type = task_model.task_type if task_model else (fallback.task_type if fallback else "concept_check")
        rubric = [
            RubricCriterionResult(
                criterion=entry.criterion,
                met=entry.met,
                notes=entry.notes.strip() if isinstance(entry.notes, str) else None,
                score=_sanitize_score(entry.score) if entry.score is not None else None,
            )
            for entry in item.rubric
        ]
        converted.append(
            TaskGradingResult(
                task_id=item.task_id,
                category_key=category_key,
                task_type=task_type,  # type: ignore[arg-type]
                score=_sanitize_score(item.score),
                confidence=_map_confidence(item.confidence),
                feedback=item.feedback.strip(),
                strengths=[value.strip() for value in item.strengths if value.strip()],
                improvements=[value.strip() for value in item.improvements if value.strip()],
                rubric=rubric,
            )
        )
    return converted


def _compute_category_outcomes(
    profile: LearnerProfile,
    task_results: List[TaskGradingResult],
) -> Tuple[List[AssessmentCategoryOutcome], Dict[str, int]]:
    grouped: Dict[str, List[TaskGradingResult]] = defaultdict(list)
    for result in task_results:
        grouped[result.category_key].append(result)

    plan_lookup: Dict[str, int] = {}
    if profile.elo_category_plan:
        for category in profile.elo_category_plan.categories:
            plan_lookup[category.key] = int(category.starting_rating)

    outcomes: List[AssessmentCategoryOutcome] = []
    ratings: Dict[str, int] = {}
    for category_key, entries in grouped.items():
        average = mean(result.score for result in entries) if entries else 0.5
        starting = plan_lookup.get(category_key, 1100)
        delta = int(round((average - 0.5) * 400))
        rating = max(starting + delta, 0)
        ratings[category_key] = rating
        rationale = (
            f"Average score {average*100:.0f}%. "
            f"Starting rating {starting} adjusted by {delta}."
        )
        outcomes.append(
            AssessmentCategoryOutcome(
                category_key=category_key,
                average_score=round(average, 4),
                initial_rating=rating,
                starting_rating=starting,
                rating_delta=delta,
                rationale=rationale,
            )
        )

    # Ensure categories without submissions retain their starting rating.
    if profile.elo_category_plan:
        for entry in profile.elo_category_plan.categories:
            if entry.key not in ratings:
                ratings[entry.key] = int(entry.starting_rating)
                outcomes.append(
                    AssessmentCategoryOutcome(
                        category_key=entry.key,
                        average_score=0.5,
                        initial_rating=int(entry.starting_rating),
                        starting_rating=int(entry.starting_rating),
                        rating_delta=0,
                        rationale="No tasks submitted for this category; initial rating preserved.",
                    )
                )

    outcomes.sort(key=lambda outcome: outcome.category_key)
    return outcomes, ratings


async def grade_submission(
    settings: Settings,
    profile: LearnerProfile,
    submission: AssessmentSubmission,
    tasks: Dict[str, AssessmentTask],
) -> Tuple[AssessmentGradingResult, Dict[str, int]]:
    payload = _payload_for_agent(profile, submission, tasks)
    message = _grading_instructions() + "\n\nINPUT:\n" + json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        default=_json_default,
    )

    agent = get_arcadia_agent(settings.arcadia_agent_model, settings.arcadia_agent_enable_web)
    thread = ThreadMetadata.model_construct(
        id=f"grading-{profile.username}-{submission.submission_id[:8]}",
    )
    metadata: Dict[str, Any] = {
        "username": profile.username,
        "submission_id": submission.submission_id,
    }
    profile_snapshot = profile.model_dump(mode="json")
    context = ArcadiaAgentContext.model_construct(
        thread=thread,
        store=MemoryStore(),
        request_context={
            "metadata": metadata,
            "profile": profile_snapshot,
        },
        sanitized_input=None,
        web_enabled=settings.arcadia_agent_enable_web,
        reasoning_level=settings.arcadia_agent_reasoning,
        attachments=[],
    )

    try:
        result = await Runner.run(
            agent,
            message,
            context=context,
            run_config=RunConfig(
                model_settings=ModelSettings(
                    reasoning=Reasoning(
                        effort=_reasoning_effort(settings.arcadia_agent_reasoning),
                        summary="auto",
                    ),
                )
            ),
        )
        response = _coerce_agent_response(result.final_output)
        task_results = _convert_tasks(response, submission, tasks)
        if not task_results:
            raise ValueError("Grading agent returned no task results.")
        category_outcomes, ratings = _compute_category_outcomes(profile, task_results)
        grading = AssessmentGradingResult(
            submission_id=submission.submission_id,
            evaluated_at=datetime.now(timezone.utc),
            overall_feedback=response.overall_feedback.strip(),
            strengths=[value.strip() for value in response.strengths if value.strip()],
            focus_areas=[value.strip() for value in response.focus_areas if value.strip()],
            task_results=task_results,
            category_outcomes=category_outcomes,
        )
        return grading, ratings
    except Exception as exc:  # noqa: BLE001
        logger.exception("Automated grading failed for submission %s: %s", submission.submission_id, exc)
        fallback = _fallback_result(submission, tasks)
        _, fallback_ratings = _compute_category_outcomes(profile, fallback.task_results)
        return fallback, fallback_ratings
