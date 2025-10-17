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
    MilestoneCompletionPayload,
    ScheduleLaunchContentPayload,
    ScheduleLaunchResponsePayload,
    Widget,
    WidgetEnvelope,
)
from .arcadia_agent import ArcadiaAgentContext, get_arcadia_agent, refresh_mcp_tool
from .config import Settings, get_settings
from .learner_profile import (
    LearnerProfile,
    MilestoneBrief,
    MilestoneCompletion,
    MilestoneGuidance,
    MilestoneProgress,
    SequencedWorkItem,
    profile_store,
)
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


def _is_mcp_tool_error(exc: OpenAIError) -> bool:
    message = str(exc)
    if "Error retrieving tool list from MCP server" in message:
        return True
    status_code = getattr(exc, "status_code", None)
    if status_code == 424:
        return True
    return False


def _is_mcp_http_detail(detail: Any) -> bool:
    if isinstance(detail, dict):
        text = json.dumps(detail)
    else:
        text = str(detail)
    if "Error retrieving tool list from MCP server" in text:
        return True
    if "Arcadia_Coach_Widgets" in text:
        return True
    return False

ATTACHMENT_POLICY: Dict[str, str] = {
    "gpt-5": "any",
    "gpt-5-mini": "any",
    "gpt-5-nano": "any",
    "gpt-5-codex": "images",
}


def _elo_delta_for_evaluation(outcome: Optional[str]) -> int:
    if outcome == "passed":
        return 24
    if outcome == "needs_revision":
        return 10
    if outcome == "failed":
        return 0
    return 12


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


def _milestone_completion_payloads(profile: LearnerProfile) -> List[MilestoneCompletionPayload]:
    completions = getattr(profile, "milestone_completions", []) or []
    return [
        MilestoneCompletionPayload(
            completion_id=entry.completion_id,
            item_id=entry.item_id,
            category_key=entry.category_key,
            title=entry.title,
            headline=entry.headline,
            summary=entry.summary,
            notes=entry.notes,
            external_links=list(entry.external_links or []),
            attachment_ids=list(entry.attachment_ids or []),
            elo_focus=list(entry.elo_focus or []),
            recommended_day_offset=entry.recommended_day_offset,
            session_id=entry.session_id,
            recorded_at=entry.recorded_at,
            project_status=getattr(entry, "project_status", "completed"),
            evaluation_outcome=getattr(entry, "evaluation_outcome", None),
            evaluation_notes=getattr(entry, "evaluation_notes", None),
            elo_delta=getattr(entry, "elo_delta", 12),
        )
        for entry in completions
    ]


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
    def _format_list(values: Iterable[str], limit: int = 6) -> str:
        items = [value for value in values if value.strip()]
        if not items:
            return ""
        display = items[:limit]
        suffix = ""
        if len(items) > limit:
            suffix = f"\n- (+{len(items) - limit} more)"
        return "\n".join(f"- {entry}" for entry in display) + suffix

    if item.kind == "milestone":
        brief = getattr(item, "milestone_brief", None)
        lines: List[str] = []
        if brief and brief.headline:
            lines.append(brief.headline)
        elif item.title:
            lines.append(item.title)
        if brief and brief.summary:
            lines.append(brief.summary)
        elif item.summary:
            lines.append(item.summary)

        project = getattr(item, "milestone_project", None) or (brief.project if brief else None)
        if project:
            if project.goal_alignment:
                lines.append(f"Goal alignment: {project.goal_alignment}")
            if project.summary:
                lines.append(project.summary)
            deliverables = _format_list(project.deliverables, limit=5)
            if deliverables:
                lines.append("Deliverables:\n" + deliverables)
            evidence = _format_list(project.evidence_checklist, limit=5)
            if evidence:
                lines.append("Evidence checklist:\n" + evidence)
        if brief:
            kickoff = _format_list(brief.kickoff_steps, limit=5)
            if kickoff:
                lines.append("Kickoff steps:\n" + kickoff)
            external = _format_list(brief.external_work, limit=5)
            if external:
                lines.append("External work checklist:\n" + external)
            criteria = _format_list(brief.success_criteria, limit=5)
            if criteria:
                lines.append("Success criteria:\n" + criteria)
            capture = _format_list(brief.capture_prompts, limit=4)
            if capture:
                lines.append("Capture prompts:\n" + capture)
            coaching = _format_list(brief.coaching_prompts, limit=4)
            if coaching:
                lines.append("Coaching prompts:\n" + coaching)
            if brief.elo_focus:
                lines.append("ELO focus: " + ", ".join(brief.elo_focus))
        return "\n\n".join(lines)

    lines: List[str] = [item.title]
    if item.summary:
        lines.append(item.summary)
    if item.objectives:
        objective_lines = "\n".join(f"- {objective}" for objective in item.objectives)
        lines.append(f"Objectives:\n{objective_lines}")
    if item.expected_outcome:
        lines.append(f"Expected outcome: {item.expected_outcome}")
    if item.focus_reason:
        lines.append(f"Focus reason: {item.focus_reason}")
    return "\n\n".join(lines)


