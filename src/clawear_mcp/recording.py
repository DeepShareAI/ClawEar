"""WAV recording metadata — stdlib `wave` only. No pydub, no ffmpeg."""
from __future__ import annotations

import struct
import wave
from pathlib import Path


def read_recording_info(path: Path, session_id: str) -> dict:
    """Return recording metadata. Never raises — missing/invalid files produce
    duration_s=0.0 with parse_error populated."""
    path = Path(path)

    if not path.exists():
        return {
            "session_id": session_id,
            "path": str(path),
            "size_bytes": 0,
            "mtime": 0.0,
            "duration_s": 0.0,
            "sample_rate": None,
            "channels": None,
            "bit_depth": None,
            "parse_error": "file not found",
        }

    stat = path.stat()
    try:
        with wave.open(str(path), "rb") as w:
            n_frames = w.getnframes()
            rate = w.getframerate()
            channels = w.getnchannels()
            sampwidth = w.getsampwidth()
            duration_s = n_frames / rate if rate else 0.0
        return {
            "session_id": session_id,
            "path": str(path),
            "size_bytes": stat.st_size,
            "mtime": stat.st_mtime,
            "duration_s": duration_s,
            "sample_rate": rate,
            "channels": channels,
            "bit_depth": sampwidth * 8,
            "parse_error": None,
        }
    except (wave.Error, EOFError, OSError, struct.error) as exc:
        return {
            "session_id": session_id,
            "path": str(path),
            "size_bytes": stat.st_size,
            "mtime": stat.st_mtime,
            "duration_s": 0.0,
            "sample_rate": None,
            "channels": None,
            "bit_depth": None,
            "parse_error": f"{type(exc).__name__}: {exc}",
        }
