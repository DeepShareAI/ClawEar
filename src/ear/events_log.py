"""Append-only JSONL events log. One JSON object per line, flushed per append."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TextIO


class EventsLog:
    def __init__(self, path: Path):
        self._path = path
        self._fh: TextIO | None = None

    def open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self._path.open("a", encoding="utf-8")

    def append(self, event: dict[str, Any]) -> None:
        if self._fh is None:
            raise RuntimeError("EventsLog is not open")
        self._fh.write(json.dumps(event, ensure_ascii=False, default=str))
        self._fh.write("\n")
        self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
