"""Shared fixtures for ear tests."""
from __future__ import annotations

import pytest

from .fake_sounddevice import FakeDeviceInfo, set_devices

# Device layout installed by the autouse fixture:
#   0 — Built-in Microphone   (input only,   48 kHz)
#   1 — Built-in Output        (output only,  48 kHz) ← default output
#   2 — AirPods Pro            (input+output, 16 kHz) ← default input


@pytest.fixture(autouse=True)
def _default_fake_devices():
    """Install a common device list for every test; individual tests can override."""
    set_devices(
        [
            FakeDeviceInfo(
                name="Built-in Microphone",
                max_input_channels=1,
                max_output_channels=0,
                default_samplerate=48000.0,
            ),
            FakeDeviceInfo(
                name="Built-in Output",
                max_input_channels=0,
                max_output_channels=2,
                default_samplerate=48000.0,
            ),
            FakeDeviceInfo(
                name="AirPods Pro",
                max_input_channels=1,
                max_output_channels=2,
                default_samplerate=16000.0,
            ),
        ],
        default_input=2,   # AirPods
        default_output=1,  # Built-in Output
    )
