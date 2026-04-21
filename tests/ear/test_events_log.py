"""Tests for ear.events_log."""
import json
from pathlib import Path

from ear.events_log import EventsLog


def test_append_writes_one_json_per_line(tmp_path: Path):
    p = tmp_path / "events.jsonl"
    log = EventsLog(p)
    log.open()
    log.append({"type": "a", "n": 1})
    log.append({"type": "b", "nested": {"k": "v"}})
    log.close()

    lines = p.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"type": "a", "n": 1}
    assert json.loads(lines[1]) == {"type": "b", "nested": {"k": "v"}}


def test_flush_after_each_append_makes_line_visible(tmp_path: Path):
    """Each line is flushed immediately so a crash mid-session leaves a readable file."""
    p = tmp_path / "events.jsonl"
    log = EventsLog(p)
    log.open()
    log.append({"type": "a"})
    # Read the file *before* close — content should already be present.
    content = p.read_text()
    assert content == '{"type": "a"}\n'
    log.close()


def test_append_before_open_raises(tmp_path: Path):
    log = EventsLog(tmp_path / "events.jsonl")
    try:
        log.append({"x": 1})
    except RuntimeError as exc:
        assert "not open" in str(exc)
        return
    raise AssertionError("expected RuntimeError")


def test_close_is_idempotent(tmp_path: Path):
    p = tmp_path / "events.jsonl"
    log = EventsLog(p)
    log.open()
    log.close()
    log.close()  # must not raise
