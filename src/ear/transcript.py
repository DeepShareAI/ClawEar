"""Session transcript builder.

State: frontmatter dict + append-only body list (strings). Flush rewrites
the whole on-disk file atomically (tmp file + os.replace).
"""
from __future__ import annotations

import os
from pathlib import Path


def _yaml_scalar(v: object) -> str:
    """Serialize a single scalar for a YAML frontmatter value.

    Only supports the limited set of value types we actually use: str, int, bool, Path.
    Strings that contain characters YAML may interpret specially get single-quoted
    (with embedded single quotes doubled).
    """
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, Path):
        return str(v)
    s = str(v)
    # Quote if it contains YAML-special characters or leading/trailing whitespace.
    needs_quote = any(c in s for c in ":#{}[],&*!|>'\"%@`\n") or s != s.strip() or s == ""
    if needs_quote:
        return "'" + s.replace("'", "''") + "'"
    return s


class TranscriptBuilder:
    def __init__(
        self,
        session_id: str,
        started_at: str,
        device: str,
        sample_rate: int,
        audio_path: Path,
        events_path: Path,
    ):
        self._frontmatter: dict[str, object] = {
            "session_id": session_id,
            "started_at": started_at,
            "device": device,
            "sample_rate": sample_rate,
            "audio_path": audio_path,
            "events_path": events_path,
            "dropped_blocks": 0,
            "truncated": False,
        }
        self._body: list[str] = []

    def append_user_turn(self, text: str) -> None:
        self._body.append(f"**User:** {text}\n\n")

    def append_assistant_turn(self, text: str) -> None:
        self._body.append(f"**Assistant:** {text}\n\n")

    def add_note(self, text: str) -> None:
        self._body.append(f"> note: {text}\n\n")

    def set_dropped_blocks(self, n: int) -> None:
        self._frontmatter["dropped_blocks"] = n

    def set_truncated(self, reason: str) -> None:
        self._frontmatter["truncated"] = True
        self._frontmatter["truncated_reason"] = reason

    def _render(self) -> str:
        parts = ["---\n"]
        for k, v in self._frontmatter.items():
            parts.append(f"{k}: {_yaml_scalar(v)}\n")
        parts.append("---\n\n")
        parts.extend(self._body)
        return "".join(parts)

    def flush(self, path: Path) -> None:
        """Atomically write the full transcript to `path`."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / (path.name + ".tmp")
        tmp.write_text(self._render(), encoding="utf-8")
        os.replace(tmp, path)
