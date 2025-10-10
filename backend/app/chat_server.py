"""ChatKit server that wires the Arcadia Coach agent."""

from __future__ import annotations

import inspect
from datetime import datetime
from typing import Any, AsyncIterator
from uuid import uuid4

from agents import RunConfig, Runner
from chatkit.agents import ThreadItemConverter, stream_agent_response
from chatkit.server import ChatKitServer, ThreadItemDoneEvent
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
from fastapi import HTTPException, status
from openai.types.responses import ResponseInputContentParam

from .arcadia_agent import ArcadiaAgentContext, arcadia_agent
from .guardrails import run_guardrail_checks
from .memory_store import MemoryStore


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


class ArcadiaChatServer(ChatKitServer[dict[str, Any]]):
    """ChatKit server bound to the Arcadia Coach agent graph."""

    def __init__(self) -> None:
        store = MemoryStore()
        super().__init__(store)
        self.store = store
        self.agent = arcadia_agent
        self._thread_item_converter = self._init_thread_item_converter()

    async def respond(
        self,
        thread: ThreadMetadata,
        item: UserMessageItem | None,
        context: dict[str, Any],
    ) -> AsyncIterator[ThreadStreamEvent]:
        if item is None:
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

        agent_context = ArcadiaAgentContext(
            thread=thread,
            store=self.store,
            request_context=context,
            sanitized_input=sanitized_text,
        )

        agent_input = await self._to_agent_input(thread, item)
        if not agent_input:
            agent_input = sanitized_text

        result = Runner.run_streamed(
            self.agent,
            agent_input,
            context=agent_context,
            run_config=RunConfig(),
        )

        async for event in stream_agent_response(agent_context, result):
            yield event

    async def to_message_content(self, _input: Attachment) -> ResponseInputContentParam:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Attachments are not supported.",
        )

    def _assistant_message(self, thread: ThreadMetadata, content: str) -> AssistantMessageItem:
        return AssistantMessageItem(
            id=_gen_id("msg"),
            thread_id=thread.id,
            created_at=datetime.utcnow(),
            role="assistant",
            content=[{"type": "output_text", "text": content}],
        )

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
    return ArcadiaChatServer()
