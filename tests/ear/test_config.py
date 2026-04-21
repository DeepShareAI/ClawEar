"""Tests for ear.config."""
from pathlib import Path

from ear.config import Config, load_config


def test_defaults_when_file_missing(tmp_path: Path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.log_level == "INFO"
    assert cfg.transcription_model == "gpt-4o-transcribe"
    assert cfg.queue_max_blocks == 1000
    assert cfg.realtime_sample_rate == 24000
    assert cfg.ws_reconnect is False
    assert cfg.recordings_dir == Path.home() / "ClawEar" / "recordings"
    assert cfg.events_dir == Path.home() / "ClawEar" / "events"
    assert cfg.transcripts_dir == Path.home() / "ClawEar" / "transcripts"
    assert not hasattr(cfg, "openai_model")
    assert not hasattr(cfg, "instructions")


def test_loads_toml(tmp_path: Path):
    p = tmp_path / "cfg.toml"
    p.write_text(
        """
log_level = "DEBUG"
transcripts_dir = "~/custom/transcripts"
recordings_dir  = "~/custom/recordings"
events_dir      = "~/custom/events"
transcription_model = "gpt-4o-mini-transcribe"
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
    assert cfg.transcription_model == "gpt-4o-mini-transcribe"
    assert cfg.queue_max_blocks == 500


def test_partial_toml_fills_defaults(tmp_path: Path):
    p = tmp_path / "cfg.toml"
    p.write_text('log_level = "WARNING"')
    cfg = load_config(p)
    assert cfg.log_level == "WARNING"
    assert cfg.transcription_model == "gpt-4o-transcribe"
    assert cfg.queue_max_blocks == 1000
    assert cfg.transcripts_dir == Path.home() / "ClawEar" / "transcripts"
    assert cfg.recordings_dir == Path.home() / "ClawEar" / "recordings"
    assert cfg.events_dir == Path.home() / "ClawEar" / "events"


def test_legacy_openai_model_and_instructions_keys_are_ignored(tmp_path: Path):
    """Users upgrading from the conversational design may still have these keys.
    The loader should silently ignore them (current TOML-loader behavior)."""
    p = tmp_path / "cfg.toml"
    p.write_text(
        """
openai_model = "gpt-4o-realtime-preview"
instructions = "legacy prompt"
transcription_model = "gpt-4o-transcribe"
"""
    )
    cfg = load_config(p)
    assert cfg.transcription_model == "gpt-4o-transcribe"
    assert not hasattr(cfg, "openai_model")
    assert not hasattr(cfg, "instructions")


def test_malformed_toml_raises(tmp_path: Path):
    import tomllib

    p = tmp_path / "cfg.toml"
    p.write_text("not = valid = toml")
    try:
        load_config(p)
    except tomllib.TOMLDecodeError:
        return
    raise AssertionError("expected TOMLDecodeError")
