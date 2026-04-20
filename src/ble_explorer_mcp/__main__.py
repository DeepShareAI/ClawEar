"""Entry point: runs the MCP server over stdio."""
from __future__ import annotations

import asyncio
import logging
import signal

from .config import load_config
from .logging_setup import configure_logging
from .manager import BLEManager
from .server import build_server


def main() -> None:
    config = load_config()
    log = configure_logging(config.log_level)
    log.info("ble-explorer-mcp starting")

    manager = BLEManager(config=config)
    server = build_server(manager)

    async def _shutdown(signame: str) -> None:
        log.info("received %s, disconnecting clients", signame)
        for addr in list(getattr(manager, "_clients", {}).keys()):
            try:
                await manager.disconnect(addr)
            except Exception as exc:  # noqa: BLE001
                log.warning("disconnect %s failed: %s", addr, exc)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda s=sig: asyncio.create_task(_shutdown(s.name))
        )

    try:
        # FastMCP handles the stdio transport and its own event loop.
        server.mcp.run()
    finally:
        logging.getLogger("ble_explorer_mcp").info("ble-explorer-mcp exiting")


if __name__ == "__main__":
    main()
