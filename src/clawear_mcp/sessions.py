"""Session registry — discovers session triples and tracks mtime for lazy refresh."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SessionEntry:
    session_id: str
    transcript_path: Path
    wav_path: Path | None
    events_path: Path | None
    transcript_mtime: float
    has_recording: bool = field(init=False)
    event_count: int = field(init=False)
    # started_at is populated by server._refresh_and_sync after frontmatter parse.
    # Stored here so list_sessions can filter by time without re-reading every .md.
    started_at: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.has_recording = self.wav_path is not None
        if self.events_path is not None and self.events_path.exists():
            try:
                with self.events_path.open() as f:
                    self.event_count = sum(1 for _ in f)
            except OSError:
                self.event_count = 0
        else:
            self.event_count = 0


class SessionsRegistry:
    """In-memory map of session_id → SessionEntry, refreshed lazily by scandir+mtime.

    Refresh is cheap (one scandir of transcripts/, mtime compare against cache). Callers
    should invoke `refresh()` at the start of any tool that reads session data.
    """

    def __init__(self, data_root: Path) -> None:
        self._root = Path(data_root)
        self._entries: dict[str, SessionEntry] = {}

    def list_ids(self) -> list[str]:
        """Return session_ids sorted by started_at DESC (most recent first).

        Ordering uses the cached `started_at` ISO-8601 string when available
        (populated by server._refresh_and_sync). Empty started_at values sort
        after populated ones. Session IDs without a cached started_at retain
        stem-lexicographic order as a deterministic fallback.
        """
        return sorted(
            self._entries.keys(),
            key=lambda sid: (self._entries[sid].started_at or sid),
            reverse=True,
        )

    def get(self, session_id: str) -> SessionEntry:
        if session_id not in self._entries:
            raise KeyError(session_id)
        return self._entries[session_id]

    def exists(self, session_id: str) -> bool:
        return session_id in self._entries

    def evict(self, session_id: str) -> None:
        """Remove a session entry. Safe to call if the id isn't present."""
        self._entries.pop(session_id, None)

    def nearest(self, session_id: str, n: int = 3) -> list[str]:
        """Prefix-matched suggestions for an unknown session_id."""
        ids = self.list_ids()
        prefix_hits = [s for s in ids if s.startswith(session_id[:10])]
        return prefix_hits[:n] if prefix_hits else ids[:n]

    def refresh(self) -> dict[str, list[str]]:
        """Re-scan transcripts/; return {'added': [...], 'modified': [...], 'removed': [...]}."""
        transcripts_dir = self._root / "transcripts"

        added: list[str] = []
        modified: list[str] = []
        removed: list[str] = []

        on_disk: dict[str, float] = {}
        if transcripts_dir.exists():
            with os.scandir(transcripts_dir) as it:
                for de in it:
                    if not de.is_file() or not de.name.endswith(".md"):
                        continue
                    sid = de.name[:-3]  # strip .md
                    try:
                        on_disk[sid] = de.stat().st_mtime
                    except OSError:
                        # File vanished between scandir and stat, or permission issue.
                        # Skip it — next refresh will try again.
                        continue

        # Additions + modifications
        for sid, mtime in on_disk.items():
            existing = self._entries.get(sid)
            if existing is None:
                self._entries[sid] = self._build_entry(sid, mtime)
                added.append(sid)
            elif mtime > existing.transcript_mtime:
                self._entries[sid] = self._build_entry(sid, mtime)
                modified.append(sid)

        # Removals
        for sid in list(self._entries.keys()):
            if sid not in on_disk:
                del self._entries[sid]
                removed.append(sid)

        return {"added": added, "modified": modified, "removed": removed}

    def _build_entry(self, sid: str, mtime: float) -> SessionEntry:
        wav = self._root / "recordings" / f"{sid}.wav"
        jsonl = self._root / "events" / f"{sid}.jsonl"
        return SessionEntry(
            session_id=sid,
            transcript_path=self._root / "transcripts" / f"{sid}.md",
            wav_path=wav if wav.exists() else None,
            events_path=jsonl if jsonl.exists() else None,
            transcript_mtime=mtime,
        )
