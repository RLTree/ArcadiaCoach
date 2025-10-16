"""Curriculum sequencing heuristics introduced in Phase 11."""

from __future__ import annotations

import heapq
import logging
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Set, Tuple

from .learner_profile import (
    AssessmentGradingResult,
    CategoryPacing,
    CurriculumModule,
    CurriculumPlan,
    CurriculumSchedule,
    LearnerProfile,
    ScheduleRationaleEntry,
    SequencedWorkItem,
    MilestoneBrief,
    MilestonePrerequisite,
    profile_store,
)
from .milestone_projects import select_milestone_project
from .telemetry import emit_event

logger = logging.getLogger(__name__)


DEFAULT_DAILY_CAP_MINUTES = 120
DEFAULT_TIME_HORIZON_DAYS = 168
MIN_LONG_RANGE_HORIZON_DAYS = 168
LONG_RANGE_THRESHOLD_DAYS = 90
REFRESHER_MIN_GAP_DAYS = 21
CHECKPOINT_MIN_GAP_DAYS = 35
MAX_LONG_RANGE_REFRESH_CYCLES = 6
MAX_RATIONALE_HISTORY = 6
NEAR_TERM_SMOOTHING_WINDOW_DAYS = 56
MIN_NEAR_TERM_CATEGORY_COUNT = 3
NEAR_TERM_CHUNK_WINDOW = 5
MAX_CONSECUTIVE_CATEGORY_ITEMS = 4
MAX_CONSECUTIVE_CATEGORY_CHUNKS = 2
MAX_SESSION_MINUTES = 120
MIN_SESSION_MINUTES = 30


