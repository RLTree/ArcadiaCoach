"""Profile-centric REST endpoints surfaced to the macOS client."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from .agent_models import (
    EloCategoryDefinitionPayload,
    EloCategoryPlanPayload,
    EloRubricBandPayload,
    LearnerProfilePayload,
    SkillRatingPayload,
)
from .learner_profile import LearnerProfile, profile_store


router = APIRouter(prefix="/api/profile", tags=["profile"])


def _serialize_profile(profile: LearnerProfile) -> LearnerProfilePayload:
    plan = profile.elo_category_plan
    plan_payload: EloCategoryPlanPayload | None = None
    if plan:
        plan_payload = EloCategoryPlanPayload(
            generated_at=plan.generated_at,
            source_goal=plan.source_goal,
            strategy_notes=plan.strategy_notes,
            categories=[
                EloCategoryDefinitionPayload(
                    key=category.key,
                    label=category.label,
                    description=category.description,
                    focus_areas=category.focus_areas,
                    weight=category.weight,
                    rubric=[
                        EloRubricBandPayload(level=band.level, descriptor=band.descriptor)
                        for band in category.rubric
                    ],
                    starting_rating=category.starting_rating,
                )
                for category in plan.categories
            ],
        )
    return LearnerProfilePayload(
        username=profile.username,
        goal=profile.goal,
        use_case=profile.use_case,
        strengths=profile.strengths,
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
    )


@router.get("/{username}", response_model=LearnerProfilePayload, status_code=status.HTTP_200_OK)
def get_profile(username: str) -> LearnerProfilePayload:
    profile = profile_store.get(username)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learner profile for '{username}' was not found.",
        )
    return _serialize_profile(profile)


@router.get(
    "/{username}/elo-plan",
    response_model=EloCategoryPlanPayload,
    status_code=status.HTTP_200_OK,
)
def get_elo_category_plan(username: str) -> EloCategoryPlanPayload:
    profile = profile_store.get(username)
    if profile is None or profile.elo_category_plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ELO categories for '{username}' are not set.",
        )
    payload = _serialize_profile(profile)
    if payload.elo_category_plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ELO categories for '{username}' are not set.",
        )
    return payload.elo_category_plan


__all__ = ["router"]
