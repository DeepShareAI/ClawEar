"""BLEManager: single owner of all BLE state (scanner, clients, buffers)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from .config import Config

log = logging.getLogger("ble_explorer_mcp.manager")


class ScanInFlightError(RuntimeError):
    """A scan is already running; wait for it to finish."""


class BLEManager:
    def __init__(
        self,
        config: Config,
        scanner_factory: Callable[[], Any] | None = None,
        client_factory: Callable[[str], Any] | None = None,
    ):
        self._config = config
        self._scanner_factory = scanner_factory or _default_scanner_factory
        self._client_factory = client_factory or _default_client_factory
        self._scan_lock = asyncio.Lock()
        self._last_scan: list[dict] = []

    async def scan(
        self,
        duration_s: int,
        name_filter: str | None = None,
        rssi_min: int | None = None,
    ) -> list[dict]:
        if self._scan_lock.locked():
            raise ScanInFlightError("A scan is already in flight.")
        duration = max(1, min(duration_s, self._config.scan_max_seconds))
        async with self._scan_lock:
            scanner = self._scanner_factory()
            discovered = await scanner.discover(timeout=duration, return_adv=True)
            log.info("scan duration=%ss found=%d", duration, len(discovered))

        results: list[dict] = []
        for address, (device, adv) in discovered.items():
            name = getattr(device, "name", None) or getattr(adv, "local_name", None)
            rssi = getattr(adv, "rssi", None)
            if name_filter and (name is None or name_filter not in name):
                continue
            if rssi_min is not None and (rssi is None or rssi < rssi_min):
                continue
            results.append(
                {
                    "address": address,
                    "name": name,
                    "rssi": rssi,
                    "adv_data": {
                        "service_uuids": list(getattr(adv, "service_uuids", []) or []),
                        "manufacturer_data": {
                            str(k): v.hex()
                            for k, v in (
                                getattr(adv, "manufacturer_data", {}) or {}
                            ).items()
                        },
                    },
                }
            )
        self._last_scan = results
        return results

    def last_scan(self) -> list[dict]:
        return list(self._last_scan)


def _default_scanner_factory():
    from bleak import BleakScanner

    return BleakScanner()


def _default_client_factory(address: str):
    from bleak import BleakClient

    return BleakClient(address)
