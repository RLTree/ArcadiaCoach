"""ChatKit server that wires the Arcadia Coach agent."""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Tuple
from uuid import uuid4

from agents import ModelSettings, RunConfig, Runner
from chatkit.agents import ThreadItemConverter, stream_agent_response
from chatkit.server import ChatKitServer, ThreadItemDoneEvent, stream_widget
from chatkit.types import (
    Attachment,
    AssistantMessageItem,
    ClientToolCallItem,
    HiddenContextItem,
    ThreadItem,
    ThreadMetadata,
    ThreadStreamEvent,
    UserMessageItem,
)
from chatkit.widgets import (
    ActionConfig,
    Badge,
    Box,
    Borders,
    Button,
    Card,
    Caption,
    Col,
    Divider,
    Icon,
    Markdown,
    Row,
    Spacer,
    Title,
    Transition,
)
from fastapi import HTTPException, UploadFile, status
from openai import AsyncOpenAI
from openai.types.responses import ResponseInputContentParam
from openai.types.shared.reasoning import Reasoning

from .arcadia_agent import ArcadiaAgentContext, get_arcadia_agent
from .guardrails import run_guardrail_checks
from .memory_store import MemoryStore

logger = logging.getLogger(__name__)


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


def _is_tool_completion_item(item: Any) -> bool:
    return isinstance(item, ClientToolCallItem)


def _user_message_text(item: UserMessageItem) -> str:
    parts: list[str] = []
    for part in item.content:
        text = getattr(part, "text", None)
        if text:
            parts.append(text)
    return " ".join(parts).strip()


LEVEL_CONFIG: List[Tuple[str, str]] = [
    ("minimal", "Minimal (gpt-5-nano)"),
    ("low", "Low (gpt-5-mini)"),
    ("medium", "Medium (gpt-5)"),
    ("high", "High (gpt-5-codex)"),
]

MODEL_FOR_LEVEL: Dict[str, str] = {
    "minimal": "gpt-5-nano",
    "low": "gpt-5-mini",
    "medium": "gpt-5",
    "high": "gpt-5-codex",
}

REASONING_FOR_LEVEL: Dict[str, str] = {
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
}

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MiB


@dataclass
class UploadedFileRef:
    storage_id: str
    name: str
    mime_type: str
    size: int
    preview: str
    openai_file_id: str | None


@dataclass
class ChatPreferences:
    web_enabled: bool = False
    reasoning_level: str = "medium"
    show_tone_picker: bool = False
    uploaded_files: list[UploadedFileRef] = field(default_factory=list)

    @property
    def level_label(self) -> str:
        for value, label in LEVEL_CONFIG:
            if value == self.reasoning_level:
                return label
        return "Medium (gpt-5)"


