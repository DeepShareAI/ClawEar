"""FastMCP server assembly: tools + resources + lifecycle."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import Config
from .events import build_summary, get_events as _get_events
from .recording import read_recording_info
from .sessions import SessionsRegistry
from .transcripts import TranscriptsIndex, parse_frontmatter, strip_notes

log = logging.getLogger("clawear_mcp.server")


@dataclass
class ClawEarContext:
    """Shared state: config + sessions registry + FTS index."""
    config: Config
    registry: SessionsRegistry
    index: TranscriptsIndex


class _Server:
    """Holds the FastMCP app plus a `name→callable` map for in-process testing."""

    def __init__(self, mcp: FastMCP, tool_impls: dict[str, Any], context: ClawEarContext):
        self.mcp = mcp
        self.tool_impls = tool_impls
        self.context = context


def _ensure_subdirs(cfg: Config) -> None:
    for p in (cfg.transcripts_dir, cfg.recordings_dir, cfg.events_dir):
        p.mkdir(parents=True, exist_ok=True)


def _refresh_and_sync(ctx: ClawEarContext) -> None:
    """Refresh the sessions registry and sync dirty entries into the FTS index."""
    changes = ctx.registry.refresh()
    for sid in changes["removed"]:
        ctx.index.delete(sid)
    for sid in changes["added"] + changes["modified"]:
        entry = ctx.registry.get(sid)
        try:
            md = entry.transcript_path.read_text()
        except FileNotFoundError:
            # File vanished between scandir and read (e.g. concurrent `ear`
            # cleanup). Drop from registry + FTS so the next refresh can
            # re-discover it or leave it evicted.
            ctx.registry._entries.pop(sid, None)
            ctx.index.delete(sid)
            continue
        fm, body = parse_frontmatter(md)
        entry.started_at = fm.get("started_at", "")
        indexable = strip_notes(body)
        ctx.index.upsert(sid, entry.started_at, indexable)


def _session_not_found_error(ctx: ClawEarContext, session_id: str) -> ValueError:
    nearest = ctx.registry.nearest(session_id)
    hint = f"nearest: {nearest}" if nearest else "no sessions indexed"
    return ValueError(f"session '{session_id}' not found. {hint}")


def _session_summary(ctx: ClawEarContext, entry) -> dict:
    """Compute the SessionSummary shape for list_sessions and get_session."""
    duration_s = 0.0
    if entry.wav_path is not None:
        duration_s = read_recording_info(entry.wav_path, session_id=entry.session_id)["duration_s"]
    return {
        "session_id": entry.session_id,
        "started_at": entry.started_at,
        "duration_s": duration_s,
        "transcript_size": entry.transcript_path.stat().st_size,
        "event_count": entry.event_count,
        "has_recording": entry.has_recording,
    }


def build_server(cfg: Config) -> _Server:
    _ensure_subdirs(cfg)
    registry = SessionsRegistry(data_root=cfg.data_root)
    index = TranscriptsIndex(cfg.index_path)
    index.ensure_schema()
    ctx = ClawEarContext(config=cfg, registry=registry, index=index)

    # Initial scan + sync
    _refresh_and_sync(ctx)

    mcp = FastMCP("clawear-mcp")
    impls: dict[str, Any] = {}

    # ----- session registry -----

    @mcp.tool()
    def list_sessions(
        since: str | None = None,
        until: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List sessions in descending started_at order, optionally filtered by time.

        `limit` is applied AFTER `since`/`until` filtering — a narrow time window may
        yield fewer than `limit` results.
        """
        _refresh_and_sync(ctx)
        out: list[dict] = []
        for sid in ctx.registry.list_ids():
            entry = ctx.registry.get(sid)
            # Use cached started_at (populated by _refresh_and_sync); falls back
            # to "" for entries that pre-date the refresh. The time filter is
            # applied BEFORE any disk reads.
            started_at = entry.started_at
            if since is not None and started_at < since:
                continue
            if until is not None and started_at >= until:
                continue
            out.append(_session_summary(ctx, entry))
            if len(out) >= limit:
                break
        return out

    impls["list_sessions"] = list_sessions

    @mcp.tool()
    def get_session(session_id: str) -> dict:
        """Return session detail (frontmatter fields + computed stats)."""
        _refresh_and_sync(ctx)
        if not ctx.registry.exists(session_id):
            raise _session_not_found_error(ctx, session_id)
        entry = ctx.registry.get(session_id)
        md = entry.transcript_path.read_text()
        fm, _body = parse_frontmatter(md)

        summary = _session_summary(ctx, entry)
        return {
            **summary,
            "device": fm.get("device"),
            "sample_rate": fm.get("sample_rate"),
            "transcript_path": str(entry.transcript_path),
            "events_path": str(entry.events_path) if entry.events_path else None,
            "audio_path": str(entry.wav_path) if entry.wav_path else None,
            "truncated": fm.get("truncated"),
            "dropped_blocks": fm.get("dropped_blocks"),
        }

    impls["get_session"] = get_session

    # ----- transcripts -----

    @mcp.tool()
    def get_transcript(session_id: str, include_frontmatter: bool = False) -> str:
        """Return the transcript markdown. Frontmatter stripped by default."""
        _refresh_and_sync(ctx)
        if not ctx.registry.exists(session_id):
            raise _session_not_found_error(ctx, session_id)
        md = ctx.registry.get(session_id).transcript_path.read_text()
        if include_frontmatter:
            return md
        _fm, body = parse_frontmatter(md)
        return body

    impls["get_transcript"] = get_transcript

    @mcp.tool()
    def search_transcripts(
        query: str,
        since: str | None = None,
        until: str | None = None,
        limit: int = 10,
        snippet_tokens: int = 32,
    ) -> list[dict]:
        """FTS5 full-text search over transcripts, optionally bounded by time."""
        _refresh_and_sync(ctx)
        return ctx.index.search(
            query=query, since=since, until=until, limit=limit, snippet_tokens=snippet_tokens
        )

    impls["search_transcripts"] = search_transcripts

    # ----- events -----

    @mcp.tool()
    def get_event_summary(session_id: str) -> dict:
        """Return counts_by_type + curated timeline + errors for a session."""
        _refresh_and_sync(ctx)
        if not ctx.registry.exists(session_id):
            raise _session_not_found_error(ctx, session_id)
        entry = ctx.registry.get(session_id)
        if entry.events_path is None or not entry.events_path.exists():
            return {
                "session_id": session_id,
                "total": 0,
                "counts_by_type": {},
                "timeline": [],
                "errors": [],
            }
        return build_summary(entry.events_path, session_id=session_id)

    impls["get_event_summary"] = get_event_summary

    @mcp.tool()
    def get_events(
        session_id: str,
        types: list[str] | None = None,
        item_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict]:
        """Filtered + paginated raw-event read."""
        _refresh_and_sync(ctx)
        if not ctx.registry.exists(session_id):
            raise _session_not_found_error(ctx, session_id)
        entry = ctx.registry.get(session_id)
        if entry.events_path is None or not entry.events_path.exists():
            return []
        return _get_events(
            entry.events_path, types=types, item_id=item_id, limit=limit, offset=offset
        )

    impls["get_events"] = get_events

    # ----- recording -----

    @mcp.tool()
    def get_recording_info(session_id: str) -> dict:
        """Return WAV metadata (duration, rate, channels, size)."""
        _refresh_and_sync(ctx)
        if not ctx.registry.exists(session_id):
            raise _session_not_found_error(ctx, session_id)
        entry = ctx.registry.get(session_id)
        if entry.wav_path is None:
            return {
                "session_id": session_id,
                "path": "",
                "size_bytes": 0,
                "mtime": 0.0,
                "duration_s": 0.0,
                "sample_rate": None,
                "channels": None,
                "bit_depth": None,
                "parse_error": "no recording for this session",
            }
        return read_recording_info(entry.wav_path, session_id=session_id)

    impls["get_recording_info"] = get_recording_info

    # ----- resources -----

    @mcp.resource("clawear://recording/{session_id}", mime_type="audio/wav")
    def recording_resource(session_id: str) -> bytes:
        """Raw PCM WAV bytes for the session's recording."""
        _refresh_and_sync(ctx)
        if not ctx.registry.exists(session_id):
            raise _session_not_found_error(ctx, session_id)
        entry = ctx.registry.get(session_id)
        if entry.wav_path is None:
            raise ValueError(f"no recording for session '{session_id}'")
        return entry.wav_path.read_bytes()

    @mcp.resource("clawear://transcript/{session_id}", mime_type="text/markdown")
    def transcript_resource(session_id: str) -> str:
        """The full transcript markdown file (including frontmatter)."""
        _refresh_and_sync(ctx)
        if not ctx.registry.exists(session_id):
            raise _session_not_found_error(ctx, session_id)
        return ctx.registry.get(session_id).transcript_path.read_text()

    @mcp.resource("clawear://events/{session_id}", mime_type="application/jsonl")
    def events_resource(session_id: str) -> str:
        """Raw OpenAI Realtime JSONL event stream for the session."""
        _refresh_and_sync(ctx)
        if not ctx.registry.exists(session_id):
            raise _session_not_found_error(ctx, session_id)
        entry = ctx.registry.get(session_id)
        if entry.events_path is None or not entry.events_path.exists():
            return ""
        return entry.events_path.read_text()

    return _Server(mcp=mcp, tool_impls=impls, context=ctx)
