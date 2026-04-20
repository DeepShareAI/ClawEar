"""BLEManager: single owner of all BLE state (scanner, clients, buffers)."""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable

from .config import Config
from .decode import decode_bytes

log = logging.getLogger("ble_explorer_mcp.manager")


class ScanInFlightError(RuntimeError):
    """A scan is already running; wait for it to finish."""


class ConnectionLimitError(RuntimeError):
    """Attempted to exceed max_connections."""


class NotConnectedError(RuntimeError):
    """No active connection for the given address."""


class WriteNotConfirmedError(RuntimeError):
    """Write attempted without confirm=True on a non-allowlisted characteristic."""


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
        self._notifications: deque = deque(
            maxlen=self._config.notification_buffer_size
        )

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

    async def connect(self, address: str, timeout_s: int = 10) -> dict:
        if not hasattr(self, "_clients"):
            self._clients: dict[str, Any] = {}
            self._service_trees: dict[str, dict] = {}
        if address in self._clients:
            return self._service_trees[address]
        if len(self._clients) >= self._config.max_connections:
            raise ConnectionLimitError(
                f"max_connections ({self._config.max_connections}) reached"
            )
        client = self._client_factory(address)
        await client.connect(timeout=timeout_s)
        tree = _build_service_tree(address, client.services)
        self._clients[address] = client
        self._service_trees[address] = tree
        log.info("connect address=%s services=%d", address, len(tree["services"]))
        return tree

    async def disconnect(self, address: str) -> dict:
        clients = getattr(self, "_clients", {})
        if address not in clients:
            raise NotConnectedError(address)
        client = clients.pop(address)
        getattr(self, "_service_trees", {}).pop(address, None)
        await client.disconnect()
        log.info("disconnect address=%s", address)
        return {"address": address, "disconnected": True}

    def list_connections(self) -> list[dict]:
        trees = getattr(self, "_service_trees", {})
        return [
            {
                "address": addr,
                "name": None,
                "services_count": len(tree["services"]),
            }
            for addr, tree in trees.items()
        ]

    def _require_client(self, address: str):
        clients = getattr(self, "_clients", {})
        if address not in clients:
            raise NotConnectedError(address)
        return clients[address]

    async def read(self, address: str, characteristic_uuid: str) -> dict:
        client = self._require_client(address)
        raw = await client.read_gatt_char(characteristic_uuid)
        log.info(
            "read address=%s char=%s bytes=%d",
            address, characteristic_uuid, len(raw),
        )
        return decode_bytes(bytes(raw))

    async def write(
        self,
        address: str,
        characteristic_uuid: str,
        data_hex: str,
        response: bool = True,
        confirm: bool = False,
    ) -> dict:
        client = self._require_client(address)
        uuid_lower = characteristic_uuid.lower()
        if not confirm and uuid_lower not in self._config.write_allowlist:
            raise WriteNotConfirmedError(
                f"Write to {characteristic_uuid} requires confirm=True or allowlist entry."
            )
        data = bytes.fromhex(data_hex)
        await client.write_gatt_char(characteristic_uuid, data, response=response)
        log.info(
            "write address=%s char=%s bytes=%d response=%s",
            address, characteristic_uuid, len(data), response,
        )
        return {"bytes_written": len(data)}

    async def subscribe(self, address: str, characteristic_uuid: str) -> dict:
        client = self._require_client(address)

        def _callback(_handle: int, data: bytearray) -> None:
            self._notifications.append(
                {
                    "address": address,
                    "characteristic_uuid": characteristic_uuid,
                    "hex": bytes(data).hex(),
                    "ts": datetime.now(timezone.utc),
                }
            )

        await client.start_notify(characteristic_uuid, _callback)
        log.info("subscribe address=%s char=%s", address, characteristic_uuid)
        return {"subscribed": True}

    async def unsubscribe(self, address: str, characteristic_uuid: str) -> dict:
        client = self._require_client(address)
        await client.stop_notify(characteristic_uuid)
        log.info("unsubscribe address=%s char=%s", address, characteristic_uuid)
        return {"subscribed": False}

    def pull_notifications(
        self,
        address: str | None = None,
        since: datetime | None = None,
        limit: int = 200,
    ) -> list[dict]:
        events = list(self._notifications)
        if address is not None:
            events = [e for e in events if e["address"] == address]
        if since is not None:
            events = [e for e in events if e["ts"] > since]
        return events[-limit:]


def _build_service_tree(address: str, services) -> dict:
    out_services = []
    for svc in services:
        out_services.append(
            {
                "uuid": svc.uuid,
                "characteristics": [
                    {"uuid": ch.uuid, "properties": list(ch.properties)}
                    for ch in svc.characteristics
                ],
            }
        )
    return {"address": address, "services": out_services}


def _default_scanner_factory():
    from bleak import BleakScanner

    return BleakScanner()


def _default_client_factory(address: str):
    from bleak import BleakClient

    return BleakClient(address)
