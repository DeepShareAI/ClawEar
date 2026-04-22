"""Tests for clawear_mcp.events — summary + filter."""
from __future__ import annotations

import json
from pathlib import Path


def test_event_summary_counts_and_timeline(tmp_data_root, sample_session):
    from clawear_mcp.events import build_summary

    events_path = tmp_data_root / "events" / f"{sample_session}.jsonl"
    summary = build_summary(events_path, session_id=sample_session)

    assert summary["session_id"] == sample_session
    assert summary["total"] == 4
    assert summary["counts_by_type"]["transcription_session.created"] == 1
    assert summary["counts_by_type"]["input_audio_buffer.speech_started"] == 1
    # Timeline curates known-interesting types
    types_in_timeline = [t["type"] for t in summary["timeline"]]
    assert "input_audio_buffer.speech_started" in types_in_timeline
    assert "input_audio_buffer.speech_stopped" in types_in_timeline
    # No errors in the fixture
    assert summary["errors"] == []


def test_event_summary_captures_errors(tmp_data_root):
    from clawear_mcp.events import build_summary

    events_path = tmp_data_root / "events" / "s.jsonl"
    with events_path.open("w") as f:
        f.write(json.dumps({"type": "error", "error": {"message": "oops"}}) + "\n")
        f.write(json.dumps({"type": "conversation.item.input_audio_transcription.error", "message": "second"}) + "\n")

    summary = build_summary(events_path, session_id="s")
    assert len(summary["errors"]) == 2
    assert summary["errors"][0]["message"] == "oops"


def test_event_summary_handles_malformed_lines(tmp_data_root):
    from clawear_mcp.events import build_summary

    events_path = tmp_data_root / "events" / "s.jsonl"
    with events_path.open("w") as f:
        f.write(json.dumps({"type": "session.created"}) + "\n")
        f.write("{not valid json\n")  # malformed
        f.write(json.dumps({"type": "error", "error": {"message": "x"}}) + "\n")

    summary = build_summary(events_path, session_id="s")
    assert summary["total"] == 3
    assert summary["counts_by_type"]["__malformed__"] == 1
    assert summary["counts_by_type"]["session.created"] == 1


def test_get_events_filters_by_type_and_paginates(tmp_data_root, sample_session):
    from clawear_mcp.events import get_events

    events_path = tmp_data_root / "events" / f"{sample_session}.jsonl"
    results = get_events(events_path, types=["input_audio_buffer.speech_started"], limit=10, offset=0)
    assert len(results) == 1
    assert results[0]["type"] == "input_audio_buffer.speech_started"


def test_get_events_filters_by_item_id(tmp_data_root, sample_session):
    from clawear_mcp.events import get_events

    events_path = tmp_data_root / "events" / f"{sample_session}.jsonl"
    results = get_events(events_path, item_id="i1", limit=10, offset=0)
    # 3 events carry item_id='i1': speech_started, speech_stopped, transcription.completed
    assert len(results) == 3
    for e in results:
        assert e.get("item_id") == "i1"


def test_get_events_pagination_preserves_order(tmp_data_root):
    from clawear_mcp.events import get_events

    events_path = tmp_data_root / "events" / "s.jsonl"
    with events_path.open("w") as f:
        for i in range(5):
            f.write(json.dumps({"type": "x", "n": i}) + "\n")

    page1 = get_events(events_path, limit=2, offset=0)
    page2 = get_events(events_path, limit=2, offset=2)

    assert [e["n"] for e in page1] == [0, 1]
    assert [e["n"] for e in page2] == [2, 3]
