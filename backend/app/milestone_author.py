"""MCP-backed milestone brief author integration (Phase 31)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

import httpx
from pydantic import BaseModel, Field, ValidationError

from .config import Settings
from .learner_profile import MilestoneBrief, MilestoneProject

logger = logging.getLogger(__name__)

MilestoneAuthorMode = Literal["off", "fallback", "primary"]


class MilestoneAuthorProjectPayload(BaseModel):
    project_id: Optional[str] = None
    title: Optional[str] = None
    goal_alignment: Optional[str] = None
    summary: Optional[str] = None
    deliverables: List[str] = Field(default_factory=list)
    evidence_checklist: List[str] = Field(default_factory=list)
    recommended_tools: List[str] = Field(default_factory=list)
    evaluation_focus: List[str] = Field(default_factory=list)
    evaluation_steps: List[str] = Field(default_factory=list)


class MilestoneAuthorBriefPayload(BaseModel):
    headline: str
    summary: Optional[str] = None
    objectives: List[str] = Field(default_factory=list)
    deliverables: List[str] = Field(default_factory=list)
    success_criteria: List[str] = Field(default_factory=list)
    external_work: List[str] = Field(default_factory=list)
    capture_prompts: List[str] = Field(default_factory=list)
    kickoff_steps: List[str] = Field(default_factory=list)
    coaching_prompts: List[str] = Field(default_factory=list)
    elo_focus: List[str] = Field(default_factory=list)
    resources: List[str] = Field(default_factory=list)
    project: Optional[MilestoneAuthorProjectPayload] = None
    rationale: Optional[str] = None
    authored_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model: Optional[str] = None
    reasoning_effort: Optional[str] = None
    source: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class MilestoneAuthorResponsePayload(BaseModel):
    brief: MilestoneAuthorBriefPayload
    latency_ms: int
    model: Optional[str] = None
    reasoning_effort: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)

    def to_domain(self) -> Tuple[MilestoneBrief, Optional[MilestoneProject]]:
        project_payload = self.brief.project
        project: Optional[MilestoneProject] = None
        if project_payload and any(
            (
                project_payload.project_id,
                project_payload.title,
                project_payload.summary,
                project_payload.goal_alignment,
                project_payload.deliverables,
                project_payload.evidence_checklist,
            )
        ):
            project = MilestoneProject(
                project_id=project_payload.project_id or "agent-generated-project",
                title=project_payload.title or self.brief.headline,
                goal_alignment=project_payload.goal_alignment or "",
                summary=project_payload.summary,
                deliverables=list(project_payload.deliverables),
                evidence_checklist=list(project_payload.evidence_checklist),
                recommended_tools=list(project_payload.recommended_tools),
                evaluation_focus=list(project_payload.evaluation_focus),
                evaluation_steps=list(project_payload.evaluation_steps),
            )
        brief = MilestoneBrief(
            headline=self.brief.headline,
            summary=self.brief.summary,
            objectives=list(self.brief.objectives),
            deliverables=list(self.brief.deliverables),
            success_criteria=list(self.brief.success_criteria),
            external_work=list(self.brief.external_work),
            capture_prompts=list(self.brief.capture_prompts),
            prerequisites=[],
            elo_focus=list(self.brief.elo_focus),
            resources=list(self.brief.resources),
            kickoff_steps=list(self.brief.kickoff_steps),
            coaching_prompts=list(self.brief.coaching_prompts),
            project=project,
            rationale=self.brief.rationale,
            authored_at=self.brief.authored_at,
            authored_by_model=self.brief.model or self.model,
            reasoning_effort=self.brief.reasoning_effort or self.reasoning_effort,
            source=self.brief.source or "agent",
            warnings=list(set(self.brief.warnings + self.warnings)),
        )
        return brief, project


class MilestoneAuthorRequestPayload(BaseModel):
    username: Optional[str] = None
    goal: Optional[str] = None
    use_case: Optional[str] = None
    strengths: Optional[str] = None
    category_key: Optional[str] = None
    category_label: Optional[str] = None
    module_title: str
    module_summary: Optional[str] = None
    module_objectives: List[str] = Field(default_factory=list)
    module_deliverables: List[str] = Field(default_factory=list)
    goal_tracks: List[Dict[str, Any]] = Field(default_factory=list)
    milestone_history: List[Dict[str, Any]] = Field(default_factory=list)
    milestone_progress: Optional[Dict[str, Any]] = None
    schedule_notes: Optional[str] = None
    timezone: Optional[str] = None
    previous_brief: Optional[Dict[str, Any]] = None


class MilestoneAuthorError(RuntimeError):
    """Raised when the milestone author agent fails."""


@dataclass(frozen=True)
class MilestoneAuthorResult:
    brief: MilestoneBrief
    project: Optional[MilestoneProject]
    latency_ms: int
    warnings: List[str]


def resolve_mode(settings: Settings) -> MilestoneAuthorMode:
    value = getattr(settings, "arcadia_milestone_author_mode", "fallback")
    if value not in ("off", "fallback", "primary"):
        return "fallback"
    return value  # type: ignore[return-value]


def should_author(settings: Settings) -> bool:
    return resolve_mode(settings) != "off"


def author_milestone_brief(
    settings: Settings,
    payload: MilestoneAuthorRequestPayload,
    *,
    client: Optional[httpx.Client] = None,
) -> MilestoneAuthorResult:
    mode = resolve_mode(settings)
    if mode == "off":
        raise MilestoneAuthorError("Milestone authoring is disabled.")

    url = settings.arcadia_mcp_url.rstrip("/")
    endpoint = f"{url}/author/milestone"
    timeout_seconds = max(getattr(settings, "arcadia_milestone_author_timeout_ms", 12000), 1000) / 1000
    local_client = client or httpx.Client(timeout=timeout_seconds)
    close_client = client is None
    try:
        response = local_client.post(endpoint, json=payload.model_dump(mode="json"))
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise MilestoneAuthorError(f"MCP milestone author call failed: {exc}") from exc
    finally:
        if close_client:
            local_client.close()

    try:
        data = response.json()
        parsed = MilestoneAuthorResponsePayload.model_validate(data)
    except (ValueError, ValidationError) as exc:
        raise MilestoneAuthorError(f"MCP milestone author returned invalid payload: {exc}") from exc

    brief, project = parsed.to_domain()
    logger.debug(
        "Milestone author succeeded (module=%s, latency_ms=%s)",
        payload.module_title,
        parsed.latency_ms,
    )
    return MilestoneAuthorResult(
        brief=brief,
        project=project,
        latency_ms=parsed.latency_ms,
        warnings=parsed.warnings,
    )


__all__ = [
    "MilestoneAuthorMode",
    "MilestoneAuthorRequestPayload",
    "MilestoneAuthorResult",
    "author_milestone_brief",
    "resolve_mode",
    "should_author",
    "MilestoneAuthorError",
]
