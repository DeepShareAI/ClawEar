"""Entry point for the `clawear` CLI."""
from __future__ import annotations

import sys

from .cli import main as _cli_main


def main() -> int:
    rc = _cli_main()
    sys.exit(rc)


if __name__ == "__main__":
    main()
