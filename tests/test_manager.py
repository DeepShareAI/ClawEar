import pytest

from ble_explorer_mcp.config import Config
from ble_explorer_mcp.manager import BLEManager, ScanInFlightError


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


async def test_concurrent_scan_raises(sample_scanner):
    import asyncio

    mgr = BLEManager(
        config=Config(),
        scanner_factory=lambda: sample_scanner,
        client_factory=lambda address: None,
    )
    t1 = asyncio.create_task(mgr.scan(duration_s=1))
    # Give t1 a chance to enter the critical section.
    await asyncio.sleep(0)
    with pytest.raises(ScanInFlightError):
        await mgr.scan(duration_s=1)
    await t1
