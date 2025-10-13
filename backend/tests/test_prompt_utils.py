from app.prompt_utils import apply_preferences_overlay


def test_apply_preferences_overlay_requires_file_search_for_supported_models():
    base = "User: Please review the latest document."
    attachments = [
        {
            "name": "notes.md",
            "mime_type": "text/markdown",
            "size": 2048,
            "preview": "Summary of the onboarding checklist and milestones.",
            "openai_file_id": "file-123",
        }
    ]

    result = apply_preferences_overlay(
        base,
        attachments,
        web_enabled=False,
        reasoning_level="medium",
        model="gpt-5",
    )

    assert "notes.md (text/markdown, 2048 bytes)" in result
    assert "OpenAI file ID: file-123" in result
    assert "call the file_search tool to read each attachment" in result
    assert "Web search is disabled" in result
    assert "Reasoning effort target: medium" in result


def test_apply_preferences_overlay_codex_guidance():
    base = "User: What do you see in the sketch?"
    attachments = [
        {
            "name": "sketch.png",
            "mime_type": "image/png",
            "size": 512000,
            "preview": "Hand-drawn system diagram showing three services.",
            "openai_file_id": None,
        }
    ]

    result = apply_preferences_overlay(
        base,
        attachments,
        web_enabled=True,
        reasoning_level="high",
        model="gpt-5-codex",
    )

    assert "Do not call file_search" in result
    assert "inline image previews" in result
    assert "call the file_search tool to read each attachment" not in result
    assert "Before responding, call the web_search tool" in result


def test_apply_preferences_overlay_without_attachments():
    result = apply_preferences_overlay(
        "User: hello",
        [],
        web_enabled=True,
        reasoning_level="low",
        model="gpt-5-mini",
    )

    assert "Uploaded files available" not in result
    assert "Before responding, call the web_search tool" in result


def test_apply_preferences_overlay_honours_explicit_web_request():
    prompt = "User: Please web search the latest Rust compiler release notes."
    result = apply_preferences_overlay(
        prompt,
        [],
        web_enabled=True,
        reasoning_level="medium",
        model="gpt-5",
    )

    assert "Before responding, call the web_search tool" in result
    assert "skipping the tool is not acceptable" in result
