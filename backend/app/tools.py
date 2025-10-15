"""Utility tools exposed to the Arcadia Coach agent."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

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

def _schedule_payload(schedule: Optional[CurriculumSchedule]) -> Optional[CurriculumSchedulePayload]:
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
    items: List[SequencedWorkItemPayload] = []
    for item in schedule.items:
        local_date = anchor_date + timedelta(days=item.recommended_day_offset)
        scheduled_for = datetime.combine(local_date, time.min, tzinfo=tz)
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
            )
        )
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
    schedule_payload = _schedule_payload(getattr(profile, "curriculum_schedule", None))
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
