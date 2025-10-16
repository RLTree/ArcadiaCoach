"""Goal-aligned milestone project templates (Phase 30)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

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
        summary="Implement a polished UI feature that reflects production-ready interaction patterns.",
        goal_alignment="Connect the feature to your long-term goal by highlighting why this UI matters for {goal}.",
        deliverables=(
            "Feature branch or sample project with compiled build artifacts.",
            "Annotated screenshots or screen recordings demonstrating the UX flow.",
            "Design notes describing state management, accessibility, and responsive behaviour.",
        ),
        evidence_checklist=(
            "Repository link with clear README and setup steps.",
            "Before/after visuals or a gif that showcase the improvement.",
            "Written reflection covering trade-offs, open questions, and next iterations.",
        ),
        recommended_tools=("SwiftUI", "Figma", "VoiceOver", "Instruments"),
        evaluation_focus=(
            "Interface accessibility and responsiveness.",
            "State management clarity and testability.",
            "Narrative tying the feature to the learner's goal.",
        ),
        evaluation_steps=(
            "Run through the feature with VoiceOver and a reduced motion setting.",
            "Collect feedback from at least one target user or peer and note takeaways.",
            "Summarise the measurable improvement versus the previous state.",
        ),
    ),
    _ProjectTemplate(
        project_id="backend-service-slice",
        title="Ship a Production-Ready Service Slice",
        category_keys=("backend-foundations", "architecture-systems", "backend", "backend-systems"),
        goal_keywords=("backend", "api", "service", "platform"),
        track_keywords=("Architecture", "Backend", "Delivery"),
        summary="Develop a service endpoint or workflow that demonstrates reliability, observability, and documentation.",
        goal_alignment="Show how this service slice advances your target outcome: {goal}.",
        deliverables=(
            "Service repository or module with automated tests.",
            "API contract or sequence diagram explaining the workflow.",
            "Operations checklist covering deployment, environment variables, and rollback.",
        ),
        evidence_checklist=(
            "Link to service repo or sandbox environment.",
            "Test report or CI run showing green builds.",
            "Observability snapshot (logs, metrics) validating the happy path.",
        ),
        recommended_tools=("FastAPI", "pytest", "PostgreSQL", "Grafana"),
        evaluation_focus=(
            "Code quality and test coverage.",
            "Operational readiness (documentation, observability hooks).",
            "Alignment to learner's stated platform goals.",
        ),
        evaluation_steps=(
            "Run load or integration tests and capture results.",
            "Validate error handling paths with synthetic failures.",
            "Document the release plan and share it with Arcadia Coach for feedback.",
        ),
    ),
    _ProjectTemplate(
        project_id="data-insight-report",
        title="Produce a Goal-Aligned Data Insight Report",
        category_keys=("data-manipulation", "ml-foundations", "data", "analytics"),
        goal_keywords=("data", "analysis", "machine learning", "ml", "analytics"),
        track_keywords=("Data", "ML", "Analytics"),
        summary="Create a reproducible notebook or report that surfaces actionable insights for your target audience.",
        goal_alignment="Frame the insights to support your long-term goal: {goal}.",
        deliverables=(
            "Cleaned dataset (or documented data pipeline) with schema notes.",
            "Exploratory notebook highlighting three compelling findings.",
            "Executive summary translating technical results into next steps.",
        ),
        evidence_checklist=(
            "Notebook link with clear instructions to rerun analyses.",
            "Charts or tables embedded in the summary.",
            "Reflection on data limitations and follow-up experiments.",
        ),
        recommended_tools=("pandas", "NumPy", "Altair", "Jupyter"),
        evaluation_focus=(
            "Data quality and validation practices.",
            "Narrative clarity for non-technical stakeholders.",
            "Reproducibility of the analysis workflow.",
        ),
        evaluation_steps=(
            "Run data validation checks and log any anomalies.",
            "Share the report with a peer/user and capture feedback highlights.",
            "Define at least two follow-up experiments informed by the findings.",
        ),
    ),
    _ProjectTemplate(
        project_id="automation-workflow",
        title="Build an Automation Workflow",
        category_keys=("python-foundations", "productivity-automation", "automation", "productivity", "scripting"),
        goal_keywords=("automation", "productivity", "workflow", "tooling"),
        track_keywords=("Productivity", "Automation", "Scripting"),
        summary="Automate a repetitive task with a reliable, well-documented script or tool.",
        goal_alignment="Explain how this automation clears space for progress toward {goal}.",
        deliverables=(
            "Executable script or command-line tool with configuration options.",
            "Usage guide or tutorial aimed at the intended audience (including you).",
            "Before/after metrics estimating time saved or errors avoided.",
        ),
        evidence_checklist=(
            "Repository link with instructions and sample configuration.",
            "Demo recording or logs from a successful automation run.",
            "Retro documenting lessons learned and remaining edge cases.",
        ),
        recommended_tools=("Python", "uv", "pytest", "Makefile"),
        evaluation_focus=(
            "Reliability and error handling.",
            "Documentation clarity.",
            "Demonstrated impact (time saved, errors reduced).",
        ),
        evaluation_steps=(
            "Run the automation on two different data sets or scenarios.",
            "Log and review failure cases; document mitigations.",
            "Share the workflow with Arcadia Coach to confirm alignment to next milestones.",
        ),
    ),
)


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
        # Fallback project that still references learner goals.
        return MilestoneProject(
            project_id="general-capstone",
            title="Create a Goal-Aligned Capstone",
            goal_alignment=f"Connect the deliverable back to your goal: {profile.goal or 'describe it succinctly'}.",
            summary="Produce a tangible artefact that shows measurable progress on your primary learning objective.",
            deliverables=[
                "Primary artefact (repository, design, notebook, or demo).",
                "Reflection covering decisions, blockers, and next steps.",
            ],
            evidence_checklist=[
                "Link to the artefact or supporting materials.",
                "Short write-up summarising outcomes and impact.",
            ],
            recommended_tools=[],
            evaluation_focus=[
                "Clarity of purpose & alignment to the stated goal.",
                "Depth of technical execution.",
                "Quality of documentation & reflection.",
            ],
            evaluation_steps=[
                "List clear success criteria and evaluate each.",
                "Capture feedback from one peer or stakeholder.",
                "Outline how this work influences your next milestone.",
            ],
        )

    goal_alignment = best_template.goal_alignment.format(goal=profile.goal or "your goal")

    return MilestoneProject(
        project_id=best_template.project_id,
        title=best_template.title,
        goal_alignment=goal_alignment,
        summary=best_template.summary,
        deliverables=list(best_template.deliverables),
        evidence_checklist=list(best_template.evidence_checklist),
        recommended_tools=list(best_template.recommended_tools),
        evaluation_focus=list(best_template.evaluation_focus),
        evaluation_steps=list(best_template.evaluation_steps),
    )


__all__ = ["select_milestone_project"]
