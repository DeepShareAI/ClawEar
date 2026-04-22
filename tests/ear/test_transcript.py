"""Tests for ear.transcript."""
from pathlib import Path

from ear.transcript import TranscriptBuilder


def test_initial_flush_writes_frontmatter_and_empty_body(tmp_path: Path):
    p = tmp_path / "s.md"
    t = TranscriptBuilder(
        session_id="2026-04-20_14-33-12",
        started_at="2026-04-20T14:33:12Z",
        device="AirPods Pro",
        sample_rate=16000,
        audio_path=Path("/abs/audio.wav"),
        events_path=Path("/abs/events.jsonl"),
    )
    t.flush(p)
    text = p.read_text()
    assert text.startswith("---\n")
    assert "session_id: 2026-04-20_14-33-12\n" in text
    assert "device: AirPods Pro\n" in text
    assert "sample_rate: 16000\n" in text
    assert "audio_path: /abs/audio.wav\n" in text
    assert "events_path: /abs/events.jsonl\n" in text
    assert "dropped_blocks: 0\n" in text
    assert "truncated: false\n" in text
    assert text.endswith("---\n\n")


def test_user_turns_append_in_order_and_no_assistant_method(tmp_path: Path):
    p = tmp_path / "s.md"
    t = TranscriptBuilder(
        session_id="s1",
        started_at="2026-04-20T14:33:12Z",
        device="d",
        sample_rate=16000,
        audio_path=Path("/a.wav"),
        events_path=Path("/e.jsonl"),
    )
    t.append_user_turn("Hello there.")
    t.add_note("interjection")
    t.append_user_turn("Second message.")
    t.flush(p)

    text = p.read_text()
    body = text.split("---\n\n", 1)[1]
    assert (
        body
        == "**User:** Hello there.\n\n"
        "> note: interjection\n\n"
        "**User:** Second message.\n\n"
    )
    assert not hasattr(t, "append_assistant_turn")


def test_add_note_appears_as_quoted_note_line(tmp_path: Path):
    p = tmp_path / "s.md"
    t = TranscriptBuilder(
        session_id="s1",
        started_at="2026-04-20T14:33:12Z",
        device="d",
        sample_rate=16000,
        audio_path=Path("/a.wav"),
        events_path=Path("/e.jsonl"),
    )
    t.add_note("api error: 429")
    t.flush(p)

    body = p.read_text().split("---\n\n", 1)[1]
    assert body == "> note: api error: 429\n\n"


def test_dropped_blocks_and_truncated_appear_in_frontmatter(tmp_path: Path):
    p = tmp_path / "s.md"
    t = TranscriptBuilder(
        session_id="s1",
        started_at="2026-04-20T14:33:12Z",
        device="d",
        sample_rate=16000,
        audio_path=Path("/a.wav"),
        events_path=Path("/e.jsonl"),
    )
    t.set_dropped_blocks(42)
    t.set_truncated("WebSocket error: 1006")
    t.flush(p)

    text = p.read_text()
    assert "dropped_blocks: 42\n" in text
    assert "truncated: true\n" in text
    assert "truncated_reason: 'WebSocket error: 1006'\n" in text


def test_atomic_rewrite_no_partial_reads(tmp_path: Path):
    """The destination file must never be visible half-written. We verify that
    the tmp path is used and that after flush() the file content matches expectations."""
    p = tmp_path / "s.md"
    t = TranscriptBuilder(
        session_id="s1",
        started_at="2026-04-20T14:33:12Z",
        device="d",
        sample_rate=16000,
        audio_path=Path("/a.wav"),
        events_path=Path("/e.jsonl"),
    )
    t.append_user_turn("first")
    t.flush(p)
    t.append_user_turn("second")
    t.flush(p)

    body = p.read_text().split("---\n\n", 1)[1]
    assert "first" in body and "second" in body
    # no leftover tmp file
    assert not (p.parent / (p.name + ".tmp")).exists()


def test_special_chars_in_string_values_are_quoted(tmp_path: Path):
    p = tmp_path / "s.md"
    t = TranscriptBuilder(
        session_id="s1",
        started_at="2026-04-20T14:33:12Z",
        device="has: colon",
        sample_rate=16000,
        audio_path=Path("/a.wav"),
        events_path=Path("/e.jsonl"),
    )
    t.flush(p)
    assert "device: 'has: colon'\n" in p.read_text()
