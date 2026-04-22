"""Entry point: `clawear-mcp` script target and `python -m clawear_mcp`."""
from __future__ import annotations

import logging
import sys

from .config import load_config
from .server import build_server
from .transcripts import FTS5NotAvailable


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    log = logging.getLogger("clawear_mcp")

    cfg = load_config()

    if not cfg.data_root.exists():
        print(
            f"error: CLAWEAR_DATA_ROOT directory does not exist: {cfg.data_root}",
            file=sys.stderr,
        )
        return 1

    try:
        srv = build_server(cfg)
    except FTS5NotAvailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    log.info("clawear-mcp ready: data_root=%s", cfg.data_root)
    srv.mcp.run()  # stdio transport
    return 0


if __name__ == "__main__":
    sys.exit(main())
