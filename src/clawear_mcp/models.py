"""Pydantic return shapes for clawear-mcp tools."""
from __future__ import annotations

from pydantic import BaseModel


class SessionSummary(BaseModel):
    session_id: str
    started_at: str  # ISO 8601 with offset
    duration_s: float
    transcript_size: int
    event_count: int
    has_recording: bool


class SessionDetail(BaseModel):
    session_id: str
    started_at: str
    device: str | None
    sample_rate: int | None
    transcript_path: str
    events_path: str
    audio_path: str | None
    duration_s: float
    event_count: int
    truncated: bool | None = None
    dropped_blocks: int | None = None


class SearchHit(BaseModel):
    session_id: str
    started_at: str
    score: float
    snippet: str


class TimelineEntry(BaseModel):
    type: str
    ts_ms: int | None
    item_id: str | None


class EventError(BaseModel):
    ts_ms: int | None
    message: str


class EventSummary(BaseModel):
    session_id: str
    total: int
    counts_by_type: dict[str, int]
    timeline: list[TimelineEntry]
    errors: list[EventError]


class RecordingInfo(BaseModel):
    session_id: str
    path: str
    size_bytes: int
    mtime: float
    duration_s: float
    sample_rate: int | None
    channels: int | None
    bit_depth: int | None
    parse_error: str | None = None
