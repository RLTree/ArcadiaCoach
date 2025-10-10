# Arcadia MCP Server

This server exposes Arcadia Coach lessons, quizzes, and milestone widgets over the Model Context Protocol (MCP). Pair it with your OpenAI AgentKit workflow to let the agent stream structured cards, lists, and stat rows straight into the macOS client.

## Features

- `lesson_catalog` tool: returns an instructional widget envelope for a requested topic.
- `quiz_results` tool: formats Elo deltas and recap widgets for quizzes.
- `milestone_update` tool: surfaces longer-form milestone announcements with supporting widgets.
- `focus_sprint` tool: emits compact assignments to fuel Pomodoro sessions.

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
| `milestone_update` | Supplies milestone celebration content. |
| `focus_sprint` | Returns checklist assignments for a short sprint. |

Each tool responds with JSON matching the `WidgetEnvelope` schema that the macOS app already renders.
