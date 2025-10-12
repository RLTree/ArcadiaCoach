"""Utility tools exposed to the Arcadia Coach agent."""

from __future__ import annotations

from typing import Any, Dict, List

from agents import function_tool

from .learner_profile import profile_store
from .vector_memory import learner_memory


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


@function_tool
def progress_start(total: int) -> Dict[str, Any]:
    """Initialise a multi-step progress tracker."""
    if total <= 0:
        total = 1
    return _progress_payload(idx=0, total=total)


@function_tool
def progress_advance(idx: int, total: int) -> Dict[str, Any]:
    """Advance the progress tracker and surface the updated status."""
    if total <= 0:
        total = 1
    next_idx = min(idx + 1, total - 1)
    return _progress_payload(idx=next_idx, total=total)


@function_tool
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


@function_tool
def learner_profile_get(username: str) -> Dict[str, Any]:
    """Fetch the persisted learner profile for the given username."""
    profile = profile_store.get(username)
    if profile is None:
        return {"found": False, "username": username}
    return {"found": True, "profile": profile.model_dump(mode="json")}


@function_tool
def learner_profile_update(
    username: str,
    goal: str | None = None,
    use_case: str | None = None,
    strengths: str | None = None,
    knowledge_tags: List[str] | None = None,
) -> Dict[str, Any]:
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
    profile = profile_store.apply_metadata(username, metadata)
    return {"profile": profile.model_dump(mode="json")}


@function_tool
def learner_memory_write(username: str, note: str, tags: List[str] | None = None) -> Dict[str, Any]:
    """Record a personalised memory note for the learner."""
    result = learner_memory.record_note(username=username, note=note, tags=tags or [])
    return {"memory": result}


AGENT_SUPPORT_TOOLS = [
    progress_start,
    progress_advance,
    elo_update,
    learner_profile_get,
    learner_profile_update,
    learner_memory_write,
]

__all__ = [
    "AGENT_SUPPORT_TOOLS",
    "elo_update",
    "learner_memory_write",
    "learner_profile_get",
    "learner_profile_update",
    "progress_advance",
    "progress_start",
]
