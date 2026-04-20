"""In-memory fakes for bleak's scanner and client.

Only the subset used by BLEManager is implemented.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class FakeAdvertisementData:
    local_name: str | None = None
    service_uuids: list[str] = field(default_factory=list)
    manufacturer_data: dict[int, bytes] = field(default_factory=dict)
    rssi: int = -60


@dataclass
class FakeBLEDevice:
    address: str
    name: str | None = None


class FakeBleakScanner:
    """Mimics bleak.BleakScanner.discover(return_adv=True)."""

    def __init__(self, devices: list[tuple[FakeBLEDevice, FakeAdvertisementData]]):
        self._devices = devices

    async def discover(
        self, timeout: float = 5.0, return_adv: bool = True
    ) -> dict[str, tuple[FakeBLEDevice, FakeAdvertisementData]]:
        await asyncio.sleep(0)
        return {dev.address: (dev, adv) for dev, adv in self._devices}


class FakeCharacteristic:
    def __init__(self, uuid: str, properties: list[str]):
        self.uuid = uuid
        self.properties = properties


class FakeService:
    def __init__(self, uuid: str, characteristics: list[FakeCharacteristic]):
        self.uuid = uuid
        self.characteristics = characteristics


class FakeBleakClient:
    """Mimics the handful of bleak.BleakClient methods BLEManager touches."""

    def __init__(
        self,
        address: str,
        services: list[FakeService] | None = None,
        read_values: dict[str, bytes] | None = None,
    ):
        self.address = address
        self._services = services or []
        self._read_values = read_values or {}
        self._connected = False
        self._notify_callbacks: dict[str, Callable[[int, bytearray], None]] = {}
        self.written: list[tuple[str, bytes, bool]] = []

    async def connect(self, timeout: float = 10.0) -> bool:
        await asyncio.sleep(0)
        self._connected = True
        return True

    async def disconnect(self) -> bool:
        await asyncio.sleep(0)
        self._connected = False
        return True

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def services(self) -> list[FakeService]:
        return self._services

    async def read_gatt_char(self, uuid: str) -> bytearray:
        await asyncio.sleep(0)
        return bytearray(self._read_values.get(uuid, b""))

    async def write_gatt_char(
        self, uuid: str, data: bytes, response: bool = True
    ) -> None:
        await asyncio.sleep(0)
        self.written.append((uuid, bytes(data), response))

    async def start_notify(
        self, uuid: str, callback: Callable[[int, bytearray], None]
    ) -> None:
        await asyncio.sleep(0)
        self._notify_callbacks[uuid] = callback

    async def stop_notify(self, uuid: str) -> None:
        await asyncio.sleep(0)
        self._notify_callbacks.pop(uuid, None)

    # Test-only helper.
    def push_notification(self, uuid: str, data: bytes) -> None:
        cb = self._notify_callbacks[uuid]
        cb(0, bytearray(data))
