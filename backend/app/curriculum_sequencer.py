"""Curriculum sequencing heuristics introduced in Phase 11."""

from __future__ import annotations

import heapq
import logging
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Set, Tuple

from .learner_profile import (
    AssessmentGradingResult,
    CategoryPacing,
    CurriculumModule,
    CurriculumPlan,
    CurriculumSchedule,
    LearnerProfile,
    FoundationTrack,
    ScheduleRationaleEntry,
    SequencedWorkItem,
    MilestoneBrief,
    MilestoneRequirement,
    MilestoneRequirementSummary,
    MilestonePrerequisite,
    MilestoneQueueEntry,
    DependencyTarget,
    SequencerAdvisorSummary,
    profile_store,
)
from .milestone_projects import select_milestone_project
from .milestone_author import (
    MilestoneAuthorError,
    MilestoneAuthorRequestPayload,
    author_milestone_brief,
    resolve_mode,
    should_author,
)
from .requirement_advisor import (
    RequirementAdvisorError,
    RequirementAdvisorRequestPayload,
    RequirementAdvisorRequirementPayload,
    RequirementAdvisorResult,
    advise_requirements,
    resolve_mode as resolve_requirement_mode,
    should_advise as should_advise_requirements,
)
from .sequencer_advisor import (
    SequencerAdvisorError,
    SequencerAdvisorRequestPayload,
    SequencerAdvisorCategoryPayload,
    SequencerAdvisorRequirementPayload,
    SequencerAdvisorModulePayload,
    advise_sequence,
    resolve_mode as resolve_sequencer_mode,
    should_advise as should_advise_sequencer,
)
from .config import get_settings
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
    requirement_gap: int = 0
    dependency_targets: List[DependencyTarget] = field(default_factory=list)
    deferral_count: int = 0


