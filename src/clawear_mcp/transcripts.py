"""Transcripts: frontmatter parsing + FTS5-backed search index."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

import logging

import yaml

log = logging.getLogger("clawear_mcp.transcripts")


class FTS5NotAvailable(RuntimeError):
    """Raised when the system sqlite3 was built without the FTS5 extension."""


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_NOTE_LINE_RE = re.compile(r"^> note:.*$", re.MULTILINE)


def parse_frontmatter(md_text: str) -> tuple[dict[str, Any], str]:
    """Split YAML frontmatter and body. Returns ({} , full_text) if no frontmatter."""
    m = _FRONTMATTER_RE.match(md_text)
    if not m:
        return {}, md_text
    raw = m.group(1)
    body = md_text[m.end():]
    fm = _parse_yaml_dict(raw)
    return fm, body


def _parse_yaml_dict(raw: str) -> dict[str, Any]:
    """Parse the frontmatter YAML block. Returns {} on parse error (logged)."""
    try:
        loaded = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        log.warning("frontmatter YAML parse failed: %s", exc)
        return {}
    return loaded if isinstance(loaded, dict) else {}


def strip_notes(body: str) -> str:
    """Remove `> note: ...` sidebar lines so they don't pollute FTS index."""
    return _NOTE_LINE_RE.sub("", body)


class TranscriptsIndex:
    """FTS5 virtual table over transcript bodies, keyed on session_id."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts USING fts5(
                    session_id UNINDEXED,
                    started_at UNINDEXED,
                    body,
                    tokenize='porter unicode61 remove_diacritics 2'
                )
                """
            )
            conn.commit()
        except sqlite3.OperationalError as exc:
            if "fts5" in str(exc).lower():
                raise FTS5NotAvailable(
                    "Your Python's sqlite3 was built without FTS5. "
                    "On macOS the bundled python should have it; on Linux, "
                    "reinstall Python via `uv` or `pyenv`."
                ) from exc
            raise

    def upsert(self, session_id: str, started_at: str, body: str) -> None:
        conn = self._connect()
        conn.execute(
            "DELETE FROM transcripts_fts WHERE session_id = ?", (session_id,)
        )
        conn.execute(
            "INSERT INTO transcripts_fts(session_id, started_at, body) VALUES (?, ?, ?)",
            (session_id, started_at, body),
        )
        conn.commit()

    def delete(self, session_id: str) -> None:
        conn = self._connect()
        conn.execute(
            "DELETE FROM transcripts_fts WHERE session_id = ?", (session_id,)
        )
        conn.commit()

    def search(
        self,
        query: str,
        since: str | None,
        until: str | None,
        limit: int,
        snippet_tokens: int,
    ) -> list[dict]:
        conn = self._connect()
        sql = """
            SELECT session_id, started_at,
                   bm25(transcripts_fts) AS score,
                   snippet(transcripts_fts, 2, '[', ']', '...', :tokens) AS snippet
            FROM transcripts_fts
            WHERE transcripts_fts MATCH :query
              AND (:since IS NULL OR started_at >= :since)
              AND (:until IS NULL OR started_at <  :until)
            ORDER BY score
            LIMIT :limit
        """
        cur = conn.execute(
            sql,
            {
                "query": query,
                "since": since,
                "until": until,
                "limit": limit,
                "tokens": snippet_tokens,
            },
        )
        return [dict(row) for row in cur.fetchall()]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
