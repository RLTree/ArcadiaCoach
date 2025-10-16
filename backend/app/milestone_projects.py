"""Goal-aligned milestone project templates (Phase 30)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence

from .learner_profile import (
    FoundationTrack,
    GoalParserInference,
    LearnerProfile,
    MilestoneProject,
)


@dataclass(frozen=True)
class _ProjectTemplate:
    project_id: str
    title: str
    category_keys: tuple[str, ...]
    goal_keywords: tuple[str, ...]
    track_keywords: tuple[str, ...]
    summary: str
    goal_alignment: str
    deliverables: tuple[str, ...]
    evidence_checklist: tuple[str, ...]
    recommended_tools: tuple[str, ...]
    evaluation_focus: tuple[str, ...]
    evaluation_steps: tuple[str, ...]


_TEMPLATES: tuple[_ProjectTemplate, ...] = (
    _ProjectTemplate(
        project_id="frontend-portfolio-feature",
        title="Design & Ship a Portfolio Feature",
        category_keys=("frontend-foundations", "ui-architecture", "frontend", "frontend-experience"),
        goal_keywords=("portfolio", "frontend", "ui", "design"),
        track_keywords=("Frontend", "UI", "Design Systems"),
        summary="Implement '{module_title}' inside a polished UI feature that reflects production-ready interaction patterns for {track_label}.",
        goal_alignment="Connect the feature to your long-term goal by highlighting why it advances {target_outcome}.",
        deliverables=(
            "Ship a {track_label} feature branch that applies '{module_title}' ideas end to end.",
            "Capture annotated screenshots or screen recordings demonstrating accessibility and responsive behaviour for {primary_focus}.",
            "Write design notes that explain state management choices and how they serve {goal}.",
        ),
        evidence_checklist=(
            "Repository link with clear README and setup steps for {primary_technology}.",
            "Before/after visuals or a gif that showcases the {track_label} improvement.",
            "Reflection covering trade-offs, open questions, and next iterations related to {target_outcome}.",
        ),
        recommended_tools=("SwiftUI", "Figma", "VoiceOver", "Instruments"),
        evaluation_focus=(
            "Interface accessibility and responsiveness for {primary_focus}.",
            "State management clarity, testability, and preview support.",
            "Narrative tying the feature to the learner's goal: {goal}.",
        ),
        evaluation_steps=(
            "Run through the feature with VoiceOver and reduced motion settings to confirm accessibility.",
            "Collect feedback from at least one target user or peer focused on {primary_focus} improvements and note takeaways.",
            "Summarise measurable improvements versus the previous state and relate them to {target_outcome}.",
        ),
    ),
    _ProjectTemplate(
        project_id="backend-service-slice",
        title="Ship a Production-Ready Service Slice",
        category_keys=("backend-foundations", "architecture-systems", "backend", "backend-systems"),
        goal_keywords=("backend", "api", "service", "platform"),
        track_keywords=("Architecture", "Backend", "Delivery"),
        summary="Develop a service endpoint or workflow that demonstrates reliability, observability, and documentation for {track_label}.",
        goal_alignment="Show how this service slice advances your target outcome: {target_outcome}.",
        deliverables=(
            "Implement a {primary_technology} service module that applies '{module_title}' practices.",
            "Document API contracts or sequence diagrams explaining the workflow for {track_label}.",
            "Author an operations checklist covering deployment, environment variables, and rollback procedures.",
        ),
        evidence_checklist=(
            "Link to the service repo or sandbox environment demonstrating {primary_technology}.",
            "Test report or CI run showing green builds and resiliency checks.",
            "Observability snapshot (logs, metrics, traces) validating the happy path and one failure scenario.",
        ),
        recommended_tools=("FastAPI", "pytest", "PostgreSQL", "Grafana"),
        evaluation_focus=(
            "Code quality and test coverage aligned to '{module_title}'.",
            "Operational readiness (documentation, observability hooks, runbooks).",
            "Alignment to the learner's platform goal: {goal}.",
        ),
        evaluation_steps=(
            "Run load or integration tests for the {primary_technology} service and capture results.",
            "Validate error handling paths with synthetic failures and log remediation notes.",
            "Document the release plan and share it with Arcadia Coach for feedback on {target_outcome}.",
        ),
    ),
    _ProjectTemplate(
        project_id="data-insight-report",
        title="Produce a Goal-Aligned Data Insight Report",
        category_keys=("data-manipulation", "ml-foundations", "data", "analytics"),
        goal_keywords=("data", "analysis", "machine learning", "ml", "analytics"),
        track_keywords=("Data", "ML", "Analytics"),
        summary="Create a reproducible notebook or report that operationalises '{module_title}' for {track_label} work.",
        goal_alignment="Frame the insights so they advance: {target_outcome}.",
        deliverables=(
            "Cleaned dataset or documented pipeline with schema notes focused on {primary_technology}.",
            "Exploratory notebook highlighting three compelling findings connected to {goal}.",
            "Executive summary translating technical results into next steps for {track_focus}.",
        ),
        evidence_checklist=(
            "Notebook link with instructions to rerun analyses on {track_technologies}.",
            "Charts or tables embedded in the summary referencing {primary_focus}.",
            "Reflection on data limitations and follow-up experiments tied to {target_outcome}.",
        ),
        recommended_tools=("pandas", "NumPy", "Altair", "Jupyter"),
        evaluation_focus=(
            "Data quality and validation practices for {primary_focus}.",
            "Narrative clarity for stakeholders focused on {goal}.",
            "Reproducibility of the analysis workflow across {track_technologies}.",
        ),
        evaluation_steps=(
            "Run data validation checks on the {primary_technology} pipeline and log anomalies.",
            "Share the report with a peer/user and capture feedback highlights mapped to {target_outcome}.",
            "Define at least two follow-up experiments informed by the findings and document next steps.",
        ),
    ),
    _ProjectTemplate(
        project_id="automation-workflow",
        title="Build an Automation Workflow",
        category_keys=("python-foundations", "productivity-automation", "automation", "productivity", "scripting"),
        goal_keywords=("automation", "productivity", "workflow", "tooling"),
        track_keywords=("Productivity", "Automation", "Scripting"),
        summary="Automate a repetitive task using '{module_title}' patterns to accelerate {track_label} work.",
        goal_alignment="Explain how this automation clears space for progress toward {target_outcome}.",
        deliverables=(
            "Executable script or command-line tool with configuration options tuned for {primary_technology}.",
            "Usage guide or tutorial aimed at the intended audience highlighting {goal}.",
            "Before/after metrics estimating time saved or errors avoided in {track_focus}.",
        ),
        evidence_checklist=(
            "Repository link with instructions and sample configuration for {primary_technology}.",
            "Demo recording or logs from a successful automation run aligned to {goal}.",
            "Retro documenting lessons learned and remaining edge cases impacting {target_outcome}.",
        ),
        recommended_tools=("Python", "uv", "pytest", "Makefile"),
        evaluation_focus=(
            "Reliability and error handling across {track_label} workflows.",
            "Documentation clarity for teammates engaged in {goal}.",
            "Demonstrated impact (time saved, errors reduced) toward {target_outcome}.",
        ),
        evaluation_steps=(
            "Run the automation on two scenarios drawn from {use_case} and log results.",
            "Log and review failure cases; document mitigations tied to {primary_focus}.",
            "Share the workflow with Arcadia Coach to confirm alignment to upcoming milestones for {goal}.",
        ),
    ),
)


class _FormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _format_text(value: Optional[str], context: Mapping[str, str]) -> Optional[str]:
    if not value or not context:
        return value
    try:
        return value.format_map(_FormatDict(context))
    except Exception:
        return value


def _format_list(values: Iterable[str], context: Mapping[str, str]) -> list[str]:
    formatted: list[str] = []
    for entry in values:
        if not entry:
            continue
        text = _format_text(entry, context)
        if text:
            formatted.append(text)
    return formatted


def _text_matches(text: str | None, keywords: Iterable[str]) -> int:
    if not text:
        return 0
    lowered = text.lower()
    return sum(1 for keyword in keywords if keyword and keyword.lower() in lowered)


def _track_matches(tracks: Sequence[FoundationTrack], keywords: Iterable[str]) -> int:
    if not tracks:
        return 0
    matches = 0
    lowered_keywords = {keyword.lower() for keyword in keywords if keyword}
    for track in tracks:
        label = track.label.lower()
        focus = " ".join(track.focus_areas).lower()
        tech = " ".join(track.technologies).lower()
        if any(keyword in label for keyword in lowered_keywords):
            matches += 1
        if any(keyword in focus for keyword in lowered_keywords):
            matches += 1
        if any(keyword in tech for keyword in lowered_keywords):
            matches += 1
    return matches


def select_milestone_project(
    profile: LearnerProfile,
    category_key: str,
    category_label: Optional[str] = None,
    *,
    goal_inference: Optional[GoalParserInference] = None,
    format_context: Optional[Mapping[str, str]] = None,
) -> Optional[MilestoneProject]:
    """Pick a project template that best fits the learner's goals and track focus."""

    goal_text = " ".join(
        filter(
            None,
            [
                getattr(profile, "goal", "") or "",
                getattr(profile, "use_case", "") or "",
                getattr(profile, "strengths", "") or "",
            ],
        )
    )
    tracks: Sequence[FoundationTrack] = goal_inference.tracks if goal_inference and goal_inference.tracks else ()
    normalized_key = category_key.lower()
    normalized_label = (category_label or "").lower()

    best_template: Optional[_ProjectTemplate] = None
    best_score = -1

    for template in _TEMPLATES:
        score = 0
        template_keys = {key.lower() for key in template.category_keys}
        if normalized_key in template_keys:
            score += 4
        elif any(key in normalized_key or normalized_key in key for key in template_keys):
            score += 3
        elif normalized_label and any(
            key.replace("-", " ") in normalized_label or normalized_label in key.replace("-", " ")
            for key in template_keys
        ):
            score += 2
        score += _text_matches(goal_text, template.goal_keywords)
        score += _track_matches(tracks, template.track_keywords)
        if score > best_score:
            best_template = template
            best_score = score

    if best_template is None:
        project = MilestoneProject(
            project_id="general-capstone",
            title="Create a Goal-Aligned Capstone",
            goal_alignment="Connect the deliverable back to your goal: {goal}.",
            summary="Produce a tangible artefact that shows measurable progress on your primary learning objective.",
            deliverables=[
                "Produce an artefact (repository, design, notebook, or demo) demonstrating '{module_title}'.",
                "Write a reflection covering decisions, blockers, and next steps that support {target_outcome}.",
            ],
            evidence_checklist=[
                "Link to the artefact or supporting materials.",
                "Short write-up summarising outcomes and impact.",
            ],
            recommended_tools=[],
            evaluation_focus=[
                "Clarity of purpose & alignment to the stated goal {goal}.",
                "Depth of technical execution for {track_label}.",
                "Quality of documentation & reflection describing {target_outcome}.",
            ],
            evaluation_steps=[
                "List clear success criteria and evaluate each against {target_outcome}.",
                "Capture feedback from one peer or stakeholder and record takeaways.",
                "Outline how this work influences your next milestone on {goal}.",
            ],
        )
    else:
        project = MilestoneProject(
            project_id=best_template.project_id,
            title=best_template.title,
            goal_alignment=best_template.goal_alignment,
            summary=best_template.summary,
            deliverables=list(best_template.deliverables),
            evidence_checklist=list(best_template.evidence_checklist),
            recommended_tools=list(best_template.recommended_tools),
            evaluation_focus=list(best_template.evaluation_focus),
            evaluation_steps=list(best_template.evaluation_steps),
        )

    if format_context:
        safe_context = {key: value for key, value in format_context.items() if isinstance(value, str)}
        if safe_context:
            project = MilestoneProject(
                project_id=project.project_id,
                title=_format_text(project.title, safe_context) or project.title,
                goal_alignment=_format_text(project.goal_alignment, safe_context) or project.goal_alignment,
                summary=_format_text(project.summary, safe_context),
                deliverables=_format_list(project.deliverables, safe_context),
                evidence_checklist=_format_list(project.evidence_checklist, safe_context),
                recommended_tools=_format_list(project.recommended_tools, safe_context),
                evaluation_focus=_format_list(project.evaluation_focus, safe_context),
                evaluation_steps=_format_list(project.evaluation_steps, safe_context),
            )

    return project


__all__ = ["select_milestone_project"]
