"""REST endpoints used by the macOS client for lesson, quiz, milestone, and chat flows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, List, Literal, Optional, Type, TypeVar, cast
from uuid import uuid4

from agents import ModelSettings, RunConfig, Runner
from chatkit.types import ThreadMetadata
from fastapi import APIRouter, Depends, HTTPException, Response, status
import json
import logging
from openai import AuthenticationError, OpenAIError
from openai.types.shared.reasoning import Reasoning
from openai.types.shared.reasoning_effort import ReasoningEffort
from pydantic import BaseModel, Field, ValidationError

from .agent_models import EndLearn, EndMilestone, EndQuiz, WidgetEnvelope
from .arcadia_agent import ArcadiaAgentContext, get_arcadia_agent
from .config import Settings, get_settings
from .learner_profile import profile_store
from .memory_store import MemoryStore


router = APIRouter(prefix="/api/session", tags=["session"])

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    store: MemoryStore
    thread: ThreadMetadata


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


async def _run_structured(
    settings: Settings,
    session_id: Optional[str],
    message: str,
    expecting: Type[T],
    metadata: Dict[str, Any] | None = None,
) -> T:
    state = _session_state(session_id)
    agent = get_arcadia_agent(
        settings.arcadia_agent_model, settings.arcadia_agent_enable_web)
    metadata_payload: Dict[str, Any] = dict(metadata or {})
    if session_id:
        metadata_payload.setdefault("session_id", session_id)

    profile_snapshot: Dict[str, Any] | None = None
    username = metadata_payload.get("username")
    if isinstance(username, str) and username.strip():
        profile = profile_store.apply_metadata(username, metadata_payload)
        profile_snapshot = profile.model_dump(mode="json")

    context = ArcadiaAgentContext.model_construct(
        thread=state.thread,
        store=state.store,
        request_context={
            "metadata": metadata_payload,
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
                        effort=cast(ReasoningEffort, _effort(
                            settings.arcadia_agent_reasoning)),
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
                return WidgetEnvelope(display=payload, widgets=[], citations=None)
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


class ResetRequest(BaseModel):
    session_id: Optional[str] = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    history: List[ChatMessage] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


def _compose_chat_prompt(history: List[ChatMessage], latest: str) -> str:
    """Flatten the chat history into a conversational prompt."""
    parts: List[str] = []
    for message in history:
        prefix = "User" if message.role == "user" else "Assistant"
        parts.append(f"{prefix}: {message.text}")
    parts.append(f"User: {latest}")
    parts.append("Assistant:")
    return "\n".join(parts)


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
    return await _run_structured(
        settings,
        payload.session_id,
        prompt,
        WidgetEnvelope,
        metadata=metadata,
    )


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_session(
    payload: ResetRequest,
) -> Response:
    _reset_state(payload.session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
