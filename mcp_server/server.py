import json
import logging
import os
import re
import sys
import traceback
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple

from anyio import ClosedResourceError, BrokenResourceError, EndOfStream
from fastapi import FastAPI, Request, Response
from mcp.server.fastmcp import FastMCP
from mcp.server.streamable_http import StreamableHTTPServerTransport
from pydantic import BaseModel, Field, ConfigDict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import Message, Scope


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


_log_level = os.getenv("MCP_LOG_LEVEL", "INFO").upper()
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(JSONFormatter())
logging.basicConfig(level=_log_level, handlers=[_handler])
logger = logging.getLogger("arcadia.mcp")


class ProductionErrorMiddleware(BaseHTTPMiddleware):
    """Catch transport exceptions and surface structured responses."""

    def __init__(self, app, include_traceback: bool = False) -> None:
        super().__init__(app)
        self.include_traceback = include_traceback
        self.logger = logging.getLogger("arcadia.mcp.middleware")

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except ClosedResourceError:
            self.logger.info("Stream closed gracefully")
            return JSONResponse(
                {"error": {"code": -32000, "message": "Session ended", "reason": "stream_closed"}},
                status_code=499,
            )
        except (BrokenResourceError, EndOfStream) as err:
            self.logger.warning("Stream broken: %s", err)
            return JSONResponse(
                {"error": {"code": -32001, "message": "Connection broken", "reason": str(err)}},
                status_code=502,
            )
        except ValueError as err:
            self.logger.warning("Invalid request: %s", err)
            return JSONResponse(
                {"error": {"code": -32602, "message": "Invalid parameters", "detail": str(err)}},
                status_code=400,
            )
        except Exception as err:  # noqa: BLE001
            self.logger.exception("Unexpected error in MCP middleware")
            error_data: Dict[str, Any] = {"type": type(err).__name__, "message": str(err)}
            if self.include_traceback:
                error_data["traceback"] = traceback.format_exc()
            return JSONResponse(
                {"error": {"code": -32603, "message": "Internal server error", "detail": error_data}},
                status_code=500,
            )


_original_handle_post_request = StreamableHTTPServerTransport._handle_post_request


async def _safe_handle_post_request(self, scope, request, receive, send):
    try:
        await _original_handle_post_request(self, scope, request, receive, send)
    except ClosedResourceError:
        logging.getLogger("arcadia.mcp.proxy").info(
            "MCP stream closed before completion; returning partial response",
        )


StreamableHTTPServerTransport._handle_post_request = _safe_handle_post_request




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
    items_per_row: Optional[int] = Field(default=None, ge=1, le=8, alias="itemsPerRow")

    model_config = ConfigDict(populate_by_name=True)


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


@dataclass(frozen=True)
class BlueprintSection:
    heading: Optional[str]
    items: Tuple[str, ...]


@dataclass(frozen=True)
class BlueprintTask:
    label: str
    href: Optional[str] = None
    meta: Optional[str] = None


@dataclass(frozen=True)
class BlueprintStat:
    label: str
    value: str


@dataclass(frozen=True)
class LessonBlueprint:
    slug: str
    match_terms: Tuple[str, ...]
    title: str
    display_template: str
    sections: Tuple[BlueprintSection, ...]
    tasks: Tuple[BlueprintTask, ...]
    stats: Tuple[BlueprintStat, ...]
    citations: Tuple[str, ...]
    intent: str = "Lesson"

    def render(self, topic: str) -> "WidgetEnvelope":
        topic_title = topic.strip() or self.slug.replace("-", " ").title()
        formatted_title = self.title.format(topic=topic_title)
        display = self.display_template.format(topic=topic_title)
        card_sections = [
            WidgetCardSection(
                heading=section.heading.format(topic=topic_title) if section.heading else None,
                items=[item.format(topic=topic_title) for item in section.items],
            )
            for section in self.sections
        ]
        card = Widget(
            type=WidgetType.CARD,
            propsCard=WidgetCardProps(
                title=formatted_title,
                sections=card_sections,
            ),
        )
        checklist = Widget(
            type=WidgetType.LIST,
            propsList=WidgetListProps(
                title="Micro tasks",
                rows=[
                    WidgetListRow(
                        label=task.label.format(topic=topic_title),
                        href=task.href.format(topic=topic_title) if task.href else None,
                        meta=task.meta.format(topic=topic_title) if task.meta else None,
                    )
                    for task in self.tasks
                ],
            ),
        )
        stat_row = Widget(
            type=WidgetType.STAT_ROW,
            propsStat=WidgetStatRowProps(
                items=[
                    WidgetStatItem(label=stat.label.format(topic=topic_title), value=stat.value.format(topic=topic_title))
                    for stat in self.stats
                ]
            ),
        )
        return WidgetEnvelope(
            intent=self.intent,
            display=display,
            widgets=[card, checklist, stat_row],
            citations=[citation.format(topic=topic_title) for citation in self.citations],
        )


