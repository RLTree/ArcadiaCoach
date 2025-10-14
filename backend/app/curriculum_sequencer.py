"""Curriculum sequencing heuristics introduced in Phase 11."""

from __future__ import annotations

import logging
import math
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Literal, Optional, Sequence, Tuple, cast

from .learner_profile import (
    AssessmentGradingResult,
    CategoryPacing,
    CurriculumModule,
    CurriculumPlan,
    CurriculumSchedule,
    LearnerProfile,
    ScheduleRationaleEntry,
    SequencedWorkItem,
    profile_store,
)
from .telemetry import emit_event

logger = logging.getLogger(__name__)


DEFAULT_DAILY_CAP_MINUTES = 120
DEFAULT_TIME_HORIZON_DAYS = 56
MAX_RATIONALE_HISTORY = 6


@dataclass
class _CategoryContext:
    key: str
    label: str
    weight: float
    rating: int
    average_score: Optional[float]
    rating_delta: Optional[int]
    modules: List[CurriculumModule]


class CurriculumSequencer:
    """Derives a near-term curriculum schedule from learner signals."""

    def __init__(
        self,
        *,
        daily_capacity_minutes: int = DEFAULT_DAILY_CAP_MINUTES,
        default_time_horizon_days: int = DEFAULT_TIME_HORIZON_DAYS,
        default_sessions_per_week: int = 4,
    ) -> None:
        self._daily_capacity = max(daily_capacity_minutes, 45)
        self._default_horizon = max(default_time_horizon_days, 7)
        self._default_sessions_per_week = max(default_sessions_per_week, 2)

    def build_schedule(
        self,
        profile: LearnerProfile,
        *,
        previous_schedule: Optional[CurriculumSchedule] = None,
        adjustments: Optional[Dict[str, int]] = None,
    ) -> CurriculumSchedule:
        if not profile.elo_category_plan and not profile.elo_snapshot:
            raise ValueError("Cannot generate a schedule without ELO categories.")

        adjustments = adjustments or getattr(profile, "schedule_adjustments", {}) or {}
        categories = self._build_category_context(profile)
        if not categories:
            raise ValueError("No curriculum categories available for sequencing.")

        pacing_sessions = self._determine_sessions_per_week(previous_schedule, adjustments)
        timeline: List[SequencedWorkItem] = []
        module_order = self._prioritize_modules(categories.values())

        for ranking, module in enumerate(module_order, start=1):
            context = categories[module.category_key]
            lesson_id = f"lesson-{module.module_id}"
            focus_reason = self._focus_reason(context, profile.goal)
            effort_level = self._effort_level(module.estimated_minutes)
            expected_minutes = module.estimated_minutes or 45

            timeline.append(
                SequencedWorkItem(
                    item_id=lesson_id,
                    category_key=module.category_key,
                    kind="lesson",
                    title=module.title,
                    summary=module.summary,
                    objectives=list(module.objectives),
                    prerequisites=[],
                    recommended_minutes=expected_minutes,
                    focus_reason=focus_reason,
                    expected_outcome=self._expected_outcome(module.deliverables, module.summary),
                    effort_level=effort_level,
                )
            )

            quiz_id = f"quiz-{module.module_id}"
            quiz_minutes = max(20, math.ceil(expected_minutes * 0.4))
            timeline.append(
                SequencedWorkItem(
                    item_id=quiz_id,
                    category_key=module.category_key,
                    kind="quiz",
                    title=f"Skill Check: {module.title}",
                    summary="Gauge retention before advancing to the next module.",
                    objectives=[
                        "Demonstrate recall of the module's key ideas.",
                        "Identify any gaps surfaced during the lesson.",
                    ],
                    prerequisites=[lesson_id],
                    recommended_minutes=quiz_minutes,
                    focus_reason=f"Validates progress before expanding {context.label.lower()} coverage.",
                    expected_outcome="Score at least 70% to stay on track.",
                    effort_level="light" if quiz_minutes <= 25 else "moderate",
                )
            )

            if ranking == 1:
                milestone_id = f"milestone-{module.category_key}"
                milestone_minutes = 90 if expected_minutes < 90 else expected_minutes + 30
                milestone_prereqs = [lesson_id, quiz_id]
                timeline.append(
                    SequencedWorkItem(
                        item_id=milestone_id,
                        category_key=module.category_key,
                        kind="milestone",
                        title=f"Milestone: Apply {context.label}",
                        summary="Translate the lesson into a tangible project increment.",
                        objectives=[
                            "Integrate lesson outcomes into a realistic deliverable.",
                            "Document decisions and open questions for agent review.",
                        ],
                        prerequisites=milestone_prereqs,
                        recommended_minutes=milestone_minutes,
                        focus_reason="Creates a tangible artefact to measure competency gains.",
                        expected_outcome="Wrap with notes ready for agent feedback.",
                        effort_level="focus",
                    )
                )

            reinforcement_minutes = max(45, math.ceil(expected_minutes * 0.6))
            timeline.append(
                SequencedWorkItem(
                    item_id=f"reinforce-{module.module_id}",
                    category_key=module.category_key,
                    kind="lesson",
                    title=f"Practice Sprint: {module.title}",
                    summary="Apply the module in a spaced-repetition sprint anchored to real workflows.",
                    objectives=[
                        "Revisit the toughest concept from the original module.",
                        "Capture a before/after reflection on confidence and blockers.",
                    ],
                    prerequisites=[quiz_id],
                    recommended_minutes=reinforcement_minutes,
                    focus_reason=f"Reinforces {context.label.lower()} several weeks after the initial lesson.",
                    expected_outcome="Document a concise improvement plan and practice notes.",
                    effort_level=self._effort_level(reinforcement_minutes),
                )
            )

        scheduled_items = self._assign_day_offsets(timeline, sessions_per_week=pacing_sessions)
        cadence_notes = self._cadence_summary(scheduled_items, profile.onboarding_assessment_result)
        horizon = max(self._default_horizon, (max(item.recommended_day_offset for item in scheduled_items) + 1))
        category_allocations = self._category_allocations(
            scheduled_items,
            categories,
            adjustments=adjustments,
            previous_schedule=previous_schedule,
        )
        rationale_history = self._build_rationale_history(
            profile=profile,
            categories=categories,
            adjustments=adjustments,
            scheduled_items=scheduled_items,
            previous_schedule=previous_schedule,
            sessions_per_week=pacing_sessions,
            category_allocations=category_allocations,
        )
        pacing_overview = self._pacing_overview(
            category_allocations,
            categories,
            pacing_sessions,
            horizon,
        )

        return CurriculumSchedule(
            generated_at=datetime.now(timezone.utc),
            time_horizon_days=horizon,
            timezone=getattr(profile, "timezone", None),
            cadence_notes=cadence_notes,
            items=scheduled_items,
            pacing_overview=pacing_overview,
            category_allocations=category_allocations,
            rationale_history=rationale_history,
        )

    def _build_category_context(self, profile: LearnerProfile) -> Dict[str, _CategoryContext]:
        modules_by_category: Dict[str, List[CurriculumModule]] = {}
        curriculum: Optional[CurriculumPlan] = profile.curriculum_plan
        if curriculum:
            for module in curriculum.modules:
                modules_by_category.setdefault(module.category_key, []).append(module)

        average_scores = self._assessment_scores(profile.onboarding_assessment_result)
        rating_deltas = self._assessment_rating_delta(profile.onboarding_assessment_result)
        category_plan = profile.elo_category_plan.categories if profile.elo_category_plan else []
        total_weight = sum(max(category.weight, 0.0) for category in category_plan) or float(len(category_plan) or 1)

        categories: Dict[str, _CategoryContext] = {}
        for category in category_plan:
            key = category.key
            label = category.label or key.replace("-", " ").title()
            rating = profile.elo_snapshot.get(key, category.starting_rating)
            categories[key] = _CategoryContext(
                key=key,
                label=label,
                weight=category.weight / total_weight,
                rating=rating,
                average_score=average_scores.get(key),
                rating_delta=rating_deltas.get(key),
                modules=modules_by_category.get(key, []),
            )

        # Handle categories present in snapshot but missing from the plan.
        for key, rating in profile.elo_snapshot.items():
            if key in categories:
                continue
            label = key.replace("-", " ").title()
            categories[key] = _CategoryContext(
                key=key,
                label=label,
                weight=1.0 / float(len(profile.elo_snapshot) or 1),
                rating=rating,
                average_score=average_scores.get(key),
                rating_delta=rating_deltas.get(key),
                modules=modules_by_category.get(key, []),
            )

        # Ensure at least one placeholder module exists per category.
        for context in categories.values():
            if context.modules:
                continue
            placeholder = CurriculumModule(
                module_id=f"{context.key}-primer",
                category_key=context.key,
                title=f"{context.label} Primer",
                summary=f"Establish a baseline for {context.label.lower()} before deeper work.",
                objectives=[
                    f"Identify personal knowledge gaps in {context.label.lower()}.",
                    "Capture one tangible practice goal.",
                ],
                activities=[
                    "Review the onboarding curriculum overview for this category.",
                ],
                deliverables=[
                    "Document a short learning journal entry summarising gaps and next steps.",
                ],
                estimated_minutes=45,
            )
            context.modules.append(placeholder)

        return categories

    def _prioritize_modules(self, contexts: Iterable[_CategoryContext]) -> List[CurriculumModule]:
        module_entries: List[tuple[float, CurriculumModule]] = []
        for context in contexts:
            priority = self._priority_score(context)
            for module in context.modules:
                module_entries.append((priority, module))
        module_entries.sort(key=lambda entry: entry[0], reverse=True)
        return [module for _, module in module_entries]

    def _priority_score(self, context: _CategoryContext) -> float:
        weight_component = context.weight * 1.25
        rating_component = max(0.0, (1300 - float(context.rating)) / 300.0)
        score_component = 0.5
        if context.average_score is not None:
            score_component = max(0.1, 1.2 - context.average_score)
        delta_component = 0.0
        if context.rating_delta is not None:
            delta_component = -context.rating_delta / 400.0
        return weight_component + rating_component + score_component + delta_component

    def _assessment_scores(self, result: Optional[AssessmentGradingResult]) -> Dict[str, float]:
        if result is None:
            return {}
        return {outcome.category_key: outcome.average_score for outcome in result.category_outcomes}

    def _assessment_rating_delta(self, result: Optional[AssessmentGradingResult]) -> Dict[str, int]:
        if result is None:
            return {}
        return {outcome.category_key: outcome.rating_delta for outcome in result.category_outcomes}

    def _determine_sessions_per_week(
        self,
        previous_schedule: Optional[CurriculumSchedule],
        adjustments: Dict[str, int],
    ) -> int:
        sessions = self._default_sessions_per_week
        if previous_schedule:
            adjusted_count = sum(1 for item in previous_schedule.items if getattr(item, "user_adjusted", False))
            if adjusted_count >= 4:
                sessions = max(2, sessions - 2)
            elif adjusted_count >= 2:
                sessions = max(2, sessions - 1)
        if adjustments:
            max_offset = max(int(value) for value in adjustments.values())
            if max_offset >= 42:
                sessions = max(2, sessions - 2)
            elif max_offset >= 21:
                sessions = max(2, sessions - 1)
            elif len(adjustments) >= 4:
                sessions = max(2, sessions - 1)
        return max(2, min(6, sessions))

    def _category_allocations(
        self,
        items: Sequence[SequencedWorkItem],
        categories: Dict[str, _CategoryContext],
        *,
        adjustments: Dict[str, int],
        previous_schedule: Optional[CurriculumSchedule],
    ) -> List[CategoryPacing]:
        totals: Dict[str, int] = defaultdict(int)
        for item in items:
            totals[item.category_key] += max(int(item.recommended_minutes), 15)
        deferral_counts: Dict[str, int] = defaultdict(int)
        deferral_magnitude: Dict[str, int] = defaultdict(int)
        if previous_schedule:
            for prior in previous_schedule.items:
                target_offset = adjustments.get(prior.item_id)
                if target_offset is not None:
                    diff = max(int(target_offset) - int(prior.recommended_day_offset), 0)
                    if diff > 0 or getattr(prior, "user_adjusted", False):
                        deferral_counts[prior.category_key] += 1
                        if diff == 0 and getattr(prior, "user_adjusted", False):
                            diff = 1
                        deferral_magnitude[prior.category_key] = max(deferral_magnitude[prior.category_key], diff)
                elif getattr(prior, "user_adjusted", False):
                    deferral_counts[prior.category_key] += 1
                    deferral_magnitude[prior.category_key] = max(deferral_magnitude[prior.category_key], 1)
        allocations: List[CategoryPacing] = []
        for key, context in categories.items():
            planned = totals.get(key, 0)
            weight = context.weight
            count = deferral_counts.get(key, 0)
            magnitude = deferral_magnitude.get(key, 0)
            pressure: Literal["low", "medium", "high"] = "low"
            if count >= 3 or magnitude >= 21:
                pressure = "high"
            elif count >= 1 or magnitude >= 7:
                pressure = "medium"
            rationale = self._category_rationale(context, pressure, count, magnitude)
            allocations.append(
                CategoryPacing(
                    category_key=key,
                    planned_minutes=planned,
                    target_share=round(weight, 4),
                    deferral_pressure=pressure,
                    deferral_count=count,
                    max_deferral_days=magnitude,
                    rationale=rationale,
                )
            )
        allocations.sort(key=lambda entry: (-entry.planned_minutes, entry.category_key))
        return allocations

    def _category_rationale(
        self,
        context: _CategoryContext,
        pressure: Literal["low", "medium", "high"],
        deferral_count: int,
        max_deferral_days: int,
    ) -> str:
        fragments: List[str] = [
            f"Weight {context.weight:.2f}",
            f"ELO {context.rating}",
        ]
        if context.average_score is not None:
            fragments.append(f"Assessment {context.average_score * 100:.0f}%")
        if context.rating_delta is not None:
            fragments.append(f"Δ{context.rating_delta:+}")
        if pressure != "low":
            fragments.append(f"{pressure.title()} deferrals ({deferral_count})")
            if max_deferral_days > 0:
                fragments.append(f"Max defer {max_deferral_days}d")
        return "; ".join(fragments)

    def _build_rationale_history(
        self,
        *,
        profile: LearnerProfile,
        categories: Dict[str, _CategoryContext],
        adjustments: Dict[str, int],
        scheduled_items: Sequence[SequencedWorkItem],
        previous_schedule: Optional[CurriculumSchedule],
        sessions_per_week: int,
        category_allocations: Sequence[CategoryPacing],
    ) -> List[ScheduleRationaleEntry]:
        history: List[ScheduleRationaleEntry] = []
        if previous_schedule and getattr(previous_schedule, "rationale_history", None):
            history.extend(previous_schedule.rationale_history[-(MAX_RATIONALE_HISTORY - 1):])
        top_allocations = [alloc for alloc in category_allocations if alloc.planned_minutes > 0][:2]
        related_categories = list(
            dict.fromkeys(
                [alloc.category_key for alloc in top_allocations]
                + [alloc.category_key for alloc in category_allocations if alloc.deferral_pressure != "low"]
            )
        )
        horizon_days = max((item.recommended_day_offset for item in scheduled_items), default=0) + 1
        goal_snippet = profile.goal.strip()
        if len(goal_snippet) > 120:
            goal_snippet = goal_snippet[:117].rstrip() + "…"
        if not goal_snippet:
            goal_text = "Goal context unavailable."
        else:
            goal_text = f"Goal: {goal_snippet}"
        adjustment_notes: List[str] = []
        for alloc in category_allocations:
            if alloc.deferral_pressure != "low":
                note = (
                    f"Adjusted pacing for {categories[alloc.category_key].label} after "
                    f"{alloc.deferral_count} deferral{'s' if alloc.deferral_count != 1 else ''}."
                )
                if alloc.max_deferral_days:
                    note += f" Max defer {alloc.max_deferral_days} days."
                adjustment_notes.append(note)
        if not adjustment_notes and adjustments:
            adjustment_notes.append("Maintained learner-selected offsets from recent deferrals.")
        if not adjustment_notes:
            adjustment_notes.append("No active deferrals carried over.")
        focus_text = ", ".join(categories[alloc.category_key].label for alloc in top_allocations) or "mixed coverage"
        headline = (
            f"Roadmap extended to {horizon_days} days with {sessions_per_week} session"
            f"{'s' if sessions_per_week != 1 else ''}/week cadence."
        )
        summary_parts = [
            f"Prioritising {focus_text} while pacing at {sessions_per_week} sessions per week.",
            goal_text,
        ]
        new_entry = ScheduleRationaleEntry(
            headline=headline,
            summary=" ".join(summary_parts),
            related_categories=related_categories,
            adjustment_notes=adjustment_notes,
        )
        history.append(new_entry)
        if len(history) > MAX_RATIONALE_HISTORY:
            history = history[-MAX_RATIONALE_HISTORY:]
        return history

    def _pacing_overview(
        self,
        allocations: Sequence[CategoryPacing],
        categories: Dict[str, _CategoryContext],
        sessions_per_week: int,
        horizon_days: int,
    ) -> str:
        total_minutes = sum(entry.planned_minutes for entry in allocations)
        focus_parts: List[str] = []
        if total_minutes > 0:
            for entry in allocations[:3]:
                share = int(round((entry.planned_minutes / total_minutes) * 100))
                label = categories[entry.category_key].label
                focus_parts.append(f"{label} {share}%")
        focus_clause = "; ".join(focus_parts) if focus_parts else "Mixed focus"
        return (
            f"Pacing {sessions_per_week} sessions/week over {horizon_days} days "
            f"(~{total_minutes} minutes planned). Focus mix: {focus_clause}."
        )

    def _sanitize_adjustments(self, adjustments: Dict[str, int]) -> Dict[str, int]:
        sanitized: Dict[str, int] = {}
        for item_id, offset in adjustments.items():
            if not isinstance(item_id, str):
                continue
            try:
                coerced = int(offset)
            except (TypeError, ValueError):
                continue
            if coerced < 0:
                coerced = 0
            sanitized[item_id] = coerced
        return sanitized

    def _apply_adjustments(
        self,
        items: Sequence[SequencedWorkItem],
        adjustments: Dict[str, int],
    ) -> Tuple[List[SequencedWorkItem], Dict[str, Tuple[int, int]]]:
        if not items:
            return [], {}
        sanitized = self._sanitize_adjustments(adjustments)
        if not sanitized:
            return [item.model_copy(deep=True) for item in items], {}

        adjusted: List[SequencedWorkItem] = []
        applied: Dict[str, Tuple[int, int]] = {}
        current_day: Optional[int] = None
        minutes_remaining = self._daily_capacity

        for item in items:
            scheduled = item.model_copy(deep=True)
            base_day = scheduled.recommended_day_offset
            forced_offset = sanitized.get(scheduled.item_id)
            target_day = base_day
            if forced_offset is not None:
                target_day = max(target_day, forced_offset)

            if current_day is None:
                current_day = target_day
                minutes_remaining = self._daily_capacity
            else:
                if target_day > current_day:
                    current_day = target_day
                    minutes_remaining = self._daily_capacity
                else:
                    target_day = current_day

            minutes = max(scheduled.recommended_minutes, 15)

            if minutes > minutes_remaining:
                current_day += 1
                minutes_remaining = self._daily_capacity
                if forced_offset is not None and current_day < forced_offset:
                    current_day = forced_offset
                    minutes_remaining = self._daily_capacity

            while minutes > minutes_remaining:
                current_day += 1
                minutes_remaining = self._daily_capacity
                if forced_offset is not None and current_day < forced_offset:
                    current_day = forced_offset

            scheduled.recommended_day_offset = current_day
            minutes_remaining -= minutes

            if scheduled.recommended_day_offset != base_day:
                applied[scheduled.item_id] = (base_day, scheduled.recommended_day_offset)

            adjusted.append(scheduled)

        return adjusted, applied

    def _focus_reason(self, context: _CategoryContext, goal: str) -> str:
        fragments: List[str] = []
        if context.average_score is not None:
            fragments.append(f"Assessment score {context.average_score * 100:.0f}%")
        fragments.append(f"ELO {context.rating}")
        if context.rating_delta:
            fragments.append(f"delta {context.rating_delta:+}")
        if goal:
            fragments.append(f"aligned with goal: {goal[:60]}".rstrip())
        return "; ".join(fragments)

    def _effort_level(self, estimated_minutes: Optional[int]) -> str:
        minutes = estimated_minutes or 45
        if minutes <= 30:
            return "light"
        if minutes <= 75:
            return "moderate"
        return "focus"

    def _expected_outcome(self, deliverables: Sequence[str], fallback_summary: str) -> str:
        for item in deliverables:
            normalized = item.strip()
            if normalized:
                return normalized
        return fallback_summary.strip()

    def _assign_day_offsets(
        self,
        items: List[SequencedWorkItem],
        *,
        sessions_per_week: int,
    ) -> List[SequencedWorkItem]:
        if not items:
            return []
        session_spacing = max(int(round(7 / max(sessions_per_week, 1))), 1)
        session_index = 0
        scheduled: List[SequencedWorkItem] = []
        for idx, item in enumerate(items):
            same_session = False
            if scheduled:
                previous = scheduled[-1]
                if (
                    item.kind == "quiz"
                    and previous.item_id in item.prerequisites
                    and item.recommended_minutes <= 35
                ):
                    same_session = True
                elif (
                    item.kind == "milestone"
                    and previous.item_id in item.prerequisites
                    and item.recommended_minutes <= self._daily_capacity
                ):
                    same_session = False
            if not same_session:
                day_offset = session_index * session_spacing
                session_index += 1
            else:
                day_offset = scheduled[-1].recommended_day_offset
            scheduled_item = item.model_copy()
            scheduled_item.recommended_day_offset = day_offset
            scheduled.append(scheduled_item)
        return scheduled

    def _cadence_summary(
        self,
        items: Sequence[SequencedWorkItem],
        assessment: Optional[AssessmentGradingResult],
    ) -> str:
        if not items:
            return "No scheduled items."
        distinct_days = len({item.recommended_day_offset for item in items})
        total_minutes = sum(item.recommended_minutes for item in items)
        span_days = max((item.recommended_day_offset for item in items), default=0) + 1
        focus_categories = {item.category_key for item in items[:3]}
        summary = (
            f"Scheduled {len(items)} items across {distinct_days} sessions "
            f"(~{total_minutes} minutes total) spanning ~{span_days} days."
        )
        if assessment and assessment.focus_areas:
            summary += f" Focus areas: {', '.join(assessment.focus_areas[:2])}."
        elif focus_categories:
            summary += f" Emphasis on {', '.join(sorted(focus_categories))}."
        return summary