def _render_milestone_envelope(
    item: SequencedWorkItem,
    base: EndMilestone,
) -> EndMilestone:
    brief: MilestoneBrief | None = getattr(item, "milestone_brief", None)
    if brief is None:
        return base

    guidance: MilestoneGuidance | None = getattr(item, "milestone_guidance", None)
    project = getattr(item, "milestone_project", None) or (brief.project if brief else None)
    summary_text = (
        (brief.summary or project.summary)
        or item.summary
        or base.display
        or f"Milestone: {item.title}"
    )
    sections: List[Dict[str, Any]] = []
    if brief.objectives:
        sections.append({"heading": "Objectives", "items": list(brief.objectives)})
    if brief.deliverables:
        sections.append({"heading": "Deliverables", "items": list(brief.deliverables)})
    if brief.success_criteria:
        sections.append({"heading": "Success criteria", "items": list(brief.success_criteria)})
    if brief.kickoff_steps:
        sections.append({"heading": "Kickoff steps", "items": list(brief.kickoff_steps)})
    if brief.coaching_prompts:
        sections.append({"heading": "Coaching prompts", "items": list(brief.coaching_prompts)})
    if not sections:
        sections.append({"heading": None, "items": [summary_text]})

    overview_card = Widget(
        type="Card",
        props={
            "title": brief.headline or item.title,
            "sections": sections,
        },
    )

    rows: List[Dict[str, Any]] = []
    for entry in brief.external_work:
        rows.append({"label": entry, "meta": "External work"})
    for prompt in brief.capture_prompts:
        rows.append({"label": prompt, "meta": "Capture prompt"})
    for prompt in brief.coaching_prompts:
        rows.append({"label": prompt, "meta": "Coaching prompt"})
    for resource in brief.resources:
        rows.append({"label": resource, "meta": "Reference"})
    if guidance:
        for action in guidance.next_actions:
            rows.append({"label": action, "meta": "Next action"})
        for warning in guidance.warnings:
            rows.append({"label": warning, "meta": "Warning"})

    list_widget: List[Widget] = []
    if rows:
        list_widget.append(
            Widget(
                type="List",
                props={
                    "title": "Milestone checklist",
                    "rows": rows,
                },
            )
        )

    stat_items: List[Dict[str, Any]] = []
    if brief.elo_focus:
        stat_items.append({"label": "Focus", "value": ", ".join(brief.elo_focus)})
    if guidance and guidance.badges:
        stat_items.append({"label": "Status", "value": ", ".join(guidance.badges)})
    if guidance and guidance.state:
        stat_items.append({"label": "State", "value": guidance.state.replace("_", " ").title()})
    if guidance and guidance.last_update_at:
        stat_items.append({"label": "Updated", "value": guidance.last_update_at.isoformat()})

    stat_widget: List[Widget] = []
    if stat_items:
        stat_widget.append(
            Widget(
                type="StatRow",
                props={"items": stat_items},
            )
        )

    widgets = [overview_card, *list_widget, *stat_widget]
    return EndMilestone(
        intent=base.intent,
        display=summary_text,
        widgets=widgets,
    )


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
    result: Any = None
    last_error: OpenAIError | None = None
    for attempt in range(2):
        agent = get_arcadia_agent(model_choice, web_enabled)
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
            break
        except AuthenticationError as exc:
            logger.error(
                "OpenAI authentication error while running agent: %s", exc
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Arcadia backend is not authorized with OpenAI. Update OPENAI_API_KEY and try again.",
            ) from exc
        except OpenAIError as exc:
            last_error = exc
            if attempt == 0 and _is_mcp_tool_error(exc):
                logger.warning(
                    "MCP tool retrieval failed (attempt=%s); refreshing tool configuration and retrying once.",
                    attempt + 1,
                )
                refresh_mcp_tool()
                continue
            logger.error("OpenAI error while running agent: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Upstream OpenAI request failed: {exc}",
            ) from exc
    else:  # pragma: no cover - defensive guard
        if last_error is not None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Upstream OpenAI request failed: {last_error}",
            ) from last_error
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream OpenAI request failed: unknown error",
        )
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
    notes: Optional[str] = Field(default=None, max_length=4000)
    external_links: List[str] = Field(default_factory=list)
    attachment_ids: List[str] = Field(default_factory=list)
    project_status: Optional[Literal["not_started", "building", "ready_for_review", "blocked", "completed"]] = None
    evaluation_outcome: Optional[Literal["passed", "needs_revision", "failed"]] = None
    evaluation_notes: Optional[str] = Field(default=None, max_length=4000)
    next_steps: List[str] = Field(default_factory=list)


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
    brief_payload = getattr(item, "milestone_brief", None)
    if brief_payload is not None:
        metadata["milestone_brief"] = brief_payload.model_dump(mode="json")
    progress_payload = getattr(item, "milestone_progress", None)
    if progress_payload is not None:
        metadata["milestone_progress"] = progress_payload.model_dump(mode="json")
    guidance_payload = getattr(item, "milestone_guidance", None)
    if guidance_payload is not None:
        metadata["milestone_guidance"] = guidance_payload.model_dump(mode="json")
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

    use_agent = not (item.kind == "milestone" and payload.force)
    if not use_agent:
        brief = item.milestone_brief or MilestoneBrief(
            headline=item.title,
            summary=item.summary,
            objectives=list(item.objectives),
        )
        item.milestone_brief = brief
        base_display = (
            brief.summary
            or item.summary
            or brief.headline
            or item.title
            or "Milestone"
        )
        base_envelope = EndMilestone(
            intent="milestone",
            display=base_display,
            widgets=[],
        )
        result = _render_milestone_envelope(item, base_envelope)
    else:
        try:
            result = await _run_structured(
                settings,
                session_id,
                message,
                expected_cls,
                metadata=metadata,
                augment_with_preferences=True,
            )
        except (OpenAIError, AuthenticationError, ValidationError, HTTPException) as exc:
            reverted_profile = profile_store.update_schedule_item(
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
        if (
            isinstance(exc, HTTPException)
            and exc.status_code == status.HTTP_502_BAD_GATEWAY
            and item.kind == "milestone"
            and _is_mcp_http_detail(exc.detail)
        ):
            fallback_profile = reverted_profile or profile_store.get(username)
            if fallback_profile and fallback_profile.curriculum_schedule:
                fallback_schedule_payload = _schedule_payload(
                    fallback_profile.curriculum_schedule,
                    elo_snapshot=getattr(fallback_profile, "elo_snapshot", {}),
                    elo_plan=getattr(fallback_profile, "elo_category_plan", None),
                )
                if fallback_schedule_payload:
                    fallback_schedule_payload.milestone_completions = _milestone_completion_payloads(fallback_profile)
                    item_payload = next(
                        (
                            entry
                            for entry in fallback_schedule_payload.items
                            if entry.item_id == item_id
                        ),
                        None,
                    )
                    if item_payload is not None:
                        fallback_content = _render_milestone_envelope(
                            item,
                            EndMilestone(
                                intent="milestone",
                                display=item.summary or item.title,
                                widgets=[],
                            ),
                        )
                        emit_event(
                            "schedule_launch_completed",
                            username=username,
                            item_id=item_id,
                            kind=item.kind,
                            status="fallback",
                            session_id=session_id,
                            error="mcp_tool_unavailable",
                        )
                        content_payload = ScheduleLaunchContentPayload(
                            kind="milestone",
                            session_id=session_id,
                            milestone=fallback_content,
                        )
                        return ScheduleLaunchResponsePayload(
                            schedule=fallback_schedule_payload,
                            item=item_payload,
                            content=content_payload,
                        )
            raise exc
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to generate the scheduled content. Try again shortly.",
        ) from exc
    if item.kind == "milestone":
        result = _render_milestone_envelope(item, result)
    duration_ms = int((perf_counter() - started_at) * 1000)
    refreshed_profile = profile_store.get(username)
    if refreshed_profile is None or refreshed_profile.curriculum_schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No curriculum schedule configured for '{username}'.",
        )
    schedule_payload = _schedule_payload(
        refreshed_profile.curriculum_schedule,
        elo_snapshot=getattr(refreshed_profile, "elo_snapshot", {}),
        elo_plan=getattr(refreshed_profile, "elo_category_plan", None),
    )
    if schedule_payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No curriculum schedule configured for '{username}'.",
        )
    schedule_payload.milestone_completions = _milestone_completion_payloads(refreshed_profile)
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
    notes = payload.notes.strip() if isinstance(payload.notes, str) and payload.notes.strip() else None
    links = [link.strip() for link in payload.external_links if isinstance(link, str) and link.strip()]
    attachment_ids = [att.strip() for att in payload.attachment_ids if isinstance(att, str) and att.strip()]
    next_steps = [step.strip() for step in payload.next_steps if isinstance(step, str) and step.strip()]
    project_status = payload.project_status
    evaluation_outcome = payload.evaluation_outcome
    evaluation_notes = (
        payload.evaluation_notes.strip() if isinstance(payload.evaluation_notes, str) and payload.evaluation_notes.strip() else None
    )
    progress_entry: Optional[MilestoneProgress] = None
    completion_project_status: Optional[str] = None
    completion_evaluation_outcome: Optional[str] = None
    completion_elo_delta: Optional[int] = None
    if (
        (notes or links or attachment_ids or project_status or evaluation_outcome or evaluation_notes or next_steps)
        and item.kind != "milestone"
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only milestone items accept project metadata, evaluation, or artefacts.",
        )
    if item.kind == "milestone" and (notes or links or attachment_ids or project_status or next_steps):
        inferred_status = project_status
        if inferred_status is None:
            if evaluation_outcome == "failed":
                inferred_status = "blocked"
            elif evaluation_outcome == "needs_revision":
                inferred_status = "ready_for_review"
            else:
                inferred_status = "completed"
        completion_project_status = inferred_status
        progress_entry = MilestoneProgress(
            notes=notes,
            external_links=links,
            attachment_ids=attachment_ids,
            project_status=completion_project_status,
            next_steps=next_steps,
        )
    try:
        profile = profile_store.update_schedule_item(
            username,
            item_id,
            status="completed",
            last_completed_at=now,
            clear_active_session=True,
            milestone_progress=progress_entry,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    if item.kind == "milestone":
        brief = getattr(item, "milestone_brief", None)
        elo_delta = _elo_delta_for_evaluation(evaluation_outcome)
        completion = MilestoneCompletion(
            item_id=item.item_id,
            category_key=item.category_key,
            title=item.title,
            headline=getattr(brief, "headline", None) or item.title,
            summary=getattr(brief, "summary", None) or item.summary,
            notes=notes,
            external_links=links,
            attachment_ids=attachment_ids,
            elo_focus=list(getattr(brief, "elo_focus", []) or [item.category_key]),
            recommended_day_offset=item.recommended_day_offset,
            session_id=payload.session_id or item.active_session_id,
            recorded_at=progress_entry.recorded_at if progress_entry is not None else now,
            project_status=completion_project_status or "completed",
            evaluation_outcome=evaluation_outcome,
            evaluation_notes=evaluation_notes,
            elo_delta=elo_delta,
        )
        profile = profile_store.record_milestone_completion(username, completion)
        completion_project_status = completion.project_status
        completion_evaluation_outcome = completion.evaluation_outcome
        completion_elo_delta = completion.elo_delta
        emit_event(
            "milestone_completion_recorded",
            username=username,
            item_id=item_id,
            category_key=item.category_key,
            recorded_at=completion.recorded_at.isoformat(),
            has_notes=bool(completion.notes),
            link_count=len(completion.external_links),
            attachment_count=len(completion.attachment_ids),
            project_status=completion.project_status,
            evaluation_outcome=completion.evaluation_outcome or "",
            elo_delta=completion.elo_delta,
        )
    schedule_payload = _schedule_payload(
        profile.curriculum_schedule,
        elo_snapshot=getattr(profile, "elo_snapshot", {}),
        elo_plan=getattr(profile, "elo_category_plan", None),
    )
    if schedule_payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No curriculum schedule configured for '{username}'.",
        )
    schedule_payload.milestone_completions = _milestone_completion_payloads(profile)
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
        progress_recorded=bool(progress_entry),
        project_status=completion_project_status or "",
        evaluation_outcome=completion_evaluation_outcome or "",
        elo_delta=completion_elo_delta if completion_elo_delta is not None else "",
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
