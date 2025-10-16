"""Utility tools exposed to the Arcadia Coach agent."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Literal, Optional

from agents import function_tool
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .learner_profile import (
    AssessmentSection,
    AssessmentTask,
    CurriculumSchedule,
    EloCategoryDefinition,
    EloCategoryPlan,
    EloRubricBand,
    FoundationModuleReference,
    FoundationTrack,
    LearnerProfile,
    MilestoneBrief,
    MilestonePrerequisite,
    profile_store,
    slice_schedule,
)
from .telemetry import emit_event
from .vector_memory import learner_memory
from .agent_models import (
    AssessmentCategoryOutcomePayload,
    AssessmentGradingPayload,
    AssessmentRubricEvaluationPayload,
    AssessmentTaskGradePayload,
    CurriculumModulePayload,
    CurriculumSchedulePayload,
    CategoryPacingPayload,
    EloCategoryDefinitionPayload,
    EloCategoryPlanPayload,
    EloRubricBandPayload,
    AssessmentSectionPayload,
    FoundationModuleReferencePayload,
    FoundationTrackPayload,
    GoalParserInferencePayload,
    LearnerEloCategoryPlanResponse,
    LearnerMemoryWriteResponse,
    LearnerProfileGetResponse,
    LearnerProfilePayload,
    LearnerProfileUpdateResponse,
    OnboardingAssessmentPayload,
    OnboardingAssessmentTaskPayload,
    OnboardingCurriculumPayload,
    ScheduleRationaleEntryPayload,
    ScheduleWarningPayload,
    ScheduleSlicePayload,
    MilestoneBriefPayload,
    MilestoneCompletionPayload,
    MilestoneProjectPayload,
    MilestonePrerequisitePayload,
    MilestoneRequirementPayload,
    MilestoneProgressPayload,
    MilestoneGuidancePayload,
    SequencedWorkItemPayload,
    SkillRatingPayload,
)


def _progress_payload(idx: int, total: int) -> Dict[str, Any]:
    display = min(idx + 1, total) if total > 0 else 0
    has_next = display < total
    return {
        "progress": {
            "idx": idx,
            "display": display,
            "total": total,
            "has_next": has_next,
        }
    }


@function_tool(strict_mode=False)
def progress_start(total: int) -> Dict[str, Any]:
    """Initialise a multi-step progress tracker."""
    if total <= 0:
        total = 1
    return _progress_payload(idx=0, total=total)


@function_tool(strict_mode=False)
def progress_advance(idx: int, total: int) -> Dict[str, Any]:
    """Advance the progress tracker and surface the updated status."""
    if total <= 0:
        total = 1
    next_idx = min(idx + 1, total - 1)
    return _progress_payload(idx=next_idx, total=total)

def _schedule_payload(
    schedule: Optional[CurriculumSchedule],
    *,
    elo_snapshot: Optional[Dict[str, int]] = None,
    elo_plan: Optional[EloCategoryPlan] = None,
) -> Optional[CurriculumSchedulePayload]:
    if schedule is None:
        return None
    tz_name = getattr(schedule, "timezone", None) or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = timezone.utc
        tz_name = "UTC"
    anchor_date = schedule.generated_at.astimezone(tz).date()
    warnings = [
        ScheduleWarningPayload(
            code=getattr(warning, "code", "refresh_failed"),
            message=getattr(warning, "message", ""),
            detail=getattr(warning, "detail", None),
            generated_at=getattr(warning, "generated_at", schedule.generated_at),
        )
    for warning in getattr(schedule, "warnings", [])
    ]
    snapshot = {
        key: int(value)
        for key, value in (elo_snapshot or {}).items()
        if isinstance(key, str) and isinstance(value, (int, float))
    }
    plan_labels = {}
    if elo_plan and getattr(elo_plan, "categories", None):
        plan_labels = {
            category.key: getattr(category, "label", category.key)
            for category in elo_plan.categories
            if getattr(category, "key", None)
        }
    items: List[SequencedWorkItemPayload] = []

    def _deduplicate_strings(values: Iterable[str]) -> List[str]:
        return list(dict.fromkeys([value.strip() for value in values if isinstance(value, str) and value.strip()]))

    def _normalize_requirements(*sources: Iterable[Any]) -> List[Any]:
        combined: List[Any] = []
        seen: set[tuple[str, int]] = set()
        for source in sources:
            for requirement in source or []:
                key = getattr(requirement, "category_key", None)
                if not key:
                    continue
                try:
                    minimum = int(getattr(requirement, "minimum_rating", 0) or 0)
                except (TypeError, ValueError):
                    minimum = 0
                identifier = (key, minimum)
                if identifier in seen:
                    continue
                combined.append(requirement)
                seen.add(identifier)
        return combined

    def _requirement_label(requirement: Any) -> str:
        label = getattr(requirement, "category_label", "") or ""
        key = getattr(requirement, "category_key", "")
        if label:
            return label
        if key and key in plan_labels:
            return plan_labels[key]
        return key or "Milestone prerequisite"

    def _locked_reason(
        target: Any,
        all_items: List[Any],
        requirements: Iterable[Any],
    ) -> tuple[Optional[str], List[tuple[Any, int]]]:
        kind = getattr(target, "kind", None)
        status = getattr(target, "launch_status", "pending")
        if kind != "milestone":
            return None, []
        incomplete = [
            other
            for other in all_items
            if getattr(other, "item_id", None) != getattr(target, "item_id", None)
            and getattr(other, "recommended_day_offset", 0) <= getattr(target, "recommended_day_offset", 0)
            and getattr(other, "kind", None) != "milestone"
            and getattr(other, "launch_status", "pending") != "completed"
        ]
        if status == "completed":
            return None, []
        if incomplete:
            return "Complete earlier lessons and quizzes before unlocking this milestone.", []
        unmet: List[tuple[Any, int]] = []
        for requirement in requirements:
            key = getattr(requirement, "category_key", None)
            minimum = getattr(requirement, "minimum_rating", None)
            if not key or minimum is None:
                continue
            try:
                required = int(minimum)
            except (TypeError, ValueError):
                continue
            current = int(snapshot.get(key, 0))
            if current < required:
                unmet.append((requirement, current))
        if unmet:
            segments = [
                f"{_requirement_label(req)} {current}/{getattr(req, 'minimum_rating', 0)}"
                for req, current in unmet[:3]
            ]
            reason = "Build your ratings to unlock this milestone: " + "; ".join(segments)
            return reason, unmet
        return None, []

    item_lookup = {entry.item_id: entry for entry in schedule.items}
    completions_lookup = {
        entry.item_id: entry for entry in getattr(schedule, "milestone_completions", []) or []
    }

    def _milestone_guidance_payload(
        item: Any,
        brief: MilestoneBrief | None,
        progress: Any,
        locked_reason: Optional[str],
        unmet_requirements: List[tuple[Any, int]],
    ) -> Optional[MilestoneGuidancePayload]:
        if getattr(item, "kind", None) != "milestone":
            return None
        now = datetime.now(tz)
        badges: List[str] = []
        next_actions: List[str] = []
        warnings_local: List[str] = []
        state: Literal["locked", "ready", "in_progress", "awaiting_submission", "completed"]
        summary: str
        last_update_at: Optional[datetime] = None

        completion = completions_lookup.get(getattr(item, "item_id", ""))
        if progress and getattr(progress, "recorded_at", None):
            last_update_at = progress.recorded_at
        if completion and completion.recorded_at:
            last_update_at = (
                max(last_update_at, completion.recorded_at) if last_update_at else completion.recorded_at
            )

        progress_status = getattr(progress, "project_status", None)
        progress_next_steps = list(getattr(progress, "next_steps", []) or [])

        if getattr(item, "launch_status", "pending") == "completed":
            if completion:
                state = "completed"
                outcome = getattr(completion, "evaluation_outcome", None)
                if outcome == "passed":
                    summary = "Milestone completed and passed. Celebrate the win and review follow-up actions."
                    badges.extend(["Completed", "Passed"])
                elif outcome == "needs_revision":
                    summary = "Milestone submitted. Address revision notes to fully unlock the milestone."
                    badges.extend(["Completed", "Needs revision"])
                    warnings_local.append("Revisit the evaluation notes to close remaining gaps.")
                    if getattr(completion, "evaluation_notes", None):
                        next_actions.append("Review evaluator notes and capture your remediation plan.")
                elif outcome == "failed":
                    summary = "Milestone submission needs major changes before it counts toward progression."
                    badges.extend(["Completed", "Requires redo"])
                    warnings_local.append("Rebuild the milestone deliverable using the evaluation checklist.")
                    next_actions.append("Schedule time to rebuild the deliverable and resubmit.")
                else:
                    summary = "Milestone completed. Review feedback and celebrate the win."
                    badges.extend(["Completed"])
                if not completion.notes:
                    next_actions.append("Add a short reflection so refreshers stay grounded.")
                has_artifacts = bool(completion.attachment_ids or completion.external_links)
                if (brief and (brief.deliverables or brief.external_work)) and not has_artifacts:
                    warnings_local.append("No artefacts attached. Add links or uploads for grading context.")
                    next_actions.append("Upload at least one artefact (link or attachment).")
                if getattr(completion, "project_status", None) == "blocked":
                    warnings_local.append("Milestone flagged as blocked during completion. Document blockers.")
                if getattr(completion, "evaluation_notes", None):
                    next_actions.append("Summarise how you'll address the evaluation feedback.")
            else:
                state = "awaiting_submission"
                summary = "Marked complete, but no submission details yet."
                badges.extend(["Completed"])
                warnings_local.append("Provide notes or artefacts so Arcadia Coach can confirm completion.")
                next_actions.append("Add notes, links, or attachments for this milestone.")
        elif getattr(item, "launch_status", "pending") == "in_progress":
            state = "in_progress"
            summary = "Milestone in progress. Capture blockers and artefacts as you go."
            badges.append("In progress")
            launch_time = getattr(item, "last_launched_at", None)
            if launch_time:
                last_update_at = max(last_update_at, launch_time) if last_update_at else launch_time
                if now - launch_time >= timedelta(hours=48):
                    warnings_local.append("Milestone has been active for over 48 hours.")
                    next_actions.append("Log progress or request support from Arcadia Coach.")
            if progress and (progress.notes or progress.external_links or progress.attachment_ids):
                badges.append("Progress logged")
            else:
                next_actions.append("Log quick notes or links to capture progress.")
            if progress_status == "blocked":
                warnings_local.append("Marked as blocked — capture blockers and reach out for support.")
                next_actions.append("Ask Arcadia Coach for help resolving the blocker.")
            elif progress_status == "ready_for_review":
                badges.append("Ready for review")
                next_actions.append("Share artefacts and submit for evaluation.")
            elif progress_status == "building":
                next_actions.append("Continue building and update progress notes after each session.")
            if progress_next_steps:
                next_actions.extend(progress_next_steps[:2])
            if brief and brief.coaching_prompts:
                next_actions.extend(list(brief.coaching_prompts)[:2])
        else:
            if unmet_requirements:
                state = "locked"
                summary = "Raise your ratings before starting this milestone."
                badges.append("Locked")
                for requirement, current in unmet_requirements[:3]:
                    minimum = getattr(requirement, "minimum_rating", 0)
                    label = _requirement_label(requirement)
                    next_actions.append(f"Reach {minimum} in {label} (currently {current}).")
                    rationale = getattr(requirement, "rationale", None)
                    if rationale:
                        warnings_local.append(rationale)
                if brief and brief.requirements:
                    warnings_local.append("Meet the milestone requirements highlighted in the brief.")
            elif locked_reason:
                state = "locked"
                summary = "Finish prerequisite lessons/quizzes before starting."
                badges.append("Locked")
                incomplete = [
                    prereq.title
                    for prereq in (brief.prerequisites if brief and brief.prerequisites else _prerequisites_for_brief(brief, item))
                    if (prereq.status if hasattr(prereq, "status") else "pending") != "completed"
                ]
                if incomplete:
                    next_actions.append(f"Complete: {', '.join(incomplete[:3])}")
            else:
                state = "ready"
                summary = "Milestone ready to launch when you have focus time."
                badges.append("Ready")
                if brief and brief.kickoff_steps:
                    next_actions.extend(list(brief.kickoff_steps)[:3])
                else:
                    next_actions.append("Block 60–90 minutes for focused work.")
                if brief and brief.coaching_prompts:
                    next_actions.append(brief.coaching_prompts[0])
                if brief and brief.project and brief.project.evidence_checklist:
                    next_actions.append(f"Prep evidence: {brief.project.evidence_checklist[0]}")

        badges = _deduplicate_strings(badges)
        next_actions = _deduplicate_strings(next_actions)[:5]
        warnings_local = _deduplicate_strings(warnings_local)[:3]

        return MilestoneGuidancePayload(
            state=state,
            summary=summary,
            badges=badges,
            next_actions=next_actions,
            warnings=warnings_local,
            last_update_at=last_update_at,
        )

    def _prerequisites_for_brief(
        brief: MilestoneBrief | None,
        item: Any,
    ) -> List[MilestonePrerequisitePayload]:
        prerequisites: List[MilestonePrerequisite] = []
        if brief and brief.prerequisites:
            prerequisites = list(brief.prerequisites)
        elif getattr(item, "prerequisites", None):
            prerequisites = [
                MilestonePrerequisite(
                    item_id=prereq_id,
                    title=getattr(item_lookup.get(prereq_id), "title", prereq_id),
                    kind=getattr(item_lookup.get(prereq_id), "kind", "lesson"),
                    status=getattr(item_lookup.get(prereq_id), "launch_status", "pending"),
                    recommended_day_offset=getattr(item_lookup.get(prereq_id), "recommended_day_offset", None),
                )
                for prereq_id in getattr(item, "prerequisites", [])
            ]

        payload: List[MilestonePrerequisitePayload] = []
        for entry in prerequisites:
            source = item_lookup.get(entry.item_id)
            title = entry.title
            kind = entry.kind
            status = entry.status
            recommended_day_offset = entry.recommended_day_offset
            if source is not None:
                title = getattr(source, "title", title)
                kind = getattr(source, "kind", kind)
                status = getattr(source, "launch_status", status)
                recommended_day_offset = getattr(source, "recommended_day_offset", recommended_day_offset)
            payload.append(
                MilestonePrerequisitePayload(
                    item_id=entry.item_id,
                    title=title,
                    kind=kind,
                    status=status,
                    required=entry.required,
                    recommended_day_offset=recommended_day_offset,
                )
            )
        return payload

    dynamic_warning_entries: List[ScheduleWarningPayload] = []

    for item in schedule.items:
        local_date = anchor_date + timedelta(days=item.recommended_day_offset)
        scheduled_for = datetime.combine(local_date, time.min, tzinfo=tz)
        milestone_brief = getattr(item, "milestone_brief", None)
        requirements = _normalize_requirements(
            getattr(item, "milestone_requirements", []) or [],
            getattr(milestone_brief, "requirements", []) if milestone_brief else [],
        )
        if milestone_brief and requirements:
            milestone_brief.requirements = list(requirements)
        locked_reason, unmet_requirements = _locked_reason(item, schedule.items, requirements)
        requirement_payloads = [
            MilestoneRequirementPayload(
                category_key=getattr(requirement, "category_key", ""),
                category_label=_requirement_label(requirement),
                minimum_rating=int(getattr(requirement, "minimum_rating", 0) or 0),
                rationale=getattr(requirement, "rationale", None),
            )
            for requirement in requirements
            if getattr(requirement, "category_key", None)
        ]
        brief_payload: MilestoneBriefPayload | None = None
        progress_payload: MilestoneProgressPayload | None = None
        milestone_progress = getattr(item, "milestone_progress", None)
        project_payload: MilestoneProjectPayload | None = None
        if milestone_brief:
            brief_payload = MilestoneBriefPayload(
                headline=milestone_brief.headline,
                summary=milestone_brief.summary,
                objectives=list(milestone_brief.objectives),
                deliverables=list(milestone_brief.deliverables),
                success_criteria=list(milestone_brief.success_criteria),
                external_work=list(milestone_brief.external_work),
                capture_prompts=list(milestone_brief.capture_prompts),
                prerequisites=_prerequisites_for_brief(milestone_brief, item),
                requirements=requirement_payloads,
                elo_focus=list(milestone_brief.elo_focus),
                resources=list(milestone_brief.resources),
                kickoff_steps=list(milestone_brief.kickoff_steps),
                coaching_prompts=list(milestone_brief.coaching_prompts),
                rationale=getattr(milestone_brief, "rationale", None),
                authored_at=getattr(milestone_brief, "authored_at", None),
                authored_by_model=getattr(milestone_brief, "authored_by_model", None),
                reasoning_effort=getattr(milestone_brief, "reasoning_effort", None),
                source=getattr(milestone_brief, "source", None),
                warnings=list(getattr(milestone_brief, "warnings", []) or []),
            )
            project = getattr(milestone_brief, "project", None)
            if project:
                project_payload = MilestoneProjectPayload(
                    project_id=project.project_id,
                    title=project.title,
                    goal_alignment=project.goal_alignment,
                    summary=project.summary,
                    deliverables=list(project.deliverables),
                    evidence_checklist=list(project.evidence_checklist),
                    recommended_tools=list(project.recommended_tools),
                    evaluation_focus=list(project.evaluation_focus),
                    evaluation_steps=list(project.evaluation_steps),
                )
                brief_payload.project = project_payload
        elif getattr(item, "prerequisites", None) or requirement_payloads:
            brief_payload = MilestoneBriefPayload(
                headline=item.title,
                summary=getattr(item, "summary", None),
                prerequisites=_prerequisites_for_brief(None, item),
                requirements=requirement_payloads,
                source="template",
                warnings=[],
            )
        if milestone_progress:
            progress_payload = MilestoneProgressPayload(
                recorded_at=milestone_progress.recorded_at,
                notes=milestone_progress.notes,
                external_links=list(milestone_progress.external_links),
                attachment_ids=list(milestone_progress.attachment_ids),
                project_status=getattr(milestone_progress, "project_status", "not_started"),
                next_steps=list(getattr(milestone_progress, "next_steps", []) or []),
            )
        if project_payload is None:
            milestone_project = getattr(item, "milestone_project", None)
            if milestone_project:
                project_payload = MilestoneProjectPayload(
                    project_id=milestone_project.project_id,
                    title=milestone_project.title,
                    goal_alignment=milestone_project.goal_alignment,
                    summary=milestone_project.summary,
                    deliverables=list(milestone_project.deliverables),
                    evidence_checklist=list(milestone_project.evidence_checklist),
                    recommended_tools=list(milestone_project.recommended_tools),
                    evaluation_focus=list(milestone_project.evaluation_focus),
                    evaluation_steps=list(milestone_project.evaluation_steps),
                )
        guidance_payload = _milestone_guidance_payload(
            item,
            milestone_brief,
            milestone_progress,
            locked_reason,
            unmet_requirements,
        )
        if guidance_payload and guidance_payload.warnings:
            for message in guidance_payload.warnings:
                dynamic_warning_entries.append(
                    ScheduleWarningPayload(
                        code="milestone_attention",
                        message=f"{item.title}: {message}",
                        detail=None,
                        generated_at=schedule.generated_at,
                    )
                )
        items.append(
            SequencedWorkItemPayload(
                item_id=item.item_id,
                kind=item.kind,
                category_key=item.category_key,
                title=item.title,
                summary=item.summary,
                objectives=list(item.objectives),
                prerequisites=list(item.prerequisites),
                recommended_minutes=item.recommended_minutes,
                recommended_day_offset=item.recommended_day_offset,
                effort_level=item.effort_level,
                focus_reason=item.focus_reason,
                expected_outcome=item.expected_outcome,
                user_adjusted=getattr(item, "user_adjusted", False),
                scheduled_for=scheduled_for,
                launch_status=getattr(item, "launch_status", "pending"),
                last_launched_at=getattr(item, "last_launched_at", None),
                last_completed_at=getattr(item, "last_completed_at", None),
                active_session_id=getattr(item, "active_session_id", None),
                launch_locked_reason=locked_reason,
                milestone_brief=brief_payload,
                milestone_progress=progress_payload,
                milestone_guidance=guidance_payload,
                milestone_project=project_payload,
                milestone_requirements=requirement_payloads,
            )
        )
    if dynamic_warning_entries:
        existing_messages = {warning.message for warning in warnings}
        for entry in dynamic_warning_entries:
            if entry.message not in existing_messages:
                warnings.append(entry)
                existing_messages.add(entry.message)
    allocations = [
        CategoryPacingPayload(
            category_key=entry.category_key,
            planned_minutes=entry.planned_minutes,
            target_share=entry.target_share,
            deferral_pressure=entry.deferral_pressure,
            deferral_count=getattr(entry, "deferral_count", 0),
            max_deferral_days=getattr(entry, "max_deferral_days", 0),
            rationale=entry.rationale,
        )
        for entry in getattr(schedule, "category_allocations", [])
    ]
    rationale_history = [
        ScheduleRationaleEntryPayload(
            generated_at=entry.generated_at,
            headline=entry.headline,
            summary=entry.summary,
            related_categories=list(entry.related_categories),
            adjustment_notes=list(entry.adjustment_notes),
        )
        for entry in getattr(schedule, "rationale_history", [])
    ]
    slice_payload: ScheduleSlicePayload | None = None
    slice_meta = getattr(schedule, "slice", None)
    if slice_meta is not None:
        slice_payload = ScheduleSlicePayload(
            start_day=slice_meta.start_day,
            end_day=slice_meta.end_day,
            day_span=slice_meta.day_span,
            total_items=slice_meta.total_items,
            total_days=slice_meta.total_days,
            has_more=slice_meta.has_more,
            next_start_day=slice_meta.next_start_day,
        )
    return CurriculumSchedulePayload(
        generated_at=schedule.generated_at,
        time_horizon_days=schedule.time_horizon_days,
        timezone=getattr(tz, "key", tz_name),
        anchor_date=anchor_date,
        cadence_notes=schedule.cadence_notes,
        is_stale=getattr(schedule, "is_stale", False),
        warnings=warnings,
        items=items,
        pacing_overview=getattr(schedule, "pacing_overview", None),
        category_allocations=allocations,
        rationale_history=rationale_history,
        sessions_per_week=getattr(schedule, "sessions_per_week", 4),
        projected_weekly_minutes=getattr(schedule, "projected_weekly_minutes", 0),
        long_range_item_count=getattr(schedule, "long_range_item_count", 0),
        extended_weeks=getattr(schedule, "extended_weeks", 0),
        long_range_category_keys=list(getattr(schedule, "long_range_category_keys", [])),
        slice=slice_payload,
    )


def _module_reference_payload(reference: FoundationModuleReference) -> FoundationModuleReferencePayload:
    return FoundationModuleReferencePayload(
        module_id=reference.module_id,
        category_key=reference.category_key,
        priority=reference.priority,
        suggested_weeks=reference.suggested_weeks,
        notes=reference.notes,
    )


def _track_payload(track: FoundationTrack) -> FoundationTrackPayload:
    return FoundationTrackPayload(
        track_id=track.track_id,
        label=track.label,
        priority=track.priority,
        confidence=track.confidence,
        weight=track.weight,
        technologies=list(track.technologies),
        focus_areas=list(track.focus_areas),
        prerequisites=list(track.prerequisites),
        recommended_modules=[_module_reference_payload(module) for module in track.recommended_modules],
        suggested_weeks=track.suggested_weeks,
        notes=track.notes,
    )


def _assessment_task_payload(task: AssessmentTask) -> OnboardingAssessmentTaskPayload:
    return OnboardingAssessmentTaskPayload(
        task_id=task.task_id,
        category_key=task.category_key,
        section_id=getattr(task, "section_id", None),
        title=task.title,
        task_type=task.task_type,
        prompt=task.prompt,
        guidance=task.guidance,
        rubric=list(task.rubric),
        expected_minutes=task.expected_minutes,
        starter_code=task.starter_code,
        answer_key=task.answer_key,
    )


def _assessment_section_payload(section: AssessmentSection) -> AssessmentSectionPayload:
    return AssessmentSectionPayload(
        section_id=section.section_id,
        title=section.title,
        description=section.description,
        intent=section.intent,
        expected_minutes=section.expected_minutes,
        tasks=[_assessment_task_payload(task) for task in section.tasks],
    )


def _profile_payload(profile: LearnerProfile) -> LearnerProfilePayload:
    plan = profile.elo_category_plan
    plan_payload: EloCategoryPlanPayload | None = None
    if plan:
        plan_payload = EloCategoryPlanPayload(
            generated_at=plan.generated_at,
            source_goal=plan.source_goal,
            strategy_notes=plan.strategy_notes,
            categories=[
                EloCategoryDefinitionPayload(
                    key=definition.key,
                    label=definition.label,
                    description=definition.description,
                    focus_areas=definition.focus_areas,
                    weight=definition.weight,
                    rubric=[
                        EloRubricBandPayload(level=band.level, descriptor=band.descriptor)
                        for band in definition.rubric
                    ],
                    starting_rating=definition.starting_rating,
                )
                for definition in plan.categories
            ],
        )
    curriculum_payload: OnboardingCurriculumPayload | None = None
    if profile.curriculum_plan:
        curriculum = profile.curriculum_plan
        curriculum_payload = OnboardingCurriculumPayload(
            generated_at=curriculum.generated_at,
            overview=curriculum.overview,
            success_criteria=list(curriculum.success_criteria),
            modules=[
                CurriculumModulePayload(
                    module_id=module.module_id,
                    category_key=module.category_key,
                    title=module.title,
                    summary=module.summary,
                    objectives=list(module.objectives),
                    activities=list(module.activities),
                    deliverables=list(module.deliverables),
                    estimated_minutes=module.estimated_minutes,
                )
                for module in curriculum.modules
            ],
        )
    assessment_payload: OnboardingAssessmentPayload | None = None
    if profile.onboarding_assessment:
        assessment = profile.onboarding_assessment
        task_payloads = [_assessment_task_payload(task) for task in assessment.tasks]
        section_payloads = [
            _assessment_section_payload(section) for section in assessment.sections
        ] if getattr(assessment, "sections", None) else []
        assessment_payload = OnboardingAssessmentPayload(
            generated_at=assessment.generated_at,
            status=assessment.status,
            tasks=task_payloads,
            sections=section_payloads,
        )
    assessment_result_payload: AssessmentGradingPayload | None = None
    if profile.onboarding_assessment_result:
        result = profile.onboarding_assessment_result
        assessment_result_payload = AssessmentGradingPayload(
            submission_id=result.submission_id,
            evaluated_at=result.evaluated_at,
            overall_feedback=result.overall_feedback,
            strengths=list(result.strengths),
            focus_areas=list(result.focus_areas),
            task_results=[
                AssessmentTaskGradePayload(
                    task_id=task.task_id,
                    category_key=task.category_key,
                    task_type=task.task_type,
                    score=task.score,
                    confidence=task.confidence,
                    feedback=task.feedback,
                    strengths=list(task.strengths),
                    improvements=list(task.improvements),
                    rubric=[
                        AssessmentRubricEvaluationPayload(
                            criterion=rubric.criterion,
                            met=rubric.met,
                            notes=rubric.notes,
                            score=rubric.score,
                        )
                        for rubric in task.rubric
                    ],
                )
                for task in result.task_results
            ],
            category_outcomes=[
                AssessmentCategoryOutcomePayload(
                    category_key=outcome.category_key,
                    average_score=outcome.average_score,
                    initial_rating=outcome.initial_rating,
                    starting_rating=outcome.starting_rating,
                    rating_delta=outcome.rating_delta,
                    rationale=outcome.rationale,
                )
                for outcome in result.category_outcomes
            ],
        )
    schedule_payload = _schedule_payload(
        getattr(profile, "curriculum_schedule", None),
        elo_snapshot=getattr(profile, "elo_snapshot", {}),
        elo_plan=getattr(profile, "elo_category_plan", None),
    )
    track_payloads = [_track_payload(track) for track in getattr(profile, "foundation_tracks", []) or []]
    inference_payload: GoalParserInferencePayload | None = None
    if profile.goal_inference:
        inference_payload = GoalParserInferencePayload(
            generated_at=profile.goal_inference.generated_at,
            summary=profile.goal_inference.summary,
            target_outcomes=list(profile.goal_inference.target_outcomes),
            tracks=[_track_payload(track) for track in profile.goal_inference.tracks],
            missing_templates=list(profile.goal_inference.missing_templates),
        )
        if not track_payloads:
            track_payloads = [ _track_payload(track) for track in profile.goal_inference.tracks ]
    completion_payloads = [
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
        for entry in getattr(profile, "milestone_completions", []) or []
    ]
    return LearnerProfilePayload(
        username=profile.username,
        goal=profile.goal,
        use_case=profile.use_case,
        strengths=profile.strengths,
        timezone=profile.timezone,
        knowledge_tags=profile.knowledge_tags,
        recent_sessions=profile.recent_sessions,
        memory_records=profile.memory_records,
        skill_ratings=[
            SkillRatingPayload(category=category, rating=value)
            for category, value in profile.elo_snapshot.items()
        ],
        memory_index_id=profile.memory_index_id,
        last_updated=profile.last_updated,
        elo_category_plan=plan_payload,
        curriculum_plan=curriculum_payload,
        curriculum_schedule=schedule_payload,
        onboarding_assessment=assessment_payload,
        onboarding_assessment_result=assessment_result_payload,
        goal_inference=inference_payload,
        foundation_tracks=track_payloads,
        milestone_completions=completion_payloads,
    )


@function_tool(strict_mode=False)
def elo_update(
    elo: Dict[str, float] | None,
    skill_weights: Dict[str, float] | None,
    score: float,
    problem_rating: int,
    K: int = 24,
) -> Dict[str, Any]:
    """Update learner skill ratings using a weighted Elo adjustment."""
    if elo is None:
        elo = {}
    if skill_weights is None:
        skill_weights = {}

    updated: Dict[str, float] = {}
    total_weight = sum(max(weight, 0.0) for weight in skill_weights.values()) or 1.0

    for skill, weight in skill_weights.items():
        weight = max(weight, 0.0) / total_weight
        rating = elo.get(skill, 1200.0)
        expected = 1.0 / (1.0 + 10 ** ((problem_rating - rating) / 400.0))
        delta = K * weight * (score - expected)
        updated[skill] = rating + delta

    # Persist untouched skills
    for skill, rating in elo.items():
        updated.setdefault(skill, rating)

    return {"updated_elo": updated}


@function_tool(strict_mode=False)
def learner_profile_get(
    username: str,
    start_day: int | None = None,
    day_span: int | None = None,
    page_token: int | None = None,
) -> LearnerProfileGetResponse:
    """Fetch the persisted learner profile, optionally returning a schedule slice."""
    profile = profile_store.get(username)
    if profile is None:
        return LearnerProfileGetResponse(found=False, profile=None)

    requested_start = page_token if page_token is not None else start_day
    normalized_start = None if requested_start is None else max(int(requested_start), 0)
    normalized_span = None if day_span is None else max(int(day_span), 1)

    if profile.curriculum_schedule and (normalized_start is not None or normalized_span is not None):
        sliced_schedule = slice_schedule(
            profile.curriculum_schedule,
            start_day=normalized_start,
            day_span=normalized_span,
        )
        profile = profile.model_copy(update={"curriculum_schedule": sliced_schedule})

    payload = _profile_payload(profile)
    return LearnerProfileGetResponse(found=True, profile=payload)


@function_tool(strict_mode=False)
def learner_profile_update(
    username: str,
    goal: str | None = None,
    use_case: str | None = None,
    strengths: str | None = None,
    knowledge_tags: List[str] | None = None,
    timezone: str | None = None,
) -> LearnerProfileUpdateResponse:
    """Update learner profile fields and return the refreshed profile snapshot."""
    metadata: Dict[str, Any] = {}
    if goal is not None:
        metadata["goal"] = goal
    if use_case is not None:
        metadata["use_case"] = use_case
    if strengths is not None:
        metadata["strengths"] = strengths
    if knowledge_tags is not None:
        metadata["knowledge_tags"] = knowledge_tags
    if timezone is not None:
        metadata["timezone"] = timezone
    profile = profile_store.apply_metadata(username, metadata)
    payload = _profile_payload(profile)
    return LearnerProfileUpdateResponse(profile=payload)


@function_tool(strict_mode=False)
def learner_memory_write(
    username: str, note: str, tags: List[str] | None = None
) -> LearnerMemoryWriteResponse:
    """Record a personalised memory note for the learner."""
    result = learner_memory.record_note(username=username, note=note, tags=tags or [])
    return LearnerMemoryWriteResponse(
        note_id=result["note_id"],
        vector_store_id=result["vector_store_id"],
        status=result["status"],
    )


def _normalise_category_key(key: str, label: str) -> str:
    candidate = key.strip() if isinstance(key, str) else ""
    if not candidate and isinstance(label, str):
        candidate = label
    slug_chars: List[str] = []
    for char in candidate:
        if char.isalnum():
            slug_chars.append(char.lower())
        elif char in {" ", "-", "_", "/"}:
            slug_chars.append("-")
    slug = "".join(slug_chars).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "category-1"


def _merge_focus_areas(existing: List[str], incoming: List[str]) -> List[str]:
    merged = {item.strip(): None for item in existing if item.strip()}
    for focus_area in incoming:
        trimmed = focus_area.strip()
        if trimmed:
            merged.setdefault(trimmed, None)
    return list(merged.keys())


def _merge_rubric(
    existing: List[EloRubricBand],
    incoming: List[EloRubricBand],
) -> List[EloRubricBand]:
    bands: Dict[str, EloRubricBand] = {band.level.lower(): band for band in existing}
    for band in incoming:
        level_key = band.level.lower()
        if level_key not in bands or not bands[level_key].descriptor:
            bands[level_key] = band
    return list(bands.values())


def _merge_categories(
    primary: EloCategoryDefinition,
    secondary: EloCategoryDefinition,
) -> EloCategoryDefinition:
    label = primary.label
    if (not label or label == primary.key.replace("-", " ").title()) and secondary.label:
        label = secondary.label
    description = primary.description or secondary.description
    focus = _merge_focus_areas(primary.focus_areas, secondary.focus_areas)
    rubric = _merge_rubric(primary.rubric, secondary.rubric)
    weight = max(primary.weight, secondary.weight)
    starting_rating = max(primary.starting_rating, secondary.starting_rating)
    return primary.model_copy(
        update={
            "label": label,
            "description": description,
            "focus_areas": focus,
            "rubric": rubric,
            "weight": weight,
            "starting_rating": starting_rating,
        }
    )


def _apply_elo_category_plan(
    username: str,
    categories: List[EloCategoryDefinitionPayload],
    source_goal: str | None = None,
    strategy_notes: str | None = None,
) -> LearnerEloCategoryPlanResponse:
    """Persist the learner's skill category plan and return the updated snapshot."""
    normalized_categories: Dict[str, EloCategoryDefinition] = {}
    collisions: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    for entry in categories:
        key = _normalise_category_key(entry.key, entry.label)
        label = entry.label.strip() if isinstance(entry.label, str) else key.title()
        description = entry.description.strip() if isinstance(entry.description, str) else ""
        focus = [
            focus_area.strip()
            for focus_area in entry.focus_areas
            if isinstance(focus_area, str) and focus_area.strip()
        ]
        rubric = [
            EloRubricBand(level=band.level.strip(), descriptor=band.descriptor.strip())
            for band in entry.rubric
            if isinstance(band.level, str) and band.level.strip()
        ]
        definition = EloCategoryDefinition(
            key=key,
            label=label,
            description=description,
            focus_areas=focus,
            weight=max(entry.weight, 0.0),
            rubric=rubric,
            starting_rating=max(int(entry.starting_rating), 0),
        )
        if key not in normalized_categories:
            normalized_categories[key] = definition
            order.append(key)
            continue
        existing = normalized_categories[key]
        merged = _merge_categories(existing, definition)
        normalized_categories[key] = merged
        meta = collisions.setdefault(
            key,
            {
                "labels": set(),
                "focus_area_count": len(merged.focus_areas),
            },
        )
        for candidate in (existing.label, label, merged.label):
            if candidate:
                meta["labels"].add(candidate)
        meta["focus_area_count"] = len(merged.focus_areas)

    merged_categories = [normalized_categories[key] for key in order]

    plan = EloCategoryPlan(
        source_goal=source_goal.strip() if isinstance(source_goal, str) and source_goal else None,
        strategy_notes=strategy_notes.strip() if isinstance(strategy_notes, str) and strategy_notes else None,
        categories=merged_categories,
    )
    profile = profile_store.set_elo_category_plan(username, plan)
    if collisions:
        emit_event(
            "elo_category_collision",
            username=username,
            collision_count=len(collisions),
            categories=[
                {
                    "key": key,
                    "labels": sorted(meta["labels"]),
                    "focus_area_count": meta["focus_area_count"],
                }
                for key, meta in collisions.items()
            ],
        )
    payload = _profile_payload(profile)
    if payload.elo_category_plan is None:
        raise ValueError("Failed to persist learner ELO category plan.")
    return LearnerEloCategoryPlanResponse(username=profile.username, plan=payload.elo_category_plan)


