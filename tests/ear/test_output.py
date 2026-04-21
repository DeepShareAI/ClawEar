"""Tests for ear.output."""
from __future__ import annotations

import numpy as np
import pytest

from ear.output import (
    BeepPlayer,
    OutputDeviceNotFoundError,
    _error_buffer,
    _start_buffer,
    _stop_buffer,
    _tone,
    resolve_output_device,
)
from tests.ear.fake_sounddevice import FakeOutputStream


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
    with pytest.raises(OutputDeviceNotFoundError):
        resolve_output_device(devices, default_output=0)


def test_output_default_index_out_of_range_raises():
    devices = [
        {"name": "Built-in Output", "max_input_channels": 0, "max_output_channels": 2},
    ]
    with pytest.raises(OutputDeviceNotFoundError):
        resolve_output_device(devices, default_output=-1)


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


def _make_device(samplerate: float = 48000.0, index: int = 0) -> dict:
    return {
        "name": "Javis BT",
        "max_input_channels": 1,
        "max_output_channels": 2,
        "default_samplerate": samplerate,
        "index": index,
    }


def test_beep_player_opens_output_stream_with_device_samplerate():
    created: list[FakeOutputStream] = []

    def factory(**kwargs) -> FakeOutputStream:
        s = FakeOutputStream(**kwargs)
        created.append(s)
        return s

    dev = _make_device(samplerate=48000.0, index=3)
    player = BeepPlayer(dev, output_stream_factory=factory)
    assert len(created) == 1
    stream = created[0]
    assert stream.samplerate == 48000
    assert stream.channels == 1
    assert stream.dtype == "int16"
    assert stream.device == 3
    assert stream._started is True
    player.close()
    assert stream._closed is True


def test_beep_start_writes_nonempty_pcm():
    created: list[FakeOutputStream] = []

    def factory(**kwargs) -> FakeOutputStream:
        s = FakeOutputStream(**kwargs)
        created.append(s)
        return s

    player = BeepPlayer(_make_device(), output_stream_factory=factory)
    player.beep_start()
    stream = created[0]
    assert len(stream.written) == 1
    buf = stream.written[0]
    assert buf.shape[0] > 0
    assert buf.dtype.name == "int16"


def test_beep_start_duration_approx_120ms():
    created: list[FakeOutputStream] = []

    def factory(**kwargs) -> FakeOutputStream:
        s = FakeOutputStream(**kwargs)
        created.append(s)
        return s

    player = BeepPlayer(_make_device(samplerate=48000.0), output_stream_factory=factory)
    player.beep_start()
    buf = created[0].written[0]
    duration_s = buf.shape[0] / 48000.0
    assert 0.114 <= duration_s <= 0.126  # 120ms ± 5%


def test_beep_error_writes_one_concatenated_buffer():
    created: list[FakeOutputStream] = []

    def factory(**kwargs) -> FakeOutputStream:
        s = FakeOutputStream(**kwargs)
        created.append(s)
        return s

    player = BeepPlayer(_make_device(samplerate=48000.0), output_stream_factory=factory)
    player.beep_error()
    stream = created[0]
    # One write of the full concatenated error buffer — not three separate writes.
    assert len(stream.written) == 1
    buf = stream.written[0]
    expected = int(48000 * 0.06) * 3 + int(48000 * 0.03) * 2
    assert buf.shape[0] == expected


def test_beep_stop_writes_500hz_buffer():
    created: list[FakeOutputStream] = []

    def factory(**kwargs) -> FakeOutputStream:
        s = FakeOutputStream(**kwargs)
        created.append(s)
        return s

    player = BeepPlayer(_make_device(samplerate=48000.0), output_stream_factory=factory)
    player.beep_stop()
    buf = created[0].written[0]
    # 120 ms at 48k.
    assert buf.shape[0] == int(48000 * 0.12)


def test_beep_sample_rate_matches_output_device():
    # Use a 16kHz device — generated buffer must match that rate.
    created: list[FakeOutputStream] = []

    def factory(**kwargs) -> FakeOutputStream:
        s = FakeOutputStream(**kwargs)
        created.append(s)
        return s

    player = BeepPlayer(_make_device(samplerate=16000.0), output_stream_factory=factory)
    player.beep_start()
    buf = created[0].written[0]
    assert buf.shape[0] == int(16000 * 0.12)


def test_beep_write_failure_is_swallowed(caplog):
    def factory(**kwargs) -> FakeOutputStream:
        s = FakeOutputStream(**kwargs)
        s.raise_on_write = RuntimeError("portaudio died")
        return s

    player = BeepPlayer(_make_device(), output_stream_factory=factory)
    # Must NOT raise.
    with caplog.at_level("WARNING", logger="ear.output"):
        player.beep_start()
    assert any("beep failed" in rec.message for rec in caplog.records)


def test_beep_open_failure_is_swallowed(caplog):
    def factory(**kwargs):
        raise RuntimeError("output device gone")

    with caplog.at_level("WARNING", logger="ear.output"):
        player = BeepPlayer(_make_device(), output_stream_factory=factory)
        # Subsequent beep_* calls must be no-ops, no raise.
        player.beep_start()
        player.beep_stop()
        player.beep_error()
        player.close()
    assert any("beep player open failed" in rec.message for rec in caplog.records)


def test_close_on_dead_stream_is_safe(caplog):
    def factory(**kwargs) -> FakeOutputStream:
        s = FakeOutputStream(**kwargs)
        s.raise_on_close = RuntimeError("close after disconnect")
        return s

    player = BeepPlayer(_make_device(), output_stream_factory=factory)
    with caplog.at_level("WARNING", logger="ear.output"):
        # Must NOT raise.
        player.close()
    assert any("beep player close failed" in rec.message for rec in caplog.records)


def test_stop_failure_during_close_is_swallowed(caplog):
    # Primary real-world trigger: Bluetooth device disconnects, PortAudio's
    # stream.stop() raises during shutdown. Must not propagate, and close()
    # must still proceed to stream.close() regardless.
    def factory(**kwargs) -> FakeOutputStream:
        s = FakeOutputStream(**kwargs)
        s.raise_on_start = None
        return s

    player = BeepPlayer(_make_device(), output_stream_factory=factory)
    # Inject post-construction: we need the stream to open cleanly (so beep_start
    # could run successfully), then have stop() raise during close(). Accessing
    # player._stream directly is the cleanest way to reach the FakeOutputStream
    # without a separate post-construction hook on BeepPlayer.
    player._stream.raise_on_stop = RuntimeError("bluetooth gone at stop")
    with caplog.at_level("WARNING", logger="ear.output"):
        player.close()  # Must NOT raise.
    assert any("beep player stop failed" in rec.message for rec in caplog.records)
    # And the _stream sentinel must still be cleared so a subsequent close is a no-op.
    assert player._stream is None


def test_double_close_is_safe():
    def factory(**kwargs) -> FakeOutputStream:
        return FakeOutputStream(**kwargs)

    player = BeepPlayer(_make_device(), output_stream_factory=factory)
    player.close()
    # Second close must be a no-op, never raise.
    player.close()
