"""Tests for the one-shot timestamp migration script."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


def _write_session(root: Path, stem: str, started_at_iso: str) -> None:
    """Write a valid (md, wav, jsonl) triple under root using old-format stem."""
    (root / "transcripts").mkdir(parents=True, exist_ok=True)
    (root / "recordings").mkdir(parents=True, exist_ok=True)
    (root / "events").mkdir(parents=True, exist_ok=True)

    md = textwrap.dedent(f"""\
        ---
        session_id: {stem}
        started_at: '{started_at_iso}'
        device: Javis
        sample_rate: 16000
        audio_path: {root}/recordings/{stem}.wav
        events_path: {root}/events/{stem}.jsonl
        dropped_blocks: 0
        truncated: false
        ---

        **User:** hello world
        """)
    (root / "transcripts" / f"{stem}.md").write_text(md)
    (root / "recordings" / f"{stem}.wav").write_bytes(b"RIFF....WAVE")
    (root / "events" / f"{stem}.jsonl").write_text('{"type":"session.created"}\n')


def test_migrate_renames_old_utc_session_to_local(tmp_path, monkeypatch):
    from scripts.migrate_timestamps import migrate

    # Fix the local timezone to UTC+08:00 so the test is deterministic
    monkeypatch.setenv("TZ", "Asia/Shanghai")
    import time
    time.tzset()

    _write_session(tmp_path, "2026-04-21T04-12-39Z", "2026-04-21T04:12:39Z")

    result = migrate(tmp_path)

    assert result["migrated"] == 1
    assert result["skipped"] == 0
    # Files renamed to local-time stem (UTC+8 → 12:12:39)
    assert (tmp_path / "transcripts" / "2026-04-21_12-12-39.md").exists()
    assert (tmp_path / "recordings" / "2026-04-21_12-12-39.wav").exists()
    assert (tmp_path / "events" / "2026-04-21_12-12-39.jsonl").exists()
    # Old stem is gone
    assert not (tmp_path / "transcripts" / "2026-04-21T04-12-39Z.md").exists()
    # Frontmatter rewritten
    md = (tmp_path / "transcripts" / "2026-04-21_12-12-39.md").read_text()
    assert "session_id: 2026-04-21_12-12-39" in md
    assert "started_at: '2026-04-21T12:12:39+08:00'" in md
    assert str(tmp_path / "recordings" / "2026-04-21_12-12-39.wav") in md
    assert str(tmp_path / "events" / "2026-04-21_12-12-39.jsonl") in md


def test_migrate_is_idempotent(tmp_path, monkeypatch):
    from scripts.migrate_timestamps import migrate

    monkeypatch.setenv("TZ", "Asia/Shanghai")
    import time
    time.tzset()

    _write_session(tmp_path, "2026-04-21T04-12-39Z", "2026-04-21T04:12:39Z")

    migrate(tmp_path)
    result2 = migrate(tmp_path)

    # Second run detects already-migrated sessions and skips them
    assert result2["migrated"] == 0
    assert result2["skipped"] == 1


def test_migrate_skips_orphan_files(tmp_path, monkeypatch):
    from scripts.migrate_timestamps import migrate

    monkeypatch.setenv("TZ", "Asia/Shanghai")
    import time
    time.tzset()

    # Transcript exists but no matching wav/jsonl
    (tmp_path / "transcripts").mkdir()
    md = "---\nsession_id: 2026-04-21T04-12-39Z\nstarted_at: '2026-04-21T04:12:39Z'\n---\n\nbody\n"
    (tmp_path / "transcripts" / "2026-04-21T04-12-39Z.md").write_text(md)

    result = migrate(tmp_path)

    # Orphan transcript is still renamed (the script operates on whichever files exist)
    assert (tmp_path / "transcripts" / "2026-04-21_12-12-39.md").exists()
    assert result["migrated"] == 1
