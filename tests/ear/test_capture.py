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
        default_index=2,
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
        default_index=2,
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
        default_index=2,
    )
    info = cap.preflight()
    assert info["name"] == "AirPods Pro"
    assert info["sample_rate"] == 16000
    assert info["channels"] == 1


async def test_fatal_status_sets_error_future():
    """A fatal PortAudio status must set capture.error without the test hook."""
    from .fake_sounddevice import make_fatal_status

    cap = Capture(
        device_spec=None,
        queue_max_blocks=100,
        input_stream_factory=InputStream,
        query_fn=query_devices,
        default_index=2,
    )
    cap.start()
    assert cap.error is not None
    assert not cap.error.done()
    cap._stream.push_status(make_fatal_status())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert cap.error.done()
    assert "fatal" in cap.error.result().lower()
    cap.stop()


async def test_recoverable_status_does_not_trip_error():
    """Input overflow alone is recoverable — must NOT set capture.error."""
    from .fake_sounddevice import make_recoverable_status

    cap = Capture(
        device_spec=None,
        queue_max_blocks=100,
        input_stream_factory=InputStream,
        query_fn=query_devices,
        default_index=2,
    )
    cap.start()
    assert cap.error is not None
    cap._stream.push_status(make_recoverable_status())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert not cap.error.done()
    cap.stop()


from ear.capture import _PREFERRED_DEVICE_SUBSTR  # noqa: F401 — used in assertions below


def test_resolve_prefers_javis_when_spec_is_none():
    devices = [
        {"name": "Built-in Microphone", "max_input_channels": 1, "max_output_channels": 0},
        {"name": "Javis BT", "max_input_channels": 1, "max_output_channels": 2},
        {"name": "External USB", "max_input_channels": 1, "max_output_channels": 0},
    ]
    chosen = resolve_device(None, devices, default_input=0)
    assert chosen["name"] == "Javis BT"


def test_resolve_javis_match_is_case_insensitive():
    devices = [
        {"name": "Built-in Microphone", "max_input_channels": 1, "max_output_channels": 0},
        {"name": "javis earbuds", "max_input_channels": 1, "max_output_channels": 2},
    ]
    chosen = resolve_device(None, devices, default_input=0)
    assert chosen["name"] == "javis earbuds"


def test_resolve_falls_back_silently_when_no_javis(capsys):
    devices = [
        {"name": "Built-in Microphone", "max_input_channels": 1, "max_output_channels": 0},
        {"name": "External USB", "max_input_channels": 1, "max_output_channels": 0},
    ]
    chosen = resolve_device(None, devices, default_input=0)
    assert chosen["name"] == "Built-in Microphone"
    captured = capsys.readouterr()
    assert captured.err == ""   # silent fallback — no stderr noise


def test_resolve_explicit_spec_overrides_javis():
    devices = [
        {"name": "Built-in Microphone", "max_input_channels": 1, "max_output_channels": 0},
        {"name": "Javis BT", "max_input_channels": 1, "max_output_channels": 2},
        {"name": "External USB", "max_input_channels": 1, "max_output_channels": 0},
    ]
    chosen = resolve_device("external", devices, default_input=0)
    assert chosen["name"] == "External USB"


def test_resolve_explicit_spec_no_match_still_raises():
    devices = [
        {"name": "Built-in Microphone", "max_input_channels": 1, "max_output_channels": 0},
        {"name": "Javis BT", "max_input_channels": 1, "max_output_channels": 2},
    ]
    with pytest.raises(DeviceNotFoundError):
        resolve_device("nonexistent", devices, default_input=0)


def test_resolve_javis_filters_to_input_channels_only():
    # Javis appears twice — once as input-only, once as output-only.
    # The input resolver must pick the input-capable entry.
    devices = [
        {"name": "Built-in Microphone", "max_input_channels": 1, "max_output_channels": 0},
        {"name": "Javis BT (Output)", "max_input_channels": 0, "max_output_channels": 2},
        {"name": "Javis BT (Input)",  "max_input_channels": 1, "max_output_channels": 0},
    ]
    chosen = resolve_device(None, devices, default_input=0)
    assert chosen["name"] == "Javis BT (Input)"


def test_preferred_device_substring_constant_is_lowercase_javis():
    assert _PREFERRED_DEVICE_SUBSTR == "javis"
