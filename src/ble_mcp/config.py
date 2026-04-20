"""Configuration loader for ble-mcp."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    write_allowlist: list[str] = field(default_factory=list)
    log_level: str = "INFO"
    scan_max_seconds: int = 30
    max_connections: int = 8
    notification_buffer_size: int = 500


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "ble-mcp" / "config.toml"


def load_config(path: Path | None = None) -> Config:
    """Load config from TOML, or return defaults if the file is absent."""
    p = path if path is not None else DEFAULT_CONFIG_PATH
    if not p.exists():
        return Config()
    raw = tomllib.loads(p.read_text())
    allowlist = [u.lower() for u in raw.get("write_allowlist", [])]
    return Config(
        write_allowlist=allowlist,
        log_level=raw.get("log_level", "INFO"),
        scan_max_seconds=raw.get("scan_max_seconds", 30),
        max_connections=raw.get("max_connections", 8),
        notification_buffer_size=raw.get("notification_buffer_size", 500),
    )
