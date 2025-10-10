"""Arcadia Coach agent configuration."""

from __future__ import annotations

from typing import Annotated, Any

from agents import Agent, AgentContext, FileSearchTool, HostedMCPTool, ModelSettings, WebSearchTool
from openai.types.shared.reasoning import Reasoning
from pydantic import ConfigDict, Field

from .constants import INSTRUCTIONS, MODEL
from .memory_store import MemoryStore
from .tools import elo_update, progress_advance, progress_start

# Tool instances ---------------------------------------------------------------

file_search = FileSearchTool(
    vector_store_ids=["vs_68e81d741f388191acdaabce2f92b7d5"],
)

web_search = WebSearchTool(
    search_context_size="high",
    user_location={"type": "approximate"},
)

mcp_widgets = HostedMCPTool(
    tool_config={
        "type": "mcp",
        "server_label": "Arcadia_Coach_Widgets",
        "server_url": "https://nonsidereal-monoeciously-delaine.ngrok-free.dev/mcp",
        "server_description": (
            "Provides lesson, quiz, milestone, and focus sprint widget envelopes for Arcadia Coach."
        ),
        "allowed_tools": [
            "lesson_catalog",
            "quiz_results",
            "milestone_update",
            "focus_sprint",
        ],
        "require_approval": "always",
    }
)


class ArcadiaAgentContext(AgentContext):
    """Context object supplied to the Arcadia Coach agent."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    store: Annotated[MemoryStore, Field(exclude=True)]
    request_context: dict[str, Any]
    sanitized_input: str | None = None


arcadia_agent = Agent[ArcadiaAgentContext](
    name="Arcadia Coach",
    instructions=INSTRUCTIONS,
    model=MODEL,
    tools=[file_search, web_search, mcp_widgets, progress_start, progress_advance, elo_update],  # type: ignore[arg-type]
    model_settings=ModelSettings(
        store=True,
        reasoning=Reasoning(
            effort="medium",
            summary="auto",
        ),
    ),
)
