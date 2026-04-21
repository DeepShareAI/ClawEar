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


import numpy as np
from ear.output import _tone, _start_buffer, _stop_buffer, _error_buffer


def test_tone_returns_int16_array():
    buf = _tone(frequency=700, duration_s=0.1, samplerate=48000)
    assert buf.dtype == np.int16


def test_tone_length_matches_samplerate_and_duration():
    sr = 48000
    duration = 0.12
    buf = _tone(frequency=700, duration_s=duration, samplerate=sr)
    expected = int(sr * duration)
    assert buf.shape == (expected,)


def test_tone_peak_amplitude_matches_spec():
    # Spec §3.3: amplitude 0.2 of int16 full-scale (~6553).
    buf = _tone(frequency=700, duration_s=0.1, samplerate=48000, amplitude=0.2)
    peak = int(np.max(np.abs(buf)))
    # Allow +/-1 for rounding at discrete sample points.
    assert 6552 <= peak <= 6554


def test_start_buffer_is_700hz_120ms():
    sr = 48000
    buf = _start_buffer(sr)
    assert buf.dtype == np.int16
    assert buf.shape == (int(sr * 0.12),)


def test_stop_buffer_is_500hz_120ms():
    sr = 48000
    buf = _stop_buffer(sr)
    assert buf.dtype == np.int16
    assert buf.shape == (int(sr * 0.12),)


def test_error_buffer_is_three_pulses():
    # Three 60ms pulses + two 30ms gaps = 240ms total.
    sr = 48000
    buf = _error_buffer(sr)
    assert buf.dtype == np.int16
    expected_total = int(sr * 0.06) * 3 + int(sr * 0.03) * 2
    assert buf.shape == (expected_total,)
    # First peak of 800 Hz at 48 kHz lands at sample 15 (quarter-period).
    # int(sr * 0.03) = 1440 = 24 complete cycles → zero crossing for 800 Hz,
    # so we probe at sample 15 instead.
    assert abs(int(buf[15])) > 1000
    # Middle of first gap should be silent.
    mid_gap = int(sr * 0.06) + int(sr * 0.015)
    assert buf[mid_gap] == 0


def test_tone_sample_rate_scales_array_length():
    # Same 100ms tone at two different rates should have proportional lengths.
    buf_16k = _tone(frequency=700, duration_s=0.1, samplerate=16000)
    buf_48k = _tone(frequency=700, duration_s=0.1, samplerate=48000)
    assert buf_48k.shape[0] == 3 * buf_16k.shape[0]
