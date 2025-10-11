"""Guardrails helpers for Arcadia Coach."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Dict, Tuple

from guardrails.runtime import instantiate_guardrails, load_config_bundle, run_guardrails
from openai import AsyncOpenAI

from .config import get_settings

logger = logging.getLogger(__name__)

_GUARDRAILS_CONFIG: Dict[str, Any] = {
    "guardrails": [
        {
            "name": "Contains PII",
            "config": {
                "block": True,
                "entities": [
                    "CREDIT_CARD",
                    "US_BANK_NUMBER",
                    "US_PASSPORT",
                    "US_SSN",
                ],
            },
        },
        {
            "name": "Moderation",
            "config": {
                "categories": [
                    "sexual/minors",
                    "hate/threatening",
                    "harassment/threatening",
                    "self-harm/instructions",
                    "violence/graphic",
                    "illicit/violent",
                ]
            },
        },
        {
            "name": "Jailbreak",
            "config": {
                "model": "gpt-4.1-mini",
                "confidence_threshold": 0.7,
            },
        },
    ]
}

_settings = get_settings()
_client: AsyncOpenAI | None
_ctx: SimpleNamespace | None

if _settings.openai_api_key:
    _client = AsyncOpenAI(api_key=_settings.openai_api_key)
    _ctx = SimpleNamespace(guardrail_llm=_client)
    _bundle = instantiate_guardrails(load_config_bundle(_GUARDRAILS_CONFIG))
else:
    logger.warning("OPENAI_API_KEY missing; guardrail checks are disabled.")
    _client = None
    _ctx = None
    _bundle = None


def _has_tripwire(results: Any) -> bool:
    return any(getattr(result, "tripwire_triggered", False) for result in results or [])


def _checked_text(results: Any, fallback: str) -> str:
    for result in results or []:
        info = getattr(result, "info", None) or {}
        if isinstance(info, dict) and "checked_text" in info:
            return info.get("checked_text") or fallback
    return fallback


def _build_failure(results: Any) -> Dict[str, Any]:
    failures = []
    for result in results or []:
        if getattr(result, "tripwire_triggered", False):
            info = getattr(result, "info", None) or {}
            failure = {"guardrail_name": info.get("guardrail_name")}
            for key in (
                "flagged",
                "confidence",
                "threshold",
                "hallucination_type",
                "hallucinated_statements",
                "verified_statements",
            ):
                if key in (info or {}):
                    failure[key] = info.get(key)
            failures.append(failure)
    return {"failed": bool(failures), "failures": failures}


async def run_guardrail_checks(text: str) -> Tuple[bool, str | Dict[str, Any]]:
    """Run guardrail policies. Return (allowed, payload)."""
    if _ctx is None or _bundle is None:
        return True, text
    results = await run_guardrails(
        _ctx,
        text,
        "text/plain",
        _bundle,
        suppress_tripwire=True,
    )
    if _has_tripwire(results):
        return False, _build_failure(results)
    sanitized = _checked_text(results, text) if results else text
    return True, sanitized
