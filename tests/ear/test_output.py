"""Tests for ear.output."""
from __future__ import annotations

import pytest

from ear.output import resolve_output_device


def test_output_prefers_javis():
    devices = [
        {"name": "Built-in Output", "max_input_channels": 0, "max_output_channels": 2},
        {"name": "Javis BT",        "max_input_channels": 1, "max_output_channels": 2},
    ]
    chosen = resolve_output_device(devices, default_output=0)
    assert chosen["name"] == "Javis BT"


def test_output_filters_input_only_devices():
    # Javis has an entry with no output channels — must be skipped.
    devices = [
        {"name": "Built-in Output",     "max_input_channels": 0, "max_output_channels": 2},
        {"name": "Javis Input (no spk)","max_input_channels": 1, "max_output_channels": 0},
        {"name": "Javis BT",            "max_input_channels": 1, "max_output_channels": 2},
    ]
    chosen = resolve_output_device(devices, default_output=0)
    assert chosen["name"] == "Javis BT"


def test_output_falls_back_to_default():
    devices = [
        {"name": "Built-in Output", "max_input_channels": 0, "max_output_channels": 2},
        {"name": "External USB",    "max_input_channels": 0, "max_output_channels": 2},
    ]
    chosen = resolve_output_device(devices, default_output=0)
    assert chosen["name"] == "Built-in Output"


def test_output_fallback_silent(capsys):
    devices = [
        {"name": "Built-in Output", "max_input_channels": 0, "max_output_channels": 2},
    ]
    resolve_output_device(devices, default_output=0)
    captured = capsys.readouterr()
    assert captured.err == ""


def test_output_default_has_no_output_channels_raises():
    devices = [
        {"name": "Built-in Microphone", "max_input_channels": 1, "max_output_channels": 0},
    ]
    from ear.output import OutputDeviceNotFoundError
    with pytest.raises(OutputDeviceNotFoundError):
        resolve_output_device(devices, default_output=0)


def test_output_default_index_out_of_range_raises():
    devices = [
        {"name": "Built-in Output", "max_input_channels": 0, "max_output_channels": 2},
    ]
    from ear.output import OutputDeviceNotFoundError
    with pytest.raises(OutputDeviceNotFoundError):
        resolve_output_device(devices, default_output=-1)
