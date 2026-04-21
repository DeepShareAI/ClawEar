"""Tests for ear.capture."""
from __future__ import annotations

import asyncio

import pytest

from ear.capture import Capture, DeviceNotFoundError, resolve_device
from .fake_sounddevice import FakeDeviceInfo, InputStream, query_devices, default


def _silence(n_samples: int) -> bytes:
    return b"\x00\x00" * n_samples


def test_list_devices_returns_input_only():
    devices = Capture.list_devices(query_fn=query_devices)
    names = [d["name"] for d in devices]
    assert "Built-in Microphone" in names
    assert "AirPods Pro" in names


def test_resolve_device_default_returns_default_input():
    devices = [
        {"name": "Built-in Microphone", "max_input_channels": 1, "default_samplerate": 48000.0},
        {"name": "AirPods Pro", "max_input_channels": 1, "default_samplerate": 16000.0},
    ]
    info = resolve_device(spec=None, devices=devices, default_input=1)
    assert info["name"] == "AirPods Pro"
    assert info["default_samplerate"] == 16000.0


def test_resolve_device_substring_match():
    devices = [
        {"name": "Built-in Microphone", "max_input_channels": 1, "default_samplerate": 48000.0},
        {"name": "AirPods Pro", "max_input_channels": 1, "default_samplerate": 16000.0},
    ]
    info = resolve_device(spec="AirPods", devices=devices, default_input=0)
    assert info["name"] == "AirPods Pro"


def test_resolve_device_no_match_raises():
    devices = [
        {"name": "Built-in Microphone", "max_input_channels": 1, "default_samplerate": 48000.0},
    ]
    with pytest.raises(DeviceNotFoundError):
        resolve_device(spec="Nothing", devices=devices, default_input=0)


async def test_callback_enqueues_blocks_on_asyncio_queue():
    cap = Capture(
        device_spec=None,
        queue_max_blocks=100,
        input_stream_factory=InputStream,
        query_fn=query_devices,
        default_index=1,
    )
    cap.start()
    # Drive the fake: push a block; the fake invokes the callback synchronously
    # on this thread, but Capture still uses loop.call_soon_threadsafe, which
    # schedules the enqueue for the current loop; run_until_idle lets it drain.
    cap._stream.push_block(_silence(320))
    cap._stream.push_block(_silence(320))
    await asyncio.sleep(0)  # let call_soon_threadsafe work flush
    await asyncio.sleep(0)
    assert cap.blocks.qsize() == 2
    cap.stop()


async def test_drop_oldest_on_queue_full():
    cap = Capture(
        device_spec=None,
        queue_max_blocks=2,  # tiny queue
        input_stream_factory=InputStream,
        query_fn=query_devices,
        default_index=1,
    )
    cap.start()
    cap._stream.push_block(_silence(1))  # block "1"
    cap._stream.push_block(_silence(2))  # block "2"
    cap._stream.push_block(_silence(3))  # block "3" → should drop "1"
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert cap.dropped_blocks == 1
    assert cap.blocks.qsize() == 2
    cap.stop()


async def test_preflight_info_has_name_and_rate():
    cap = Capture(
        device_spec="AirPods",
        queue_max_blocks=100,
        input_stream_factory=InputStream,
        query_fn=query_devices,
        default_index=1,
    )
    info = cap.preflight()
    assert info["name"] == "AirPods Pro"
    assert info["sample_rate"] == 16000
    assert info["channels"] == 1