@function_tool(strict_mode=False)
def learner_elo_category_plan_set(
    username: str,
    categories: List[EloCategoryDefinitionPayload],
    source_goal: str | None = None,
    strategy_notes: str | None = None,
) -> LearnerEloCategoryPlanResponse:
    """Persist the learner's skill category plan and return the updated snapshot."""
    return _apply_elo_category_plan(
        username=username,
        categories=categories,
        source_goal=source_goal,
        strategy_notes=strategy_notes,
    )


@function_tool(strict_mode=False)
def current_time(timezone_name: str | None = None, format: str | None = None) -> Dict[str, str]:
    """Return the current time. Provide an IANA timezone (e.g., 'America/Los_Angeles') to localise the output."""
    tz = timezone.utc
    tz_key = "UTC"
    if timezone_name:
        try:
            tz = ZoneInfo(timezone_name)
            tz_key = tz.key  # type: ignore[attr-defined]
        except ZoneInfoNotFoundError:
            tz = timezone.utc
            tz_key = "UTC"
    now = datetime.now(tz)
    if format:
        try:
            display = now.strftime(format)
        except Exception:  # noqa: BLE001
            display = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    else:
        display = now.strftime("%A, %B %d, %Y %H:%M:%S %Z")
    return {
        "timezone": tz_key,
        "iso_timestamp": now.isoformat(),
        "display": display,
    }


AGENT_SUPPORT_TOOLS = [
    progress_start,
    progress_advance,
    elo_update,
    learner_profile_get,
    learner_profile_update,
    learner_memory_write,
    learner_elo_category_plan_set,
    current_time,
]

__all__ = [
    "AGENT_SUPPORT_TOOLS",
    "elo_update",
    "learner_memory_write",
    "learner_elo_category_plan_set",
    "learner_profile_get",
    "learner_profile_update",
    "progress_advance",
    "progress_start",
    "current_time",
]