def _normalize_topic(topic: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\\s]+", " ", topic.lower())
    return " ".join(cleaned.split())


TRANSFORMERS_BLUEPRINT = LessonBlueprint(
    slug="transformers",
    match_terms=("transformer", "attention", "self attention"),
    title="Transformers: anchor the attention stack",
    display_template="Today's dive on {topic} — start with the attention math, then trace a minimal forward pass.",
    sections=(
        BlueprintSection(
            heading="Core building blocks",
            items=(
                "Sketch the flow from embeddings → multi-head self-attention → feed-forward and residual paths.",
                "Write out attention(Q,K,V)=softmax(QKᵀ/√d_k)V and note where masking enters decoder-only models.",
                "Contrast encoder-only (BERT), decoder-only (GPT), and encoder-decoder (T5) stacks; capture which problems each unlocks.",
            ),
        ),
        BlueprintSection(
            heading="Implementation watchpoints",
            items=(
                "Track tensor shapes at every projection (batch, sequence, heads, head_dim) to avoid silent broadcasting bugs.",
                "Profile a single attention block in fp16 vs fp32—log memory usage and any stability issues.",
                "Keep a failure log for vanishing gradients or NaNs and map them back to initialization or normalization choices.",
            ),
        ),
    ),
    tasks=(
        BlueprintTask(
            label="Annotate 'Attention Is All You Need' sections 2–4",
            href="https://arxiv.org/pdf/1706.03762.pdf",
            meta="30 min • highlight the Q/K/V math",
        ),
        BlueprintTask(
            label="Step through The Annotated Transformer (PyTorch)",
            href="https://nlp.seas.harvard.edu/annotated-transformer/",
            meta="45 min • instrument attention weights",
        ),
        BlueprintTask(
            label="Implement scaled dot-product attention from scratch",
            meta="Validate masking + dimension checks in your framework",
        ),
    ),
    stats=(
        BlueprintStat(label="Focus chunks", value="4 × 12m"),
        BlueprintStat(label="Build time", value="45m"),
        BlueprintStat(label="Reflection", value="Capture 2 aha moments"),
    ),
    citations=(
        "Vaswani et al., Attention Is All You Need (2017)",
        "Harvard NLP, The Annotated Transformer",
        "OpenAI Cookbook · Understand Attention Blocks",
    ),
)

DIFFUSION_BLUEPRINT = LessonBlueprint(
    slug="diffusion-models",
    match_terms=("diffusion", "score model", "ddpm", "stable diffusion"),
    title="Diffusion models: rehearse the denoise loop",
    display_template="Today's dive on {topic} — map the forward noise process, then code the reverse sampler.",
    sections=(
        BlueprintSection(
            heading="Key ideas",
            items=(
                "Describe the forward noising schedule q(x_t | x_{t-1}) and how β_t controls variance.",
                "Derive the denoising objective ‖ε - ε_θ(x_t, t)‖² and why predicting noise works.",
                "Explain classifier-free guidance and how scaling condition vectors alters samples.",
            ),
        ),
        BlueprintSection(
            heading="Build instincts",
            items=(
                "Visualize a batch of x_t samples at early, mid, and late timesteps to cement intuition.",
                "Instrument inference time vs. quality when you vary the number of sampling steps.",
                "Record failure modes (mode collapse, washed-out colors) and tie them to schedule choices.",
            ),
        ),
    ),
    tasks=(
        BlueprintTask(
            label="Skim Ho et al., Denoising Diffusion Probabilistic Models",
            href="https://arxiv.org/abs/2006.11239",
            meta="25 min • note the objective",
        ),
        BlueprintTask(
            label="Replicate a minimal DDPM in PyTorch or JAX",
            meta="Use 64×64 images; log loss and sample grids",
        ),
        BlueprintTask(
            label="Experiment with classifier-free guidance scales",
            meta="Compare FID or simple perceptual scores",
        ),
    ),
    stats=(
        BlueprintStat(label="Focus chunks", value="3 × 15m"),
        BlueprintStat(label="Experiment window", value="60m"),
        BlueprintStat(label="Energy check", value="Hydrate before coding sprint"),
    ),
    citations=(
        "Ho et al., Denoising Diffusion Probabilistic Models (2020)",
        "OpenAI Diffusion Engineering Notes",
        "Stability AI, Stable Diffusion Technical Overview",
    ),
)

