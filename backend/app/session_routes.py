"""REST endpoints used by the macOS client for lesson, quiz, milestone, and chat flows."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Dict, List, Literal, Optional, Sequence, Type, TypeVar, cast
from uuid import uuid4

from agents import ModelSettings, RunConfig, Runner
from chatkit.types import ThreadMetadata
from fastapi import APIRouter, Depends, HTTPException, Response, status
from openai import AuthenticationError, OpenAIError
from openai.types.shared.reasoning import Reasoning
from openai.types.shared.reasoning_effort import ReasoningEffort
from pydantic import BaseModel, Field, ValidationError, ConfigDict

from .agent_models import (
    CurriculumSchedulePayload,
    EndLearn,
    EndMilestone,
    EndQuiz,
    ScheduleLaunchContentPayload,
    ScheduleLaunchResponsePayload,
    WidgetEnvelope,
)
from .arcadia_agent import ArcadiaAgentContext, get_arcadia_agent
from .config import Settings, get_settings
from .learner_profile import LearnerProfile, SequencedWorkItem, profile_store
from .memory_store import MemoryStore
from .prompt_utils import apply_preferences_overlay, schedule_summary_from_profile
from .telemetry import emit_event
from .tools import _schedule_payload


router = APIRouter(prefix="/api/session", tags=["session"])

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)

MODEL_FOR_LEVEL: Dict[str, str] = {
    "minimal": "gpt-5-nano",
    "low": "gpt-5-mini",
    "medium": "gpt-5",
    "high": "gpt-5-codex",
}

ATTACHMENT_POLICY: Dict[str, str] = {
    "gpt-5": "any",
    "gpt-5-mini": "any",
    "gpt-5-nano": "any",
    "gpt-5-codex": "images",
}


@dataclass
class SessionState:
    store: MemoryStore
    thread: ThreadMetadata
    attachments: list[dict[str, Any]] = field(default_factory=list)


_session_states: Dict[str, SessionState] = {}


def _effort(reasoning: str) -> str:
    options = {"minimal", "low", "medium", "high"}
    return reasoning if reasoning in options else "medium"


def _session_state(session_id: Optional[str]) -> SessionState:
    key = session_id or "default"
    if key not in _session_states:
        thread = ThreadMetadata.model_construct(
            id=f"session-{key}-{uuid4().hex[:8]}",
        )
        _session_states[key] = SessionState(store=MemoryStore(), thread=thread)
    return _session_states[key]


def _reset_state(session_id: Optional[str]) -> None:
    if session_id:
        _session_states.pop(session_id, None)
    else:
        _session_states.clear()


def _schedule_locked_reason(
    item: SequencedWorkItem,
    schedule_items: Sequence[SequencedWorkItem],
) -> Optional[str]:
    if item.kind != "milestone" or item.launch_status == "completed":
        return None
    incomplete_prereqs = [
        other
        for other in schedule_items
        if other.item_id != item.item_id
        and other.kind != "milestone"
        and other.recommended_day_offset <= item.recommended_day_offset
        and other.launch_status != "completed"
    ]
    if incomplete_prereqs:
        return "Complete earlier lessons and quizzes before unlocking this milestone."
    return None


def _build_schedule_launch_message(item: SequencedWorkItem, profile: LearnerProfile) -> str:
    lines: List[str] = [
        f"Deliver the scheduled {item.kind} titled '{item.title}'.",
        f"Recommended duration: approximately {item.recommended_minutes} minutes.",
    ]
    if item.summary:
        lines.append(f"Summary: {item.summary}")
    if item.objectives:
        objective_lines = "\n".join(f"- {objective}" for objective in item.objectives)
        lines.append(f"Objectives:\n{objective_lines}")
    if item.expected_outcome:
        lines.append(f"Expected outcome: {item.expected_outcome}")
    if item.focus_reason:
        lines.append(f"Focus reason: {item.focus_reason}")
    if profile.goal:
        lines.append(f"Learner goal: {profile.goal}")
    if profile.strengths:
        lines.append(f"Learner strengths: {profile.strengths}")
    if profile.use_case:
        lines.append(f"Learner use case: {profile.use_case}")
    return "\n\n".join(lines)


async def _run_structured(
    settings: Settings,
    session_id: Optional[str],
    message: str,
    expecting: Type[T],
    metadata: Dict[str, Any] | None = None,
    web_enabled_override: bool | None = None,
    reasoning_level_override: str | None = None,
    model_override: str | None = None,
    attachments: Sequence[Dict[str, Any]] | None = None,
    augment_with_preferences: bool = False,
) -> T:
    state = _session_state(session_id)
    web_enabled = (
        web_enabled_override
        if web_enabled_override is not None
        else settings.arcadia_agent_enable_web
    )
    reasoning_level = _effort(
        reasoning_level_override or settings.arcadia_agent_reasoning
    )
    selected_model = model_override or settings.arcadia_agent_model
    if model_override:
        model_choice = model_override
    else:
        model_choice = MODEL_FOR_LEVEL.get(reasoning_level, selected_model)
    agent = get_arcadia_agent(model_choice, web_enabled)
    logger.debug(
        "Resolved chat session settings (model=%s, web_enabled=%s, reasoning=%s)",
        model_choice,
        web_enabled,
        reasoning_level,
    )
    metadata_payload: Dict[str, Any] = dict(metadata or {})
    if session_id:
        metadata_payload.setdefault("session_id", session_id)

    profile_snapshot: Dict[str, Any] | None = None
    schedule_summary: str | None = None
    username = metadata_payload.get("username")
    timezone_hint: str | None = metadata_payload.get("timezone")
    if isinstance(username, str) and username.strip():
        profile = profile_store.apply_metadata(username, metadata_payload)
        profile_snapshot = profile.model_dump(mode="json")
        if not timezone_hint and isinstance(profile.timezone, str) and profile.timezone.strip():
            timezone_hint = profile.timezone.strip()
        schedule_summary = schedule_summary_from_profile(profile_snapshot)
        if schedule_summary:
            metadata_payload.setdefault("schedule_summary", schedule_summary)
    if not timezone_hint:
        tz_env = settings.arcadia_agent_timezone
        if tz_env:
            timezone_hint = tz_env
    if timezone_hint:
        metadata_payload.setdefault("timezone", timezone_hint)

    attachments_payload: list[Dict[str, Any]] = []
    if attachments:
        new_items = [
            {
                "file_id": item.get("file_id"),
                "name": item.get("name"),
                "mime_type": item.get("mime_type"),
                "size": item.get("size"),
                "preview": item.get("preview"),
                "openai_file_id": item.get("openai_file_id"),
            }
            for item in attachments
        ]
        merged = _merge_attachments(state.attachments, new_items)
        state.attachments = merged
        attachments_payload = merged
    else:
        attachments_payload = list(state.attachments)

    policy = ATTACHMENT_POLICY.get(model_choice, "any")
    if policy == "none":
        attachments_payload = []
        state.attachments = []
    elif policy == "images":
        attachments_payload = [
            item
            for item in attachments_payload
            if isinstance(item.get("mime_type"), str) and item["mime_type"].lower().startswith("image/")
        ]
        state.attachments = [dict(item) for item in attachments_payload]

    if attachments_payload:
        metadata_payload.setdefault(
            "attachments",
            [
                {k: v for k, v in attachment.items() if k != "file_id"}
                for attachment in attachments_payload
            ],
        )

    if augment_with_preferences:
        message = apply_preferences_overlay(
            message,
            attachments_payload,
            web_enabled=web_enabled,
            reasoning_level=reasoning_level,
            model=model_choice,
            schedule_summary=schedule_summary,
        )
    elif schedule_summary:
        message = f"{message.rstrip()}\n\n{schedule_summary}"
    metadata_payload.setdefault("web_enabled", web_enabled)
    metadata_payload.setdefault("reasoning_level", reasoning_level)
    metadata_payload.setdefault("model", model_choice)

    context = ArcadiaAgentContext.model_construct(
        thread=state.thread,
        store=state.store,
        request_context={
            "metadata": metadata_payload,
            "profile": profile_snapshot,
        },
        sanitized_input=None,
        web_enabled=web_enabled,
        reasoning_level=reasoning_level,
        attachments=attachments_payload,
    )
    try:
        result = await Runner.run(
            agent,
            message,
            context=context,
            run_config=RunConfig(
                model_settings=ModelSettings(
                    reasoning=Reasoning(
                        effort=cast(ReasoningEffort, reasoning_level),
                        summary="auto",
                    ),
                )
            ),
        )
    except AuthenticationError as exc:
        logger.error(
            "OpenAI authentication error while running agent: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Arcadia backend is not authorized with OpenAI. Update OPENAI_API_KEY and try again.",
        ) from exc
    except OpenAIError as exc:
        logger.error("OpenAI error while running agent: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Upstream OpenAI request failed: {exc}",
        ) from exc
    logger.debug(
        "Agent run complete (session_id=%s, message=%s, output_type=%s)",
        session_id or "default",
        message,
        type(result.final_output).__name__,
    )
    logger.debug("Agent final output payload: %s", result.final_output)
    return _coerce_output(result.final_output, expecting)


def _coerce_output(payload: Any, expecting: Type[T]) -> T:
    if isinstance(payload, expecting):
        return payload
    if isinstance(payload, BaseModel):
        if isinstance(payload, WidgetEnvelope) and expecting in (EndLearn, EndQuiz, EndMilestone):
            data = _fix_widget_props(payload.model_dump())
            if expecting == EndLearn:
                data["intent"] = "lesson"
            elif expecting == EndQuiz:
                data["intent"] = "quiz"
                data.setdefault("elo", {})
                data.setdefault("last_quiz", None)
            elif expecting == EndMilestone:
                data["intent"] = "milestone"
            return expecting.model_validate(data)
        return expecting.model_validate(payload.model_dump())
    if isinstance(payload, dict):
        payload = _fix_widget_props(payload)
        if expecting in (EndLearn, EndQuiz, EndMilestone) and "intent" not in payload:
            if expecting == EndLearn:
                payload["intent"] = "lesson"
            elif expecting == EndQuiz:
                payload["intent"] = "quiz"
                payload.setdefault("elo", {})
                payload.setdefault("last_quiz", None)
            elif expecting == EndMilestone:
                payload["intent"] = "milestone"
        return expecting.model_validate(payload)
    if isinstance(payload, list):
        return expecting.model_validate({"widgets": payload})
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            logger.warning(
                "Non-JSON payload received for %s; wrapping as display string: %s",
                expecting.__name__,
                exc,
            )
            if expecting == WidgetEnvelope:
                return cast(T, WidgetEnvelope(display=payload, widgets=[], citations=None))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Agent returned malformed payload for {expecting.__name__}",
            ) from exc
        data = _fix_widget_props(data) if isinstance(data, dict) else data
        if isinstance(data, dict) and expecting in (EndLearn, EndQuiz, EndMilestone) and "intent" not in data:
            if expecting == EndLearn:
                data["intent"] = "lesson"
            elif expecting == EndQuiz:
                data["intent"] = "quiz"
                data.setdefault("elo", {})
                data.setdefault("last_quiz", None)
            elif expecting == EndMilestone:
                data["intent"] = "milestone"
        return expecting.model_validate(data)
    try:
        return expecting.model_validate(payload)  # type: ignore[arg-type]
    except ValidationError as exc:  # pragma: no cover - guardrail
        logger.error(
            "Failed to decode payload type %s into %s: %s",
            type(payload).__name__,
            expecting.__name__,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Agent returned unsupported payload for {expecting.__name__}",
        ) from exc


def _fix_widget_props(data: dict) -> dict:
    """Normalize widget payloads coming back from MCP tools."""
    widgets = data.get("widgets")
    if not isinstance(widgets, list):
        return data
    normalized: list[dict[str, Any]] = []
    for widget in widgets:
        if not isinstance(widget, dict):
            normalized.append(widget)
            continue
        if "props" not in widget or not isinstance(widget.get("props"), dict):
            props: dict[str, Any] = {}
            for key in ("propsCard", "propsList", "propsStat", "propsMiniChatbot", "propsArcadiaChatbot"):
                if isinstance(widget.get(key), dict):
                    props.update(widget[key])  # type: ignore[arg-type]
            if props:
                widget["props"] = props
        normalized.append(widget)
    data["widgets"] = normalized
    return data


class TopicRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ScheduleLaunchRequest(BaseModel):
    username: str = Field(..., min_length=1)
    item_id: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    force: bool = False


class ScheduleCompleteRequest(BaseModel):
    username: str = Field(..., min_length=1)
    item_id: str = Field(..., min_length=1)
    session_id: Optional[str] = None


class ResetRequest(BaseModel):
    session_id: Optional[str] = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class ChatAttachment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    file_id: str = Field(..., alias="file_id", min_length=1)
    name: str = Field(..., min_length=1)
    mime_type: str = Field(..., alias="mime_type", min_length=1)
    size: int = Field(..., ge=0)
    preview: str | None = None
    openai_file_id: str | None = Field(default=None, alias="openai_file_id")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    history: List[ChatMessage] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    web_enabled: Optional[bool] = None
    reasoning_level: Optional[str] = Field(default=None)
    model: Optional[str] = None
    attachments: List[ChatAttachment] = Field(default_factory=list)


def _compose_chat_prompt(history: List[ChatMessage], latest: str) -> str:
    """Flatten the chat history into a conversational prompt."""
    parts: List[str] = []
    for message in history:
        prefix = "User" if message.role == "user" else "Assistant"
        parts.append(f"{prefix}: {message.text}")
    parts.append(f"User: {latest}")
    parts.append("Assistant:")
    return "\n".join(parts)


def _attachment_key(data: Dict[str, Any]) -> str:
    candidate = data.get("file_id") or data.get("openai_file_id") or data.get("name") or data.get("id")
    if isinstance(candidate, str) and candidate:
        return candidate
    return uuid4().hex


def _merge_attachments(
    existing: Sequence[Dict[str, Any]],
    new: Sequence[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    merged: list[Dict[str, Any]] = [dict(item) for item in existing]
    index: Dict[str, Dict[str, Any]] = {
        _attachment_key(item): item for item in merged
    }
    for item in new:
        cleaned = {k: v for k, v in item.items() if v is not None}
        key = _attachment_key(cleaned)
        if key in index:
            index[key].update(cleaned)
        else:
            merged.append(cleaned)
            index[key] = cleaned
    return merged


@router.post(
    "/schedule/launch",
    response_model=ScheduleLaunchResponsePayload,
    status_code=status.HTTP_200_OK,
)
async def launch_schedule_item(
    payload: ScheduleLaunchRequest,
    settings: Settings = Depends(get_settings),
) -> ScheduleLaunchResponsePayload:
    started_at = perf_counter()
    username = payload.username.strip()
    item_id = payload.item_id.strip()
    if not username or not item_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Username and schedule item id are required.",
        )
    profile = profile_store.get(username)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learner profile for '{username}' was not found.",
        )
    schedule = profile.curriculum_schedule
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No curriculum schedule configured for '{username}'.",
        )
    item = next((entry for entry in schedule.items if entry.item_id == item_id), None)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule item '{item_id}' was not found.",
        )
    locked_reason = _schedule_locked_reason(item, schedule.items)
    if locked_reason and not payload.force:
        emit_event(
            "schedule_launch_initiated",
            username=username,
            item_id=item_id,
            kind=item.kind,
            status="blocked",
            reason=locked_reason,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "milestone_locked", "message": locked_reason},
        )
    previous_status = item.launch_status
    session_id = payload.session_id or item.active_session_id or f"{username}-{uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    try:
        profile = profile_store.update_schedule_item(
            username,
            item_id,
            status="in_progress",
            last_launched_at=now,
            active_session_id=session_id,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    schedule = profile.curriculum_schedule
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No curriculum schedule configured for '{username}'.",
        )
    item = next((entry for entry in schedule.items if entry.item_id == item_id), item)
    emit_event(
        "schedule_launch_initiated",
        username=username,
        item_id=item_id,
        kind=item.kind,
        status="in_progress",
        previous_status=previous_status,
        session_id=session_id,
    )
    metadata: Dict[str, Any] = {
        "username": username,
        "schedule_item_id": item.item_id,
        "schedule_kind": item.kind,
        "schedule_category": item.category_key,
        "recommended_minutes": str(item.recommended_minutes),
    }
    if profile.goal:
        metadata["goal"] = profile.goal
    if profile.use_case:
        metadata["use_case"] = profile.use_case
    if profile.strengths:
        metadata["strengths"] = profile.strengths
    if profile.timezone:
        metadata["timezone"] = profile.timezone
    message = _build_schedule_launch_message(item, profile)
    expecting_map: Dict[str, Type[BaseModel]] = {
        "lesson": EndLearn,
        "quiz": EndQuiz,
        "milestone": EndMilestone,
    }
    expected_cls = expecting_map.get(item.kind)
    if expected_cls is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported schedule item kind '{item.kind}'.",
        )
    try:
        result = await _run_structured(
            settings,
            session_id,
            message,
            expected_cls,
            metadata=metadata,
            augment_with_preferences=True,
        )
    except (OpenAIError, AuthenticationError, ValidationError) as exc:
        profile_store.update_schedule_item(
            username,
            item_id,
            status=previous_status,
            active_session_id=session_id if previous_status == "in_progress" else None,
            clear_active_session=previous_status != "in_progress",
        )
        emit_event(
            "schedule_launch_completed",
            username=username,
            item_id=item_id,
            kind=item.kind,
            status="failed",
            session_id=session_id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to generate the scheduled content. Try again shortly.",
        ) from exc
    duration_ms = int((perf_counter() - started_at) * 1000)
    refreshed_profile = profile_store.get(username)
    if refreshed_profile is None or refreshed_profile.curriculum_schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No curriculum schedule configured for '{username}'.",
        )
    schedule_payload = _schedule_payload(refreshed_profile.curriculum_schedule)
    if schedule_payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No curriculum schedule configured for '{username}'.",
        )
    item_payload = next((entry for entry in schedule_payload.items if entry.item_id == item_id), None)
    if item_payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule item '{item_id}' was not found.",
        )
    content_kwargs: Dict[str, Any] = {"kind": item.kind, "session_id": session_id}
    if item.kind == "lesson":
        content_kwargs["lesson"] = result
    elif item.kind == "quiz":
        content_kwargs["quiz"] = result
    else:
        content_kwargs["milestone"] = result
    content_payload = ScheduleLaunchContentPayload(**content_kwargs)
    emit_event(
        "schedule_launch_completed",
        username=username,
        item_id=item_id,
        kind=item.kind,
        status="delivered",
        session_id=session_id,
        duration_ms=duration_ms,
    )
    return ScheduleLaunchResponsePayload(
        schedule=schedule_payload,
        item=item_payload,
        content=content_payload,
    )


@router.post(
    "/schedule/complete",
    response_model=CurriculumSchedulePayload,
    status_code=status.HTTP_200_OK,
)
def complete_schedule_item(payload: ScheduleCompleteRequest) -> CurriculumSchedulePayload:
    username = payload.username.strip()
    item_id = payload.item_id.strip()
    if not username or not item_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Username and schedule item id are required.",
        )
    profile = profile_store.get(username)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learner profile for '{username}' was not found.",
        )
    schedule = profile.curriculum_schedule
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No curriculum schedule configured for '{username}'.",
        )
    item = next((entry for entry in schedule.items if entry.item_id == item_id), None)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule item '{item_id}' was not found.",
        )
    previous_launch = item.last_launched_at
    previous_status = item.launch_status
    now = datetime.now(timezone.utc)
    try:
        profile = profile_store.update_schedule_item(
            username,
            item_id,
            status="completed",
            last_completed_at=now,
            clear_active_session=True,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    schedule_payload = _schedule_payload(profile.curriculum_schedule)
    if schedule_payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No curriculum schedule configured for '{username}'.",
        )
    duration_ms: Optional[int] = None
    if previous_launch is not None:
        duration_ms = int((now - previous_launch).total_seconds() * 1000)
    emit_event(
        "schedule_launch_completed",
        username=username,
        item_id=item_id,
        kind=item.kind,
        status="completed",
        session_id=payload.session_id or item.active_session_id,
        duration_ms=duration_ms,
        previous_status=previous_status,
    )
    return schedule_payload


@router.post("/lesson", response_model=EndLearn, status_code=status.HTTP_200_OK)
async def create_lesson(
    payload: TopicRequest,
    settings: Settings = Depends(get_settings),
) -> EndLearn:
    message = f"learn {payload.topic}".strip()
    metadata = dict(payload.metadata)
    if payload.session_id:
        metadata.setdefault("session_id", payload.session_id)
    result = await _run_structured(
        settings,
        payload.session_id,
        message,
        EndLearn,
        metadata=metadata,
    )
    logger.info("Returning EndLearn response: %s", result.model_dump_json())
    return result


@router.post("/quiz", response_model=EndQuiz, status_code=status.HTTP_200_OK)
async def create_quiz(
    payload: TopicRequest,
    settings: Settings = Depends(get_settings),
) -> EndQuiz:
    message = f"quiz {payload.topic}".strip()
    metadata = dict(payload.metadata)
    if payload.session_id:
        metadata.setdefault("session_id", payload.session_id)
    result = await _run_structured(
        settings,
        payload.session_id,
        message,
        EndQuiz,
        metadata=metadata,
    )
    logger.info("Returning EndQuiz response: %s", result.model_dump_json())
    return result


@router.post("/milestone", response_model=EndMilestone, status_code=status.HTTP_200_OK)
async def create_milestone(
    payload: TopicRequest,
    settings: Settings = Depends(get_settings),
) -> EndMilestone:
    message = f"milestone {payload.topic}".strip()
    metadata = dict(payload.metadata)
    if payload.session_id:
        metadata.setdefault("session_id", payload.session_id)
    result = await _run_structured(
        settings,
        payload.session_id,
        message,
        EndMilestone,
        metadata=metadata,
    )
    logger.info("Returning EndMilestone response: %s", result.model_dump_json())
    return result


@router.post("/chat", response_model=WidgetEnvelope, status_code=status.HTTP_200_OK)
async def chat_with_agent(
    payload: ChatRequest,
    settings: Settings = Depends(get_settings),
) -> WidgetEnvelope:
    prompt = _compose_chat_prompt(payload.history, payload.message)
    metadata = dict(payload.metadata)
    if payload.session_id:
        metadata.setdefault("session_id", payload.session_id)
    attachments = [attachment.model_dump(mode="json") for attachment in payload.attachments]
    return await _run_structured(
        settings,
        payload.session_id,
        prompt,
        WidgetEnvelope,
        metadata=metadata,
        web_enabled_override=payload.web_enabled,
        reasoning_level_override=payload.reasoning_level,
        model_override=payload.model,
        attachments=attachments,
        augment_with_preferences=True,
    )


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_session(
    payload: ResetRequest,
) -> Response:
    _reset_state(payload.session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
