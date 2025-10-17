"""Milestone requirement advisor that fine-tunes unlock thresholds (Phase 33)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Dict, Iterable, List, Optional

from agents import Agent, ModelSettings, Runner
from pydantic import BaseModel, Field, ValidationError

from .arcadia_agent import ArcadiaAgentContext
from .config import Settings, get_settings
from .learner_profile import MilestoneRequirement

logger = logging.getLogger(__name__)

RequirementAdvisorMode = str


class RequirementAdvisorError(RuntimeError):
    """Raised when the advisor fails to return usable guidance."""


class RequirementAdvisorRequirementPayload(BaseModel):
    category_key: str
    minimum_rating: int = Field(ge=0)
    rationale: Optional[str] = None


class RequirementAdvisorResponsePayload(BaseModel):
    version: str = Field(default="v1")
    requirements: List[RequirementAdvisorRequirementPayload] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class RequirementAdvisorRequestPayload(BaseModel):
    username: str
    category_key: str
    category_label: str
    baseline_requirements: List[RequirementAdvisorRequirementPayload] = Field(default_factory=list)
    elo_snapshot: Dict[str, int] = Field(default_factory=dict)
    recent_rating_changes: Dict[str, int] = Field(default_factory=dict)
    goal_summary: Optional[str] = None
    schedule_notes: Optional[str] = None
    outstanding_prereqs: List[str] = Field(default_factory=list)
    candidate_categories: List[str] = Field(default_factory=list)


@dataclass(frozen=True)
class RequirementAdvisorResult:
    requirements: List[MilestoneRequirement]
    version: str
    warnings: List[str]
    latency_ms: float


def resolve_mode(settings: Settings) -> RequirementAdvisorMode:
    value = getattr(settings, "arcadia_requirement_advisor_mode", "fallback")
    if value not in {"off", "fallback", "primary"}:
        return "fallback"
    return value


def should_advise(settings: Settings) -> bool:
    return resolve_mode(settings) != "off"


def _advisor_model(settings: Settings) -> str:
    explicit = getattr(settings, "arcadia_requirement_advisor_model", None)
    if explicit:
        return explicit
    return settings.arcadia_agent_model or "gpt-5"

_ADVISOR_CACHE: Dict[str, Agent[ArcadiaAgentContext]] = {}


def _advisor_agent(model: str) -> Agent[ArcadiaAgentContext]:
    if model not in _ADVISOR_CACHE:
        instructions = (
            "You are Arcadia Coach's Requirement Advisor. Given a milestone context, output JSON describing the "
            "unlock requirements a learner must meet before starting the milestone. Focus on actionable, "
            "measurable thresholds using Arcadia's ELO ratings. Keep the requirement list concise (1-3 items). "
            "If existing requirements already look good, you may keep them but feel free to tweak the minimum "
            "rating or rationale. Always respond with JSON that matches the provided schema."
        )
        _ADVISOR_CACHE[model] = Agent[ArcadiaAgentContext](
            name="Arcadia Requirement Advisor",
            instructions=instructions,
            model=model,
            tools=[],
            model_settings=ModelSettings(store=False),
        )
    return _ADVISOR_CACHE[model]


def advise_requirements(
    payload: RequirementAdvisorRequestPayload,
    *,
    settings: Optional[Settings] = None,
) -> RequirementAdvisorResult:
    resolved_settings = settings or get_settings()
    mode = resolve_mode(resolved_settings)
    if mode == "off":
        raise RequirementAdvisorError("Requirement advisor is disabled.")

    agent = _advisor_agent(_advisor_model(resolved_settings))
    schema = RequirementAdvisorResponsePayload.model_json_schema()
    message = {
        "username": payload.username,
        "category_key": payload.category_key,
        "category_label": payload.category_label,
        "baseline_requirements": [req.model_dump(mode="json") for req in payload.baseline_requirements],
        "elo_snapshot": payload.elo_snapshot,
        "recent_rating_changes": payload.recent_rating_changes,
        "goal_summary": payload.goal_summary,
        "schedule_notes": payload.schedule_notes,
        "outstanding_prereqs": payload.outstanding_prereqs,
        "candidate_categories": payload.candidate_categories,
    }
    prompt = (
        "Respond strictly with JSON. Schema:\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        "CONTEXT:\n"
        f"{json.dumps(message, ensure_ascii=False, indent=2)}"
    )
    started = perf_counter()
    try:
        result = Runner.run_sync(agent, prompt, context=None)
    except Exception as exc:  # noqa: BLE001
        raise RequirementAdvisorError(f"Requirement advisor call failed: {exc}") from exc

    latency_ms = round((perf_counter() - started) * 1000.0, 2)
    try:
        payload_obj = RequirementAdvisorResponsePayload.model_validate_json(result.final_output)
    except (ValidationError, json.JSONDecodeError) as exc:
        raise RequirementAdvisorError(f"Requirement advisor returned invalid payload: {exc}") from exc

    requirements = _merge_with_snapshot(
        payload_obj.requirements,
        payload.baseline_requirements,
        payload.elo_snapshot,
    )
    converted = [
        MilestoneRequirement(
            category_key=req.category_key,
            category_label=_infer_label(req.category_key, payload.category_label),
            minimum_rating=req.minimum_rating,
            rationale=req.rationale,
            current_rating=payload.elo_snapshot.get(req.category_key, 0),
            progress_percent=_progress(payload.elo_snapshot.get(req.category_key, 0), req.minimum_rating),
        )
        for req in requirements
    ]

    return RequirementAdvisorResult(
        requirements=converted,
        version=payload_obj.version or "v1",
        warnings=list(payload_obj.warnings or []),
        latency_ms=latency_ms,
    )


def _merge_with_snapshot(
    generated: Iterable[RequirementAdvisorRequirementPayload],
    fallback: Iterable[RequirementAdvisorRequirementPayload],
    snapshot: Dict[str, int],
) -> List[RequirementAdvisorRequirementPayload]:
    merged: Dict[str, RequirementAdvisorRequirementPayload] = {}
    for entry in fallback:
        merged[entry.category_key] = entry
    for entry in generated:
        merged[entry.category_key] = entry
    results: List[RequirementAdvisorRequirementPayload] = []
    for key, entry in merged.items():
        minimum = max(int(entry.minimum_rating or 0), 1100)
        rationale = entry.rationale
        current = snapshot.get(key, 0)
        if rationale and current >= minimum:
            rationale = rationale.strip()
        results.append(
            RequirementAdvisorRequirementPayload(
                category_key=key,
                minimum_rating=minimum,
                rationale=rationale,
            )
        )
    return results


def _progress(current: int, minimum: int) -> float:
    if minimum <= 0:
        return 1.0
    return max(0.0, min(float(current) / float(minimum), 1.0))


def _infer_label(category_key: str, fallback_label: str) -> str:
    if fallback_label:
        return fallback_label
    return category_key


__all__ = [
    "RequirementAdvisorError",
    "RequirementAdvisorRequestPayload",
    "RequirementAdvisorResult",
    "advise_requirements",
    "resolve_mode",
    "should_advise",
]
