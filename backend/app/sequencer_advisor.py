"""Sequencer Advisor agent integration (Phase 35)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from time import perf_counter
from typing import List, Optional

from agents import Agent, ModelSettings, Runner
from pydantic import BaseModel, Field, ValidationError

from .arcadia_agent import ArcadiaAgentContext
from .config import Settings, get_settings

logger = logging.getLogger(__name__)

SequencerAdvisorMode = str


class SequencerAdvisorError(RuntimeError):
    """Raised when the sequencer advisor fails to provide usable guidance."""


class SequencerAdvisorCategoryPayload(BaseModel):
    category_key: str
    category_label: str
    rating: int = Field(default=0)
    weight: float = Field(default=0.0)
    requirement_deficit: int = Field(default=0)
    track_weight: float = Field(default=0.0)
    average_score: Optional[float] = None
    rating_delta: Optional[int] = None
    deferral_count: int = Field(default=0)
    days_since_completion: Optional[int] = Field(default=None, ge=0)


class SequencerAdvisorRequirementPayload(BaseModel):
    milestone_item_id: str
    milestone_title: str
    category_key: str
    category_label: str
    target_rating: int = Field(default=0)
    current_rating: int = Field(default=0)
    deficit: int = Field(default=0)
    requirement_rationale: Optional[str] = None


class SequencerAdvisorModulePayload(BaseModel):
    module_id: str
    category_key: str
    priority_score: float
    estimated_minutes: int = Field(default=45)


class SequencerAdvisorRequestPayload(BaseModel):
    username: str
    categories: List[SequencerAdvisorCategoryPayload] = Field(default_factory=list)
    requirements: List[SequencerAdvisorRequirementPayload] = Field(default_factory=list)
    candidate_modules: List[SequencerAdvisorModulePayload] = Field(default_factory=list)
    schedule_adjustment_count: int = Field(default=0, ge=0)
    sessions_per_week: int = Field(default=4, ge=1)
    goal_summary: Optional[str] = None


class SequencerAdvisorResponsePayload(BaseModel):
    version: str = Field(default="v1")
    recommended_order: List[str] = Field(default_factory=list)
    slice_span_days: Optional[int] = Field(default=None, ge=1)
    notes: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


@dataclass(frozen=True)
class SequencerAdvisorResult:
    recommended_modules: List[str]
    slice_span_days: Optional[int]
    notes: Optional[str]
    version: str
    warnings: List[str]
    latency_ms: float


def resolve_mode(settings: Settings) -> SequencerAdvisorMode:
    value = getattr(settings, "arcadia_sequencer_advisor_mode", "fallback")
    if value not in {"off", "fallback", "primary"}:
        return "fallback"
    return value


def should_advise(settings: Settings) -> bool:
    return resolve_mode(settings) != "off"


def _advisor_model(settings: Settings) -> str:
    explicit = getattr(settings, "arcadia_sequencer_advisor_model", None)
    if explicit:
        return explicit
    return settings.arcadia_agent_model or "gpt-5"


_ADVISOR_CACHE: dict[str, Agent[ArcadiaAgentContext]] = {}


def _advisor_agent(model: str) -> Agent[ArcadiaAgentContext]:
    if model not in _ADVISOR_CACHE:
        instructions = (
            "You are Arcadia Coach's Sequencer Advisor. Given curriculum context, recommend the ordering of modules "
            "that will unlock upcoming milestones. Always respond with JSON that matches the provided schema. "
            "Focus on modules that close requirement deficits first, while respecting prerequisite logic."
        )
        _ADVISOR_CACHE[model] = Agent[ArcadiaAgentContext](
            name="Arcadia Sequencer Advisor",
            instructions=instructions,
            model=model,
            tools=[],
            model_settings=ModelSettings(store=False),
        )
    return _ADVISOR_CACHE[model]


def advise_sequence(
    payload: SequencerAdvisorRequestPayload,
    *,
    settings: Optional[Settings] = None,
) -> SequencerAdvisorResult:
    resolved_settings = settings or get_settings()
    mode = resolve_mode(resolved_settings)
    if mode == "off":
        raise SequencerAdvisorError("Sequencer advisor is disabled.")

    agent = _advisor_agent(_advisor_model(resolved_settings))
    schema = SequencerAdvisorResponsePayload.model_json_schema()
    message = payload.model_dump(mode="json")
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
        raise SequencerAdvisorError(f"Sequencer advisor call failed: {exc}") from exc

    latency_ms = round((perf_counter() - started) * 1000.0, 2)
    try:
        payload_obj = SequencerAdvisorResponsePayload.model_validate_json(result.final_output)
    except (ValidationError, json.JSONDecodeError) as exc:
        raise SequencerAdvisorError(f"Sequencer advisor returned invalid payload: {exc}") from exc

    return SequencerAdvisorResult(
        recommended_modules=list(payload_obj.recommended_order or []),
        slice_span_days=payload_obj.slice_span_days,
        notes=payload_obj.notes,
        version=payload_obj.version or "v1",
        warnings=list(payload_obj.warnings or []),
        latency_ms=latency_ms,
    )


__all__ = [
    "SequencerAdvisorCategoryPayload",
    "SequencerAdvisorRequirementPayload",
    "SequencerAdvisorModulePayload",
    "SequencerAdvisorRequestPayload",
    "SequencerAdvisorResponsePayload",
    "SequencerAdvisorResult",
    "SequencerAdvisorError",
    "advise_sequence",
    "resolve_mode",
    "should_advise",
]
