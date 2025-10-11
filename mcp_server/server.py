import os
import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import FastAPI, Request, Response
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse
from starlette.types import Message, Scope, Receive, Send


class WidgetType(str, Enum):
    CARD = "Card"
    LIST = "List"
    STAT_ROW = "StatRow"


class WidgetCardSection(BaseModel):
    heading: Optional[str] = None
    items: List[str] = Field(default_factory=list, max_length=8)


class WidgetCardProps(BaseModel):
    title: str
    sections: Optional[List[WidgetCardSection]] = Field(default_factory=list)


class WidgetListRow(BaseModel):
    label: str
    href: Optional[str] = Field(default=None, description="Optional deep link to supporting material.")
    meta: Optional[str] = Field(default=None, description="Short annotation for the row.")


class WidgetListProps(BaseModel):
    title: Optional[str] = None
    rows: List[WidgetListRow]


class WidgetStatItem(BaseModel):
    label: str
    value: str


class WidgetStatRowProps(BaseModel):
    items: List[WidgetStatItem]


class Widget(BaseModel):
    type: WidgetType
    propsCard: Optional[WidgetCardProps] = None
    propsList: Optional[WidgetListProps] = None
    propsStat: Optional[WidgetStatRowProps] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "type": "Card",
                    "propsCard": {
                        "title": "Sample Widget",
                        "sections": [{"heading": "Overview", "items": ["Point A", "Point B"]}],
                    },
                }
            ]
        }
    }


class WidgetEnvelope(BaseModel):
    display: Optional[str] = None
    widgets: List[Widget]
    citations: Optional[List[str]] = Field(
        default=None,
        description="Optional supporting citations to display alongside the widget content.",
    )


def _resolve_host() -> str:
    return os.getenv("HOST", os.getenv("MCP_HOST", "0.0.0.0"))


def _resolve_port() -> int:
    value = os.getenv("PORT") or os.getenv("MCP_PORT") or "8001"
    try:
        return int(value)
    except ValueError:
        return 8001


mcp = FastMCP(
    name="Arcadia Coach Widgets",
    instructions="Provides lesson, quiz, milestone, and focus sprint widget envelopes for Arcadia Coach.",
)
mcp.settings.streamable_http_path = "/mcp_internal"
mcp.settings.message_path = "/messages/"
mcp.settings.stateless_http = True
mcp.settings.json_response = True


class _AppLifespan:
    def __init__(self, app):
        self.app = app
        self._context = app.router.lifespan_context(app)

    async def __aenter__(self) -> None:
        await self._context.__aenter__()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._context.__aexit__(exc_type, exc, tb)


@mcp.custom_route("/health", methods=["GET"])
async def health_route(_request):
    return JSONResponse({"status": "ok", "service": "arcadia-mcp"})


@mcp.custom_route("/mcp/health", methods=["GET"])
async def scoped_health_route(_request):
    return JSONResponse({"status": "ok", "service": "arcadia-mcp"})


@mcp.tool()
def lesson_catalog(topic: str) -> WidgetEnvelope:
    """Generate a widget envelope for a requested lesson topic."""
    card = Widget(
        type=WidgetType.CARD,
        propsCard=WidgetCardProps(
            title=f"Core ideas of {topic.title()}",
            sections=[
                WidgetCardSection(
                    heading="What to notice",
                    items=[
                        "Chunk concepts into no-more-than-3 bullet summaries",
                        "Pair terminology with a concrete code snippet",
                        "Highlight sensory anchors (color, sound, or tactile cues) to aid recall",
                    ],
                ),
                WidgetCardSection(
                    heading="Mindful debugging",
                    items=[
                        "Write down the expected flow before running code",
                        "Use sticky-note style checkpoints after each block",
                    ],
                ),
            ],
        ),
    )
    checklist = Widget(
        type=WidgetType.LIST,
        propsList=WidgetListProps(
            title="Micro tasks",
            rows=[
                WidgetListRow(label="Skim reference implementation",
                              href="https://platform.openai.com/docs"),
                WidgetListRow(
                    label="Re-type core loop from memory", meta="10 minutes"),
                WidgetListRow(label="Explain to rubber duck",
                              meta="Verbalise outcome"),
            ],
        ),
    )
    stats = Widget(
        type=WidgetType.STAT_ROW,
        propsStat=WidgetStatRowProps(
            items=[
                WidgetStatItem(label="Focus chunks", value="3"),
                WidgetStatItem(label="Est. time", value="25m"),
                WidgetStatItem(label="Energy check", value="Snack/Water"),
            ]
        ),
    )
    return WidgetEnvelope(
        intent="Lesson",
        display=f"Today's dive on {topic.title()} — take it in two passes and pause after each chunk.",
        widgets=[card, checklist, stats],
        citations=[
            "Arcadia Coach Playbook, 2025",
            "OpenAI Docs"
        ],
    )


