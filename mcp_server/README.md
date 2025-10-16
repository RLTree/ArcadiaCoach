# Arcadia MCP Server

This server exposes Arcadia Coach lessons, quizzes, and milestone widgets over the Model Context Protocol (MCP). Pair it with your OpenAI AgentKit workflow to let the agent stream structured cards, lists, and stat rows straight into the macOS client.

## Features

- `lesson_catalog` tool: returns an instructional widget envelope for a requested topic.
- `quiz_results` tool: formats Elo deltas and recap widgets for quizzes.
- `milestone_update` tool: surfaces longer-form milestone announcements with supporting widgets.
- `focus_sprint` tool: emits compact assignments to fuel Pomodoro sessions.
- `milestone_project_author` tool: calls GPT-5 to author bespoke milestone briefs (with fallback-safe JSON output).

## Requirements

- Python 3.10+
- The `mcp` Python SDK with FastMCP extras (installed automatically via `mcp[fast]`).

## Setup

```bash
cd mcp_server
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run the server

```bash
python server.py
```

By default the server listens on `localhost:8001` for MCP host connections. Configure your Agent or workflow to talk to the exposed tools via MCP.

## Tools

| Tool | Description |
|------|-------------|
| `lesson_catalog` | Generates a lesson widget envelope for a topic. |
| `quiz_results` | Builds a quiz recap (Elo delta, next drills, resources). |
| `milestone_project_author` | Produces agent-authored milestone briefs via the OpenAI Responses API. |
| `milestone_update` | Supplies milestone celebration content. |
| `focus_sprint` | Returns checklist assignments for a short sprint. |

Each tool responds with JSON matching the `WidgetEnvelope` schema that the macOS app already renders.

## Configuration

| Environment variable | Default | Purpose |
|----------------------|---------|---------|
| `OPENAI_API_KEY` | _required_ | Grants the authoring tool access to the OpenAI Responses API. |
| `MCP_MILESTONE_AUTHOR_MODEL` | `gpt-5` | Model used when generating milestone briefs. |
| `MCP_MILESTONE_AUTHOR_REASONING` | `medium` | Reasoning effort hint passed to the Responses API. |
| `MCP_MILESTONE_AUTHOR_TIMEOUT` | `18.0` | Request timeout (seconds) for authoring calls. |
| `MCP_MILESTONE_AUTHOR_TEMPERATURE` | `0.6` | Temperature applied to authoring calls. |

The server also exposes a REST shortcut at `POST /author/milestone` that accepts the same payload as the MCP tool and is used by the backend sequencer for low-latency calls.
