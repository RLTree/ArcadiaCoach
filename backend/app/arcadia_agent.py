"""Arcadia Coach agent configuration."""

from __future__ import annotations

from typing import Annotated, Any, Dict, Tuple

from agents import Agent, FileSearchTool, HostedMCPTool, ModelSettings, WebSearchTool
from chatkit.agents import AgentContext
from openai.types.shared.reasoning import Reasoning
from pydantic import ConfigDict, Field

from .constants import INSTRUCTIONS, MODEL
from .config import get_settings
from .memory_store import MemoryStore
from .tools import AGENT_SUPPORT_TOOLS

# Tool instances ---------------------------------------------------------------

file_search = FileSearchTool(
    vector_store_ids=["vs_68e81d741f388191acdaabce2f92b7d5"],
)

web_search = WebSearchTool(
    search_context_size="high",
    user_location={"type": "approximate"},
)

settings = get_settings()
_mcp_url = settings.arcadia_mcp_url
_mcp_label = settings.arcadia_mcp_label
_require_approval = settings.arcadia_mcp_require_approval

mcp_widgets = HostedMCPTool(
    tool_config={
        "type": "mcp",
        "server_label": _mcp_label,
        "server_url": _mcp_url,
        "server_description": (
            "Provides lesson, quiz, milestone, and focus sprint widget envelopes for Arcadia Coach."
        ),
        "allowed_tools": [
            "lesson_catalog",
            "quiz_results",
            "milestone_update",
            "focus_sprint",
        ],
        "require_approval": _require_approval,
    }
)


class ArcadiaAgentContext(AgentContext):
    """Context object supplied to the Arcadia Coach agent."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    store: Annotated[MemoryStore, Field(exclude=True)]
    request_context: dict[str, Any]
    sanitized_input: str | None = None
    web_enabled: bool = False
    reasoning_level: str = "medium"
    attachments: list[Dict[str, Any]] = Field(default_factory=list)


_AGENT_CACHE: dict[Tuple[str, bool], Agent[ArcadiaAgentContext]] = {}

SUPPORTED_MODELS = {
    "gpt-5-nano",
    "gpt-5-mini",
    "gpt-5",
    "gpt-5-codex",
}


def _build_agent(model: str, web_enabled: bool) -> Agent[ArcadiaAgentContext]:
    tools: list[Any] = []
    if model not in {"gpt-5-nano", "gpt-5-codex"}:
        tools.append(file_search)
    if web_enabled:
        tools.append(web_search)
    tools.extend(AGENT_SUPPORT_TOOLS)
    tools.append(mcp_widgets)
    return Agent[ArcadiaAgentContext](
        name="Arcadia Coach",
        instructions=INSTRUCTIONS,
        model=model,
        tools=tools,  # type: ignore[arg-type]
        model_settings=ModelSettings(
            store=True,
        ),
    )


def get_arcadia_agent(model: str | None, web_enabled: bool) -> Agent[ArcadiaAgentContext]:
    """Return a cached Arcadia agent configured for the requested model and web toggle."""
    selected = model or MODEL
    if selected not in SUPPORTED_MODELS:
        selected = MODEL
    cache_key: Tuple[str, bool] = (selected, web_enabled)
    if cache_key not in _AGENT_CACHE:
        _AGENT_CACHE[cache_key] = _build_agent(selected, web_enabled)
    return _AGENT_CACHE[cache_key]
