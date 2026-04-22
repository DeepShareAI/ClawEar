"""Tests for clawear_mcp.sessions — registry + lazy freshness."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_registry_scan_discovers_sessions(tmp_data_root, sample_session):
    from clawear_mcp.sessions import SessionsRegistry

    reg = SessionsRegistry(data_root=tmp_data_root)
    reg.refresh()

    assert sample_session in reg.list_ids()
    entry = reg.get(sample_session)
    assert entry.transcript_path.name == f"{sample_session}.md"


def test_registry_detects_new_session_after_refresh(tmp_data_root, sample_session):
    from clawear_mcp.sessions import SessionsRegistry
    from tests.clawear_mcp.conftest import _write_transcript

    reg = SessionsRegistry(data_root=tmp_data_root)
    reg.refresh()

    new_sid = "2026-04-21_16-00-00"
    _write_transcript(
        tmp_data_root / "transcripts" / f"{new_sid}.md",
        new_sid,
        "body",
        tmp_data_root,
    )

    changed = reg.refresh()
    assert new_sid in reg.list_ids()
    assert new_sid in changed["added"]


def test_registry_detects_mtime_change(tmp_data_root, sample_session):
    from clawear_mcp.sessions import SessionsRegistry

    reg = SessionsRegistry(data_root=tmp_data_root)
    reg.refresh()

    md_path = tmp_data_root / "transcripts" / f"{sample_session}.md"
    # Ensure mtime actually changes (filesystems have 1s resolution on some FS)
    new_mtime = md_path.stat().st_mtime + 2
    os.utime(md_path, (new_mtime, new_mtime))

    changed = reg.refresh()
    assert sample_session in changed["modified"]


def test_registry_evicts_deleted_sessions(tmp_data_root, sample_session):
    from clawear_mcp.sessions import SessionsRegistry

    reg = SessionsRegistry(data_root=tmp_data_root)
    reg.refresh()
    assert sample_session in reg.list_ids()

    (tmp_data_root / "transcripts" / f"{sample_session}.md").unlink()
    changed = reg.refresh()

    assert sample_session not in reg.list_ids()
    assert sample_session in changed["removed"]


def test_registry_handles_partial_session(tmp_data_root, partial_session):
    from clawear_mcp.sessions import SessionsRegistry

    reg = SessionsRegistry(data_root=tmp_data_root)
    reg.refresh()

    entry = reg.get(partial_session)
    assert entry.has_recording is False
    assert entry.wav_path is None


def test_registry_nearest_returns_prefix_matches(tmp_data_root, sample_session):
    """nearest() returns sessions sharing a date prefix with the query."""
    from clawear_mcp.sessions import SessionsRegistry
    from tests.clawear_mcp.conftest import _write_transcript

    # Add a second session on the same date + one on a different date
    _write_transcript(
        tmp_data_root / "transcripts" / "2026-04-21_18-00-00.md",
        "2026-04-21_18-00-00",
        "later same day",
        tmp_data_root,
    )
    _write_transcript(
        tmp_data_root / "transcripts" / "2026-03-01_09-00-00.md",
        "2026-03-01_09-00-00",
        "different day",
        tmp_data_root,
    )

    reg = SessionsRegistry(data_root=tmp_data_root)
    reg.refresh()

    # Date prefix match — should return the two 2026-04-21 sessions, descending
    hits = reg.nearest("2026-04-21")
    assert "2026-04-21_18-00-00" in hits
    assert sample_session in hits
    assert "2026-03-01_09-00-00" not in hits


def test_registry_nearest_falls_back_to_top_n_when_no_prefix_hits(tmp_data_root, sample_session):
    from clawear_mcp.sessions import SessionsRegistry

    reg = SessionsRegistry(data_root=tmp_data_root)
    reg.refresh()

    # Query with no matching prefix — fall back to top-n of all sessions
    hits = reg.nearest("1999-01-01", n=5)
    assert sample_session in hits


def test_registry_nearest_empty_registry(tmp_data_root):
    from clawear_mcp.sessions import SessionsRegistry

    reg = SessionsRegistry(data_root=tmp_data_root)
    reg.refresh()

    assert reg.nearest("anything") == []
