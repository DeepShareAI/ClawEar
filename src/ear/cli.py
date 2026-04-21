"""argparse surface for the `clawear` CLI."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from .capture import Capture
from .config import load_config
from .logging_setup import configure_logging
from .session import run


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="clawear", description="ClawEar audio pipeline.")
    sub = p.add_subparsers(dest="command", required=True)

    ps = sub.add_parser("start", help="Start a recording session.")
    ps.add_argument(
        "--device",
        default=None,
        help="Substring match against input device name (default: system default).",
    )
    ps.add_argument(
        "--instructions-file",
        default=None,
        help="Path to a text file whose contents override config.instructions.",
    )
    ps.add_argument(
        "--dry-run",
        action="store_true",
        help="Preflight the device and exit; do not open the WebSocket.",
    )

    sub.add_parser("list-devices", help="List input devices and exit.")

    return p


def _cmd_list_devices() -> int:
    devices = Capture.list_devices()
    for d in devices:
        print(
            f"- {d['name']}  ({int(d['default_samplerate'])} Hz, "
            f"{d['max_input_channels']} ch)"
        )
    return 0


def _cmd_start(args: argparse.Namespace) -> int:
    config = load_config()
    configure_logging(config.log_level)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("error: OPENAI_API_KEY not set in environment", file=sys.stderr)
        return 1

    instructions_override: str | None = None
    if args.instructions_file is not None:
        p = Path(args.instructions_file).expanduser()
        if not p.exists():
            print(f"error: --instructions-file not found: {p}", file=sys.stderr)
            return 1
        instructions_override = p.read_text(encoding="utf-8")

    # JavisContext auto-index warning.
    if str(config.transcripts_dir).endswith("ClawEar/transcripts"):
        print(
            "warning: transcripts_dir is the default (~/ClawEar/transcripts). "
            "JavisContext will only auto-index if this path is inside a "
            "WATCH_DIRECTORIES entry.",
            file=sys.stderr,
        )

    return asyncio.run(
        run(
            config=config,
            api_key=api_key,
            device_spec=args.device,
            instructions_override=instructions_override,
            dry_run=args.dry_run,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "list-devices":
        return _cmd_list_devices()
    if args.command == "start":
        return _cmd_start(args)
    parser.error(f"unknown command: {args.command}")
    return 2
