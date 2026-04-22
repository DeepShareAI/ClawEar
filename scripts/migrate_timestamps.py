"""One-shot migration: rename ClawEar sessions from UTC stems to local-time stems.

Old stem: 2026-04-21T04-12-39Z   (UTC, single filename-safe form)
New stem: 2026-04-21_12-12-39    (local time, e.g. UTC+08:00)

Also rewrites frontmatter fields `session_id`, `started_at`, `audio_path`,
`events_path` to match. Idempotent: already-migrated sessions are detected
(new stem format in filename AND frontmatter has explicit offset) and skipped.

Usage:
    python -m scripts.migrate_timestamps [--data-root PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Old format: 2026-04-21T04-12-39Z
_OLD_STEM_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})Z$")
# New format: 2026-04-21_04-12-39
_NEW_STEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$")


@dataclass
class MigrationResult:
    migrated: int = 0
    skipped: int = 0
    errors: list[str] = None
    plan: list[dict] = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []
        if self.plan is None:
            self.plan = []

    def as_dict(self) -> dict:
        return {
            "migrated": self.migrated,
            "skipped": self.skipped,
            "errors": self.errors,
            "plan": self.plan,
        }


def _old_stem_to_local(old_stem: str) -> tuple[str, str] | None:
    """Convert `2026-04-21T04-12-39Z` → (new_stem, iso_started_at) using local TZ.

    Returns None if the input doesn't match the old format.
    """
    m = _OLD_STEM_RE.match(old_stem)
    if not m:
        return None
    date, hh, mm, ss = m.groups()
    # Parse as UTC, convert to local
    utc_dt = datetime.fromisoformat(f"{date}T{hh}:{mm}:{ss}+00:00")
    local_dt = utc_dt.astimezone()
    new_stem = local_dt.strftime("%Y-%m-%d_%H-%M-%S")
    iso_started_at = local_dt.isoformat(timespec="seconds")
    return new_stem, iso_started_at


def _rewrite_frontmatter(
    md_text: str, new_stem: str, new_started_at: str, data_root: Path
) -> str:
    """Replace session_id, started_at, audio_path, events_path fields in frontmatter."""
    lines = md_text.splitlines(keepends=True)
    out = []
    in_frontmatter = False
    fm_ended = False
    for i, line in enumerate(lines):
        if i == 0 and line.strip() == "---":
            in_frontmatter = True
            out.append(line)
            continue
        if in_frontmatter and not fm_ended and line.strip() == "---":
            fm_ended = True
            out.append(line)
            continue
        if in_frontmatter and not fm_ended:
            if line.startswith("session_id:"):
                out.append(f"session_id: {new_stem}\n")
            elif line.startswith("started_at:"):
                out.append(f"started_at: '{new_started_at}'\n")
            elif line.startswith("audio_path:"):
                out.append(f"audio_path: {data_root}/recordings/{new_stem}.wav\n")
            elif line.startswith("events_path:"):
                out.append(f"events_path: {data_root}/events/{new_stem}.jsonl\n")
            else:
                out.append(line)
        else:
            out.append(line)
    if not fm_ended:
        raise ValueError(
            "no YAML frontmatter found (expected leading '---' block)"
        )
    return "".join(out)


def migrate(data_root: Path, dry_run: bool = False) -> dict:
    """Walk data_root and rename any old-format sessions to the new local-time format.

    Returns {'migrated': N, 'skipped': N, 'errors': [...]}.
    """
    data_root = Path(data_root)
    result = MigrationResult()

    transcripts_dir = data_root / "transcripts"
    recordings_dir = data_root / "recordings"
    events_dir = data_root / "events"

    if not transcripts_dir.exists():
        return result.as_dict()

    for md_path in sorted(transcripts_dir.glob("*.md")):
        stem = md_path.stem
        if _NEW_STEM_RE.match(stem):
            result.skipped += 1
            continue

        converted = _old_stem_to_local(stem)
        if converted is None:
            result.errors.append(f"unrecognized stem: {stem}")
            continue
        new_stem, iso_started_at = converted

        result.plan.append({
            "old_stem": stem,
            "new_stem": new_stem,
            "iso_started_at": iso_started_at,
        })

        if dry_run:
            result.migrated += 1
            continue

        # Rewrite frontmatter with atomic temp-file swap so a mid-write crash
        # cannot leave a partially-written md on disk.
        md_text = md_path.read_text()
        try:
            new_md_text = _rewrite_frontmatter(md_text, new_stem, iso_started_at, data_root)
        except ValueError as exc:
            result.errors.append(f"{md_path.name}: {exc}")
            continue
        tmp_path = md_path.with_suffix(md_path.suffix + ".tmp")
        tmp_path.write_text(new_md_text)
        tmp_path.replace(md_path)

        # Rename the three siblings (whichever exist)
        md_path.rename(transcripts_dir / f"{new_stem}.md")
        wav_old = recordings_dir / f"{stem}.wav"
        if wav_old.exists():
            wav_old.rename(recordings_dir / f"{new_stem}.wav")
        jsonl_old = events_dir / f"{stem}.jsonl"
        if jsonl_old.exists():
            jsonl_old.rename(events_dir / f"{new_stem}.jsonl")

        result.migrated += 1

    return result.as_dict()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ.get("CLAWEAR_DATA_ROOT", Path.home() / "ClawEar")),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"Migrating sessions under {args.data_root} (dry_run={args.dry_run})")
    result = migrate(args.data_root, dry_run=args.dry_run)
    if args.dry_run and result["plan"]:
        print("  would rename:")
        for entry in result["plan"]:
            print(f"    {entry['old_stem']}  →  {entry['new_stem']}  ({entry['iso_started_at']})")
    print(f"  migrated: {result['migrated']}")
    print(f"  skipped (already new format): {result['skipped']}")
    if result["errors"]:
        print("  errors:")
        for e in result["errors"]:
            print(f"    - {e}")
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
