import pytest

from .fake_bleak import (
    FakeAdvertisementData,
    FakeBleakClient,
    FakeBleakScanner,
    FakeBLEDevice,
    FakeCharacteristic,
    FakeService,
)


@pytest.fixture
def sample_scanner() -> FakeBleakScanner:
    return FakeBleakScanner(
        [
            (FakeBLEDevice("AA:BB:CC:DD:EE:01", "HRM-1"),
             FakeAdvertisementData(local_name="HRM-1", rssi=-50)),
            (FakeBLEDevice("AA:BB:CC:DD:EE:02", None),
             FakeAdvertisementData(local_name=None, rssi=-80)),
        ]
    )


@pytest.fixture
def sample_client() -> FakeBleakClient:
    svc = FakeService(
        "0000180d-0000-1000-8000-00805f9b34fb",
        [
            FakeCharacteristic(
                "00002a37-0000-1000-8000-00805f9b34fb",
                ["read", "notify"],
            ),
            FakeCharacteristic(
                "00002a38-0000-1000-8000-00805f9b34fb",
                ["read"],
            ),
        ],
    )
    return FakeBleakClient(
        "AA:BB:CC:DD:EE:01",
        services=[svc],
        read_values={"00002a38-0000-1000-8000-00805f9b34fb": b"\x01"},
    )
