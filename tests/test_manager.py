import pytest

from ble_mcp.config import Config
from ble_mcp.manager import BLEManager, ScanInFlightError


async def test_scan_returns_devices(sample_scanner):
    mgr = BLEManager(
        config=Config(),
        scanner_factory=lambda: sample_scanner,
        client_factory=lambda address: None,
    )
    results = await mgr.scan(duration_s=1)
    assert len(results) == 2
    assert results[0]["address"] == "AA:BB:CC:DD:EE:01"
    assert results[0]["name"] == "HRM-1"
    assert results[0]["rssi"] == -50


async def test_scan_name_filter(sample_scanner):
    mgr = BLEManager(
        config=Config(),
        scanner_factory=lambda: sample_scanner,
        client_factory=lambda address: None,
    )
    results = await mgr.scan(duration_s=1, name_filter="HRM")
    assert len(results) == 1
    assert results[0]["name"] == "HRM-1"


async def test_scan_rssi_min(sample_scanner):
    mgr = BLEManager(
        config=Config(),
        scanner_factory=lambda: sample_scanner,
        client_factory=lambda address: None,
    )
    results = await mgr.scan(duration_s=1, rssi_min=-60)
    assert len(results) == 1
    assert results[0]["address"] == "AA:BB:CC:DD:EE:01"


async def test_scan_duration_clamped(sample_scanner):
    mgr = BLEManager(
        config=Config(scan_max_seconds=10),
        scanner_factory=lambda: sample_scanner,
        client_factory=lambda address: None,
    )
    # duration above max is silently clamped.
    results = await mgr.scan(duration_s=9999)
    assert len(results) == 2


async def test_last_scan_returns_cache(sample_scanner):
    mgr = BLEManager(
        config=Config(),
        scanner_factory=lambda: sample_scanner,
        client_factory=lambda address: None,
    )
    await mgr.scan(duration_s=1)
    cached = mgr.last_scan()
    assert len(cached) == 2


async def test_last_scan_empty_before_any_scan():
    mgr = BLEManager(
        config=Config(),
        scanner_factory=lambda: None,
        client_factory=lambda address: None,
    )
    assert mgr.last_scan() == []


async def test_concurrent_scan_raises():
    import asyncio

    from .fake_bleak import FakeBleakScanner

    # Slow scanner so the second scan observes in-flight state deterministically.
    slow_scanner = FakeBleakScanner(devices=[], delay_s=0.05)
    mgr = BLEManager(
        config=Config(),
        scanner_factory=lambda: slow_scanner,
        client_factory=lambda address: None,
    )
    t1 = asyncio.create_task(mgr.scan(duration_s=1))
    # Yield so t1 enters the critical section.
    await asyncio.sleep(0.01)
    with pytest.raises(ScanInFlightError):
        await mgr.scan(duration_s=1)
    await t1


async def test_connect_returns_service_tree(sample_client):
    mgr = BLEManager(
        config=Config(),
        scanner_factory=lambda: None,
        client_factory=lambda address: sample_client,
    )
    tree = await mgr.connect("AA:BB:CC:DD:EE:01")
    assert tree["address"] == "AA:BB:CC:DD:EE:01"
    assert len(tree["services"]) == 1
    assert len(tree["services"][0]["characteristics"]) == 2
    chars = {c["uuid"] for c in tree["services"][0]["characteristics"]}
    assert "00002a37-0000-1000-8000-00805f9b34fb" in chars


async def test_connect_twice_is_idempotent(sample_client):
    mgr = BLEManager(
        config=Config(),
        scanner_factory=lambda: None,
        client_factory=lambda address: sample_client,
    )
    await mgr.connect("AA:BB:CC:DD:EE:01")
    # Second connect returns the cached tree, does not reconnect.
    await mgr.connect("AA:BB:CC:DD:EE:01")
    assert len(mgr.list_connections()) == 1


async def test_max_connections_enforced(sample_client):
    from ble_mcp.manager import ConnectionLimitError

    mgr = BLEManager(
        config=Config(max_connections=1),
        scanner_factory=lambda: None,
        client_factory=lambda address: sample_client,
    )
    await mgr.connect("AA:BB:CC:DD:EE:01")
    with pytest.raises(ConnectionLimitError):
        await mgr.connect("AA:BB:CC:DD:EE:99")


async def test_disconnect(sample_client):
    mgr = BLEManager(
        config=Config(),
        scanner_factory=lambda: None,
        client_factory=lambda address: sample_client,
    )
    await mgr.connect("AA:BB:CC:DD:EE:01")
    result = await mgr.disconnect("AA:BB:CC:DD:EE:01")
    assert result["disconnected"] is True
    assert mgr.list_connections() == []


async def test_list_connections_shape(sample_client):
    mgr = BLEManager(
        config=Config(),
        scanner_factory=lambda: None,
        client_factory=lambda address: sample_client,
    )
    await mgr.connect("AA:BB:CC:DD:EE:01")
    infos = mgr.list_connections()
    assert infos[0]["address"] == "AA:BB:CC:DD:EE:01"
    assert infos[0]["services_count"] == 1


async def test_read_returns_decoded(sample_client):
    mgr = BLEManager(
        config=Config(),
        scanner_factory=lambda: None,
        client_factory=lambda address: sample_client,
    )
    await mgr.connect("AA:BB:CC:DD:EE:01")
    r = await mgr.read(
        "AA:BB:CC:DD:EE:01", "00002a38-0000-1000-8000-00805f9b34fb"
    )
    assert r["hex"] == "01"
    assert r["int_le_or_none"] == 1
    assert r["length"] == 1


