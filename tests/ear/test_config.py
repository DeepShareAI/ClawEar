"""Tests for ear.config."""
from pathlib import Path

from ear.config import DEFAULT_INSTRUCTIONS, Config, load_config


def test_defaults_when_file_missing(tmp_path: Path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.log_level == "INFO"
    assert cfg.openai_model == "gpt-4o-realtime-preview"
    assert cfg.queue_max_blocks == 1000
    assert cfg.realtime_sample_rate == 24000
    assert cfg.ws_reconnect is False
    assert cfg.instructions == DEFAULT_INSTRUCTIONS
    # Path fields default to under ~/ClawEar (with ~ expanded)
    assert cfg.recordings_dir == Path.home() / "ClawEar" / "recordings"
    assert cfg.events_dir == Path.home() / "ClawEar" / "events"
    # transcripts_dir default warns but still resolves
    assert cfg.transcripts_dir == Path.home() / "ClawEar" / "transcripts"


def test_loads_toml(tmp_path: Path):
    p = tmp_path / "cfg.toml"
    p.write_text(
        """
log_level = "DEBUG"
transcripts_dir = "~/custom/transcripts"
recordings_dir  = "~/custom/recordings"
events_dir      = "~/custom/events"
openai_model = "gpt-4o-realtime-preview"
instructions = "custom instructions"
queue_max_blocks = 500
realtime_sample_rate = 24000
ws_reconnect = false
"""
    )
    cfg = load_config(p)
    assert cfg.log_level == "DEBUG"
    assert cfg.transcripts_dir == Path.home() / "custom" / "transcripts"
    assert cfg.recordings_dir == Path.home() / "custom" / "recordings"
    assert cfg.events_dir == Path.home() / "custom" / "events"
    assert cfg.instructions == "custom instructions"
    assert cfg.queue_max_blocks == 500


def test_partial_toml_fills_defaults(tmp_path: Path):
    p = tmp_path / "cfg.toml"
    p.write_text('log_level = "WARNING"')
    cfg = load_config(p)
    assert cfg.log_level == "WARNING"
    assert cfg.openai_model == "gpt-4o-realtime-preview"  # unchanged default
    assert cfg.queue_max_blocks == 1000
    # Path fallbacks when key missing from TOML.
    assert cfg.transcripts_dir == Path.home() / "ClawEar" / "transcripts"
    assert cfg.recordings_dir == Path.home() / "ClawEar" / "recordings"
    assert cfg.events_dir == Path.home() / "ClawEar" / "events"


def test_malformed_toml_raises(tmp_path: Path):
    import tomllib

    p = tmp_path / "cfg.toml"
    p.write_text("not = valid = toml")
    try:
        load_config(p)
    except tomllib.TOMLDecodeError:
        return
    raise AssertionError("expected TOMLDecodeError")
