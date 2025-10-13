"""Curriculum sequencing heuristics introduced in Phase 11."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence

from .learner_profile import (
    AssessmentGradingResult,
    CurriculumModule,
    CurriculumPlan,
    CurriculumSchedule,
    LearnerProfile,
    SequencedWorkItem,
    profile_store,
)


DEFAULT_DAILY_CAP_MINUTES = 120
DEFAULT_TIME_HORIZON_DAYS = 14


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
    ) -> None:
        self._daily_capacity = max(daily_capacity_minutes, 45)
        self._default_horizon = max(default_time_horizon_days, 7)

    def build_schedule(self, profile: LearnerProfile) -> CurriculumSchedule:
        if not profile.elo_category_plan and not profile.elo_snapshot:
            raise ValueError("Cannot generate a schedule without ELO categories.")

        categories = self._build_category_context(profile)
        if not categories:
            raise ValueError("No curriculum categories available for sequencing.")

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

        scheduled_items = self._assign_day_offsets(timeline)
        cadence_notes = self._cadence_summary(scheduled_items, profile.onboarding_assessment_result)
        horizon = max(self._default_horizon, (max(item.recommended_day_offset for item in scheduled_items) + 1))

        return CurriculumSchedule(
            generated_at=datetime.now(timezone.utc),
            time_horizon_days=horizon,
            cadence_notes=cadence_notes,
            items=scheduled_items,
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

    def _assign_day_offsets(self, items: List[SequencedWorkItem]) -> List[SequencedWorkItem]:
        day_offset = 0
        minutes_remaining = self._daily_capacity
        scheduled: List[SequencedWorkItem] = []
        for item in items:
            minutes = max(item.recommended_minutes, 15)
            if minutes > minutes_remaining and scheduled:
                day_offset += 1
                minutes_remaining = self._daily_capacity
            scheduled_item = item.model_copy()
            scheduled_item.recommended_day_offset = day_offset
            minutes_remaining -= minutes
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
        focus_categories = {item.category_key for item in items[:3]}
        summary = f"Scheduled {len(items)} items across {distinct_days} days (~{total_minutes} minutes total)."
        if assessment and assessment.focus_areas:
            summary += f" Focus areas: {', '.join(assessment.focus_areas[:2])}."
        elif focus_categories:
            summary += f" Emphasis on {', '.join(sorted(focus_categories))}."
        return summary


sequencer = CurriculumSequencer()


def generate_schedule_for_user(username: str) -> CurriculumSchedule:
    """Generate and persist a curriculum schedule for the given learner."""
    profile = profile_store.get(username)
    if profile is None:
        raise LookupError(f"Learner profile '{username}' was not found.")
    schedule = sequencer.build_schedule(profile)
    return profile_store.set_curriculum_schedule(username, schedule)


__all__ = ["CurriculumSequencer", "generate_schedule_for_user", "sequencer"]