sequencer = CurriculumSequencer()


def generate_schedule_for_user(username: str) -> LearnerProfile:
    """Generate and persist a curriculum schedule for the given learner."""
    profile = profile_store.get(username)
    if profile is None:
        raise LookupError(f"Learner profile '{username}' was not found.")
    adjustments = sequencer._sanitize_adjustments(getattr(profile, "schedule_adjustments", {}))
    previous_schedule = profile.curriculum_schedule.model_copy(deep=True) if profile.curriculum_schedule else None
    previous_adjustments = dict(getattr(profile, "schedule_adjustments", {}))
    start = time.perf_counter()
    try:
        schedule = sequencer.build_schedule(
            profile,
            previous_schedule=previous_schedule,
            adjustments=adjustments,
        )
    except Exception as exc:  # noqa: BLE001
        duration_ms = (time.perf_counter() - start) * 1000.0
        emit_event(
            "schedule_generation",
            username=username,
            status="error",
            duration_ms=round(duration_ms, 2),
            item_count=0,
            error=str(exc),
            exception_type=exc.__class__.__name__,
        )
        logger.exception("Failed to generate schedule for %s", username)
        raise
    duration_ms = (time.perf_counter() - start) * 1000.0
    schedule.is_stale = False
    schedule.warnings.clear()
    applied_deltas: Dict[str, Tuple[int, int]] = {}
    if adjustments:
        adjusted_items, applied_deltas = sequencer._apply_adjustments(schedule.items, adjustments)
        schedule.items = adjusted_items
    updated_adjustments = {
        item.item_id: item.recommended_day_offset
        for item in schedule.items
        if item.item_id in adjustments
        }
    for item in schedule.items:
        item.user_adjusted = item.item_id in updated_adjustments
    if schedule.items:
        schedule.time_horizon_days = max(
            sequencer._default_horizon,
            max(item.recommended_day_offset for item in schedule.items) + 1,
        )
    schedule.cadence_notes = sequencer._cadence_summary(
        schedule.items,
        profile.onboarding_assessment_result,
    )
    unchanged = False
    if previous_schedule is not None:
        if (
            updated_adjustments == previous_adjustments
            and schedule.items == previous_schedule.items
            and schedule.time_horizon_days == previous_schedule.time_horizon_days
            and schedule.cadence_notes == previous_schedule.cadence_notes
        ):
            unchanged = True
            schedule = previous_schedule
            for item in schedule.items:
                item.user_adjusted = item.item_id in previous_adjustments
    emit_event(
        "schedule_generation",
        username=username,
        status="unchanged" if unchanged else "success",
        duration_ms=round(duration_ms, 2),
        item_count=len(schedule.items),
        horizon_days=schedule.time_horizon_days,
        adjustment_count=len(updated_adjustments),
    )
    if applied_deltas:
        emit_event(
            "schedule_adjustments_applied",
            username=username,
            count=len(applied_deltas),
            items=[
                {"item_id": item_id, "from": before, "to": after}
                for item_id, (before, after) in applied_deltas.items()
            ],
        )
    if unchanged:
        profile.curriculum_schedule = schedule
        return profile
    return profile_store.set_curriculum_schedule(username, schedule, adjustments=updated_adjustments)


__all__ = ["CurriculumSequencer", "generate_schedule_for_user", "sequencer"]