@dataclass
class _CategoryContext:
    key: str
    label: str
    weight: float
    rating: int
    average_score: Optional[float]
    rating_delta: Optional[int]
    modules: List[CurriculumModule]
    track_weight: float = 0.0
    last_completion_at: Optional[datetime] = None
    completion_count: int = 0


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
        module_order = self._prioritize_modules(categories.values())
        module_chunks: List[Tuple[str, List[SequencedWorkItem]]] = []
        milestone_attached = False
        milestone_target_key = self._select_milestone_category(categories)

        for module in module_order:
            context = categories[module.category_key]
            lesson_id = f"lesson-{module.module_id}"
            focus_reason = self._focus_reason(context, profile.goal)
            effort_level = self._effort_level(module.estimated_minutes)
            expected_minutes = module.estimated_minutes or 45
            chunk: List[SequencedWorkItem] = []

            lesson_parts = self._split_work_item(
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
            chunk.extend(lesson_parts)
            lesson_tail_id = lesson_parts[-1].item_id

            quiz_id = f"quiz-{module.module_id}"
            quiz_minutes = max(20, math.ceil(expected_minutes * 0.4))
            quiz_parts = self._split_work_item(
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
                    prerequisites=[lesson_tail_id],
                    recommended_minutes=quiz_minutes,
                    focus_reason=f"Validates progress before expanding {context.label.lower()} coverage.",
                    expected_outcome="Score at least 70% to stay on track.",
                    effort_level="light" if quiz_minutes <= 25 else "moderate",
                )
            )
            chunk.extend(quiz_parts)
            quiz_tail_id = quiz_parts[-1].item_id

            if not milestone_attached and (
                milestone_target_key is None or module.category_key == milestone_target_key
            ):
                milestone_id = f"milestone-{module.category_key}"
                milestone_minutes = 90 if expected_minutes < 90 else expected_minutes + 30
                milestone_item = SequencedWorkItem(
                    item_id=milestone_id,
                    category_key=module.category_key,
                    kind="milestone",
                    title=f"Milestone: Apply {context.label}",
                    summary="Translate the lesson into a tangible project increment.",
                    objectives=[
                        "Integrate lesson outcomes into a realistic deliverable.",
                        "Document decisions and open questions for agent review.",
                    ],
                    prerequisites=[lesson_tail_id, quiz_tail_id],
                    recommended_minutes=milestone_minutes,
                    focus_reason="Creates a tangible artefact to measure competency gains.",
                    expected_outcome="Wrap with notes ready for agent feedback.",
                    effort_level="focus",
                )
                milestone_item.milestone_brief = self._build_milestone_brief(
                    module,
                    context,
                    profile,
                    lesson_tail_id,
                    quiz_tail_id,
                )
                if milestone_item.milestone_brief and milestone_item.milestone_brief.project:
                    milestone_item.milestone_project = milestone_item.milestone_brief.project
                milestone_parts = self._split_work_item(milestone_item)
                chunk.extend(milestone_parts)
                milestone_attached = True

            reinforcement_minutes = max(45, math.ceil(expected_minutes * 0.6))
            reinforce_parts = self._split_work_item(
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
                    prerequisites=[quiz_tail_id],
                    recommended_minutes=reinforcement_minutes,
                    focus_reason=f"Reinforces {context.label.lower()} several weeks after the initial lesson.",
                    expected_outcome="Document a concise improvement plan and practice notes.",
                    effort_level=self._effort_level(reinforcement_minutes),
                )
            )
            chunk.extend(reinforce_parts)
            reinforce_tail_id = reinforce_parts[-1].item_id

            if context.track_weight >= 1.3:
                deep_minutes = max(60, math.ceil(expected_minutes * 0.75))
                deep_parts = self._split_work_item(
                    SequencedWorkItem(
                        item_id=f"deepdive-{module.module_id}",
                        category_key=module.category_key,
                        kind="lesson",
                        title=f"Deep Dive: {module.title}",
                        summary="Extended practice sprint anchored to critical foundation tracks.",
                        objectives=[
                            "Tackle a stretch challenge tied to the goal parser roadmap.",
                            "Document insights and blockers to review with the coach.",
                        ],
                        prerequisites=[reinforce_tail_id],
                        recommended_minutes=deep_minutes,
                        focus_reason="Goal parser flagged this track as high priority; apply spaced repetition for long-term retention.",
                        expected_outcome="Share a reflection detailing breakthroughs, blockers, and next experiments.",
                        effort_level=self._effort_level(deep_minutes),
                    )
                )
                chunk.extend(deep_parts)

            module_chunks.append((module.category_key, chunk))

        balanced_chunks = self._balance_module_chunks(module_chunks)
        timeline: List[SequencedWorkItem] = []
        for _, chunk in balanced_chunks:
            timeline.extend(chunk)

        scheduled_items = self._assign_day_offsets(timeline, sessions_per_week=pacing_sessions)
        scheduled_items = self._inject_long_range_refreshers(
            scheduled_items,
            categories=categories,
            sessions_per_week=pacing_sessions,
        )
        cadence_notes = self._cadence_summary(scheduled_items, profile.onboarding_assessment_result)
        max_offset = max(item.recommended_day_offset for item in scheduled_items) if scheduled_items else 0
        horizon = max(self._default_horizon, MIN_LONG_RANGE_HORIZON_DAYS, max_offset + 1)
        total_minutes = sum(item.recommended_minutes for item in scheduled_items)
        projected_weekly_minutes = self._projected_weekly_minutes(total_minutes, horizon)
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
        long_range_items = [
            item for item in scheduled_items if item.recommended_day_offset >= LONG_RANGE_THRESHOLD_DAYS
        ]
        long_range_category_keys = sorted({item.category_key for item in long_range_items})
        extended_weeks = math.ceil(horizon / 7) if horizon > 0 else 0
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
            sessions_per_week=pacing_sessions,
            projected_weekly_minutes=projected_weekly_minutes,
            long_range_item_count=len(long_range_items),
            extended_weeks=extended_weeks,
            long_range_category_keys=long_range_category_keys,
        )

    def _build_category_context(self, profile: LearnerProfile) -> Dict[str, _CategoryContext]:
        modules_by_category: Dict[str, List[CurriculumModule]] = {}
        curriculum: Optional[CurriculumPlan] = profile.curriculum_plan
        if curriculum:
            for module in curriculum.modules:
                modules_by_category.setdefault(module.category_key, []).append(module)

        track_weights: Dict[str, float] = {}
        for track in getattr(profile, "foundation_tracks", []) or []:
            weight = track.weight if track.weight and track.weight > 0 else 1.0
            for reference in track.recommended_modules:
                category_key = reference.category_key
                if category_key:
                    track_weights[category_key] = max(track_weights.get(category_key, 0.0), weight)
            if not track.recommended_modules and track.track_id:
                track_weights.setdefault(track.track_id, weight)

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
                track_weight=track_weights.get(key, 0.0),
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
                track_weight=track_weights.get(key, 0.0),
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
                tier=1,
            )
            context.modules.append(placeholder)

        completions = getattr(profile, "milestone_completions", []) or []
        if completions:
            for completion in sorted(completions, key=lambda entry: entry.recorded_at, reverse=True):
                context = categories.get(completion.category_key)
                if context is None:
                    continue
                context.completion_count += 1
                if (
                    context.last_completion_at is None
                    or completion.recorded_at > context.last_completion_at
                ):
                    context.last_completion_at = completion.recorded_at

        return categories

    def _prioritize_modules(self, contexts: Iterable[_CategoryContext]) -> List[CurriculumModule]:
        module_entries: List[tuple[float, CurriculumModule]] = []
        for context in contexts:
            priority = self._priority_score(context)
            for module in context.modules:
                module_entries.append((priority, module))
        if not module_entries:
            return []
        ordered = self._order_modules_with_dependencies(module_entries)
        return ordered

    def _order_modules_with_dependencies(
        self,
        module_entries: Sequence[Tuple[float, CurriculumModule]],
    ) -> List[CurriculumModule]:
        module_map: Dict[str, CurriculumModule] = {}
        priority_map: Dict[str, float] = {}
        for priority, module in module_entries:
            module_map[module.module_id] = module
            priority_map[module.module_id] = priority

        if not module_map:
            return []

        graph: Dict[str, Set[str]] = {module_id: set() for module_id in module_map}
        indegree: Dict[str, int] = {module_id: 0 for module_id in module_map}

        for module_id, module in module_map.items():
            dependencies = self._module_dependencies(module, module_map)
            if not dependencies:
                continue
            for dependency in dependencies:
                if dependency == module_id:
                    logger.warning("Module %s references itself as a prerequisite; skipping.", module_id)
                    continue
                if dependency not in module_map:
                    logger.warning(
                        "Module %s references missing prerequisite %s; ignoring.",
                        module_id,
                        dependency,
                    )
                    continue
                if module_id in graph[dependency]:
                    continue
                graph[dependency].add(module_id)
                indegree[module_id] += 1

        available: List[Tuple[float, str]] = []
        for module_id, degree in indegree.items():
            if degree == 0:
                heapq.heappush(available, (-priority_map.get(module_id, 0.0), module_id))

        ordered_ids: List[str] = []
        while available:
            _, module_id = heapq.heappop(available)
            ordered_ids.append(module_id)
            for neighbour in graph[module_id]:
                indegree[neighbour] -= 1
                if indegree[neighbour] == 0:
                    heapq.heappush(available, (-priority_map.get(neighbour, 0.0), neighbour))

        if len(ordered_ids) != len(module_map):
            unresolved = [module_id for module_id, degree in indegree.items() if degree > 0]
            logger.warning(
                "Detected module dependency cycle involving %s; falling back to priority order.",
                ", ".join(unresolved),
            )
            fallback = sorted(module_entries, key=lambda entry: entry[0], reverse=True)
            return [module for _, module in fallback]

        return [module_map[module_id] for module_id in ordered_ids]

    def _module_dependencies(
        self,
        module: CurriculumModule,
        module_map: Dict[str, CurriculumModule],
    ) -> Set[str]:
        dependencies: Set[str] = set(module.prerequisite_module_ids or [])
        module_tier = getattr(module, "tier", None)
        if module_tier and module_tier > 1:
            for other in module_map.values():
                if other.module_id == module.module_id:
                    continue
                other_tier = getattr(other, "tier", None)
                if (
                    other.category_key == module.category_key
                    and other_tier
                    and other_tier < module_tier
                ):
                    dependencies.add(other.module_id)
        return dependencies

    def _split_work_item(self, item: SequencedWorkItem) -> List[SequencedWorkItem]:
        minutes = max(int(item.recommended_minutes or MIN_SESSION_MINUTES), MIN_SESSION_MINUTES)
        if minutes <= MAX_SESSION_MINUTES:
            cloned = item.model_copy()
            cloned.prerequisites = list(item.prerequisites)
            cloned.recommended_minutes = minutes
            cloned.user_adjusted = False
            cloned.milestone_brief = item.milestone_brief.model_copy(deep=True) if item.milestone_brief else None
            cloned.milestone_progress = (
                item.milestone_progress.model_copy(deep=True) if item.milestone_progress else None
            )
            cloned.milestone_project = (
                item.milestone_project.model_copy(deep=True) if item.milestone_project else None
            )
            return [cloned]

        parts = math.ceil(minutes / MAX_SESSION_MINUTES)
        base_minutes = minutes // parts
        remainder = minutes % parts
        results: List[SequencedWorkItem] = []
        base_title = item.title

        for index in range(parts):
            part_minutes = base_minutes + (1 if index < remainder else 0)
            if part_minutes < MIN_SESSION_MINUTES:
                part_minutes = MIN_SESSION_MINUTES
            part = item.model_copy()
            part.recommended_minutes = part_minutes
            if parts > 1:
                part.title = f"{base_title} (Part {index + 1} of {parts})"
            if index == 0:
                part.item_id = item.item_id
                part.prerequisites = list(item.prerequisites)
            else:
                part.item_id = f"{item.item_id}-part{index + 1}"
                part.prerequisites = [results[-1].item_id]
            part.user_adjusted = False
            part.milestone_brief = item.milestone_brief.model_copy(deep=True) if item.milestone_brief else None
            part.milestone_progress = (
                item.milestone_progress.model_copy(deep=True) if item.milestone_progress else None
            )
            part.milestone_project = (
                item.milestone_project.model_copy(deep=True) if item.milestone_project else None
            )
            results.append(part)

        total_minutes = sum(part.recommended_minutes for part in results)
        correction = minutes - total_minutes
        if correction != 0:
            last = results[-1]
            adjusted = last.recommended_minutes + correction
            if adjusted < MIN_SESSION_MINUTES:
                adjusted = MIN_SESSION_MINUTES
            if adjusted > MAX_SESSION_MINUTES:
                adjusted = MAX_SESSION_MINUTES
            last.recommended_minutes = adjusted

        return results

    def _build_milestone_brief(
        self,
        module: CurriculumModule,
        context: _CategoryContext,
        profile: LearnerProfile,
        lesson_tail_id: str,
        quiz_tail_id: str,
    ) -> MilestoneBrief:
        summary = module.summary or f"Apply {context.label} in a realistic deliverable."
        objectives = list(module.objectives) or [
            f"Demonstrate core {context.label.lower()} fluency.",
            "Document the journey so future refreshers anchor to real work.",
        ]
        deliverables = list(module.deliverables) or [
            "Concrete project artefact (repo branch, design mock, notebook).",
            "Reflection journal covering choices made during implementation.",
        ]
        success_criteria = [
            f"Evidence that {context.label.lower()} skills improved through a tangible output.",
            "Clear explanation of decisions, trade-offs, and any open risks.",
        ]
        if profile.goal:
            success_criteria.append(f"Connect the milestone to the learner goal: {profile.goal}.")
        external_work = [
            f"Block focus time outside Arcadia to build or extend a {module.title.lower()} artefact.",
            "Capture screenshots, repo links, or notes that illustrate progress.",
        ]
        capture_prompts = [
            "What outcome did you produce and how does it serve your longer-term goal?",
            "Which blockers or questions surfaced while working through the milestone?",
            "What support or follow-ups do you want from Arcadia Coach next?",
        ]
        prerequisites = [
            MilestonePrerequisite(
                item_id=lesson_tail_id,
                title=f"Lesson • {module.title}",
                kind="lesson",
            ),
            MilestonePrerequisite(
                item_id=quiz_tail_id,
                title=f"Skill Check • {module.title}",
                kind="quiz",
            ),
        ]
        resources: List[str] = []
        if module.summary:
            resources.append(module.summary)
        kickoff_steps = [
            "Block 60–90 minutes of focused time on your calendar.",
            f"Review your lesson and quiz notes for {module.title}.",
            "Outline the deliverable and list any dependencies before you start building.",
        ]
        coaching_prompts = [
            "Ask Arcadia Coach to sanity-check your milestone plan before diving in.",
            "Share blockers or missing context as soon as you hit friction.",
            "Capture artefacts (links, screenshots, repos) so the agent can grade effectively.",
        ]
        project = select_milestone_project(
            profile,
            module.category_key,
            category_label=context.label,
            goal_inference=getattr(profile, "goal_inference", None),
        )
        brief = MilestoneBrief(
            headline=f"Ship {module.title}",
            summary=summary,
            objectives=objectives,
            deliverables=deliverables,
            success_criteria=success_criteria,
            external_work=external_work,
            capture_prompts=capture_prompts,
            prerequisites=prerequisites,
            elo_focus=[context.label] if context.label else [],
            resources=resources,
            kickoff_steps=kickoff_steps,
            coaching_prompts=coaching_prompts,
        )
        if project:
            brief.project = project
        return brief

    def _balance_module_chunks(
        self,
        chunks: List[Tuple[str, List[SequencedWorkItem]]],
    ) -> List[Tuple[str, List[SequencedWorkItem]]]:
        if len(chunks) <= 1:
            return chunks

        balanced = list(chunks)

        changed = True
        while changed:
            changed = False
            streak = 1
            for idx in range(1, len(balanced)):
                previous_key = balanced[idx - 1][0]
                current_key = balanced[idx][0]
                if current_key == previous_key:
                    streak += 1
                    if streak > MAX_CONSECUTIVE_CATEGORY_CHUNKS:
                        swap_idx = self._find_next_distinct_chunk(balanced, idx + 1, current_key)
                        if swap_idx is None or swap_idx == 0:
                            continue
                        balanced[idx], balanced[swap_idx] = balanced[swap_idx], balanced[idx]
                        changed = True
                        streak = 1
                else:
                    streak = 1

        available_categories = {key for key, _ in balanced}
        if len(available_categories) >= MIN_NEAR_TERM_CATEGORY_COUNT:
            seen: set[str] = set()
            for idx in range(min(len(balanced), NEAR_TERM_CHUNK_WINDOW)):
                key = balanced[idx][0]
                if idx == 0:
                    seen.add(key)
                    continue
                if key in seen:
                    swap_idx = self._find_chunk_with_new_category(balanced, idx + 1, seen)
                    if swap_idx is None:
                        break
                    balanced[idx], balanced[swap_idx] = balanced[swap_idx], balanced[idx]
                    key = balanced[idx][0]
                seen.add(key)

        return balanced

    def _find_next_distinct_chunk(
        self,
        chunks: Sequence[Tuple[str, List[SequencedWorkItem]]],
        start_idx: int,
        disallowed_key: str,
    ) -> Optional[int]:
        for idx in range(start_idx, len(chunks)):
            candidate_key, _ = chunks[idx]
            if candidate_key != disallowed_key:
                return idx
        return None

    def _find_chunk_with_new_category(
        self,
        chunks: Sequence[Tuple[str, List[SequencedWorkItem]]],
        start_idx: int,
        seen: set[str],
    ) -> Optional[int]:
        for idx in range(start_idx, len(chunks)):
            candidate_key, _ = chunks[idx]
            if candidate_key not in seen:
                return idx
        return None

    def _select_milestone_category(self, categories: Dict[str, _CategoryContext]) -> Optional[str]:
        if not categories:
            return None
        prioritized = sorted(categories.values(), key=self._priority_score, reverse=True)
        without_history = [context for context in prioritized if context.last_completion_at is None]
        if without_history:
            return without_history[0].key
        now = datetime.now(timezone.utc)
        best_key = prioritized[0].key
        best_days = self._days_since_completion(prioritized[0], now)
        for context in prioritized:
            days_since = self._days_since_completion(context, now)
            if days_since >= 21:
                return context.key
            if days_since > best_days:
                best_key = context.key
                best_days = days_since
        return best_key

    @staticmethod
    def _days_since_completion(context: _CategoryContext, now: datetime) -> int:
        if context.last_completion_at is None:
            return 10_000
        delta = now - context.last_completion_at
        return max(int(delta.days), 0)

    def _priority_score(self, context: _CategoryContext) -> float:
        weight_component = context.weight * 1.25
        rating_component = max(0.0, (1300 - float(context.rating)) / 300.0)
        score_component = 0.5
        if context.average_score is not None:
            score_component = max(0.1, 1.2 - context.average_score)
        delta_component = 0.0
        if context.rating_delta is not None:
            delta_component = -context.rating_delta / 400.0
        track_component = context.track_weight * 0.6
        completion_penalty = 0.0
        if context.last_completion_at is not None:
            days_since = max((datetime.now(timezone.utc) - context.last_completion_at).days, 0)
            if days_since < 14:
                completion_penalty += 0.6
            elif days_since < 28:
                completion_penalty += 0.35
            elif days_since < 42:
                completion_penalty += 0.2
        completion_penalty += min(context.completion_count * 0.05, 0.3)
        return (
            weight_component
            + rating_component
            + score_component
            + delta_component
            + track_component
            - completion_penalty
        )

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
        if getattr(profile, "milestone_completions", None):
            latest_completion = profile.milestone_completions[0]
            summary_parts.append(
                f"Latest milestone: {latest_completion.title} completed on {latest_completion.recorded_at.date().isoformat()}."
            )
        milestone_with_project = next(
            (item for item in scheduled_items if item.kind == "milestone" and getattr(item, "milestone_project", None)),
            None,
        )
        if milestone_with_project and milestone_with_project.milestone_project:
            project = milestone_with_project.milestone_project
            summary_parts.append(
                f"Next project: {project.title} — {project.goal_alignment}"
            )
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
        weeks = max(horizon_days / 7.0, 1.0)
        weekly_minutes = int(round(total_minutes / weeks)) if total_minutes > 0 else 0
        week_count = math.ceil(weeks)
        return (
            f"Pacing {sessions_per_week} sessions/week (~{weekly_minutes} minutes/week) over {horizon_days} days "
            f"(~{week_count} weeks, ~{total_minutes} minutes total). Focus mix: {focus_clause}."
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

    def _inject_long_range_refreshers(
        self,
        scheduled: List[SequencedWorkItem],
        *,
        categories: Dict[str, _CategoryContext],
        sessions_per_week: int,
    ) -> List[SequencedWorkItem]:
        if not scheduled:
            return []

        target_horizon = max(self._default_horizon, MIN_LONG_RANGE_HORIZON_DAYS)
        current_horizon = max(item.recommended_day_offset for item in scheduled) + 1
        if current_horizon >= target_horizon:
            scheduled.sort(key=lambda item: (item.recommended_day_offset, item.item_id))
            return scheduled

        category_latest: Dict[str, SequencedWorkItem] = {}
        for item in scheduled:
            existing = category_latest.get(item.category_key)
            if existing is None or item.recommended_day_offset > existing.recommended_day_offset:
                category_latest[item.category_key] = item

        prioritized_contexts = [
            context
            for context in sorted(
                categories.values(),
                key=lambda ctx: (ctx.weight, ctx.track_weight, -ctx.rating),
                reverse=True,
            )
            if context.key in category_latest
        ]
        if not prioritized_contexts:
            scheduled.sort(key=lambda item: (item.recommended_day_offset, item.item_id))
            return scheduled

        refreshers: List[SequencedWorkItem] = []
        base_spacing = max(int(round(7 / max(sessions_per_week, 1))), 1)
        refresh_gap = max(REFRESHER_MIN_GAP_DAYS, base_spacing * 6)
        checkpoint_gap = max(CHECKPOINT_MIN_GAP_DAYS, refresh_gap // 2 + base_spacing * 2)

        latest_offsets: Dict[str, int] = {
            context.key: category_latest[context.key].recommended_day_offset for context in prioritized_contexts
        }
        latest_ids: Dict[str, str] = {
            context.key: category_latest[context.key].item_id for context in prioritized_contexts
        }
        offset_cursor = max(current_horizon - 1, max(latest_offsets.values()))
        contexts_cycle = deque(prioritized_contexts)
        cycles = 0
        consecutive_limit = MAX_CONSECUTIVE_CATEGORY_ITEMS
        multi_category = len(prioritized_contexts) > 1

        last_category, current_run = self._initial_run_state(scheduled)

        def _append_refresh_block(context: _CategoryContext) -> None:
            nonlocal offset_cursor, last_category, current_run
            last_offset = latest_offsets[context.key]
            offset_cursor = max(offset_cursor + refresh_gap, last_offset + refresh_gap)
            prerequisite_id = latest_ids[context.key]
            refresh_minutes = max(30, int(round(self._daily_capacity * 0.35)))
            refresh_item = SequencedWorkItem(
                item_id=f"refresh-{context.key}-{offset_cursor}",
                category_key=context.key,
                kind="lesson",
                title=f"Spaced Refresh: {context.label}",
                summary="Revisit core concepts through spaced repetition and low-pressure practice.",
                objectives=[
                    "Review the most challenging concept from previous modules.",
                    "Document confidence shifts and blockers since the last session.",
                ],
                prerequisites=[prerequisite_id],
                recommended_minutes=refresh_minutes,
                recommended_day_offset=offset_cursor,
                focus_reason=f"Extends {context.label.lower()} retention for the long-range roadmap.",
                expected_outcome="Share a reflection covering wins, blockers, and next experiments.",
                effort_level=self._effort_level(refresh_minutes),
            )
            refreshers.append(refresh_item)
            latest_offsets[context.key] = refresh_item.recommended_day_offset
            latest_ids[context.key] = refresh_item.item_id
            last_category, current_run = self._advance_run_state(last_category, current_run, context.key)

            offset_cursor = max(offset_cursor + checkpoint_gap, refresh_item.recommended_day_offset + checkpoint_gap)
            checkpoint_minutes = max(25, int(round(refresh_minutes * 0.8)))
            checkpoint_item = SequencedWorkItem(
                item_id=f"checkpoint-{context.key}-{offset_cursor}",
                category_key=context.key,
                kind="quiz",
                title=f"Checkpoint Quiz: {context.label}",
                summary="Quick mastery check to confirm spaced-refresh retention.",
                objectives=[
                    "Demonstrate recall of key concepts without external notes.",
                    "Capture follow-up actions for any concepts that slipped.",
                ],
                prerequisites=[refresh_item.item_id],
                recommended_minutes=checkpoint_minutes,
                recommended_day_offset=offset_cursor,
                focus_reason="Validates long-range retention before scheduling the next block.",
                expected_outcome="Score at least 70% and note any follow-up support needed.",
                effort_level="light" if checkpoint_minutes <= 30 else "moderate",
            )
            refreshers.append(checkpoint_item)
            latest_offsets[context.key] = checkpoint_item.recommended_day_offset
            latest_ids[context.key] = checkpoint_item.item_id
            last_category, current_run = self._advance_run_state(last_category, current_run, context.key)

        while max(latest_offsets.values()) < target_horizon and cycles < MAX_LONG_RANGE_REFRESH_CYCLES:
            progressed = False
            for _ in range(len(contexts_cycle)):
                context = contexts_cycle[0]
                contexts_cycle.rotate(-1)
                if multi_category and last_category == context.key and current_run >= consecutive_limit:
                    continue
                _append_refresh_block(context)
                progressed = True
                break

            if not progressed:
                context = contexts_cycle[0]
                contexts_cycle.rotate(-1)
                _append_refresh_block(context)

            if max(latest_offsets.values()) >= target_horizon:
                break
            cycles += 1

        combined = scheduled + refreshers
        combined.sort(key=lambda item: (item.recommended_day_offset, item.item_id))
        return combined

    def _initial_run_state(
        self,
        items: Sequence[SequencedWorkItem],
    ) -> Tuple[Optional[str], int]:
        if not items:
            return None, 0
        last_category = items[-1].category_key
        run_length = 0
        for item in reversed(items):
            if item.category_key == last_category:
                run_length += 1
            else:
                break
        return last_category, run_length

    def _advance_run_state(
        self,
        last_category: Optional[str],
        run_length: int,
        new_category: str,
    ) -> Tuple[Optional[str], int]:
        if last_category == new_category:
            return new_category, run_length + 1
        return new_category, 1

    def _summarize_distribution(
        self,
        items: Sequence[SequencedWorkItem],
        *,
        horizon_days: int,
        long_range_threshold: int = LONG_RANGE_THRESHOLD_DAYS,
        smoothing_window_days: int = NEAR_TERM_SMOOTHING_WINDOW_DAYS,
    ) -> Dict[str, Any]:
        if not items:
            return {
                "category_counts": {},
                "longest_streaks": {},
                "long_range_counts": {},
                "first_appearance_week": {},
                "window_unique_categories": [],
                "window_unique_count": 0,
                "horizon_days": horizon_days,
                "long_range_threshold": long_range_threshold,
                "smoothing_window_days": smoothing_window_days,
            }
        counts: Dict[str, int] = defaultdict(int)
        longest: Dict[str, int] = defaultdict(int)
        long_range_counts: Dict[str, int] = defaultdict(int)
        first_week: Dict[str, int] = {}
        last_category: Optional[str] = None
        run_length = 0

        for item in items:
            category = item.category_key
            counts[category] += 1
            if item.recommended_day_offset >= long_range_threshold:
                long_range_counts[category] += 1
            week_index = item.recommended_day_offset // 7
            if category not in first_week:
                first_week[category] = int(week_index)
            if category == last_category:
                run_length += 1
            else:
                last_category = category
                run_length = 1
            if run_length > longest[category]:
                longest[category] = run_length

        window_categories = sorted(
            {item.category_key for item in items if item.recommended_day_offset < smoothing_window_days}
        )

        return {
            "category_counts": dict(counts),
            "longest_streaks": dict(longest),
            "long_range_counts": dict(long_range_counts),
            "first_appearance_week": first_week,
            "window_unique_categories": window_categories,
            "window_unique_count": len(window_categories),
            "horizon_days": horizon_days,
            "long_range_threshold": long_range_threshold,
            "smoothing_window_days": smoothing_window_days,
        }

    def _projected_weekly_minutes(self, total_minutes: int, horizon_days: int) -> int:
        if horizon_days <= 0:
            return total_minutes
        weeks = max(horizon_days / 7.0, 1.0)
        return int(round(total_minutes / weeks))

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
    if previous_schedule is not None:
        previous_lookup = {item.item_id: item for item in previous_schedule.items}
        for item in schedule.items:
            prior = previous_lookup.get(item.item_id)
            if prior is None:
                continue
            item.launch_status = getattr(prior, "launch_status", item.launch_status)
            item.last_launched_at = getattr(prior, "last_launched_at", item.last_launched_at)
            item.last_completed_at = getattr(prior, "last_completed_at", item.last_completed_at)
            item.active_session_id = getattr(prior, "active_session_id", item.active_session_id)
            prior_progress = getattr(prior, "milestone_progress", None)
            if prior_progress is not None:
                item.milestone_progress = prior_progress.model_copy(deep=True)
            if getattr(prior, "milestone_project", None) is not None and item.milestone_project is None:
                item.milestone_project = prior.milestone_project.model_copy(deep=True)
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
    total_minutes = sum(item.recommended_minutes for item in schedule.items)
    unique_days = len({item.recommended_day_offset for item in schedule.items})
    average_session_minutes = (
        int(round(total_minutes / max(unique_days, 1))) if schedule.items else 0
    )
    long_range_category_count = len(schedule.long_range_category_keys)
    user_adjusted_count = sum(1 for item in schedule.items if item.user_adjusted)

    emit_event(
        "schedule_generation",
        username=username,
        status="unchanged" if unchanged else "success",
        duration_ms=round(duration_ms, 2),
        item_count=len(schedule.items),
        horizon_days=schedule.time_horizon_days,
        adjustment_count=len(updated_adjustments),
        sessions_per_week=schedule.sessions_per_week,
        projected_weekly_minutes=schedule.projected_weekly_minutes,
        total_minutes=total_minutes,
        average_session_minutes=average_session_minutes,
        long_range_item_count=schedule.long_range_item_count,
        long_range_category_count=long_range_category_count,
        long_range_weeks=schedule.extended_weeks,
        user_adjusted_count=user_adjusted_count,
        milestone_completion_total=len(getattr(profile, "milestone_completions", []) or []),
    )
    distribution_payload = sequencer._summarize_distribution(
        schedule.items,
        horizon_days=schedule.time_horizon_days,
    )
    emit_event(
        "long_range_distribution",
        username=username,
        **distribution_payload,
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
