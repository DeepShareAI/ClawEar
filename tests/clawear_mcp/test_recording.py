"""Tests for clawear_mcp.recording — WAV metadata parsing."""
from __future__ import annotations

import wave
from pathlib import Path


def test_valid_wav_returns_metadata(tmp_data_root, sample_session):
    from clawear_mcp.recording import read_recording_info

    wav_path = tmp_data_root / "recordings" / f"{sample_session}.wav"
    info = read_recording_info(wav_path, session_id=sample_session)

    assert info["session_id"] == sample_session
    assert info["duration_s"] == 2.5
    assert info["sample_rate"] == 16000
    assert info["channels"] == 1
    assert info["bit_depth"] == 16
    assert info["parse_error"] is None
    assert info["size_bytes"] > 0


def test_44_byte_placeholder_does_not_raise(tmp_data_root):
    from clawear_mcp.recording import read_recording_info

    wav_path = tmp_data_root / "recordings" / "placeholder.wav"
    # Write just the 44-byte RIFF header stub (invalid data payload)
    wav_path.write_bytes(b"RIFF" + b"\x00" * 40)

    info = read_recording_info(wav_path, session_id="placeholder")
    assert info["duration_s"] == 0.0
    assert info["parse_error"] is not None
    assert info["size_bytes"] == 44


def test_zero_byte_file(tmp_data_root):
    from clawear_mcp.recording import read_recording_info

    wav_path = tmp_data_root / "recordings" / "empty.wav"
    wav_path.write_bytes(b"")

    info = read_recording_info(wav_path, session_id="empty")
    assert info["duration_s"] == 0.0
    assert info["size_bytes"] == 0
    assert info["parse_error"] is not None


def test_missing_file(tmp_data_root):
    from clawear_mcp.recording import read_recording_info

    info = read_recording_info(
        tmp_data_root / "recordings" / "nope.wav", session_id="nope"
    )
    assert info["duration_s"] == 0.0
    assert info["size_bytes"] == 0
    assert info["parse_error"] is not None
