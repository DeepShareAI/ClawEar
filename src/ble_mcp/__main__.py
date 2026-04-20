"""Entry point: runs the MCP server over stdio."""
from __future__ import annotations

from .config import load_config
from .logging_setup import configure_logging
from .manager import BLEManager
from .server import build_server


def main() -> None:
    config = load_config()
    log = configure_logging(config.log_level)
    log.info("ble-mcp starting")

    manager = BLEManager(config=config)
    server = build_server(manager)

    try:
        # FastMCP owns the event loop and stdio transport; it also catches
        # SIGINT/SIGTERM internally and runs the lifespan teardown, which is
        # where we disconnect outstanding BLE clients.
        server.mcp.run()
    finally:
        log.info("ble-mcp exiting")


if __name__ == "__main__":
    main()
