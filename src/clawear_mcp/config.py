"""Configuration for clawear-mcp. One source of truth: the CLAWEAR_DATA_ROOT env var."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    data_root: Path

    @property
    def transcripts_dir(self) -> Path:
        return self.data_root / "transcripts"

    @property
    def recordings_dir(self) -> Path:
        return self.data_root / "recordings"

    @property
    def events_dir(self) -> Path:
        return self.data_root / "events"

    @property
    def index_path(self) -> Path:
        return self.data_root / ".clawear_mcp" / "index.sqlite3"


def load_config() -> Config:
    """Resolve CLAWEAR_DATA_ROOT (or default to ~/ClawEar). Does not validate existence."""
    env = os.environ.get("CLAWEAR_DATA_ROOT")
    data_root = Path(env).expanduser() if env else Path.home() / "ClawEar"
    return Config(data_root=data_root)