RLHF_BLUEPRINT = LessonBlueprint(
    slug="rlhf",
    match_terms=("rlhf", "reinforcement learning from human feedback", "preference model"),
    title="RLHF: connect preference data to policy updates",
    display_template="Today's dive on {topic} — reconcile the supervised warm start with the PPO fine-tune loop.",
    sections=(
        BlueprintSection(
            heading="Pipeline overview",
            items=(
                "Outline the three phases: supervised fine-tuning, reward modeling, and RL policy improvement.",
                "Clarify how pairwise preference data trains the reward model and where label noise creeps in.",
                "Track KL penalties that keep the policy near the supervised model during PPO updates.",
            ),
        ),
        BlueprintSection(
            heading="Operational guardrails",
            items=(
                "Document metrics to monitor (KL divergence, reward model drift, toxic output rate).",
                "Design rapid evaluation tasks that can flag reward hacking examples early.",
                "List interventions when humans disagree—escalate for relabeling vs. adjust sampling temperature.",
            ),
        ),
    ),
    tasks=(
        BlueprintTask(
            label="Read the InstructGPT RLHF training section",
            href="https://openai.com/research/instructgpt",
            meta="20 min • note reward shaping details",
        ),
        BlueprintTask(
            label="Simulate PPO updates with a toy reward model",
            meta="Track KL and reward per iteration",
        ),
        BlueprintTask(
            label="Draft evaluation rubric for your deployment context",
            meta="Include safety & user-impact checks",
        ),
    ),
    stats=(
        BlueprintStat(label="Focus chunks", value="3 × 10m"),
        BlueprintStat(label="Review window", value="35m"),
        BlueprintStat(label="Next action", value="Sync with safety reviewer"),
    ),
    citations=(
        "Ouyang et al., Training language models to follow instructions (2022)",
        "OpenAI Alignment Handbook",
        "Anthropic, RLHF Lessons Learned (2024)",
    ),
)

DEFAULT_BLUEPRINT = LessonBlueprint(
    slug="general",
    match_terms=tuple(),
    title="{topic}: build a deliberate practice loop",
    display_template="Today's dive on {topic} — clarify the why, then build a small artifact to test your understanding.",
    sections=(
        BlueprintSection(
            heading="Orient",
            items=(
                "Write down what success with {topic} looks like for this week.",
                "List the top 3 unknown terms or steps you need to clarify.",
                "Identify one example or case study that shows {topic} in action.",
            ),
        ),
        BlueprintSection(
            heading="Deepen",
            items=(
                "Pair a primary reference with a hands-on notebook; note surprises.",
                "Generate at least two questions you would ask a mentor about {topic}.",
                "Capture sensory anchors (visuals, sounds, tactile cues) that help you recall the idea quickly.",
            ),
        ),
    ),
    tasks=(
        BlueprintTask(
            label="Skim a trusted reference on {topic}",
            meta="Highlight 3 insights worth teaching forward",
        ),
        BlueprintTask(
            label="Draft a small demo or outline applying {topic}",
            meta="Keep it <25 minutes end-to-end",
        ),
        BlueprintTask(
            label="Summarize the key takeaway for a peer",
            meta="1 paragraph or short Loom",
        ),
    ),
    stats=(
        BlueprintStat(label="Focus chunks", value="3 × 10m"),
        BlueprintStat(label="Review cadence", value="End with a quick reflection"),
        BlueprintStat(label="Energy check", value="Stretch + hydrate"),
    ),
    citations=(
        "Arcadia Coach Playbook, 2025",
    ),
)

LESSON_BLUEPRINTS: Tuple[LessonBlueprint, ...] = (
    TRANSFORMERS_BLUEPRINT,
    DIFFUSION_BLUEPRINT,
    RLHF_BLUEPRINT,
)


def _select_blueprint(topic: str) -> LessonBlueprint:
    normalized = _normalize_topic(topic)
    for blueprint in LESSON_BLUEPRINTS:
        if blueprint.slug in normalized:
            return blueprint
        if any(term in normalized for term in blueprint.match_terms):
            return blueprint
    return DEFAULT_BLUEPRINT

