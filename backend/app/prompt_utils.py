"""Utilities that build Arcadia Coach agent prompts."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

ATTACHMENT_MODELS_REQUIRE_FILE_SEARCH = {"gpt-5", "gpt-5-mini", "gpt-5-nano"}


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
) -> str:
    """Append preference, attachment, and capability guidance to the user prompt."""
    sections: list[str] = [base_text.rstrip()]

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
        else:
            attachment_lines.append(
                "Use file_search on attachments when doing so will materially improve the answer."
            )

        sections.append("\n".join(attachment_lines))

    if web_enabled:
        sections.append("Web search is enabled. Use the web_search tool whenever it adds trustworthy context.")
    else:
        sections.append("Web search is disabled; rely on internal knowledge and any uploaded files.")

    sections.append(
        f"Reasoning effort target: {reasoning_level}. Balance depth with timely responses."
    )

    return "\n\n".join(sections)
