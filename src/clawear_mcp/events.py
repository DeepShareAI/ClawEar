"""Event JSONL streaming — summary + filtered read."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

# Curated "interesting" event types that get a slot in the timeline skeleton
_TIMELINE_TYPES = frozenset({
    "transcription_session.created",
    "session.created",
    "input_audio_buffer.speech_started",
    "input_audio_buffer.speech_stopped",
    "conversation.item.input_audio_transcription.completed",
    "error",
})


def _stream_jsonl(path: Path) -> Iterator[tuple[int, dict | None]]:
    """Yield (line_index, event | None) where None marks a malformed line."""
    if not path.exists():
        return
    with path.open("r") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                yield i, json.loads(line)
            except json.JSONDecodeError:
                yield i, None


def _event_ts_ms(event: dict) -> int | None:
    if "audio_start_ms" in event:
        return event["audio_start_ms"]
    if "audio_end_ms" in event:
        return event["audio_end_ms"]
    return None


def _is_error_event(event_type: str) -> bool:
    return event_type == "error" or event_type.endswith(".error")


def build_summary(path: Path, session_id: str) -> dict:
    """Stream the JSONL once; return counts_by_type + timeline + errors."""
    counts: dict[str, int] = {}
    timeline: list[dict] = []
    errors: list[dict] = []
    total = 0

    for _idx, ev in _stream_jsonl(Path(path)):
        total += 1
        if ev is None:
            counts["__malformed__"] = counts.get("__malformed__", 0) + 1
            continue
        et = ev.get("type", "")
        counts[et] = counts.get(et, 0) + 1
        if et in _TIMELINE_TYPES:
            timeline.append({
                "type": et,
                "ts_ms": _event_ts_ms(ev),
                "item_id": ev.get("item_id"),
            })
        if _is_error_event(et):
            msg = ""
            if isinstance(ev.get("error"), dict):
                msg = ev["error"].get("message", "")
            msg = msg or ev.get("message", "") or et
            errors.append({"ts_ms": _event_ts_ms(ev), "message": msg})

    return {
        "session_id": session_id,
        "total": total,
        "counts_by_type": counts,
        "timeline": timeline,
        "errors": errors,
    }


def get_events(
    path: Path,
    types: list[str] | None = None,
    item_id: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """Return raw event objects, filtered + paginated in JSONL line order."""
    type_set = set(types) if types else None
    matching: list[dict] = []
    for _idx, ev in _stream_jsonl(Path(path)):
        if ev is None:
            continue
        if type_set is not None and ev.get("type") not in type_set:
            continue
        if item_id is not None and ev.get("item_id") != item_id:
            continue
        matching.append(ev)
    return matching[offset : offset + limit]