class WidgetEnvelope(BaseModel):
    intent: Optional[str] = Field(
        default=None,
        description="Optional intent label consumed by legacy Arcadia Coach clients.",
    )
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


@asynccontextmanager
async def _mcp_lifespan(_app):
    logger.info("Arcadia MCP server starting up")
    logger.info("Python version: %s", sys.version.replace("\n", " "))
    try:
        yield
    finally:
        logger.info("Arcadia MCP server shutting down")


mcp = FastMCP(
    name="Arcadia Coach Widgets",
    instructions="Provides lesson, quiz, milestone, and focus sprint widget envelopes for Arcadia Coach.",
    lifespan=_mcp_lifespan,
)
mcp.settings.streamable_http_path = "/mcp_internal"
mcp.settings.message_path = "/messages/"
mcp.settings.stateless_http = True
mcp.settings.json_response = True

_include_traceback = os.getenv("DEBUG", "false").lower() == "true"


class _AppLifespan:
    def __init__(self, app):
        self.app = app
        self._context = app.router.lifespan_context(app)

    async def __aenter__(self) -> None:
        await self._context.__aenter__()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._context.__aexit__(exc_type, exc, tb)


@mcp.custom_route("/", methods=["GET"])
async def root_route(_request):
    return JSONResponse(
        {
            "service": "arcadia-coach-mcp",
            "health": "/health",
            "transport": "streamable-http",
            "status": "running",
        }
    )


@mcp.custom_route("/health", methods=["GET"])
async def health_route(_request):
    return JSONResponse(
        {
            "status": "healthy",
            "service": "arcadia-coach-mcp",
            "transport": "streamable-http",
        }
    )


@mcp.custom_route("/mcp/health", methods=["GET"])
async def scoped_health_route(_request):
    return JSONResponse(
        {
            "status": "healthy",
            "service": "arcadia-coach-mcp",
            "transport": "streamable-http",
        }
    )


@mcp.tool()
def lesson_catalog(topic: str) -> WidgetEnvelope:
    """Generate a widget envelope for a requested lesson topic."""
    blueprint = _select_blueprint(topic)
    return blueprint.render(topic)


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
def milestone_update(
    name: str,
    summary: Optional[str] = None,
    brief: Optional[dict] = None,
) -> WidgetEnvelope:
    """Celebrate a milestone and render its structured brief."""

    if brief:
        headline = brief.get("headline") or name
        objectives = brief.get("objectives") or []
        deliverables = brief.get("deliverables") or []
        success = brief.get("success_criteria") or []
        external = brief.get("external_work") or []
        capture = brief.get("capture_prompts") or []
        elo_focus = brief.get("elo_focus") or []
        resources = brief.get("resources") or []

        overview_sections = []
        if objectives:
            overview_sections.append(WidgetCardSection(heading="Objectives", items=list(objectives)))
        if deliverables:
            overview_sections.append(WidgetCardSection(heading="Deliverables", items=list(deliverables)))
        if success:
            overview_sections.append(WidgetCardSection(heading="Success criteria", items=list(success)))
        kickoff = brief.get("kickoff_steps") or []
        if kickoff:
            overview_sections.append(WidgetCardSection(heading="Kickoff steps", items=list(kickoff)))

        overview_card = Widget(
            type=WidgetType.CARD,
            propsCard=WidgetCardProps(
                title=headline,
                sections=overview_sections or [
                    WidgetCardSection(
                        heading=None,
                        items=[summary or "Capture how you applied this milestone."],
                    )
                ],
            ),
        )

        rows: List[WidgetListRow] = []
        if external:
            rows.extend(WidgetListRow(label=item, meta="External work") for item in external)
        if capture:
            rows.extend(WidgetListRow(label=prompt, meta="Capture prompt") for prompt in capture)
        if resources:
            rows.extend(WidgetListRow(label=resource, meta="Reference") for resource in resources)
        coaching = brief.get("coaching_prompts") or []
        if coaching:
            rows.extend(WidgetListRow(label=prompt, meta="Coaching prompt") for prompt in coaching)

        checklist_widget = None
        if rows:
            checklist_widget = Widget(
                type=WidgetType.LIST,
                propsList=WidgetListProps(
                    title="Milestone checklist",
                    rows=rows,
                ),
            )

        stats_widget = None
        if elo_focus:
            stats_widget = Widget(
                type=WidgetType.STAT_ROW,
                propsStat=WidgetStatRowProps(
                    items=[WidgetStatItem(label="Focus", value=focus) for focus in elo_focus[:4]]
                ),
            )

        widgets = [overview_card]
        if checklist_widget:
            widgets.append(checklist_widget)
        if stats_widget:
            widgets.append(stats_widget)

        display_text = summary or brief.get("summary") or "Celebrate the milestone and capture what you accomplished."
        return WidgetEnvelope(
            intent="Milestone",
            display=display_text,
            widgets=widgets,
            citations=None,
        )

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
                        "Invite-only study circle",
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
                WidgetListRow(label="Draft a project retrospective", meta="15 minutes"),
                WidgetListRow(label="Teach a friend one core concept", meta="10 minutes"),
                WidgetListRow(label="Update Arcadia roadmap", href="https://arcadia.example/roadmap"),
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
    proxy_app = create_proxy_app(inner_app, include_traceback=_include_traceback)

    import uvicorn

    uvicorn.run(
        proxy_app,
        host=host,
        port=port,
        log_level="info",
        timeout_keep_alive=1800,
        timeout_graceful_shutdown=60,
    )


