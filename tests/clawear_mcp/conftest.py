"""Shared fixtures for clawear_mcp tests."""
from __future__ import annotations

import textwrap
import wave
from pathlib import Path

import pytest


def _write_wav(path: Path, duration_s: float = 1.0, sample_rate: int = 16000) -> None:
    """Write a minimal mono 16-bit PCM WAV of the given duration."""
    n_frames = int(duration_s * sample_rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * n_frames)


def _write_transcript(path: Path, session_id: str, body: str, root: Path) -> None:
    """Write a valid transcript markdown with frontmatter pointing at siblings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    md = textwrap.dedent(f"""\
        ---
        session_id: {session_id}
        started_at: '{session_id[:10]}T{session_id[11:].replace('-', ':')}+08:00'
        device: Javis
        sample_rate: 16000
        audio_path: {root}/recordings/{session_id}.wav
        events_path: {root}/events/{session_id}.jsonl
        dropped_blocks: 0
        truncated: false
        ---

        {body}
        """)
    path.write_text(md)


def _write_events(path: Path, events: list[dict]) -> None:
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


@pytest.fixture
def tmp_data_root(tmp_path) -> Path:
    (tmp_path / "transcripts").mkdir()
    (tmp_path / "recordings").mkdir()
    (tmp_path / "events").mkdir()
    return tmp_path


@pytest.fixture
def sample_session(tmp_data_root) -> str:
    """Write one complete session. Returns the session_id."""
    sid = "2026-04-21_14-12-39"
    _write_transcript(
        tmp_data_root / "transcripts" / f"{sid}.md",
        sid,
        "**User:** Hello world, this is a sample conversation about MCP servers.",
        tmp_data_root,
    )
    _write_wav(tmp_data_root / "recordings" / f"{sid}.wav", duration_s=2.5)
    _write_events(
        tmp_data_root / "events" / f"{sid}.jsonl",
        [
            {"type": "transcription_session.created", "event_id": "e1"},
            {"type": "input_audio_buffer.speech_started", "audio_start_ms": 500, "item_id": "i1"},
            {"type": "input_audio_buffer.speech_stopped", "audio_end_ms": 2200, "item_id": "i1"},
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "i1",
                "transcript": "Hello world",
            },
        ],
    )
    return sid


@pytest.fixture
def partial_session(tmp_data_root) -> str:
    """Session with only a transcript (no wav, no jsonl)."""
    sid = "2026-04-21_15-00-00"
    _write_transcript(
        tmp_data_root / "transcripts" / f"{sid}.md",
        sid,
        "**User:** transcript-only session",
        tmp_data_root,
    )
    return sid