class ArcadiaChatServer(ChatKitServer[dict[str, Any]]):
    """ChatKit server bound to the Arcadia Coach agent graph."""

    def __init__(self) -> None:
        store = MemoryStore()
        super().__init__(store)
        self.store = store
        self._thread_item_converter = self._init_thread_item_converter()
        self._preferences: dict[str, ChatPreferences] = {}
        self._uploaded_files: dict[str, UploadedFileRef] = {}
        self._openai = AsyncOpenAI()

    async def respond(
        self,
        thread: ThreadMetadata,
        item: UserMessageItem | None,
        context: dict[str, Any],
    ) -> AsyncIterator[ThreadStreamEvent]:
        prefs = self._get_preferences(thread.id)

        if item is None:
            async for event in self._emit_widget(thread, context, prefs):
                yield event
            return

        if _is_tool_completion_item(item):
            return

        message_text = _user_message_text(item)
        if not message_text:
            return

        allowed, payload = await run_guardrail_checks(message_text)
        if not allowed:
            detail = payload if isinstance(payload, dict) else {"message": "Content blocked."}
            failure_notice = (
                "I’m sorry, but I can’t help with that request. "
                "Please adjust the content and try again."
            )
            yield ThreadItemDoneEvent(
                item=HiddenContextItem(
                    id=_gen_id("guardrail"),
                    thread_id=thread.id,
                    created_at=datetime.utcnow(),
                    content=f'<GUARDRAIL_FAILURE detail="{detail}"/>',
                )
            )
            yield ThreadItemDoneEvent(item=self._assistant_message(thread, failure_notice))
            return

        sanitized_text = payload if isinstance(payload, str) else message_text

        augmented_input = self._augment_input_with_preferences(
            sanitized_text,
            prefs,
        )

        agent_context = ArcadiaAgentContext(
            thread=thread,
            store=self.store,
            request_context=context,
            sanitized_input=augmented_input,
            web_enabled=prefs.web_enabled,
            reasoning_level=prefs.reasoning_level,
            attachments=[
                {
                    "name": ref.name,
                    "mime_type": ref.mime_type,
                    "preview": ref.preview,
                    "openai_file_id": ref.openai_file_id,
                }
                for ref in prefs.uploaded_files
            ],
        )

        agent_input = await self._to_agent_input(thread, item)
        if not agent_input:
            agent_input = augmented_input

        model_name = MODEL_FOR_LEVEL.get(prefs.reasoning_level, "gpt-5")
        agent = get_arcadia_agent(model_name, prefs.web_enabled)
        reasoning_effort = REASONING_FOR_LEVEL.get(prefs.reasoning_level, "medium")

        result = Runner.run_streamed(
            agent,
            agent_input,
            context=agent_context,
            run_config=RunConfig(
                model_settings=ModelSettings(
                    reasoning=Reasoning(
                        effort=reasoning_effort,
                        summary="auto",
                    ),
                )
            ),
        )

        async for event in stream_agent_response(agent_context, result):
            yield event

        prefs.show_tone_picker = False
        async for event in self._emit_widget(thread, context, prefs):
            yield event

    async def action(
        self,
        thread: ThreadMetadata,
        action: dict[str, Any],
        sender: AssistantMessageItem | None,
        context: dict[str, Any],
    ) -> AsyncIterator[ThreadStreamEvent]:
        prefs = self._get_preferences(thread.id)
        action_type = (action or {}).get("type")
        payload = (action or {}).get("payload") or {}

        if action_type == "toggle_web":
            prefs.web_enabled = not prefs.web_enabled
            yield ThreadItemDoneEvent(
                item=self._assistant_message(
                    thread,
                    "Web search is now {}.".format("enabled" if prefs.web_enabled else "disabled"),
                )
            )
        elif action_type == "toggle_tone":
            prefs.show_tone_picker = not prefs.show_tone_picker
        elif action_type == "set_level":
            level = payload.get("level")
            if level in MODEL_FOR_LEVEL:
                prefs.reasoning_level = level
                prefs.show_tone_picker = False
                yield ThreadItemDoneEvent(
                    item=self._assistant_message(
                        thread,
                        f"Reasoning effort set to {prefs.level_label}.",
                    )
                )
        elif action_type == "files_uploaded":
            files = payload.get("files") or []
            summaries = []
            for file_info in files:
                storage_id = file_info.get("file_id")
                ref = self._uploaded_files.get(storage_id)
                if not ref:
                    continue
                if any(existing.storage_id == ref.storage_id for existing in prefs.uploaded_files):
                    continue
                prefs.uploaded_files.append(ref)
                summaries.append(f"- {ref.name} ({ref.mime_type}, {ref.size} bytes)")
            if summaries:
                yield ThreadItemDoneEvent(
                    item=self._assistant_message(
                        thread,
                        "Uploaded files received:\n" + "\n".join(summaries),
                    )
                )
        elif action_type == "start_lesson":
            topic = payload.get("topic") or "general topic"
            yield ThreadItemDoneEvent(
                item=self._assistant_message(
                    thread,
                    f"Starting lesson on {topic}. Let me prepare the materials...",
                )
            )
        elif action_type == "start_quiz":
            topic = payload.get("topic") or "general topic"
            yield ThreadItemDoneEvent(
                item=self._assistant_message(
                    thread,
                    f"Preparing quiz on {topic}...",
                )
            )
        elif action_type == "milestone":
            milestone_name = payload.get("name") or "Achievement"
            yield ThreadItemDoneEvent(
                item=self._assistant_message(
                    thread,
                    f"Recording milestone: {milestone_name}",
                )
            )
        else:
            return

        async for event in self._emit_widget(thread, context, prefs):
            yield event

    async def to_message_content(self, _input: Attachment) -> ResponseInputContentParam:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Attachments are not supported.",
        )

    async def handle_file_upload(self, upload_file: UploadFile) -> dict[str, Any]:
        data = await upload_file.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File too large (max 5 MiB).")

        storage_id = _gen_id("file")
        mime_type = upload_file.content_type or "application/octet-stream"
        preview = self._summarize_file(data, mime_type)

        openai_file_id = None
        try:
            response = await self._openai.files.create(
                file=(upload_file.filename, data, mime_type),
                purpose="assistants",
            )
            openai_file_id = response.id
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to upload file to OpenAI: %s", exc)

        ref = UploadedFileRef(
            storage_id=storage_id,
            name=upload_file.filename,
            mime_type=mime_type,
            size=len(data),
            preview=preview,
            openai_file_id=openai_file_id,
        )
        self._uploaded_files[storage_id] = ref

        return {
            "file_id": storage_id,
            "name": ref.name,
            "mime_type": ref.mime_type,
            "size": ref.size,
            "preview": ref.preview,
            "openai_file_id": ref.openai_file_id,
        }

    def _assistant_message(self, thread: ThreadMetadata, content: str) -> AssistantMessageItem:
        return AssistantMessageItem(
            id=_gen_id("msg"),
            thread_id=thread.id,
            created_at=datetime.utcnow(),
            role="assistant",
            content=[{"type": "output_text", "text": content}],
        )

    def _augment_input_with_preferences(self, text: str, prefs: ChatPreferences) -> str:
        augmented = text
        if prefs.uploaded_files:
            augmented += "\n\nUploaded files:\n"
            for ref in prefs.uploaded_files:
                augmented += f"- {ref.name} ({ref.mime_type}, {ref.size} bytes)\n  Summary: {ref.preview}\n"
        if prefs.web_enabled:
            augmented += "\n\nWeb search is enabled. Use the web_search tool freely when needed."
        else:
            augmented += "\n\nWeb search is disabled; rely on internal knowledge and uploaded files."
        augmented += (
            f"\n\nReasoning effort target: {prefs.reasoning_level}. "
            "Be mindful of latency when responding."
        )
        return augmented

    async def _emit_widget(
        self,
        thread: ThreadMetadata,
        context: dict[str, Any],
        prefs: ChatPreferences,
    ) -> AsyncIterator[ThreadStreamEvent]:
        widget = await self._build_chatbot_widget(thread, context, prefs)
        if widget is None:
            logger.warning(
                "Widget builder returned None for thread %s; streaming fallback widget.", thread.id
            )
            widget = self._fallback_widget(thread, prefs)
        logger.info(
            "Streaming Arcadia chatbot widget (thread=%s, web_enabled=%s, reasoning=%s)",
            thread.id,
            prefs.web_enabled,
            prefs.reasoning_level,
        )
        events_streamed = 0
        try:
            async for event in stream_widget(thread, widget):
                events_streamed += 1
                logger.debug(
                    "Emitting widget event #%s for thread %s (%s)",
                    events_streamed,
                    thread.id,
                    event.__class__.__name__,
                )
                yield event
        except Exception:
            logger.exception("Failed while streaming widget for thread %s", thread.id)
            raise
        finally:
            logger.info(
                "Completed widget stream for thread %s (events=%s)",
                thread.id,
                events_streamed,
            )

    async def _build_chatbot_widget(
        self,
        thread: ThreadMetadata,
        context: dict[str, Any],
        prefs: ChatPreferences,
    ) -> Card | None:
        try:
            page = await self.store.load_thread_items(
                thread.id,
                after=None,
                limit=100,
                order="asc",
                context=context,
            )
        except Exception:
            return None

        message_rows: list[Row] = []
        for item in page.data:
            role = None
            text = None
            if isinstance(item, UserMessageItem):
                role = "user"
                text = _user_message_text(item)
            elif isinstance(item, AssistantMessageItem):
                role = "assistant"
                text = self._assistant_message_text(item)
            if not text:
                continue
            bubble = Box(
                children=[Markdown(value=text)],
                maxWidth="80%",
                padding=3,
                radius="xl",
                background="surface-secondary" if role == "user" else "surface-elevated-secondary",
                border=Borders(size=1),
            )
            children: list[Any] = []
            if role != "user":
                children.append(
                    Box(
                        background="alpha-10",
                        radius="full",
                        padding=1,
                        children=[Icon(name="sparkle", size="sm")],
                    )
                )
            children.append(bubble)
            if role == "user":
                children.append(
                    Box(
                        background="alpha-10",
                        radius="full",
                        padding=1,
                        children=[Icon(name="profile", size="sm")],
                    )
                )
            message_rows.append(
                Row(
                    key=getattr(item, "id", None),
                    justify="end" if role == "user" else "start",
                    children=children,
                )
            )

        if not message_rows:
            message_rows.append(
                Row(
                    justify="start",
                    children=[
                        Box(
                            children=[Markdown(value="Hi! Ask me anything to get started.")],
                            maxWidth="80%",
                            padding=3,
                            radius="xl",
                            background="surface-elevated-secondary",
                            border=Borders(size=1),
                        )
                    ],
                )
            )

        tone_buttons = [
            Button(
                key=value,
                label=label,
                size="sm",
                variant="solid" if value == prefs.reasoning_level else "outline",
                color="primary" if value == prefs.reasoning_level else "secondary",
                onClickAction=ActionConfig(type="chat.setLevel", payload={"level": value}),
            )
            for value, label in LEVEL_CONFIG
        ]

        footer_buttons = Row(
            align="center",
            background="surface-elevated-secondary",
            padding=4,
            gap=2,
            children=[
                Button(
                    iconStart="globe",
                    uniform=True,
                    size="lg",
                    variant="solid" if prefs.web_enabled else "outline",
                    color="info" if prefs.web_enabled else "secondary",
                    onClickAction=ActionConfig(type="chat.toggleWeb"),
                ),
                Button(
                    iconStart="lightbulb",
                    uniform=True,
                    size="lg",
                    variant="solid" if prefs.show_tone_picker else "outline",
                    color="secondary",
                    onClickAction=ActionConfig(type="chat.toggleTone"),
                ),
                Button(
                    iconStart="plus",
                    uniform=True,
                    size="lg",
                    variant="outline",
                    color="secondary",
                    onClickAction=ActionConfig(type="chat.add"),
                ),
                Spacer(),
                Caption(
                    value=f"Level: {prefs.level_label}",
                    color="secondary",
                ),
            ],
        )

        body_children: list[Any] = message_rows
        if prefs.show_tone_picker:
            body_children.append(
                Transition(
                    children=Box(
                        key="tone",
                        background="surface-elevated-secondary",
                        padding=3,
                        radius="lg",
                        border=Borders(size=1),
                        children=[Row(gap=2, wrap="wrap", children=tone_buttons)],
                    )
                )
            )

        if prefs.uploaded_files:
            attachment_rows = []
            for ref in prefs.uploaded_files:
                preview_text = ref.preview if ref.preview else f"{ref.mime_type}, {ref.size} bytes"
                attachment_rows.append(
                    Row(
                        key=f"file_{ref.storage_id}",
                        align="center",
                        gap=2,
                        children=[
                            Icon(name="document", color="secondary"),
                            Markdown(
                                value=f"**{ref.name}** ({ref.mime_type}, {ref.size} bytes)\\n{preview_text}"
                            ),
                        ],
                    )
                )
            body_children.extend(
                [
                    Divider(),
                    Col(
                        gap=2,
                        children=[
                            Caption(value="Attached files", color="secondary"),
                            Col(gap=1, children=attachment_rows),
                        ],
                    ),
                ]
            )

        body = Col(
            padding=4,
            gap=2,
            minHeight="180px",
            children=body_children,
        )

        header = Row(
            align="center",
            padding={"x": 4, "y": 3},
            children=[
                Icon(name="sparkle", color="primary"),
                Title(value="Arcadia Coach", size="sm"),
                Spacer(),
                Badge(label=prefs.level_label, color="info"),
            ],
        )

        card = Card(
            id="arcadia_chatbot",
            size="md",
            padding=0,
            children=[
                Col(
                    gap=0,
                    children=[
                        header,
                        Divider(flush=True),
                        body,
                        Divider(flush=True),
                        footer_buttons,
                    ],
                )
            ],
        )
        try:
            card_json = card.model_dump_json()
            logger.info("Widget card built successfully (bytes=%s)", len(card_json))
        except Exception as exc:  # noqa: BLE001
            logger.error("Widget card serialization failed: %s", exc)
            return None

        return card

    def _fallback_widget(self, thread: ThreadMetadata, prefs: ChatPreferences) -> Card:
        logger.debug(
            "Building fallback widget for thread %s (web_enabled=%s, reasoning=%s).",
            thread.id,
            prefs.web_enabled,
            prefs.reasoning_level,
        )
        return Card(
            id="arcadia_chatbot_fallback",
            size="md",
            padding=0,
            children=[
                Col(
                    gap=0,
                    children=[
                        Row(
                            align="center",
                            padding={"x": 4, "y": 3},
                            children=[
                                Icon(name="sparkle", color="primary"),
                                Title(value="Arcadia Coach", size="sm"),
                                Spacer(),
                                Badge(label=prefs.level_label, color="info"),
                            ],
                        ),
                        Divider(flush=True),
                        Col(
                            padding=4,
                            gap=2,
                            minHeight="120px",
                            children=[
                                Row(
                                    justify="start",
                                    children=[
                                        Box(
                                            children=[
                                                Markdown(
                                                    value=(
                                                        "Arcadia Coach is ready. "
                                                        "Start the conversation to see lesson, quiz, "
                                                        "and milestone widgets here."
                                                    )
                                                )
                                            ],
                                            maxWidth="80%",
                                            padding=3,
                                            radius="xl",
                                            background="surface-elevated-secondary",
                                            border=Borders(size=1),
                                        )
                                    ],
                                )
                            ],
                        ),
                        Divider(flush=True),
                        Row(
                            align="center",
                            background="surface-elevated-secondary",
                            padding=4,
                            gap=2,
                            children=[
                                Button(
                                    iconStart="globe",
                                    uniform=True,
                                    size="lg",
                                    variant="solid" if prefs.web_enabled else "outline",
                                    color="info" if prefs.web_enabled else "secondary",
                                    onClickAction=ActionConfig(type="chat.toggleWeb"),
                                ),
                                Button(
                                    iconStart="lightbulb",
                                    uniform=True,
                                    size="lg",
                                    variant="outline",
                                    color="secondary",
                                    onClickAction=ActionConfig(type="chat.toggleTone"),
                                ),
                                Spacer(),
                                Caption(value="Waiting for your first question…", color="secondary"),
                            ],
                        ),
                    ],
                )
            ],
        )

    def _assistant_message_text(self, item: AssistantMessageItem) -> str:
        parts: list[str] = []
        for part in getattr(item, "content", []) or []:
            text = getattr(part, "text", None)
            if text:
                parts.append(text)
        return " ".join(parts).strip()

    def _get_preferences(self, thread_id: str) -> ChatPreferences:
        prefs = self._preferences.get(thread_id)
        if prefs is None:
            prefs = ChatPreferences()
            self._preferences[thread_id] = prefs
        return prefs

    def _summarize_file(self, data: bytes, mime_type: str) -> str:
        if mime_type.startswith("text/") or mime_type in {"application/json", "application/xml"}:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                return f"{mime_type} file ({len(data)} bytes)."
            sanitized = " ".join(text.split())
            return sanitized[:400] + ("…" if len(sanitized) > 400 else "")
        return f"{mime_type} file ({len(data)} bytes)."

    def _init_thread_item_converter(self) -> Any | None:
        converter_cls = ThreadItemConverter
        if converter_cls is None or not callable(converter_cls):
            return None

        attempts: tuple[dict[str, Any], ...] = (
            {"to_message_content": self.to_message_content},
            {"message_content_converter": self.to_message_content},
            {},
        )

        for kwargs in attempts:
            try:
                return converter_cls(**kwargs)
            except TypeError:
                continue
        return None

    async def _to_agent_input(
        self,
        thread: ThreadMetadata,
        item: ThreadItem,
    ) -> Any | None:
        if _is_tool_completion_item(item):
            return None

        converter = getattr(self, "_thread_item_converter", None)
        if converter is not None:
            for attr in (
                "to_input_item",
                "convert",
                "convert_item",
                "convert_thread_item",
            ):
                method = getattr(converter, attr, None)
                if method is None:
                    continue
                call_args: list[Any] = [item]
                call_kwargs: dict[str, Any] = {}
                try:
                    signature = inspect.signature(method)
                except (TypeError, ValueError):
                    signature = None

                if signature is not None:
                    params = [
                        parameter
                        for parameter in signature.parameters.values()
                        if parameter.kind
                        not in (
                            inspect.Parameter.VAR_POSITIONAL,
                            inspect.Parameter.VAR_KEYWORD,
                        )
                    ]
                    if len(params) >= 2:
                        next_param = params[1]
                        if next_param.kind in (
                            inspect.Parameter.POSITIONAL_ONLY,
                            inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        ):
                            call_args.append(thread)
                        else:
                            call_kwargs[next_param.name] = thread

                result = method(*call_args, **call_kwargs)
                if inspect.isawaitable(result):
                    return await result
                return result

        if isinstance(item, UserMessageItem):
            return _user_message_text(item)

        return None


def create_chat_server() -> ArcadiaChatServer:
    """Return a configured ChatKit server instance."""
    return ArcadiaChatServer()