@mcp.tool()
def quiz_results(topic: str, correct: int, total: int) -> WidgetEnvelope:
    """Return quiz recap widgets, including Elo deltas."""
    score_percent = int((correct / max(total, 1)) * 100)
    recap = Widget(
        type=WidgetType.CARD,
        propsCard=WidgetCardProps(
            title=f"Quiz recap • {topic.title()}",
            sections=[
                WidgetCardSection(
                    heading="Celebrate",
                    items=[
                        f"Scored {score_percent}% ({correct}/{total})",
                        "Streak extended — log a reward break",
                    ],
                ),
                WidgetCardSection(
                    heading="Sharpen",
                    items=[
                        "Revisit tensor broadcasting cheat sheet",
                        "Watch gradient flow animation with captions",
                    ],
                ),
            ],
        ),
    )
    stat_row = Widget(
        type=WidgetType.STAT_ROW,
        propsStat=WidgetStatRowProps(
            items=[
                WidgetStatItem(label="Δ Coding Elo", value="+18"),
                WidgetStatItem(label="Δ MATH", value="+9"),
                WidgetStatItem(
                    label="Focus streak",
                    value=f"{datetime.now(timezone.utc).timetuple().tm_yday}d",
                ),
            ]
        ),
    )
    drill_list = Widget(
        type=WidgetType.LIST,
        propsList=WidgetListProps(
            title="Next drills",
            rows=[
                WidgetListRow(label="3 spaced repetition cards",
                              meta="7 minutes"),
                WidgetListRow(label="Pair program with mentor",
                              meta="Book 15 minutes"),
                WidgetListRow(label="Share insight in community",
                              href="https://discord.gg"),
            ],
        ),
    )
    return WidgetEnvelope(
        intent="Quiz",
        display=f"Quiz stats for {topic} — focus on highlighted review items.",
        widgets=[recap, stat_row, drill_list],
        citations=None,
    )


@mcp.tool()
def milestone_update(name: str, summary: Optional[str] = None) -> WidgetEnvelope:
    """Celebrate a milestone and propose next steps."""
    celebration = Widget(
        type=WidgetType.CARD,
        propsCard=WidgetCardProps(
            title=f"Milestone: {name}",
            sections=[
                WidgetCardSection(
                    heading="What you unlocked",
                    items=[
                        "Unlocked new practice arena",
                        "Bonus focus timer theme",
                        "Invite-only study circle"
                    ],
                ),
                WidgetCardSection(
                    heading="Keep momentum",
                    items=[
                        "Schedule a reflection journal entry",
                        "Pick one celebratory activity (music, movement, craft)",
                    ],
                ),
            ],
        ),
    )
    next_steps = Widget(
        type=WidgetType.LIST,
        propsList=WidgetListProps(
            title="Suggested quests",
            rows=[
                WidgetListRow(
                    label="Draft a project retrospective", meta="15 minutes"),
                WidgetListRow(
                    label="Teach a friend one core concept", meta="10 minutes"),
                WidgetListRow(label="Update Arcadia roadmap",
                              href="https://arcadia.example/roadmap"),
            ],
        ),
    )
    return WidgetEnvelope(
        intent="Milestone",
        display=summary or "You crossed a milestone — notice what worked and plan a gentle next sprint.",
        widgets=[celebration, next_steps],
        citations=None,
    )


@mcp.tool()
def focus_sprint(duration_minutes: int = 25) -> WidgetEnvelope:
    """Provide a focus sprint checklist tailored to the preferred chunk size."""
    checklist = Widget(
        type=WidgetType.LIST,
        propsList=WidgetListProps(
            title=f"Focus sprint ({duration_minutes} min)",
            rows=[
                WidgetListRow(label="Prep environment",
                              meta="Set lights + playlist"),
                WidgetListRow(label="Review acceptance criteria",
                              meta="3 minutes"),
                WidgetListRow(label="Commit to first micro-task",
                              meta="Write what 'done' looks like"),
            ],
        ),
    )
    stats = Widget(
        type=WidgetType.STAT_ROW,
        propsStat=WidgetStatRowProps(
            items=[
                WidgetStatItem(label="Chunk length",
                               value=f"{duration_minutes}m"),
                WidgetStatItem(label="Break", value="5m"),
                WidgetStatItem(label="Mood check", value="Note energy"),
            ],
        ),
    )
    return WidgetEnvelope(
        intent="FocusSprint",
        display="Focus sprint deck — keep cues visible and celebrate micro wins.",
        widgets=[checklist, stats],
        citations=None,
    )


