"""MCP tool surface. Thin wrappers around BLEManager."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from mcp.server.fastmcp import FastMCP

from .manager import BLEManager

log = logging.getLogger("ble_mcp.server")


class _Server:
    """Holds the FastMCP app plus a name→callable map for in-process tests."""

    def __init__(self, mcp: FastMCP, tool_impls: dict[str, Any]):
        self.mcp = mcp
        self.tool_impls = tool_impls


def build_server(manager: BLEManager) -> _Server:
    @asynccontextmanager
    async def _lifespan(_server: FastMCP):
        try:
            yield {}
        finally:
            for addr in list(manager._clients.keys()):
                try:
                    await manager.disconnect(addr)
                except Exception as exc:  # noqa: BLE001
                    log.warning("shutdown: disconnect %s failed: %s", addr, exc)

    mcp = FastMCP("ble-mcp", lifespan=_lifespan)
    impls: dict[str, Any] = {}

    @mcp.tool()
    async def ble_scan(
        duration_s: int = 5,
        name_filter: str | None = None,
        rssi_min: int | None = None,
    ) -> list[dict]:
        """Scan for BLE peripherals. Caps duration per config.scan_max_seconds."""
        return await manager.scan(
            duration_s=duration_s, name_filter=name_filter, rssi_min=rssi_min
        )

    impls["ble_scan"] = ble_scan

    @mcp.tool()
    def ble_last_scan() -> list[dict]:
        """Return the cached result of the most recent scan."""
        return manager.last_scan()

    impls["ble_last_scan"] = ble_last_scan

    @mcp.tool()
    async def ble_connect(address: str, timeout_s: int = 10) -> dict:
        """Connect to a peripheral by address. Returns service tree."""
        return await manager.connect(address=address, timeout_s=timeout_s)

    impls["ble_connect"] = ble_connect

    @mcp.tool()
    async def ble_disconnect(address: str) -> dict:
        """Disconnect from a peripheral."""
        return await manager.disconnect(address=address)

    impls["ble_disconnect"] = ble_disconnect

    @mcp.tool()
    def ble_list_connections() -> list[dict]:
        """List currently-connected peripherals."""
        return manager.list_connections()

    impls["ble_list_connections"] = ble_list_connections

    @mcp.tool()
    async def ble_read(address: str, characteristic_uuid: str) -> dict:
        """Read a characteristic. Returns hex + best-effort utf8/int-le decodings."""
        return await manager.read(
            address=address, characteristic_uuid=characteristic_uuid
        )

    impls["ble_read"] = ble_read

    @mcp.tool()
    async def ble_write(
        address: str,
        characteristic_uuid: str,
        data_hex: str,
        response: bool = True,
        confirm: bool = False,
    ) -> dict:
        """Write bytes (hex) to a characteristic. Requires confirm=True unless allow-listed."""
        return await manager.write(
            address=address,
            characteristic_uuid=characteristic_uuid,
            data_hex=data_hex,
            response=response,
            confirm=confirm,
        )

    impls["ble_write"] = ble_write

    @mcp.tool()
    async def ble_subscribe(address: str, characteristic_uuid: str) -> dict:
        """Enable notifications on a characteristic; events go to the buffer."""
        return await manager.subscribe(
            address=address, characteristic_uuid=characteristic_uuid
        )

    impls["ble_subscribe"] = ble_subscribe

    @mcp.tool()
    async def ble_unsubscribe(address: str, characteristic_uuid: str) -> dict:
        """Disable notifications on a characteristic."""
        return await manager.unsubscribe(
            address=address, characteristic_uuid=characteristic_uuid
        )

    impls["ble_unsubscribe"] = ble_unsubscribe

    @mcp.tool()
    def ble_notifications(
        address: str | None = None,
        since: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        """Pull captured notification events (optionally filter by address/since iso8601)."""
        since_dt: datetime | None = None
        if since is not None:
            since_dt = datetime.fromisoformat(since)
        events = manager.pull_notifications(
            address=address, since=since_dt, limit=limit
        )
        return [
            {**e, "ts": e["ts"].isoformat()}
            for e in events
        ]

    impls["ble_notifications"] = ble_notifications

    return _Server(mcp=mcp, tool_impls=impls)
