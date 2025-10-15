"""Goal Parser agent that maps learner goals to foundational tracks (Phase 16)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence, cast

from agents import Agent, ModelSettings, RunConfig, Runner
from openai.types.shared.reasoning import Reasoning
from openai.types.shared.reasoning_effort import ReasoningEffort
from pydantic import BaseModel, Field, ValidationError

from .arcadia_agent import ArcadiaAgentContext
from .config import Settings, get_settings
from .learner_profile import (
    FoundationModuleReference,
    FoundationTrack,
    GoalParserInference,
    profile_store,
)

logger = logging.getLogger(__name__)


GOAL_PARSER_INSTRUCTIONS = (
    "You are the Arcadia Coach Goal Parser. Analyse the learner's stated goal, use case, and strengths to infer the"
    " complete stack of prerequisite technologies, frameworks, and tooling they must master. Chunk the stack into"
    " foundation tracks that can be sequenced over multiple months. Each track should include suggested modules from"
    " Arcadia's library when available, or describe the gap if no matching template exists. Output only JSON following"
    " the provided schema with keys: summary, target_outcomes, tracks, missing_templates."
)


DEFAULT_TRACK_SUGGESTED_WEEKS = 6
DEFAULT_MODULE_SUGGESTED_WEEKS = 3
LONG_TRACK_WEIGHT_THRESHOLD = 1.3
LONG_TRACK_BONUS_WEEKS = 2


class GoalParserModulePayload(BaseModel):
    module_id: str
    category_key: str
    priority: str = Field(default="core")
    suggested_weeks: Optional[float] = Field(default=None, ge=0.1)
    notes: Optional[str] = None


class GoalParserTrackPayload(BaseModel):
    track_id: str
    label: str
    priority: str = Field(default="now")
    confidence: str = Field(default="medium")
    weight: float = Field(default=1.0, ge=0.0)
    technologies: List[str] = Field(default_factory=list)
    focus_areas: List[str] = Field(default_factory=list)
    prerequisites: List[str] = Field(default_factory=list)
    recommended_modules: List[GoalParserModulePayload] = Field(default_factory=list)
    suggested_weeks: Optional[int] = Field(default=None, ge=1)
    notes: Optional[str] = None


class GoalParserPayload(BaseModel):
    summary: Optional[str] = None
    target_outcomes: List[str] = Field(default_factory=list)
    tracks: List[GoalParserTrackPayload] = Field(default_factory=list)
    missing_templates: List[str] = Field(default_factory=list)


_goal_parser_cache: Dict[str, Agent[ArcadiaAgentContext]] = {}


def _goal_parser_effort(value: str) -> ReasoningEffort:
    allowed = {"minimal", "low", "medium", "high"}
    effort = value if value in allowed else "medium"
    return cast(ReasoningEffort, effort)


def _build_goal_parser_agent(model: str) -> Agent[ArcadiaAgentContext]:
    return Agent[ArcadiaAgentContext](
        name="Arcadia Goal Parser",
        instructions=GOAL_PARSER_INSTRUCTIONS,
        model=model,
        tools=[],
        model_settings=ModelSettings(store=False),
    )


def get_goal_parser_agent(settings: Settings) -> Agent[ArcadiaAgentContext]:
    model = settings.arcadia_agent_model or "gpt-5"
    if model not in _goal_parser_cache:
        _goal_parser_cache[model] = _build_goal_parser_agent(model)
    return _goal_parser_cache[model]


def _fallback_tracks(goal: str) -> List[FoundationTrack]:
    """Heuristic fallback when the agent response is unavailable."""
    normalized = goal.lower()
    tracks: List[FoundationTrack] = []
    tracks.append(
        FoundationTrack(
            track_id="foundations-programming",
            label="Programming Foundations",
            priority="now",
            confidence="medium",
            weight=1.0,
            technologies=["Python"],
            focus_areas=["syntax", "testing"],
            prerequisites=["Programming basics"],
            recommended_modules=[
                FoundationModuleReference(module_id="foundation-python-syntax", category_key="python-foundations"),
                FoundationModuleReference(module_id="foundation-python-testing", category_key="python-foundations", priority="reinforcement"),
            ],
            suggested_weeks=4,
            notes="Ensure daily Python practice while ramping up.",
        )
    )
    if any(keyword in normalized for keyword in ("data", "analysis", "analytics", "machine learning", "ml", "model")):
        tracks.append(
            FoundationTrack(
                track_id="foundations-data",
                label="Data & ML Foundations",
                priority="now",
                confidence="medium",
                weight=0.9,
                technologies=["NumPy", "pandas"],
                focus_areas=["data-manipulation", "eda"],
                prerequisites=["Python Foundations"],
                recommended_modules=[
                    FoundationModuleReference(module_id="foundation-numpy-basics", category_key="data-manipulation"),
                    FoundationModuleReference(module_id="foundation-pandas-proficiency", category_key="data-manipulation"),
                ],
                suggested_weeks=6,
                notes="Layer data tooling fundamentals to support modelling.",
            )
        )
    if any(keyword in normalized for keyword in ("backend", "api", "service", "platform", "architecture")):
        tracks.append(
            FoundationTrack(
                track_id="foundations-architecture",
                label="Architecture & Delivery",
                priority="up_next",
                confidence="medium",
                weight=0.75,
                technologies=["FastAPI", "system design"],
                focus_areas=["architecture", "observability"],
                prerequisites=["Programming foundations"],
                recommended_modules=[
                    FoundationModuleReference(module_id="foundation-service-design", category_key="backend-foundations"),
                ],
                suggested_weeks=5,
                notes="Ground service architecture practices for backend execution.",
            )
        )
    return tracks


def _coerce_goal_parser_payload(payload: Any) -> GoalParserPayload:
    if isinstance(payload, GoalParserPayload):
        return payload
    if isinstance(payload, dict):
        return GoalParserPayload.model_validate(payload)
    if isinstance(payload, BaseModel):
        return GoalParserPayload.model_validate(payload.model_dump())
    if isinstance(payload, str):
        data = json.loads(payload)
        return GoalParserPayload.model_validate(data)
    raise TypeError(f"Unsupported goal parser payload type: {type(payload).__name__}")


def _convert_track(entry: GoalParserTrackPayload) -> FoundationTrack:
    modules = [_sanitize_module(module) for module in entry.recommended_modules]
    priority = entry.priority if entry.priority in {"now", "up_next", "later"} else "now"
    confidence = entry.confidence if entry.confidence in {"low", "medium", "high"} else "medium"
    weight = entry.weight if entry.weight >= 0 else 1.0
    track = FoundationTrack(
        track_id=entry.track_id,
        label=entry.label,
        priority=priority,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        weight=weight,
        technologies=[tech.strip() for tech in entry.technologies if tech.strip()],
        focus_areas=[focus.strip() for focus in entry.focus_areas if focus.strip()],
        prerequisites=[item.strip() for item in entry.prerequisites if item.strip()],
        recommended_modules=modules,
        suggested_weeks=entry.suggested_weeks,
        notes=entry.notes,
    )
    return _sanitize_track(track)


async def parse_goal(
    settings: Settings,
    username: str,
    goal: str,
    use_case: str,
    strengths: str,
    *,
    previous_tracks: Optional[Iterable[FoundationTrack]] = None,
) -> GoalParserInference:
    """Run the Goal Parser agent and persist the resulting inference."""
    agent = get_goal_parser_agent(settings)
    context_payload: Dict[str, Any] = {
        "username": username,
        "goal": goal,
        "use_case": use_case,
        "strengths": strengths,
    }
    if previous_tracks:
        context_payload["previous_tracks"] = [
            track.model_dump(mode="json") for track in previous_tracks
        ]

    schema_description = (
        "Respond strictly as JSON with keys: summary (string), target_outcomes (array of strings), "
        "tracks (array), missing_templates (array of strings). "
        "Each track must include track_id (slug), label, priority ('now' | 'up_next' | 'later'), "
        "confidence ('low' | 'medium' | 'high'), weight (float >= 0), technologies (string array), "
        "focus_areas (string array), prerequisites (string array), recommended_modules (array of {module_id, category_key, priority, suggested_weeks, notes}), "
        "and suggested_weeks (int >=1)."
    )

    message = (
        "Analyse the learner context and infer the foundational tracks needed to reach the long-term goal. "
        "Decompose adjacent technologies and call out any gaps where Arcadia lacks templates. "
        "Keep tracks focused (2-6 technologies each) and specify priority order for multi-month planning.\n\n"
        f"{schema_description}\n\n"
        f"LEARNER CONTEXT:\n{json.dumps(context_payload, ensure_ascii=False, indent=2)}"
    )

    try:
        result = await Runner.run(
            agent,
            message,
            context=None,
            run_config=RunConfig(
                model_settings=ModelSettings(
                    reasoning=Reasoning(
                        effort=_goal_parser_effort(settings.arcadia_agent_reasoning),
                        summary="auto",
                    ),
                )
            ),
        )
        payload = _coerce_goal_parser_payload(result.final_output)
        tracks = [_convert_track(entry) for entry in payload.tracks]
        if tracks:
            tracks = _merge_duplicate_tracks(tracks)
        else:
            tracks = _fallback_tracks(goal)
        inference = GoalParserInference(
            summary=payload.summary,
            target_outcomes=[item.strip() for item in payload.target_outcomes if item.strip()],
            tracks=[_sanitize_track(track) for track in tracks],
            missing_templates=[item.strip() for item in payload.missing_templates if item.strip()],
        )
        profile_store.set_goal_inference(username, inference)
        return inference
    except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
        logger.warning("Goal parser returned invalid payload for %s: %s", username, exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Goal parser execution failed for %s", username, exc_info=exc)

    fallback_tracks = _merge_duplicate_tracks(_fallback_tracks(goal))
    inference = GoalParserInference(
        summary="Fallback inference based on heuristic signals.",
        target_outcomes=[goal] if goal else [],
        tracks=fallback_tracks,
        missing_templates=["Custom module authoring required"],
    )
    profile_store.set_goal_inference(username, inference)
    return inference


async def ensure_goal_inference(
    settings: Optional[Settings],
    username: str,
    goal: str,
    use_case: str,
    strengths: str,
) -> GoalParserInference:
    """Fetch or compute the latest goal parser inference for the learner."""
    resolved_settings = settings or get_settings()
    profile = profile_store.get(username)
    if profile and profile.goal_inference and profile.goal_inference.tracks:
        sanitized = profile.goal_inference.model_copy(
            update={"tracks": [_sanitize_track(track) for track in profile.goal_inference.tracks]}
        )
        if sanitized != profile.goal_inference:
            profile_store.set_goal_inference(username, sanitized)
        return sanitized
    previous_tracks = profile.foundation_tracks if profile else None
    return await parse_goal(
        resolved_settings,
        username=username,
        goal=goal,
        use_case=use_case,
        strengths=strengths,
        previous_tracks=previous_tracks,
    )


__all__ = ["ensure_goal_inference", "parse_goal"]


def _sanitize_module(module: GoalParserModulePayload) -> FoundationModuleReference:
    sanitized_weeks = _coerce_weeks(module.suggested_weeks, DEFAULT_MODULE_SUGGESTED_WEEKS)
    priority = module.priority if module.priority in {"core", "reinforcement", "extension"} else "core"
    return FoundationModuleReference(
        module_id=module.module_id,
        category_key=module.category_key,
        priority=priority,  # type: ignore[arg-type]
        suggested_weeks=sanitized_weeks,
        notes=module.notes,
    )


def _sanitize_track(track: FoundationTrack) -> FoundationTrack:
    sanitized_modules = [
        module.model_copy(
            update={
                "suggested_weeks": _coerce_weeks(module.suggested_weeks, DEFAULT_MODULE_SUGGESTED_WEEKS)
            }
        )
        for module in track.recommended_modules
    ]
    fallback_weeks = _track_weeks_fallback(track, sanitized_modules)
    sanitized_weeks = _coerce_weeks(track.suggested_weeks, fallback_weeks)
    return track.model_copy(
        update={
            "recommended_modules": sanitized_modules,
            "suggested_weeks": sanitized_weeks,
        }
    )


def _coerce_weeks(value: Optional[int], fallback: int) -> int:
    if isinstance(value, int) and value >= 1:
        return value
    return fallback


def _track_weeks_fallback(track: FoundationTrack, modules: Sequence[FoundationModuleReference]) -> int:
    module_total = sum(
        module.suggested_weeks if isinstance(module.suggested_weeks, int) and module.suggested_weeks >= 1 else DEFAULT_MODULE_SUGGESTED_WEEKS
        for module in modules
    )
    if module_total <= 0:
        module_total = DEFAULT_TRACK_SUGGESTED_WEEKS
    bonus = LONG_TRACK_BONUS_WEEKS if track.weight and track.weight >= LONG_TRACK_WEIGHT_THRESHOLD else 0
    baseline = DEFAULT_TRACK_SUGGESTED_WEEKS + bonus
    return max(baseline, module_total)


def _merge_duplicate_tracks(tracks: Sequence[FoundationTrack]) -> List[FoundationTrack]:
    priority_order = {"now": 3, "up_next": 2, "later": 1}
    confidence_order = {"low": 1, "medium": 2, "high": 3}

    merged: Dict[str, FoundationTrack] = {}
    order: List[str] = []

    for track in tracks:
        key_source = track.track_id or track.label
        if not key_source:
            key_source = f"track-{len(order) + 1}"
        normalized_key = key_source.strip().lower()
        if normalized_key not in merged:
            merged[normalized_key] = track
            order.append(normalized_key)
            continue

        existing = merged[normalized_key]
        priority = existing.priority
        if priority_order.get(track.priority, 0) > priority_order.get(existing.priority, 0):
            priority = track.priority
        confidence = existing.confidence
        if confidence_order.get(track.confidence, 0) > confidence_order.get(existing.confidence, 0):
            confidence = track.confidence
        weight = max(existing.weight, track.weight)
        technologies = _merge_list(existing.technologies, track.technologies)
        focus_areas = _merge_list(existing.focus_areas, track.focus_areas)
        prerequisites = _merge_list(existing.prerequisites, track.prerequisites)
        suggested_weeks = max(existing.suggested_weeks or 0, track.suggested_weeks or 0) or existing.suggested_weeks or track.suggested_weeks
        if existing.notes and track.notes and existing.notes != track.notes:
            notes = f"{existing.notes}\n{track.notes}"
        else:
            notes = existing.notes or track.notes
        modules = _merge_modules(existing.recommended_modules, track.recommended_modules)
        merged[normalized_key] = FoundationTrack(
            track_id=existing.track_id or track.track_id or normalized_key,
            label=existing.label or track.label,
            priority=priority,  # type: ignore[arg-type]
            confidence=confidence,  # type: ignore[arg-type]
            weight=weight,
            technologies=technologies,
            focus_areas=focus_areas,
            prerequisites=prerequisites,
            recommended_modules=modules,
            suggested_weeks=suggested_weeks,
            notes=notes,
        )

    return [_sanitize_track(merged[key]) for key in order]


def _merge_list(existing: Sequence[str], incoming: Sequence[str]) -> List[str]:
    seen: Dict[str, None] = {}
    for value in list(existing) + list(incoming):
        trimmed = value.strip()
        if trimmed and trimmed not in seen:
            seen[trimmed] = None
    return list(seen.keys())


def _merge_modules(
    existing: Sequence[FoundationModuleReference],
    incoming: Sequence[FoundationModuleReference],
) -> List[FoundationModuleReference]:
    modules: Dict[tuple[str, str], FoundationModuleReference] = {}
    for module in list(existing) + list(incoming):
        key = (module.module_id, module.category_key)
        if key not in modules:
            modules[key] = module
            continue
        current = modules[key]
        priority = _merge_module_priority(current.priority, module.priority)
        suggested_weeks = max(current.suggested_weeks or 0, module.suggested_weeks or 0) or current.suggested_weeks or module.suggested_weeks
        notes = current.notes or module.notes
        modules[key] = FoundationModuleReference(
            module_id=module.module_id,
            category_key=module.category_key,
            priority=priority,  # type: ignore[arg-type]
            suggested_weeks=suggested_weeks,
            notes=notes,
        )
    return [modules[key] for key in modules]


def _merge_module_priority(current: str, incoming: str) -> str:
    priority_rank = {"core": 3, "reinforcement": 2, "extension": 1}
    return current if priority_rank.get(current, 0) >= priority_rank.get(incoming, 0) else incoming
