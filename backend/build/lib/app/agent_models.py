"""Pydantic models mirroring the Swift agent payloads."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class Widget(BaseModel):
    type: Literal["Card", "List", "StatRow", "MiniChatbot"]
    props: Dict[str, Any] = Field(default_factory=dict)


class WidgetEnvelope(BaseModel):
    display: Optional[str] = None
    widgets: List[Widget] = Field(default_factory=list)
    citations: Optional[List[str]] = None


class EndLearn(BaseModel):
    intent: str
    display: str
    widgets: List[Widget] = Field(default_factory=list)
    citations: Optional[List[str]] = None


class QuizMetadata(BaseModel):
    topic: Optional[str] = None
    score: Optional[float] = None


class EndQuiz(BaseModel):
    intent: str
    display: Optional[str] = None
    widgets: List[Widget] = Field(default_factory=list)
    elo: Dict[str, int] = Field(default_factory=dict)
    last_quiz: Optional[QuizMetadata] = None


class EndMilestone(BaseModel):
    intent: str
    display: str
    widgets: List[Widget] = Field(default_factory=list)
