"""Tests for clawear_mcp.config."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_config_default_data_root(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAWEAR_DATA_ROOT", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    from clawear_mcp.config import load_config

    cfg = load_config()
    assert cfg.data_root == tmp_path / "ClawEar"


def test_config_honors_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAWEAR_DATA_ROOT", str(tmp_path / "custom"))

    from clawear_mcp.config import load_config

    cfg = load_config()
    assert cfg.data_root == tmp_path / "custom"


def test_config_derives_subdirs_and_index_path(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAWEAR_DATA_ROOT", str(tmp_path))

    from clawear_mcp.config import load_config

    cfg = load_config()
    assert cfg.transcripts_dir == tmp_path / "transcripts"
    assert cfg.recordings_dir == tmp_path / "recordings"
    assert cfg.events_dir == tmp_path / "events"
    assert cfg.index_path == tmp_path / ".clawear_mcp" / "index.sqlite3"
