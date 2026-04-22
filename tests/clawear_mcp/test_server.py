"""Tests for clawear_mcp.server — tool surface via in-process invocation."""
from __future__ import annotations

import pytest


@pytest.fixture
def server(tmp_data_root):
    """Build a server against the tmp data root. Returns the _Server test handle."""
    from clawear_mcp.config import Config
    from clawear_mcp.server import build_server

    cfg = Config(data_root=tmp_data_root)
    return build_server(cfg)


def test_list_sessions_returns_empty(tmp_data_root):
    from clawear_mcp.config import Config
    from clawear_mcp.server import build_server

    cfg = Config(data_root=tmp_data_root)
    srv = build_server(cfg)
    result = srv.tool_impls["list_sessions"]()
    assert result == []


def test_list_sessions_with_one_session(server, sample_session):
    result = server.tool_impls["list_sessions"]()
    assert len(result) == 1
    assert result[0]["session_id"] == sample_session
    assert result[0]["has_recording"] is True


def test_get_session_returns_detail(server, sample_session):
    detail = server.tool_impls["get_session"](session_id=sample_session)
    assert detail["session_id"] == sample_session
    assert detail["device"] == "Javis"
    assert detail["event_count"] == 4


def test_get_session_unknown_raises_with_hint(server, sample_session):
    with pytest.raises(ValueError) as exc_info:
        server.tool_impls["get_session"](session_id="does-not-exist")
    assert "not found" in str(exc_info.value).lower()


def test_get_transcript_strips_frontmatter_by_default(server, sample_session):
    body = server.tool_impls["get_transcript"](session_id=sample_session)
    assert "session_id:" not in body
    assert "Hello world" in body


def test_get_transcript_with_frontmatter(server, sample_session):
    full = server.tool_impls["get_transcript"](
        session_id=sample_session, include_frontmatter=True
    )
    assert "session_id:" in full


def test_search_transcripts_finds_matching(server, sample_session):
    hits = server.tool_impls["search_transcripts"](query="MCP")
    assert len(hits) == 1
    assert hits[0]["session_id"] == sample_session
    assert "[MCP]" in hits[0]["snippet"]


def test_get_event_summary(server, sample_session):
    summary = server.tool_impls["get_event_summary"](session_id=sample_session)
    assert summary["total"] == 4
    assert len(summary["timeline"]) >= 2


def test_get_events_filtered(server, sample_session):
    events = server.tool_impls["get_events"](
        session_id=sample_session,
        types=["input_audio_buffer.speech_started"],
    )
    assert len(events) == 1


def test_get_recording_info(server, sample_session):
    info = server.tool_impls["get_recording_info"](session_id=sample_session)
    assert info["duration_s"] == 2.5
    assert info["sample_rate"] == 16000
