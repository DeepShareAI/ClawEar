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


async def test_tool_ble_connect(sample_client):
    mgr = _mgr(None, sample_client)
    server = build_server(mgr)
    tree = await server.tool_impls["ble_connect"](address="AA:BB:CC:DD:EE:01")
    assert tree["address"] == "AA:BB:CC:DD:EE:01"
    assert len(tree["services"]) == 1


async def test_tool_ble_disconnect(sample_client):
    mgr = _mgr(None, sample_client)
    server = build_server(mgr)
    await server.tool_impls["ble_connect"](address="AA:BB:CC:DD:EE:01")
    r = await server.tool_impls["ble_disconnect"](address="AA:BB:CC:DD:EE:01")
    assert r["disconnected"] is True


async def test_tool_ble_list_connections(sample_client):
    mgr = _mgr(None, sample_client)
    server = build_server(mgr)
    await server.tool_impls["ble_connect"](address="AA:BB:CC:DD:EE:01")
    infos = server.tool_impls["ble_list_connections"]()
    assert len(infos) == 1


async def test_tool_ble_read(sample_client):
    mgr = _mgr(None, sample_client)
    server = build_server(mgr)
    await server.tool_impls["ble_connect"](address="AA:BB:CC:DD:EE:01")
    r = await server.tool_impls["ble_read"](
        address="AA:BB:CC:DD:EE:01",
        characteristic_uuid="00002a38-0000-1000-8000-00805f9b34fb",
    )
    assert r["hex"] == "01"


async def test_tool_ble_write_requires_confirm(sample_client):
    import pytest
    from ble_explorer_mcp.manager import WriteNotConfirmedError

    mgr = _mgr(None, sample_client)
    server = build_server(mgr)
    await server.tool_impls["ble_connect"](address="AA:BB:CC:DD:EE:01")
    with pytest.raises(WriteNotConfirmedError):
        await server.tool_impls["ble_write"](
            address="AA:BB:CC:DD:EE:01",
            characteristic_uuid="00002a38-0000-1000-8000-00805f9b34fb",
            data_hex="ff",
        )


async def test_tool_ble_write_ok(sample_client):
    mgr = _mgr(None, sample_client)
    server = build_server(mgr)
    await server.tool_impls["ble_connect"](address="AA:BB:CC:DD:EE:01")
    r = await server.tool_impls["ble_write"](
        address="AA:BB:CC:DD:EE:01",
        characteristic_uuid="00002a38-0000-1000-8000-00805f9b34fb",
        data_hex="ff",
        confirm=True,
    )
    assert r["bytes_written"] == 1