@dataclass(frozen=True)
class _CategoryLookup:
    plan_index: Dict[str, str]
    plan_labels: Dict[str, str]
    plan_weights: Dict[str, float]
    context_index: Dict[str, str]
    context_labels: Dict[str, str]
    snapshot_index: Dict[str, str]
    snapshot_ratings: Dict[str, int]


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

    @staticmethod
    def _slugify_category(value: Optional[str]) -> str:
        if not value:
            return ""
        slug_chars: List[str] = []
        for char in value:
            if char.isalnum():
                slug_chars.append(char.lower())
            elif char in {" ", "-", "_", "/"}:
                slug_chars.append("-")
        slug = "".join(slug_chars).strip("-")
        while "--" in slug:
            slug = slug.replace("--", "-")
        return slug

    @staticmethod
    def _closest_slug(target: str, candidates: Iterable[str]) -> Optional[str]:
        if not target:
            return None
        best_slug: Optional[str] = None
        best_score = 0.0
        for candidate in candidates:
            if not candidate:
                continue
            score = SequenceMatcher(None, target, candidate).ratio()
            if score > best_score:
                best_score = score
                best_slug = candidate
        if best_score >= 0.55:
            return best_slug
        return None

    def _build_category_lookup(
        self,
        profile: LearnerProfile,
        categories: Dict[str, _CategoryContext],
    ) -> _CategoryLookup:
        plan_index: Dict[str, str] = {}
        plan_labels: Dict[str, str] = {}
        plan_weights: Dict[str, float] = {}
        plan = getattr(profile, "elo_category_plan", None)
        if plan and getattr(plan, "categories", None):
            for entry in plan.categories:
                if not getattr(entry, "key", None):
                    continue
                key = entry.key
                plan_weights[key] = max(float(getattr(entry, "weight", 0.0) or 0.0), 0.0)
                plan_labels[key] = getattr(entry, "label", None) or key.replace("-", " ").title()
                for candidate in (entry.key, getattr(entry, "label", None)):
                    slug = self._slugify_category(candidate)
                    if slug and slug not in plan_index:
                        plan_index[slug] = key

        context_index: Dict[str, str] = {}
        context_labels: Dict[str, str] = {}
        for key, context in categories.items():
            context_labels[key] = context.label
            for candidate in (key, context.label):
                slug = self._slugify_category(candidate)
                if slug and slug not in context_index:
                    context_index[slug] = key

        snapshot = dict(getattr(profile, "elo_snapshot", {}) or {})
        snapshot_index = {
            self._slugify_category(key): key for key in snapshot.keys() if self._slugify_category(key)
        }

        return _CategoryLookup(
            plan_index=plan_index,
            plan_labels=plan_labels,
            plan_weights=plan_weights,
            context_index=context_index,
            context_labels=context_labels,
            snapshot_index=snapshot_index,
            snapshot_ratings={key: int(value) for key, value in snapshot.items()},
        )

    def _resolve_category_metadata(
        self,
        candidate_key: Optional[str],
        candidate_label: Optional[str],
        *,
        lookup: _CategoryLookup,
        categories: Dict[str, _CategoryContext],
    ) -> tuple[str, str, _CategoryContext]:
        resolved: Optional[str] = None
        for candidate in (candidate_key, candidate_label):
            slug = self._slugify_category(candidate)
            if not slug:
                continue
            if slug in lookup.context_index:
                resolved = lookup.context_index[slug]
                break
            if slug in lookup.plan_index:
                resolved = lookup.plan_index[slug]
                break
            if slug in lookup.snapshot_index:
                resolved = lookup.snapshot_index[slug]
                break

        if resolved is None:
            slug = self._slugify_category(candidate_label or candidate_key)
            combined_map: Dict[str, str] = {}
            combined_map.update(lookup.context_index)
            combined_map.update(lookup.plan_index)
            combined_map.update(lookup.snapshot_index)
            closest_slug = self._closest_slug(slug, combined_map.keys())
            if closest_slug and combined_map.get(closest_slug):
                resolved = combined_map[closest_slug]
            else:
                text = (candidate_label or candidate_key or "").strip().lower()
                best_key: Optional[str] = None
                best_score = 0.0
                if text:
                    label_sources: Dict[str, str] = {}
                    label_sources.update(lookup.context_labels)
                    label_sources.update(lookup.plan_labels)
                    for key, label in label_sources.items():
                        if not label:
                            continue
                        label_lower = label.lower()
                        overall = SequenceMatcher(None, text, label_lower).ratio()
                        best_local = overall
                        for word in {segment for segment in label_lower.replace("&", " ").replace("-", " ").split() if segment}:
                            score = SequenceMatcher(None, text, word).ratio()
                            if score > best_local:
                                best_local = score
                        if best_local > best_score:
                            best_score = best_local
                            best_key = key
                    if best_key and best_score >= 0.65:
                        resolved = best_key
                if resolved is None:
                    seed = (candidate_key or candidate_label or "").strip()
                    resolved = seed or "category-1"

        label = (
            lookup.context_labels.get(resolved)
            or lookup.plan_labels.get(resolved)
            or candidate_label
            or resolved.replace("-", " ").title()
        )

        context = categories.get(resolved)
        if context is None:
            weight = lookup.plan_weights.get(resolved, 0.0)
            rating = lookup.snapshot_ratings.get(resolved, 0)
            context = _CategoryContext(
                key=resolved,
                label=label,
                weight=weight,
                rating=rating,
                average_score=None,
                rating_delta=None,
                modules=[],
                track_weight=0.0,
            )
        return resolved, label, context

    @staticmethod
    def _summarize_requirements(
        requirements: Sequence[MilestoneRequirement],
    ) -> Optional[MilestoneRequirementSummary]:
        if not requirements:
            return None
        total = len(requirements)
        met = 0
        progress_sum = 0.0
        blocking: List[str] = []
        for requirement in requirements:
            current = int(getattr(requirement, "current_rating", 0) or 0)
            minimum = int(getattr(requirement, "minimum_rating", 0) or 0)
            if current >= minimum and minimum > 0:
                met += 1
            progress = _clamp_progress(current, minimum)
            progress_sum += progress
            if current < max(minimum, 1):
                label = getattr(requirement, "category_label", None) or getattr(requirement, "category_key", "")
                if label and label not in blocking:
                    blocking.append(label)
        average_progress = 0.0
        if total:
            average_progress = round(progress_sum / float(total), 4)
        return MilestoneRequirementSummary(
            total=total,
            met=met,
            average_progress=average_progress,
            blocking_count=len(blocking),
            blocking_categories=blocking,
        )

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
        module_order, advisor_summary = self._prioritize_modules(
            categories.values(),
            profile=profile,
            adjustments=adjustments,
            previous_schedule=previous_schedule,
        )
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
                    categories,
                )
                if milestone_item.milestone_brief:
                    milestone_item.milestone_requirements = list(
                        milestone_item.milestone_brief.requirements or []
                    )
                    milestone_item.requirement_advisor_version = getattr(
                        milestone_item.milestone_brief, "advisor_version", None
                    )
                    milestone_item.requirement_progress_snapshot = [
                        requirement.model_copy(deep=True)
                        for requirement in milestone_item.milestone_requirements
                    ]
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
        for item in scheduled_items:
            if item.kind == "milestone":
                self._apply_requirement_progress(item, profile)
        milestone_queue, dependency_targets_map = self._build_milestone_queue(
            scheduled_items=scheduled_items,
            profile=profile,
            categories=categories,
        )
        aggregated_dependency_targets: Dict[Tuple[str, str], DependencyTarget] = {}
        for targets in dependency_targets_map.values():
            for target in targets:
                aggregated_dependency_targets[(target.milestone_item_id, target.category_key)] = target.model_copy(deep=True)
        for item in scheduled_items:
            category_targets = dependency_targets_map.get(item.category_key, [])
            if not category_targets and item.kind == "milestone":
                continue
            if category_targets:
                unique: Dict[Tuple[str, str], DependencyTarget] = {}
                for target in category_targets:
                    unique[(target.milestone_item_id, target.category_key)] = target
                item.dependency_targets = [
                    entry.model_copy(deep=True) for entry in unique.values()
                ]
        dependency_targets = list(aggregated_dependency_targets.values())
        for target in dependency_targets:
            emit_event(
                "sequencer_dependency_target",
                username=profile.username,
                milestone_item_id=target.milestone_item_id,
                category_key=target.category_key,
                deficit=target.deficit,
                target_rating=target.target_rating,
            )
        if advisor_summary:
            emit_event(
                "sequencer_advisor_applied",
                username=profile.username,
                source=advisor_summary.ordering_source,
                recommended_count=len(advisor_summary.recommended_modules),
                slice_span=advisor_summary.slice_span_days,
                applied=advisor_summary.applied,
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
            milestone_queue=milestone_queue,
            dependency_targets=dependency_targets,
            sequencer_advisor_summary=advisor_summary,
        )

    def _collect_requirement_targets(self, profile: LearnerProfile) -> Dict[str, List[DependencyTarget]]:
        snapshot = dict(getattr(profile, "elo_snapshot", {}) or {})
        targets_by_category: Dict[str, Dict[str, DependencyTarget]] = {}
        schedule = getattr(profile, "curriculum_schedule", None)
        if not schedule:
            return {}

        def _record(
            milestone_id: str,
            title: str,
            requirement: MilestoneRequirement,
            advisor_version: Optional[str],
        ) -> None:
            current_raw = snapshot.get(requirement.category_key, requirement.current_rating)
            try:
                current_rating = int(current_raw or 0)
            except (TypeError, ValueError):
                current_rating = 0
            try:
                target_rating = int(getattr(requirement, "minimum_rating", 0) or 0)
            except (TypeError, ValueError):
                target_rating = 0
            deficit = max(target_rating - current_rating, 0)
            if deficit <= 0 or not requirement.category_key:
                return
            bucket = targets_by_category.setdefault(requirement.category_key, {})
            existing = bucket.get(milestone_id)
            if existing and existing.deficit >= deficit:
                return
            bucket[milestone_id] = DependencyTarget(
                milestone_item_id=milestone_id,
                milestone_title=title,
                category_key=requirement.category_key,
                category_label=requirement.category_label or requirement.category_key.replace("-", " ").title(),
                target_rating=target_rating,
                current_rating=current_rating,
                deficit=deficit,
                requirement_rationale=requirement.rationale,
                advisor_version=advisor_version,
            )

        for entry in getattr(schedule, "milestone_queue", []) or []:
            for existing in getattr(entry, "dependency_targets", []) or []:
                bucket = targets_by_category.setdefault(existing.category_key, {})
                bucket[existing.milestone_item_id] = existing.model_copy(deep=True)
            for requirement in getattr(entry, "requirements", []) or []:
                _record(entry.item_id, entry.title, requirement, None)

        for item in getattr(schedule, "items", []) or []:
            if getattr(item, "kind", None) != "milestone":
                continue
            if getattr(item, "launch_status", "pending") == "completed":
                continue
            for existing in getattr(item, "dependency_targets", []) or []:
                bucket = targets_by_category.setdefault(existing.category_key, {})
                bucket[existing.milestone_item_id] = existing.model_copy(deep=True)
            for requirement in getattr(item, "milestone_requirements", []) or []:
                _record(
                    item.item_id,
                    item.title,
                    requirement,
                    getattr(item, "requirement_advisor_version", None),
                )

        aggregated: Dict[str, List[DependencyTarget]] = {}
        for category_key, bucket in targets_by_category.items():
            aggregated[category_key] = [
                target.model_copy(deep=True) for target in sorted(
                    bucket.values(),
                    key=lambda entry: entry.deficit,
                    reverse=True,
                )
            ]
        return aggregated

    def _category_deferral_counts(self, profile: LearnerProfile) -> Dict[str, int]:
        adjustments = getattr(profile, "schedule_adjustments", {}) or {}
        if not adjustments:
            return {}
        schedule = getattr(profile, "curriculum_schedule", None)
        if not schedule:
            return {}
        lookup = {item.item_id: item for item in getattr(schedule, "items", []) or []}
        counts: Dict[str, int] = defaultdict(int)
        for item_id in adjustments.keys():
            item = lookup.get(item_id)
            if item is None:
                continue
            counts[item.category_key] += 1
        return counts

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

        requirement_targets = self._collect_requirement_targets(profile)
        deferral_counts = self._category_deferral_counts(profile)

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
        for key, context in categories.items():
            targets = requirement_targets.get(key, [])
            context.requirement_gap = max((target.deficit for target in targets), default=0)
            context.dependency_targets = [target.model_copy(deep=True) for target in targets]
            context.deferral_count = deferral_counts.get(key, 0)

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

    def _prioritize_modules(
        self,
        contexts: Iterable[_CategoryContext],
        *,
        profile: LearnerProfile,
        adjustments: Dict[str, int],
        previous_schedule: Optional[CurriculumSchedule],
    ) -> Tuple[List[CurriculumModule], Optional[SequencerAdvisorSummary]]:
        context_list = list(contexts)
        module_entries: List[tuple[float, CurriculumModule]] = []
        for context in context_list:
            priority = self._priority_score(context)
            for module in context.modules:
                module_entries.append((priority, module))
        if not module_entries:
            return [], None
        context_map = {context.key: context for context in context_list}
        adjusted_entries, advisor_summary = self._apply_sequencer_advisor_priorities(
            module_entries,
            profile=profile,
            contexts=context_map,
            adjustments=adjustments,
            previous_schedule=previous_schedule,
        )
        ordered = self._order_modules_with_dependencies(adjusted_entries)
        return ordered, advisor_summary

    def _apply_sequencer_advisor_priorities(
        self,
        module_entries: List[Tuple[float, CurriculumModule]],
        *,
        profile: LearnerProfile,
        contexts: Dict[str, _CategoryContext],
        adjustments: Dict[str, int],
        previous_schedule: Optional[CurriculumSchedule],
    ) -> Tuple[List[Tuple[float, CurriculumModule]], Optional[SequencerAdvisorSummary]]:
        settings = get_settings()
        if not should_advise_sequencer(settings):
            return module_entries, None

        mode = resolve_sequencer_mode(settings)
        now = datetime.now(timezone.utc)
        category_payloads: List[SequencerAdvisorCategoryPayload] = []
        requirement_payloads: List[SequencerAdvisorRequirementPayload] = []
        recommendation_targets: set[str] = set()

        for context in contexts.values():
            days_since_completion: Optional[int] = None
            if context.last_completion_at is not None:
                try:
                    days_since_completion = max((now - context.last_completion_at).days, 0)
                except Exception:  # noqa: BLE001
                    days_since_completion = None
            category_payloads.append(
                SequencerAdvisorCategoryPayload(
                    category_key=context.key,
                    category_label=context.label,
                    rating=context.rating,
                    weight=context.weight,
                    requirement_deficit=context.requirement_gap,
                    track_weight=context.track_weight,
                    average_score=context.average_score,
                    rating_delta=context.rating_delta,
                    deferral_count=context.deferral_count,
                    days_since_completion=days_since_completion,
                )
            )
            for target in context.dependency_targets:
                requirement_payloads.append(
                    SequencerAdvisorRequirementPayload(
                        milestone_item_id=target.milestone_item_id,
                        milestone_title=target.milestone_title,
                        category_key=target.category_key,
                        category_label=target.category_label,
                        target_rating=target.target_rating,
                        current_rating=target.current_rating,
                        deficit=target.deficit,
                        requirement_rationale=target.requirement_rationale,
                    )
                )
                recommendation_targets.add(target.milestone_item_id)

        module_payloads: List[SequencerAdvisorModulePayload] = []
        for priority, module in module_entries:
            module_payloads.append(
                SequencerAdvisorModulePayload(
                    module_id=module.module_id,
                    category_key=module.category_key,
                    priority_score=priority,
                    estimated_minutes=module.estimated_minutes or 45,
                )
            )

        payload = SequencerAdvisorRequestPayload(
            username=profile.username,
            categories=category_payloads,
            requirements=requirement_payloads,
            candidate_modules=module_payloads,
            schedule_adjustment_count=len(adjustments),
            sessions_per_week=(
                previous_schedule.sessions_per_week
                if previous_schedule and previous_schedule.sessions_per_week
                else self._default_sessions_per_week
            ),
            goal_summary=getattr(getattr(profile, "goal_inference", None), "summary", None)
            or (profile.goal or None),
        )

        emit_event(
            "sequencer_advisor_invoked",
            username=profile.username,
            mode=mode,
            module_count=len(module_payloads),
            requirement_count=len(requirement_payloads),
            target_count=len(recommendation_targets),
        )

        try:
            result = advise_sequence(payload, settings=settings)
        except SequencerAdvisorError as exc:
            emit_event(
                "sequencer_advisor_fallback",
                username=profile.username,
                mode=mode,
                reason=str(exc),
            )
            summary = SequencerAdvisorSummary(
                mode=mode,
                applied=False,
                ordering_source="heuristic",
                fallback_reason=str(exc),
            )
            return module_entries, summary

        emit_event(
            "sequencer_advisor_latency",
            username=profile.username,
            mode=mode,
            latency_ms=result.latency_ms,
            recommended_count=len(result.recommended_modules),
            slice_span=result.slice_span_days,
            warning_count=len(result.warnings),
        )

        summary = SequencerAdvisorSummary(
            mode=mode,
            applied=bool(result.recommended_modules),
            ordering_source="advisor" if result.recommended_modules else "heuristic",
            recommended_modules=list(result.recommended_modules),
            slice_span_days=result.slice_span_days,
            notes=result.notes,
            version=result.version,
            latency_ms=result.latency_ms,
            fallback_reason=None,
            warning_count=len(result.warnings),
        )
        if result.warnings:
            merged_note = " ".join(result.warnings)
            summary.notes = f"{summary.notes} {merged_note}".strip() if summary.notes else merged_note

        ranking = {module_id: index for index, module_id in enumerate(result.recommended_modules)}
        max_rank = len(result.recommended_modules) or 1
        adjusted: List[Tuple[float, CurriculumModule]] = []
        for priority, module in module_entries:
            rank = ranking.get(module.module_id)
            if rank is not None:
                boost = max(max_rank - rank, 1) * 0.2
                priority += boost
            adjusted.append((priority, module))

        return adjusted, summary

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
        if item.kind == "milestone":
            minutes = max(int(item.recommended_minutes or MIN_SESSION_MINUTES), MIN_SESSION_MINUTES)
            clone = item.model_copy()
            clone.recommended_minutes = minutes
            clone.prerequisites = list(item.prerequisites)
            clone.user_adjusted = False
            clone.milestone_brief = item.milestone_brief.model_copy(deep=True) if item.milestone_brief else None
            clone.milestone_progress = (
                item.milestone_progress.model_copy(deep=True) if item.milestone_progress else None
            )
            clone.milestone_project = (
                item.milestone_project.model_copy(deep=True) if item.milestone_project else None
            )
            clone.milestone_requirements = [
                requirement.model_copy(deep=True) for requirement in item.milestone_requirements
            ]
            clone.requirement_advisor_version = getattr(item, "requirement_advisor_version", None)
            clone.requirement_progress_snapshot = [
                requirement.model_copy(deep=True)
                for requirement in getattr(item, "requirement_progress_snapshot", []) or []
            ]
            clone.unlock_notified_at = getattr(item, "unlock_notified_at", None)
            return [clone]

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
            cloned.milestone_requirements = [
                requirement.model_copy(deep=True) for requirement in item.milestone_requirements
            ]
            cloned.requirement_advisor_version = getattr(item, "requirement_advisor_version", None)
            cloned.requirement_progress_snapshot = [
                requirement.model_copy(deep=True)
                for requirement in getattr(item, "requirement_progress_snapshot", []) or []
            ]
            cloned.unlock_notified_at = getattr(item, "unlock_notified_at", None)
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
            part.milestone_requirements = [
                requirement.model_copy(deep=True) for requirement in item.milestone_requirements
            ]
            part.requirement_advisor_version = getattr(item, "requirement_advisor_version", None)
            part.requirement_progress_snapshot = [
                requirement.model_copy(deep=True)
                for requirement in getattr(item, "requirement_progress_snapshot", []) or []
            ]
            part.unlock_notified_at = getattr(item, "unlock_notified_at", None)
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
        categories: Dict[str, _CategoryContext],
    ) -> MilestoneBrief:
        lookup = self._build_category_lookup(profile, categories)
        fallback_brief = self._fallback_milestone_brief(
            module,
            context,
            profile,
            lesson_tail_id,
            quiz_tail_id,
            categories,
            lookup,
        )
        fallback_requirements = list(fallback_brief.requirements or [])
        settings = get_settings()
        if not should_author(settings):
            return fallback_brief

        mode = resolve_mode(settings)
        payload = self._author_payload(module, context, profile, fallback_brief)
        emit_event(
            "milestone_author_invoked",
            username=profile.username,
            module_id=module.module_id,
            category_key=module.category_key,
            mode=mode,
        )
        try:
            result = author_milestone_brief(settings, payload)
        except MilestoneAuthorError as exc:
            emit_event(
                "milestone_author_fallback",
                username=profile.username,
                module_id=module.module_id,
                category_key=module.category_key,
                mode=mode,
                reason=str(exc),
            )
            fallback_brief.warnings.append("Agent brief unavailable; using template guidance.")
            return fallback_brief
        except Exception:  # noqa: BLE001
            logger.exception("Milestone author failed for module=%s", module.module_id)
            emit_event(
                "milestone_author_fallback",
                username=profile.username,
                module_id=module.module_id,
                category_key=module.category_key,
                mode=mode,
                reason="exception",
            )
            fallback_brief.warnings.append("Agent brief failed; using template guidance.")
            return fallback_brief

        brief = result.brief
        brief.prerequisites = fallback_brief.prerequisites
        if not brief.elo_focus and fallback_brief.elo_focus:
            brief.elo_focus = fallback_brief.elo_focus
        if not brief.external_work and fallback_brief.external_work:
            brief.external_work = fallback_brief.external_work
        if not brief.capture_prompts and fallback_brief.capture_prompts:
            brief.capture_prompts = fallback_brief.capture_prompts
        if not brief.kickoff_steps and fallback_brief.kickoff_steps:
            brief.kickoff_steps = fallback_brief.kickoff_steps
        if not brief.coaching_prompts and fallback_brief.coaching_prompts:
            brief.coaching_prompts = fallback_brief.coaching_prompts
        if not brief.success_criteria and fallback_brief.success_criteria:
            brief.success_criteria = fallback_brief.success_criteria
        if not brief.objectives and fallback_brief.objectives:
            brief.objectives = fallback_brief.objectives
        if not brief.deliverables and fallback_brief.deliverables:
            brief.deliverables = fallback_brief.deliverables
        if not brief.resources and fallback_brief.resources:
            brief.resources = fallback_brief.resources
        if brief.project is None and fallback_brief.project is not None:
            brief.project = fallback_brief.project
        brief.requirements = self._merge_milestone_requirements(
            profile,
            context,
            getattr(brief, "requirements", []) or [],
            fallback_requirements,
            categories,
            lookup,
            module=module,
        )
        advisor_result = self._run_requirement_advisor(
            profile=profile,
            module=module,
            context=context,
            brief=brief,
            fallback_requirements=fallback_requirements,
            categories=categories,
            lookup=lookup,
        )
        if advisor_result:
            brief.requirements = advisor_result.requirements
            brief.advisor_version = advisor_result.version
            brief.advisor_warnings = advisor_result.warnings
            if advisor_result.warnings:
                merged_warning_set = dict.fromkeys(brief.warnings + advisor_result.warnings)
                brief.warnings = list(merged_warning_set.keys())
        brief.source = "agent"
        combined_warnings = list(
            dict.fromkeys(fallback_brief.warnings + brief.warnings + result.warnings)
        )
        brief.warnings = combined_warnings
        emit_event(
            "milestone_author_latency",
            username=profile.username,
            module_id=module.module_id,
            category_key=module.category_key,
            latency_ms=result.latency_ms,
            warnings=len(result.warnings),
            mode=mode,
        )
        return brief

    def _fallback_milestone_brief(
        self,
        module: CurriculumModule,
        context: _CategoryContext,
        profile: LearnerProfile,
        lesson_tail_id: str,
        quiz_tail_id: str,
        categories: Dict[str, _CategoryContext],
        lookup: _CategoryLookup,
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
        format_context = {
            "goal": profile.goal or "",
            "target_outcome": profile.goal or profile.use_case or "",
            "module_title": module.title,
            "track_label": context.label or module.category_key,
            "primary_focus": context.label or module.category_key,
            "primary_technology": module.category_key,
            "track_focus": context.label or module.category_key,
            "use_case": profile.use_case or "",
        }
        project = select_milestone_project(
            profile,
            module.category_key,
            category_label=context.label,
            goal_inference=getattr(profile, "goal_inference", None),
            format_context=format_context,
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
            if module.category_key and module.category_key not in project.related_categories:
                project.related_categories.append(module.category_key)
            brief.project = project
        related_categories = list(getattr(project, "related_categories", []) or [])
        brief.requirements = self._fallback_requirements(
            module,
            context,
            profile,
            categories,
            lookup,
            related_categories=related_categories,
        )
        return brief

    def _author_payload(
        self,
        module: CurriculumModule,
        context: _CategoryContext,
        profile: LearnerProfile,
        fallback_brief: MilestoneBrief,
    ) -> MilestoneAuthorRequestPayload:
        goal_tracks: List[Dict[str, Any]] = []
        inference = getattr(profile, "goal_inference", None)
        if inference and getattr(inference, "tracks", None):
            goal_tracks = [
                track.model_dump(mode="json")
                for track in inference.tracks[:6]
            ]
        plan = getattr(profile, "elo_category_plan", None)
        elo_categories: List[Dict[str, Any]] = []
        if plan and getattr(plan, "categories", None):
            elo_categories = [
                category.model_dump(mode="json")
                for category in plan.categories[:12]
            ]
        history = [
            completion.model_dump(mode="json")
            for completion in getattr(profile, "milestone_completions", [])[:5]
        ]
        candidate_categories: Set[str] = {
            requirement.category_key
            for requirement in getattr(fallback_brief, "requirements", []) or []
            if getattr(requirement, "category_key", None)
        }
        project = getattr(fallback_brief, "project", None)
        if project and getattr(project, "related_categories", None):
            candidate_categories.update(
                value for value in project.related_categories if value
            )
        candidate_categories_list = sorted(candidate_categories)
        return MilestoneAuthorRequestPayload(
            username=getattr(profile, "username", None),
            goal=getattr(profile, "goal", None),
            use_case=getattr(profile, "use_case", None),
            strengths=getattr(profile, "strengths", None),
            category_key=module.category_key,
            category_label=context.label,
            module_title=module.title,
            module_summary=module.summary,
            module_objectives=list(module.objectives),
            module_deliverables=list(module.deliverables),
            goal_tracks=goal_tracks,
            milestone_history=history,
            milestone_progress=None,
            schedule_notes=self._author_schedule_notes(context, profile),
            timezone=getattr(profile, "timezone", None),
            previous_brief=fallback_brief.model_dump(mode="json"),
            elo_snapshot=dict(getattr(profile, "elo_snapshot", {}) or {}),
            elo_categories=elo_categories,
            candidate_categories=candidate_categories_list,
        )

    def _author_schedule_notes(
        self,
        context: _CategoryContext,
        profile: LearnerProfile,
    ) -> Optional[str]:
        details: List[str] = []
        if context.weight:
            details.append(f"Category weight {context.weight:.2f}")
        if context.track_weight:
            details.append(f"Track weight {context.track_weight:.2f}")
        if context.rating:
            details.append(f"Current rating {context.rating}")
        if context.rating_delta:
            details.append(f"Recent rating delta {context.rating_delta}")
        if context.average_score is not None:
            details.append(f"Assessment average {context.average_score:.2f}")
        curriculum = getattr(profile, "curriculum_plan", None)
        overview = getattr(curriculum, "overview", None) if curriculum else None
        if overview:
            details.append(f"Curriculum focus: {overview[:180]}")
        return "; ".join(details) if details else None

    def _default_requirement_threshold(
        self,
        profile: LearnerProfile,
        category_key: str,
        context: _CategoryContext,
    ) -> int:
        baseline = 1200
        plan = getattr(profile, "elo_category_plan", None)
        if plan and getattr(plan, "categories", None):
            for category in plan.categories:
                if category.key == category_key:
                    try:
                        baseline = max(baseline, int(category.starting_rating))
                    except (TypeError, ValueError):
                        pass
                    break
        if getattr(context, "rating", None):
            try:
                baseline = max(baseline, int(context.rating))
            except (TypeError, ValueError):
                pass
        snapshot = getattr(profile, "elo_snapshot", {}) or {}
        current = int(snapshot.get(category_key, 0) or 0)
        if current > 0:
            baseline = max(baseline, current + 40)
        return min(max(baseline, 1100), 2400)

    def _fallback_requirements(
        self,
        module: CurriculumModule,
        context: _CategoryContext,
        profile: LearnerProfile,
        categories: Dict[str, _CategoryContext],
        lookup: _CategoryLookup,
        *,
        related_categories: Optional[Iterable[str]] = None,
    ) -> List[MilestoneRequirement]:
        module_index: Dict[str, _CategoryContext] = {}
        for cat_context in categories.values():
            for mod in getattr(cat_context, "modules", []) or []:
                module_index.setdefault(mod.module_id, cat_context)

        snapshot = lookup.snapshot_ratings
        seen: Set[str] = set()
        requirements: List[MilestoneRequirement] = []

        def _append_requirement(
            candidate_key: Optional[str],
            candidate_label: Optional[str],
        ) -> None:
            if not candidate_key and not candidate_label:
                return
            resolved_key, resolved_label, resolved_context = self._resolve_category_metadata(
                candidate_key,
                candidate_label,
                lookup=lookup,
                categories=categories,
            )
            if resolved_key in seen:
                return
            minimum = self._default_requirement_threshold(profile, resolved_key, resolved_context)
            minimum = min(max(minimum, 1100), 2400)
            rationale = f"Reach {minimum} in {resolved_label} before launching this milestone."
            current = int(snapshot.get(resolved_key, 0) or 0)
            requirements.append(
                MilestoneRequirement(
                    category_key=resolved_key,
                    category_label=resolved_label,
                    minimum_rating=minimum,
                    rationale=rationale,
                    current_rating=current,
                    progress_percent=_clamp_progress(current, minimum),
                )
            )
            seen.add(resolved_key)

        # Always include the primary milestone category.
        _append_requirement(module.category_key, context.label)

        # Include categories tied to prerequisite modules.
        for prerequisite_id in getattr(module, "prerequisite_module_ids", []) or []:
            prereq_context = module_index.get(prerequisite_id)
            if prereq_context:
                _append_requirement(prereq_context.key, prereq_context.label)

        # Include categories suggested by the milestone project template/agent.
        for related in related_categories or []:
            _append_requirement(related, related)

        if not requirements:
            label = context.label or module.category_key
            minimum = self._default_requirement_threshold(profile, module.category_key, context)
            minimum = min(max(minimum, 1100), 2400)
            rationale = (
                f"Reach {minimum} in {label} before launching this milestone."
                if label
                else f"Reach a rating of {minimum} before launching this milestone."
            )
            requirements.append(
                MilestoneRequirement(
                    category_key=module.category_key,
                    category_label=label or module.category_key,
                    minimum_rating=minimum,
                    rationale=rationale,
                )
            )

        return requirements

    def _merge_milestone_requirements(
        self,
        profile: LearnerProfile,
        context: _CategoryContext,
        generated: Iterable[MilestoneRequirement],
        fallback: List[MilestoneRequirement],
        categories: Dict[str, _CategoryContext],
        lookup: _CategoryLookup,
        *,
        module: CurriculumModule,
    ) -> List[MilestoneRequirement]:
        fallback_by_slug: Dict[str, MilestoneRequirement] = {
            self._slugify_category(entry.category_key): entry for entry in fallback if entry.category_key
        }
        merged: List[MilestoneRequirement] = []
        seen_keys: Set[str] = set()
        snapshot = lookup.snapshot_ratings
        fallback_slugs = set(fallback_by_slug.keys())
        generated_slugs: Set[str] = set()

        for entry in generated or []:
            key = (getattr(entry, "category_key", "") or "").strip()
            if not key:
                continue
            resolved_key, resolved_label, resolved_context = self._resolve_category_metadata(
                key,
                getattr(entry, "category_label", None),
                lookup=lookup,
                categories=categories,
            )
            slug = self._slugify_category(resolved_key)
            generated_slugs.add(slug)
            if resolved_key in seen_keys:
                continue
            try:
                minimum = int(getattr(entry, "minimum_rating", 0) or 0)
            except (TypeError, ValueError):
                minimum = 0
            if minimum <= 0:
                fallback_requirement = fallback_by_slug.get(slug)
                if fallback_requirement:
                    minimum = fallback_requirement.minimum_rating
                else:
                    minimum = self._default_requirement_threshold(profile, resolved_key, resolved_context)
            minimum = min(max(minimum, 1100), 2400)
            rationale = getattr(entry, "rationale", None)
            current = int(
                getattr(entry, "current_rating", None)
                or snapshot.get(resolved_key, 0)
            )
            progress = getattr(entry, "progress_percent", None)
            if progress is None:
                progress = _clamp_progress(current, minimum)
            merged.append(
                MilestoneRequirement(
                    category_key=resolved_key,
                    category_label=resolved_label,
                    minimum_rating=minimum,
                    rationale=rationale,
                    current_rating=current,
                    progress_percent=progress,
                    last_met_at=getattr(entry, "last_met_at", None),
                )
            )
            seen_keys.add(resolved_key)

        for entry in fallback:
            resolved_key, resolved_label, resolved_context = self._resolve_category_metadata(
                entry.category_key,
                entry.category_label,
                lookup=lookup,
                categories=categories,
            )
            if resolved_key in seen_keys:
                continue
            minimum = min(max(int(getattr(entry, "minimum_rating", 0) or 0), 1100), 2400)
            current = int(snapshot.get(resolved_key, getattr(entry, "current_rating", 0) or 0))
            progress = getattr(entry, "progress_percent", None)
            if progress is None:
                progress = _clamp_progress(current, minimum)
            merged.append(
                MilestoneRequirement(
                    category_key=resolved_key,
                    category_label=resolved_label,
                    minimum_rating=minimum,
                    rationale=getattr(entry, "rationale", None),
                    current_rating=current,
                    progress_percent=progress,
                    last_met_at=getattr(entry, "last_met_at", None),
                )
            )
            seen_keys.add(resolved_key)

        if not merged:
            return [entry.model_copy(deep=True) for entry in fallback]

        if len(merged) > 1:
            emit_event(
                "milestone_requirements_multicategory",
                username=profile.username,
                module_id=module.module_id,
                category_key=module.category_key,
                requirement_keys=[requirement.category_key for requirement in merged],
            )

        missing_slugs = fallback_slugs - generated_slugs
        if missing_slugs:
            emit_event(
                "milestone_requirement_fallback_applied",
                username=profile.username,
                module_id=module.module_id,
                category_key=module.category_key,
                missing_categories=[
                    fallback_by_slug[slug].category_key for slug in sorted(missing_slugs) if slug in fallback_by_slug
                ],
            )
        return merged

    def _run_requirement_advisor(
        self,
        *,
        profile: LearnerProfile,
        module: CurriculumModule,
        context: _CategoryContext,
        brief: MilestoneBrief,
        fallback_requirements: List[MilestoneRequirement],
        categories: Dict[str, _CategoryContext],
        lookup: _CategoryLookup,
    ) -> Optional[RequirementAdvisorResult]:
        settings = get_settings()
        if not should_advise_requirements(settings):
            return None
        baseline_requirements = list(brief.requirements or fallback_requirements or [])
        if not baseline_requirements:
            return None
        candidate_categories: Set[str] = {
            requirement.category_key
            for requirement in baseline_requirements
            if getattr(requirement, "category_key", None)
        }
        project = getattr(brief, "project", None)
        if project and getattr(project, "related_categories", None):
            for related in project.related_categories:
                resolved_key, _, _ = self._resolve_category_metadata(
                    related,
                    related,
                    lookup=lookup,
                    categories=categories,
                )
                candidate_categories.add(resolved_key)
        candidate_list = sorted({value for value in candidate_categories if value})
        mode = resolve_requirement_mode(settings)
        emit_event(
            "requirement_advisor_invoked",
            username=profile.username,
            module_id=module.module_id,
            category_key=module.category_key,
            mode=mode,
        )
        payload = RequirementAdvisorRequestPayload(
            username=profile.username,
            category_key=module.category_key,
            category_label=context.label or module.category_key,
            baseline_requirements=[
                RequirementAdvisorRequirementPayload(
                    category_key=req.category_key,
                    minimum_rating=req.minimum_rating,
                    rationale=req.rationale,
                )
                for req in baseline_requirements
            ],
            elo_snapshot=dict(getattr(profile, "elo_snapshot", {}) or {}),
            recent_rating_changes=(
                {module.category_key: int(context.rating_delta)}
                if context.rating_delta is not None
                else {}
            ),
            goal_summary=getattr(getattr(profile, "goal_inference", None), "summary", None)
            or (profile.goal or None),
            schedule_notes=brief.rationale
            or getattr(getattr(profile, "curriculum_plan", None), "overview", None),
            outstanding_prereqs=[
                prereq.title
                for prereq in getattr(brief, "prerequisites", []) or []
                if getattr(prereq, "required", True)
            ],
            candidate_categories=candidate_list,
        )
        try:
            result = advise_requirements(payload, settings=settings)
        except RequirementAdvisorError as exc:
            emit_event(
                "requirement_advisor_fallback",
                username=profile.username,
                module_id=module.module_id,
                category_key=module.category_key,
                mode=mode,
                reason=str(exc),
            )
            return None
        emit_event(
            "requirement_advisor_latency",
            username=profile.username,
            module_id=module.module_id,
            category_key=module.category_key,
            mode=mode,
            latency_ms=result.latency_ms,
            requirement_count=len(result.requirements),
            version=result.version,
        )
        return result

    def _apply_requirement_progress(self, item: SequencedWorkItem, profile: LearnerProfile) -> None:
        snapshot = dict(getattr(profile, "elo_snapshot", {}) or {})
        requirements = getattr(item, "milestone_requirements", []) or []
        for requirement in requirements:
            current = int(snapshot.get(requirement.category_key, 0) or 0)
            requirement.current_rating = current
            requirement.progress_percent = _clamp_progress(current, requirement.minimum_rating)
            if current >= requirement.minimum_rating and getattr(requirement, "last_met_at", None) is None:
                requirement.last_met_at = datetime.now(timezone.utc)
                emit_event(
                    "milestone_requirement_met",
                    username=profile.username,
                    category_key=requirement.category_key,
                    item_id=item.item_id,
                    current_rating=current,
                    minimum_rating=requirement.minimum_rating,
                )
        item.requirement_progress_snapshot = [
            requirement.model_copy(deep=True) for requirement in requirements
        ]
        summary = self._summarize_requirements(requirements)
        item.requirement_summary = summary.model_copy(deep=True) if summary else None

    def _build_milestone_queue(
        self,
        *,
        scheduled_items: Sequence[SequencedWorkItem],
        profile: LearnerProfile,
        categories: Dict[str, _CategoryContext],
    ) -> Tuple[List[MilestoneQueueEntry], Dict[str, List[DependencyTarget]]]:
        queue: List[MilestoneQueueEntry] = []
        dependency_map: Dict[str, List[DependencyTarget]] = defaultdict(list)
        for item in scheduled_items:
            if item.kind != "milestone":
                continue
            requirements = [
                requirement.model_copy(deep=True)
                for requirement in getattr(item, "milestone_requirements", []) or []
            ]
            requirements_summary = self._summarize_requirements(requirements)
            lock_reason = self._milestone_lock_reason(item, scheduled_items)
            unmet = [
                requirement
                for requirement in requirements
                if requirement.current_rating < requirement.minimum_rating
            ]
            dependency_targets: List[DependencyTarget] = []
            for requirement in unmet:
                deficit = max(requirement.minimum_rating - requirement.current_rating, 0)
                dependency_target = DependencyTarget(
                    milestone_item_id=item.item_id,
                    milestone_title=item.title,
                    category_key=requirement.category_key,
                    category_label=requirement.category_label,
                    target_rating=requirement.minimum_rating,
                    current_rating=requirement.current_rating,
                    deficit=deficit,
                    requirement_rationale=requirement.rationale,
                    advisor_version=getattr(item, "requirement_advisor_version", None),
                )
                dependency_targets.append(dependency_target)
                dependency_map[requirement.category_key].append(dependency_target)
            if item.launch_status == "completed":
                state: Literal["locked", "ready", "in_progress", "completed"] = "completed"
            elif item.launch_status == "in_progress":
                state = "in_progress"
            elif not unmet and not lock_reason:
                state = "ready"
            else:
                state = "locked"
            badges: List[str] = []
            if state == "completed":
                badges.append("Completed")
            elif state == "in_progress":
                badges.append("In progress")
            elif state == "ready":
                badges.append("Ready")
            else:
                badges.append("Locked")
            next_actions: List[str] = []
            warnings: List[str] = []
            for requirement in unmet:
                next_actions.append(
                    f"Reach {requirement.minimum_rating} in {requirement.category_label} "
                    f"(current {requirement.current_rating})."
                )
                if requirement.rationale:
                    warnings.append(requirement.rationale)
            if lock_reason:
                warnings.append(lock_reason)
            if state == "ready":
                next_actions.append("Launch the milestone when you can focus for 60–90 minutes.")
                if getattr(item, "unlock_notified_at", None) is None:
                    timestamp = datetime.now(timezone.utc)
                    item.unlock_notified_at = timestamp
                    emit_event(
                        "milestone_unlock_ready",
                        username=profile.username,
                        item_id=item.item_id,
                        category_key=item.category_key,
                        advisor_version=getattr(item, "requirement_advisor_version", None),
                    )
            elif state == "in_progress":
                next_actions.append("Capture blockers and artefacts before marking complete.")
            elif state == "completed":
                next_actions.append("Review feedback and celebrate the milestone win.")
            summary = item.summary
            if not summary and item.milestone_brief and item.milestone_brief.summary:
                summary = item.milestone_brief.summary
            queue.append(
                MilestoneQueueEntry(
                    item_id=item.item_id,
                    title=item.title,
                    summary=summary,
                    category_key=item.category_key,
                    readiness_state=state,
                    badges=list(dict.fromkeys(badges)),
                    next_actions=list(dict.fromkeys([action for action in next_actions if action])),
                    warnings=list(dict.fromkeys([warning for warning in warnings if warning])),
                    launch_locked_reason=lock_reason,
                    last_updated_at=self._milestone_last_updated(item),
                    requirements=requirements,
                    requirement_summary=(
                        requirements_summary.model_copy(deep=True)
                        if requirements_summary
                        else None
                    ),
                    dependency_targets=[target.model_copy(deep=True) for target in dependency_targets],
                )
            )
        queue.sort(
            key=lambda entry: (
                {"ready": 3, "in_progress": 2, "locked": 1, "completed": 0}.get(entry.readiness_state, 0),
                max((req.progress_percent for req in entry.requirements), default=0.0),
            ),
            reverse=True,
        )
        return queue, dependency_map

    def _milestone_last_updated(self, item: SequencedWorkItem) -> Optional[datetime]:
        candidates: List[datetime] = []
        if getattr(item, "milestone_progress", None) and getattr(item.milestone_progress, "recorded_at", None):
            candidates.append(item.milestone_progress.recorded_at)
        if getattr(item, "last_completed_at", None):
            candidates.append(item.last_completed_at)
        if getattr(item, "last_launched_at", None):
            candidates.append(item.last_launched_at)
        if not candidates:
            return None
        return max(candidates)

    def _milestone_lock_reason(
        self,
        item: SequencedWorkItem,
        scheduled_items: Sequence[SequencedWorkItem],
    ) -> Optional[str]:
        if item.launch_status == "completed":
            return None
        incomplete_prereqs = [
            other
            for other in scheduled_items
            if other.item_id != item.item_id
            and other.kind != "milestone"
            and other.recommended_day_offset <= item.recommended_day_offset
            and getattr(other, "launch_status", "pending") != "completed"
        ]
        if incomplete_prereqs:
            return "Complete earlier lessons and quizzes before unlocking this milestone."
        return None

    def _match_track(
        self,
        profile: LearnerProfile,
        category_key: str,
        category_label: str,
    ) -> Optional[FoundationTrack]:
        inference = getattr(profile, "goal_inference", None)
        if not inference or not getattr(inference, "tracks", None):
            return None
        normalized_key = category_key.lower()
        label_lower = category_label.lower()

        for track in inference.tracks:
            if track.track_id == category_key:
                return track
            if any(ref.category_key == category_key for ref in track.recommended_modules):
                return track
            if track.label.lower() == label_lower:
                return track

        for track in inference.tracks:
            combined_focus = " ".join(track.focus_areas).lower()
            combined_tech = " ".join(track.technologies).lower()
            if normalized_key and (normalized_key in combined_focus or normalized_key in combined_tech):
                return track
            if label_lower and (label_lower in combined_focus or label_lower in combined_tech):
                return track

        return inference.tracks[0] if inference.tracks else None

    def _milestone_format_context(
        self,
        profile: LearnerProfile,
        module: CurriculumModule,
        context: _CategoryContext,
        track: Optional[FoundationTrack],
    ) -> dict[str, str]:
        inference = getattr(profile, "goal_inference", None)
        target_outcome = ""
        if inference and getattr(inference, "target_outcomes", None):
            target_outcome = inference.target_outcomes[0]

        primary_focus = context.label
        if track and track.focus_areas:
            primary_focus = track.focus_areas[0]

        primary_technology = context.label
        if track and track.technologies:
            primary_technology = track.technologies[0]

        return {
            "goal": profile.goal or "",
            "goal_summary": getattr(inference, "summary", "") if inference else "",
            "use_case": profile.use_case or "",
            "strengths": profile.strengths or "",
            "module_title": module.title,
            "module_summary": module.summary or "",
            "module_objectives": "; ".join(module.objectives) if module.objectives else "",
            "category_label": context.label,
            "category_key": module.category_key,
            "track_label": track.label if track else context.label,
            "track_focus": ", ".join(track.focus_areas) if track and track.focus_areas else "",
            "primary_focus": primary_focus,
            "track_technologies": ", ".join(track.technologies) if track and track.technologies else "",
            "primary_technology": primary_technology,
            "target_outcome": target_outcome or (profile.goal or ""),
        }

    @staticmethod
    def _merge_unique(*iterables: Iterable[str]) -> List[str]:
        merged: List[str] = []
        seen: set[str] = set()
        for collection in iterables:
            if not collection:
                continue
            for item in collection:
                if not item:
                    continue
                if item not in seen:
                    seen.add(item)
                    merged.append(item)
        return merged

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
        requirement_component = min(context.requirement_gap / 80.0, 3.0)
        deferral_component = min(context.deferral_count * 0.15, 1.5)
        return (
            weight_component
            + rating_component
            + score_component
            + delta_component
            + track_component
            + requirement_component
            + deferral_component
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
        dependency_focus: List[str] = []
        for item in scheduled_items:
            for target in getattr(item, "dependency_targets", []) or []:
                if getattr(target, "deficit", 0) > 0:
                    label = getattr(target, "category_label", target.category_key)
                    dependency_focus.append(f"{label} → {target.target_rating}")
        if dependency_focus:
            adjustment_notes.append(
                "Unlock focus: " + ", ".join(dependency_focus[:3])
            )
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


def _clamp_progress(current: int, minimum: int) -> float:
    if minimum <= 0:
        return 1.0
    try:
        return max(0.0, min(float(current) / float(minimum), 1.0))
    except ZeroDivisionError:
        return 1.0


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
