"""MCP tool surface. Thin wrappers around BLEManager."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from mcp.server.fastmcp import FastMCP

from .manager import BLEManager


class _Server:
    """Holds the FastMCP app plus a name→callable map for in-process tests."""

    def __init__(self, mcp: FastMCP, tool_impls: dict[str, Any]):
        self.mcp = mcp
        self.tool_impls = tool_impls


def build_server(manager: BLEManager) -> _Server:
    mcp = FastMCP("ble-explorer")
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

    return _Server(mcp=mcp, tool_impls=impls)