async def test_read_raises_when_not_connected():
    from ble_mcp.manager import NotConnectedError

    mgr = BLEManager(
        config=Config(),
        scanner_factory=lambda: None,
        client_factory=lambda address: None,
    )
    with pytest.raises(NotConnectedError):
        await mgr.read("AA:BB:CC:DD:EE:01", "00002a38-0000-1000-8000-00805f9b34fb")


async def test_write_requires_confirm(sample_client):
    from ble_mcp.manager import WriteNotConfirmedError

    mgr = BLEManager(
        config=Config(),
        scanner_factory=lambda: None,
        client_factory=lambda address: sample_client,
    )
    await mgr.connect("AA:BB:CC:DD:EE:01")
    with pytest.raises(WriteNotConfirmedError):
        await mgr.write(
            "AA:BB:CC:DD:EE:01",
            "00002a38-0000-1000-8000-00805f9b34fb",
            "01",
            response=True,
            confirm=False,
        )


async def test_write_with_confirm_succeeds(sample_client):
    mgr = BLEManager(
        config=Config(),
        scanner_factory=lambda: None,
        client_factory=lambda address: sample_client,
    )
    await mgr.connect("AA:BB:CC:DD:EE:01")
    r = await mgr.write(
        "AA:BB:CC:DD:EE:01",
        "00002a38-0000-1000-8000-00805f9b34fb",
        "deadbeef",
        response=True,
        confirm=True,
    )
    assert r["bytes_written"] == 4
    assert sample_client.written[-1][1] == b"\xde\xad\xbe\xef"


async def test_write_allowlist_bypasses_confirm(sample_client):
    cfg = Config(
        write_allowlist=["00002a38-0000-1000-8000-00805f9b34fb"]
    )
    mgr = BLEManager(
        config=cfg,
        scanner_factory=lambda: None,
        client_factory=lambda address: sample_client,
    )
    await mgr.connect("AA:BB:CC:DD:EE:01")
    r = await mgr.write(
        "AA:BB:CC:DD:EE:01",
        "00002a38-0000-1000-8000-00805f9b34fb",
        "aa",
        response=False,
        confirm=False,
    )
    assert r["bytes_written"] == 1


async def test_write_rejects_malformed_hex(sample_client):
    mgr = BLEManager(
        config=Config(),
        scanner_factory=lambda: None,
        client_factory=lambda address: sample_client,
    )
    await mgr.connect("AA:BB:CC:DD:EE:01")
    with pytest.raises(ValueError, match="data_hex must be a valid hex string"):
        await mgr.write(
            "AA:BB:CC:DD:EE:01",
            "00002a38-0000-1000-8000-00805f9b34fb",
            "zz",
            confirm=True,
        )


async def test_subscribe_captures_notifications(sample_client):
    mgr = BLEManager(
        config=Config(),
        scanner_factory=lambda: None,
        client_factory=lambda address: sample_client,
    )
    await mgr.connect("AA:BB:CC:DD:EE:01")
    await mgr.subscribe(
        "AA:BB:CC:DD:EE:01", "00002a37-0000-1000-8000-00805f9b34fb"
    )
    # Fire two notifications through the fake.
    sample_client.push_notification(
        "00002a37-0000-1000-8000-00805f9b34fb", b"\x01\x50"
    )
    sample_client.push_notification(
        "00002a37-0000-1000-8000-00805f9b34fb", b"\x01\x55"
    )
    events = mgr.pull_notifications()
    assert len(events) == 2
    assert events[0]["hex"] == "0150"
    assert events[1]["hex"] == "0155"


async def test_unsubscribe_stops_buffering(sample_client):
    mgr = BLEManager(
        config=Config(),
        scanner_factory=lambda: None,
        client_factory=lambda address: sample_client,
    )
    await mgr.connect("AA:BB:CC:DD:EE:01")
    await mgr.subscribe(
        "AA:BB:CC:DD:EE:01", "00002a37-0000-1000-8000-00805f9b34fb"
    )
    await mgr.unsubscribe(
        "AA:BB:CC:DD:EE:01", "00002a37-0000-1000-8000-00805f9b34fb"
    )
    # After unsubscribe, pushing would not be received (fake removes cb).
    assert (
        "00002a37-0000-1000-8000-00805f9b34fb"
        not in sample_client._notify_callbacks
    )


async def test_pull_notifications_filter_by_address(sample_client):
    mgr = BLEManager(
        config=Config(),
        scanner_factory=lambda: None,
        client_factory=lambda address: sample_client,
    )
    await mgr.connect("AA:BB:CC:DD:EE:01")
    await mgr.subscribe(
        "AA:BB:CC:DD:EE:01", "00002a37-0000-1000-8000-00805f9b34fb"
    )
    sample_client.push_notification(
        "00002a37-0000-1000-8000-00805f9b34fb", b"\x00"
    )
    events = mgr.pull_notifications(address="OTHER")
    assert events == []
    events = mgr.pull_notifications(address="AA:BB:CC:DD:EE:01")
    assert len(events) == 1


async def test_notification_buffer_bounded(sample_client):
    mgr = BLEManager(
        config=Config(notification_buffer_size=3),
        scanner_factory=lambda: None,
        client_factory=lambda address: sample_client,
    )
    await mgr.connect("AA:BB:CC:DD:EE:01")
    await mgr.subscribe(
        "AA:BB:CC:DD:EE:01", "00002a37-0000-1000-8000-00805f9b34fb"
    )
    for i in range(5):
        sample_client.push_notification(
            "00002a37-0000-1000-8000-00805f9b34fb", bytes([i])
        )
    events = mgr.pull_notifications()
    # Oldest two dropped, keeps last 3.
    assert [e["hex"] for e in events] == ["02", "03", "04"]
