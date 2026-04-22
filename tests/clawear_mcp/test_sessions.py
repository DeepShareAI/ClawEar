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
