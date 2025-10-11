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
) -> T:
    state = _session_state(session_id)
    agent = get_arcadia_agent(
        settings.arcadia_agent_model, settings.arcadia_agent_enable_web)
    context = ArcadiaAgentContext.model_construct(
        thread=state.thread,
        store=state.store,
        request_context={},
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
            data = payload.model_dump()
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
            logger.error(
                "Failed to decode JSON string payload into %s: %s",
                expecting.__name__,
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Agent returned malformed payload for {expecting.__name__}",
            ) from exc
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
    return await _run_structured(settings, payload.session_id, message, EndLearn)


@router.post("/quiz", response_model=EndQuiz, status_code=status.HTTP_200_OK)
async def create_quiz(
    payload: TopicRequest,
    settings: Settings = Depends(get_settings),
) -> EndQuiz:
    message = f"quiz {payload.topic}".strip()
    return await _run_structured(settings, payload.session_id, message, EndQuiz)


@router.post("/milestone", response_model=EndMilestone, status_code=status.HTTP_200_OK)
async def create_milestone(
    payload: TopicRequest,
    settings: Settings = Depends(get_settings),
) -> EndMilestone:
    message = f"milestone {payload.topic}".strip()
    return await _run_structured(settings, payload.session_id, message, EndMilestone)


@router.post("/chat", response_model=WidgetEnvelope, status_code=status.HTTP_200_OK)
async def chat_with_agent(
    payload: ChatRequest,
    settings: Settings = Depends(get_settings),
) -> WidgetEnvelope:
    prompt = _compose_chat_prompt(payload.history, payload.message)
    return await _run_structured(settings, payload.session_id, prompt, WidgetEnvelope)


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_session(
    payload: ResetRequest,
) -> Response:
    _reset_state(payload.session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
