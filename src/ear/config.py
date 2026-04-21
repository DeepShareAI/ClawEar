"""Configuration loader for ClawEar."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_INSTRUCTIONS = (
    "You are an audio observer. Transcribe the speaker's words faithfully.\n"
    "When a clear topic shift, action item, decision, or named entity appears,\n"
    'add a short inline note on its own line prefixed with "> note:".\n'
    "Do not respond conversationally; do not add commentary beyond such notes.\n"
)


@dataclass(frozen=True)
class Config:
    log_level: str = "INFO"
    transcripts_dir: Path = field(
        default_factory=lambda: Path.home() / "ClawEar" / "transcripts"
    )
    recordings_dir: Path = field(
        default_factory=lambda: Path.home() / "ClawEar" / "recordings"
    )
    events_dir: Path = field(
        default_factory=lambda: Path.home() / "ClawEar" / "events"
    )
    openai_model: str = "gpt-4o-realtime-preview"
    instructions: str = DEFAULT_INSTRUCTIONS
    queue_max_blocks: int = 1000
    realtime_sample_rate: int = 24000
    ws_reconnect: bool = False


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "clawear" / "config.toml"


def load_config(path: Path | None = None) -> Config:
    """Load config from TOML, or return defaults if the file is absent."""
    p = path if path is not None else DEFAULT_CONFIG_PATH
    if not p.exists():
        return Config()
    raw = tomllib.loads(p.read_text())
    defaults = Config()
    return Config(
        log_level=raw.get("log_level", defaults.log_level),
        transcripts_dir=(
            Path(raw["transcripts_dir"]).expanduser()
            if "transcripts_dir" in raw
            else defaults.transcripts_dir
        ),
        recordings_dir=(
            Path(raw["recordings_dir"]).expanduser()
            if "recordings_dir" in raw
            else defaults.recordings_dir
        ),
        events_dir=(
            Path(raw["events_dir"]).expanduser()
            if "events_dir" in raw
            else defaults.events_dir
        ),
        openai_model=raw.get("openai_model", defaults.openai_model),
        instructions=raw.get("instructions", defaults.instructions),
        queue_max_blocks=int(raw.get("queue_max_blocks", defaults.queue_max_blocks)),
        realtime_sample_rate=int(
            raw.get("realtime_sample_rate", defaults.realtime_sample_rate)
        ),
        ws_reconnect=bool(raw.get("ws_reconnect", defaults.ws_reconnect)),
    )