def create_proxy_app(inner_app, include_traceback: bool) -> FastAPI:
    app = FastAPI()
    logger = logging.getLogger("arcadia.mcp.proxy")
    lifespan_manager: _AppLifespan | None = None

    app.add_middleware(ProductionErrorMiddleware, include_traceback=include_traceback)

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

    @app.get("/")
    async def root() -> Dict[str, str]:
        return {
            "service": "arcadia-mcp",
            "transport": "streamable-http",
            "health": "/health",
        }

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok", "service": "arcadia-mcp"}

    @app.get("/mcp")
    async def mcp_info() -> Dict[str, str]:
        return {
            "service": "arcadia-mcp",
            "endpoint": "/mcp",
            "internal_path": mcp.settings.streamable_http_path,
        }

    @app.get("/mcp/health")
    async def scoped_health() -> Dict[str, str]:
        return {"status": "ok", "service": "arcadia-mcp"}

    allow_headers = (
        "Content-Type, Authorization, Mcp-Session-Id, Mcp-Protocol-Version, Accept"
    )
    allow_methods = "POST, OPTIONS, HEAD, GET"

    @app.options("/mcp")
    async def mcp_options() -> Response:
        logger.info("OPTIONS /mcp called")
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": allow_headers,
                "Access-Control-Allow-Methods": allow_methods,
            },
        )

    @app.head("/mcp")
    async def mcp_head() -> Response:
        logger.info("HEAD /mcp called")
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json",
            },
        )

    @app.post("/mcp")
    async def proxy(request: Request) -> Response:
        logger.info("POST /mcp called from %s", request.client)
        body = await request.body()
        logger.debug("MCP request body (first 200 bytes): %s", body[:200])
        try:
            payload = json.loads(body)
            logger.info("Parsed MCP method: %s", payload.get("method"))
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
        internal_path = mcp.settings.streamable_http_path.rstrip("/") + "/"
        scope["path"] = internal_path
        scope["headers"] = quoted_headers

        try:
            status, headers, content = await _call_inner_app(inner_app, scope, body)
            logger.info("Inner MCP app returned status %s (len=%d)", status, len(content))
        except Exception:  # noqa: BLE001
            logger.exception("Unhandled exception proxying MCP request")
            return Response(content="Internal Server Error", status_code=500)

        if status >= 400:
            logger.warning(
                "MCP inner app returned %s for method %s: %s",
                status,
                payload.get("method") if isinstance(payload, dict) else "<unknown>",
                content.decode(errors="ignore")[:500],
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
    request_body: Optional[bytes] = body

    async def receive() -> Message:
        nonlocal request_body
        if request_body is not None:
            chunk = request_body
            request_body = None
            return {"type": "http.request", "body": chunk, "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        nonlocal status_code, response_headers, response_body
        if message["type"] == "http.response.start":
            status_code = message["status"]
            response_headers = message.get("headers", [])
        elif message["type"] == "http.response.body":
            response_body.extend(message.get("body", b""))

    try:
        await app(scope, receive, send)
    except (ClosedResourceError, BrokenResourceError, EndOfStream) as err:
        logging.getLogger("arcadia.mcp.proxy").info(
            "Stream closed while proxying MCP request: %s", err
        )
    return status_code, response_headers, bytes(response_body)


if __name__ == "__main__":
    main()
