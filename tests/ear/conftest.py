"""Shared fixtures for ear tests."""
from __future__ import annotations

import pytest

from .fake_sounddevice import FakeDeviceInfo, set_devices


@pytest.fixture(autouse=True)
def _default_fake_devices():
    """Install a common device list for every test; individual tests can override."""
    set_devices(
        [
            FakeDeviceInfo(
                name="Built-in Microphone",
                max_input_channels=1,
                default_samplerate=48000.0,
            ),
            FakeDeviceInfo(
                name="AirPods Pro",
                max_input_channels=1,
                default_samplerate=16000.0,
            ),
        ],
        default_input=1,  # AirPods is the default.
    )
