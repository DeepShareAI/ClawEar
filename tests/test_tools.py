from ble_explorer_mcp.config import Config
from ble_explorer_mcp.manager import BLEManager
from ble_explorer_mcp.server import build_server


def _mgr(scanner, client):
    return BLEManager(
        config=Config(),
        scanner_factory=lambda: scanner,
        client_factory=lambda address: client,
    )


async def test_tool_ble_scan(sample_scanner):
    mgr = _mgr(sample_scanner, None)
    server = build_server(mgr)
    tool = server.tool_impls["ble_scan"]
    result = await tool(duration_s=1)
    assert len(result) == 2


async def test_tool_ble_last_scan(sample_scanner):
    mgr = _mgr(sample_scanner, None)
    server = build_server(mgr)
    await server.tool_impls["ble_scan"](duration_s=1)
    result = server.tool_impls["ble_last_scan"]()
    assert len(result) == 2
