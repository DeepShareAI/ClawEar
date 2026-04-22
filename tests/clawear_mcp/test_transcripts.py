"""Tests for clawear_mcp.transcripts — frontmatter + FTS5 index."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def test_parse_frontmatter_extracts_fields(tmp_data_root, sample_session):
    from clawear_mcp.transcripts import parse_frontmatter

    md_path = tmp_data_root / "transcripts" / f"{sample_session}.md"
    fm, body = parse_frontmatter(md_path.read_text())

    assert fm["session_id"] == sample_session
    assert fm["device"] == "Javis"
    assert fm["sample_rate"] == 16000
    assert "Hello world" in body
    assert "---" not in body.splitlines()[0]


def test_strip_notes_removes_sidebars():
    from clawear_mcp.transcripts import strip_notes

    raw = "**User:** hello\n\n> note: api error: foo\n\n**User:** world\n"
    cleaned = strip_notes(raw)

    assert "api error" not in cleaned
    assert "hello" in cleaned
    assert "world" in cleaned


def test_fts_index_insert_and_search(tmp_path):
    from clawear_mcp.transcripts import TranscriptsIndex

    idx = TranscriptsIndex(tmp_path / "idx.sqlite3")
    idx.ensure_schema()

    idx.upsert("s1", "2026-04-21T14:12:39+08:00", "hello world karpathy skills")
    idx.upsert("s2", "2026-04-20T10:00:00+08:00", "unrelated content")

    hits = idx.search("karpathy", since=None, until=None, limit=10, snippet_tokens=8)

    assert len(hits) == 1
    assert hits[0]["session_id"] == "s1"
    assert "[karpathy]" in hits[0]["snippet"]


def test_fts_index_time_range_filter(tmp_path):
    from clawear_mcp.transcripts import TranscriptsIndex

    idx = TranscriptsIndex(tmp_path / "idx.sqlite3")
    idx.ensure_schema()

    idx.upsert("s1", "2026-04-21T14:00:00+08:00", "skills content")
    idx.upsert("s2", "2026-04-20T10:00:00+08:00", "skills content")

    hits = idx.search(
        "skills",
        since="2026-04-21T00:00:00+08:00",
        until="2026-04-22T00:00:00+08:00",
        limit=10,
        snippet_tokens=8,
    )

    assert len(hits) == 1
    assert hits[0]["session_id"] == "s1"


def test_fts_index_delete_removes_row(tmp_path):
    from clawear_mcp.transcripts import TranscriptsIndex

    idx = TranscriptsIndex(tmp_path / "idx.sqlite3")
    idx.ensure_schema()
    idx.upsert("s1", "2026-04-21T14:12:39+08:00", "hello")
    idx.delete("s1")

    hits = idx.search("hello", since=None, until=None, limit=10, snippet_tokens=8)
    assert hits == []


def test_fts_missing_raises_with_hint(tmp_path, monkeypatch):
    """If FTS5 is not compiled into sqlite3, a clear error is raised."""
    from unittest.mock import MagicMock

    from clawear_mcp.transcripts import TranscriptsIndex, FTS5NotAvailable

    fake_conn = MagicMock()
    fake_conn.execute.side_effect = sqlite3.OperationalError("no such module: fts5")

    # Patch sqlite3.connect in the transcripts module's namespace so the lazy
    # _connect() returns our mock. (Connection.execute itself is a C-extension
    # method and cannot be patched — we replace the whole connection instead.)
    monkeypatch.setattr(
        "clawear_mcp.transcripts.sqlite3.connect",
        lambda *a, **kw: fake_conn,
    )

    idx = TranscriptsIndex(tmp_path / "idx.sqlite3")
    with pytest.raises(FTS5NotAvailable):
        idx.ensure_schema()
