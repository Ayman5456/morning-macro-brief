from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


BriefType = Literal["morning", "evening"]


class BriefOptions(BaseModel):
    target_date: str | None = None
    timezone: str = "Asia/Singapore"
    region: str = "global"
    depth: Literal["standard", "deep"] = "deep"
    target_audio_minutes: int = 15
    brief_type: BriefType = "morning"


class AudioChapter(BaseModel):
    title: str
    summary: str


class BriefOutput(BaseModel):
    title: str
    market_date: str
    brief_type: BriefType = "morning"
    generated_at: str
    markdown: str
    audio_script: str = Field(description="2200-2700 word narration script for a 15-minute brief.")
    audio_chapters: list[AudioChapter] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)


class BriefJobResult(BaseModel):
    output: BriefOutput
    markdown_path: str
    json_path: str
    audio_path: str | None = None
    audio_segment_paths: list[str] = Field(default_factory=list)
    context: dict[str, Any] | None = None
