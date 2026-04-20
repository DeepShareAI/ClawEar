from pathlib import Path

from ble_explorer_mcp.config import Config, load_config


def test_defaults_when_file_missing(tmp_path: Path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg == Config(
        write_allowlist=[],
        log_level="INFO",
        scan_default_seconds=5,
        scan_max_seconds=30,
        max_connections=8,
        notification_buffer_size=500,
    )


def test_loads_toml(tmp_path: Path):
    p = tmp_path / "cfg.toml"
    p.write_text(
        """
log_level = "DEBUG"
scan_default_seconds = 10
write_allowlist = ["0000ffe1-0000-1000-8000-00805f9b34fb"]
"""
    )
    cfg = load_config(p)
    assert cfg.log_level == "DEBUG"
    assert cfg.scan_default_seconds == 10
    assert cfg.write_allowlist == ["0000ffe1-0000-1000-8000-00805f9b34fb"]
    # Unspecified fields keep defaults.
    assert cfg.max_connections == 8


def test_allowlist_lowercased(tmp_path: Path):
    p = tmp_path / "cfg.toml"
    p.write_text('write_allowlist = ["0000FFE1-0000-1000-8000-00805F9B34FB"]')
    cfg = load_config(p)
    assert cfg.write_allowlist == ["0000ffe1-0000-1000-8000-00805f9b34fb"]
