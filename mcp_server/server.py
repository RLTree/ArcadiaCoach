from datetime import datetime
from typing import List, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field


class WidgetCardSection(BaseModel):
    heading: Optional[str] = None
    items: List[str] = Field(default_factory=list)


class WidgetCardProps(BaseModel):
    title: str
    sections: Optional[List[WidgetCardSection]] = None


class WidgetListRow(BaseModel):
    label: str
    href: Optional[str] = None
    meta: Optional[str] = None


class WidgetListProps(BaseModel):
    title: Optional[str] = None
    rows: List[WidgetListRow]


class WidgetStatItem(BaseModel):
    label: str
    value: str


class WidgetStatRowProps(BaseModel):
    items: List[WidgetStatItem]


class Widget(BaseModel):
    type: str
    propsCard: Optional[WidgetCardProps] = None
    propsList: Optional[WidgetListProps] = None
    propsStat: Optional[WidgetStatRowProps] = None


class WidgetEnvelope(BaseModel):
    display: Optional[str] = None
    widgets: List[Widget]
    citations: Optional[List[str]] = None


app = FastMCP(
    name="Arcadia Coach Widgets",
    instructions="Provides lesson, quiz, milestone, and focus sprint widget envelopes for Arcadia Coach.",
)


@app.tool()
def lesson_catalog(topic: str) -> WidgetEnvelope:
    """Generate a widget envelope for a requested lesson topic."""
    card = Widget(
        type="Card",
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
        type="List",
        propsList=WidgetListProps(
            title="Micro tasks",
            rows=[
                WidgetListRow(label="Skim reference implementation", href="https://platform.openai.com/docs"),
                WidgetListRow(label="Re-type core loop from memory", meta="10 minutes"),
                WidgetListRow(label="Explain to rubber duck", meta="Verbalise outcome"),
            ],
        ),
    )
    stats = Widget(
        type="StatRow",
        propsStat=WidgetStatRowProps(
            items=[
                WidgetStatItem(label="Focus chunks", value="3"),
                WidgetStatItem(label="Est. time", value="25m"),
                WidgetStatItem(label="Energy check", value="Snack/Water"),
            ]
        ),
    )
    return WidgetEnvelope(
        display=f"Today's dive on {topic.title()} — take it in two passes and pause after each chunk.",
        widgets=[card, checklist, stats],
        citations=[
            "Arcadia Coach Playbook, 2025",
            "OpenAI Docs"
        ],
    )


@app.tool()
def quiz_results(topic: str, correct: int, total: int) -> WidgetEnvelope:
    """Return quiz recap widgets, including Elo deltas."""
    score_percent = int((correct / max(total, 1)) * 100)
    recap = Widget(
        type="Card",
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
        type="StatRow",
        propsStat=WidgetStatRowProps(
            items=[
                WidgetStatItem(label="Δ Coding Elo", value="+18"),
                WidgetStatItem(label="Δ MATH", value="+9"),
                WidgetStatItem(label="Focus streak", value=f"{datetime.utcnow().strftime('%j')}d"),
            ]
        ),
    )
    drill_list = Widget(
        type="List",
        propsList=WidgetListProps(
            title="Next drills",
            rows=[
                WidgetListRow(label="3 spaced repetition cards", meta="7 minutes"),
                WidgetListRow(label="Pair program with mentor", meta="Book 15 minutes"),
                WidgetListRow(label="Share insight in community", href="https://discord.gg"),
            ],
        ),
    )
    return WidgetEnvelope(
        display=f"Quiz stats for {topic} — focus on highlighted review items.",
        widgets=[recap, stat_row, drill_list],
        citations=None,
    )


@app.tool()
def milestone_update(name: str, summary: Optional[str] = None) -> WidgetEnvelope:
    """Celebrate a milestone and propose next steps."""
    celebration = Widget(
        type="Card",
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
        type="List",
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
        display=summary or "You crossed a milestone — notice what worked and plan a gentle next sprint.",
        widgets=[celebration, next_steps],
        citations=None,
    )


@app.tool()
def focus_sprint(duration_minutes: int = 25) -> WidgetEnvelope:
    """Provide a focus sprint checklist tailored to the preferred chunk size."""
    checklist = Widget(
        type="List",
        propsList=WidgetListProps(
            title=f"Focus sprint ({duration_minutes} min)",
            rows=[
                WidgetListRow(label="Prep environment", meta="Set lights + playlist"),
                WidgetListRow(label="Review acceptance criteria", meta="3 minutes"),
                WidgetListRow(label="Commit to first micro-task", meta="Write what 'done' looks like"),
            ],
        ),
    )
    stats = Widget(
        type="StatRow",
        propsStat=WidgetStatRowProps(
            items=[
                WidgetStatItem(label="Chunk length", value=f"{duration_minutes}m"),
                WidgetStatItem(label="Break", value="5m"),
                WidgetStatItem(label="Mood check", value="Note energy"),
            ],
        ),
    )
    return WidgetEnvelope(
        display="Focus sprint deck — keep cues visible and celebrate micro wins.",
        widgets=[checklist, stats],
        citations=None,
    )


def main() -> None:
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
