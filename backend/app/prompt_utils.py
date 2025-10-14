"""Utilities that build Arcadia Coach agent prompts."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ATTACHMENT_MODELS_REQUIRE_FILE_SEARCH = {"gpt-5", "gpt-5-mini"}


def _attachment_attr(attachment: Any, key: str) -> Any:
    if isinstance(attachment, Mapping):
        return attachment.get(key)
    return getattr(attachment, key, None)


def _format_size_label(value: Any) -> str:
    if isinstance(value, int) and value >= 0:
        return f"{value} bytes"
    return "size unknown"


def apply_preferences_overlay(
    base_text: str,
    attachments: Sequence[Any],
    *,
    web_enabled: bool,
    reasoning_level: str,
    model: str,
    schedule_summary: str | None = None,
) -> str:
    """Append preference, attachment, and capability guidance to the user prompt."""
    stripped = base_text.rstrip()
    sections: list[str] = [stripped]

    if schedule_summary:
        sections.append(schedule_summary)

    lower_text = stripped.lower()
    user_explicit_web_request = any(
        phrase in lower_text
        for phrase in (
            "web search",
            "search the web",
            "search online",
            "look up online",
            "use web results",
            "google this",
        )
    )

    if attachments:
        attachment_lines: list[str] = ["Uploaded files available:"]
        for item in attachments:
            name = _attachment_attr(item, "name") or "Attachment"
            mime_type = _attachment_attr(item, "mime_type") or "application/octet-stream"
            size_label = _format_size_label(_attachment_attr(item, "size"))
            preview = _attachment_attr(item, "preview")
            openai_file_id = _attachment_attr(item, "openai_file_id")

            line = f"- {name} ({mime_type}, {size_label})"
            attachment_lines.append(line)
            if openai_file_id:
                attachment_lines.append(f"  OpenAI file ID: {openai_file_id}")
            if preview:
                trimmed_preview = " ".join(str(preview).split())
                attachment_lines.append(f"  Preview: {trimmed_preview[:320]}" + ("…" if len(trimmed_preview) > 320 else ""))

        if model in ATTACHMENT_MODELS_REQUIRE_FILE_SEARCH:
            attachment_lines.append(
                "Before responding, call the file_search tool to read each attachment. "
                "Use focused queries that reference the filenames or OpenAI file IDs, and wait to answer until you have incorporated the results with inline citations."
            )
        elif model == "gpt-5-codex":
            attachment_lines.append(
                "Do not call file_search for these attachments. Inspect the inline image previews directly and describe how they inform your response."
            )
        elif model == "gpt-5-nano":
            attachment_lines.append(
                "file_search is unavailable with this model. Acknowledge that you cannot open the uploaded files and offer alternatives such as switching to GPT-5 or GPT-5 Mini if detailed file analysis is required."
            )
        else:
            attachment_lines.append(
                "Use file_search on attachments when doing so will materially improve the answer."
            )

        sections.append("\n".join(attachment_lines))

    if web_enabled:
        web_line = (
            "Web search is enabled. Before responding, call the web_search tool to gather current sources relevant to this message. "
            "Summarise the findings alongside other context and cite each source using Markdown hyperlinks like [Title](https://example.com)."
        )
        if user_explicit_web_request:
            web_line += " The learner explicitly requested web search, so skipping the tool is not acceptable."
        sections.append(web_line)
    else:
        sections.append("Web search is disabled; rely on internal knowledge and any uploaded files.")

    sections.append(
        f"Reasoning effort target: {reasoning_level}. Balance depth with timely responses."
    )

    return "\n\n".join(sections)


def schedule_summary_from_profile(profile: Mapping[str, Any] | None, *, max_items: int = 5) -> str | None:
    """Generate a short natural-language summary of the learner's upcoming schedule."""
    if not profile:
        return None
    schedule = profile.get("curriculum_schedule")
    if not isinstance(schedule, Mapping):
        return None
    items = schedule.get("items")
    if not isinstance(items, Sequence) or not items:
        return None

    tz_name = schedule.get("timezone") or profile.get("timezone") or "UTC"
    try:
        tz = ZoneInfo(str(tz_name))
        tz_key = getattr(tz, "key", str(tz_name))
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
        tz_key = "UTC"

    anchor_date = _resolve_anchor_date(schedule, tz)
    lines: list[str] = [
        f"Curriculum schedule ({tz_key}; dates reflect local daylight-saving offsets when applicable):"
    ]

    remaining = max(0, len(items) - max_items)
    for entry in list(items)[:max_items]:
        if not isinstance(entry, Mapping):
            continue
        offset_raw = entry.get("recommended_day_offset", 0)
        try:
            offset = int(offset_raw)
        except (TypeError, ValueError):
            offset = 0
        local_date = anchor_date + timedelta(days=offset)
        local_dt = datetime.combine(local_date, time(hour=12, minute=0), tzinfo=tz)
        date_label = local_dt.strftime("%A, %B %d, %Y")
        tz_abbr = local_dt.tzname() or tz_key
        kind = str(entry.get("kind", "")).capitalize() or "Item"
        title = str(entry.get("title", "")).strip() or "Untitled"
        lines.append(f"- {date_label} ({tz_abbr}): {kind} – {title}")

    if remaining > 0:
        lines.append(f"- …plus {remaining} more scheduled items.")

    return "\n".join(lines)


def _resolve_anchor_date(schedule: Mapping[str, Any], tz: ZoneInfo) -> datetime.date:
    from datetime import date  # local import to avoid circularity for typing

    anchor_raw = schedule.get("anchor_date")
    if isinstance(anchor_raw, str):
        try:
            return date.fromisoformat(anchor_raw)
        except ValueError:
            pass
    generated_raw = schedule.get("generated_at")
    if isinstance(generated_raw, str):
        parsed = _parse_iso_datetime(generated_raw)
        return parsed.astimezone(tz).date()
    return datetime.now(tz).date()


def _parse_iso_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now(tz=ZoneInfo("UTC"))