def main() -> None:
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    host = _resolve_host()
    port = _resolve_port()
    logger.info("Starting MCP server on %s:%s (mount=/mcp)", host, port)
    mcp.settings.host = host
    mcp.settings.port = port

    inner_app = mcp.streamable_http_app()
    proxy_app = create_proxy_app(inner_app)

    import uvicorn

    uvicorn.run(proxy_app, host=host, port=port, log_level="info")


def create_proxy_app(inner_app) -> FastAPI:
    app = FastAPI()
    logger = logging.getLogger("arcadia.mcp.proxy")
    lifespan_manager: _AppLifespan | None = None

    @app.on_event("startup")
    async def startup() -> None:
        nonlocal lifespan_manager
        lifespan_manager = _AppLifespan(inner_app)
        await lifespan_manager.__aenter__()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        nonlocal lifespan_manager
        if lifespan_manager is not None:
            await lifespan_manager.__aexit__(None, None, None)

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok", "service": "arcadia-mcp"}

    @app.get("/mcp/health")
    async def scoped_health() -> Dict[str, str]:
        return {"status": "ok", "service": "arcadia-mcp"}

    @app.post("/mcp")
    async def proxy(request: Request) -> Response:
        body = await request.body()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.warning("Received non-JSON payload on /mcp")
            payload = None
        else:
            if isinstance(payload, dict):
                method = payload.get("method")
                if isinstance(method, str) and "." in method:
                    payload["method"] = method.replace(".", "/")
                    method = payload["method"]

                if method == "initialize":
                    params = payload.setdefault("params", {})
                    if "clientInfo" not in params:
                        client_info = params.get("client")
                        if isinstance(client_info, dict):
                            params["clientInfo"] = client_info
                        else:
                            params["clientInfo"] = {"name": "HostedMCPTool", "version": "1.0"}
                    params.setdefault(
                        "protocolVersion",
                        request.headers.get("mcp-protocol-version", "2025-06-18"),
                    )
                    params.setdefault("capabilities", {})
                    params.pop("client", None)

                body = json.dumps(payload).encode("utf-8")
            else:
                logger.debug("Unexpected payload type for /mcp: %s", type(payload))

        quoted_headers = _prepare_headers(request.scope["headers"], body)

        scope = dict(request.scope)
        scope["path"] = mcp.settings.streamable_http_path
        scope["headers"] = quoted_headers

        try:
            status, headers, content = await _call_inner_app(inner_app, scope, body)
        except Exception:  # noqa: BLE001
            logger.exception("Unhandled exception proxying MCP request")
            return Response(content="Internal Server Error", status_code=500)

        if status >= 400:
            logger.warning(
                "MCP inner app returned %s for method %s: %s",
                status,
                payload.get("method") if isinstance(payload, dict) else "<unknown>",
                content.decode(errors="ignore"),
            )

        return Response(
            content=content,
            status_code=status,
            headers={k.decode(): v.decode() for k, v in headers},
            media_type=None,
        )

    return app


def _prepare_headers(headers: Iterable[Tuple[bytes, bytes]], body: bytes) -> list[tuple[bytes, bytes]]:
    filtered = [(k, v) for k, v in headers if k not in {b"content-length", b"accept"}]
    filtered.append((b"content-length", str(len(body)).encode()))
    filtered.append((b"accept", b"application/json, text/event-stream"))
    return filtered


async def _call_inner_app(app, scope: Scope, body: bytes) -> Tuple[int, list[Tuple[bytes, bytes]], bytes]:
    response_body = bytearray()
    response_headers: list[Tuple[bytes, bytes]] = []
    status_code = 500

    async def receive() -> Message:
        nonlocal body
        if body is not None:
            chunk = body
            body = None
            return {"type": "http.request", "body": chunk, "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        nonlocal status_code, response_headers, response_body
        if message["type"] == "http.response.start":
            status_code = message["status"]
            response_headers = message.get("headers", [])
        elif message["type"] == "http.response.body":
            response_body.extend(message.get("body", b""))

    await app(scope, receive, send)
    return status_code, response_headers, bytes(response_body)


if __name__ == "__main__":
    main()
