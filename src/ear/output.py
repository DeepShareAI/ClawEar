"""Output device resolution and lifecycle beep playback.

Mirrors capture.py for the output side. Exposes resolve_output_device
(auto-prefers 'javis' then falls back to system default output) and
BeepPlayer (see subsequent tasks).
"""
from __future__ import annotations

import logging
from typing import Any, Callable

import numpy as np

from .capture import _PREFERRED_DEVICE_SUBSTR

log = logging.getLogger("ear.output")


class OutputDeviceNotFoundError(RuntimeError):
    """No usable output device (preferred substring absent AND no valid default)."""


def resolve_output_device(devices: list[dict], default_output: int) -> dict:
    """Pick an output device.

    Auto-prefer a device whose name contains _PREFERRED_DEVICE_SUBSTR
    (case-insensitive), else fall back to devices[default_output].
    Silent fallback — no stderr warning.
    """
    outputs = [d for d in devices if d.get("max_output_channels", 0) > 0]
    for d in outputs:
        if _PREFERRED_DEVICE_SUBSTR in d["name"].lower():
            return d
    if default_output < 0 or default_output >= len(devices):
        raise OutputDeviceNotFoundError(
            "No default output device available."
        )
    candidate = devices[default_output]
    if candidate.get("max_output_channels", 0) <= 0:
        raise OutputDeviceNotFoundError(
            f"Default output device {candidate['name']!r} has no output channels."
        )
    return candidate


def _tone(
    frequency: float,
    duration_s: float,
    samplerate: int,
    amplitude: float = 0.2,
) -> "np.ndarray":
    """Generate a pure sine tone as int16 mono PCM.

    amplitude is relative to int16 full-scale (1.0 = 32767).
    """
    n = int(samplerate * duration_s)
    t = np.arange(n, dtype=np.float64) / float(samplerate)
    wave = np.sin(2.0 * np.pi * frequency * t)
    peak = int(round(amplitude * 32767))
    return (wave * peak).astype(np.int16)


def _silence(duration_s: float, samplerate: int) -> "np.ndarray":
    return np.zeros(int(samplerate * duration_s), dtype=np.int16)


def _start_buffer(samplerate: int) -> "np.ndarray":
    return _tone(frequency=700.0, duration_s=0.12, samplerate=samplerate)


def _stop_buffer(samplerate: int) -> "np.ndarray":
    return _tone(frequency=500.0, duration_s=0.12, samplerate=samplerate)


def _error_buffer(samplerate: int) -> "np.ndarray":
    pulse = _tone(frequency=800.0, duration_s=0.06, samplerate=samplerate)
    gap = _silence(duration_s=0.03, samplerate=samplerate)
    # pulse + gap + pulse + gap + pulse
    return np.concatenate([pulse, gap, pulse, gap, pulse])


def _default_output_stream_factory(**kwargs: Any) -> Any:
    """Lazy-import sounddevice so tests can inject a fake factory without the real audio stack."""
    import sounddevice
    return sounddevice.OutputStream(**kwargs)


class BeepPlayer:
    """Plays short lifecycle tones through a pre-resolved output device.

    All public methods (beep_*, close) catch every exception and log at
    WARNING rather than re-raising. A dead output device, a disconnected
    Bluetooth headset, or a PortAudio error must never abort the session.
    """

    def __init__(
        self,
        device: dict,
        output_stream_factory: Callable[..., Any] = _default_output_stream_factory,
    ):
        self._device = device
        self._samplerate = int(device.get("default_samplerate", 48000))
        self._stream: Any = None
        try:
            self._stream = output_stream_factory(
                samplerate=self._samplerate,
                channels=1,
                dtype="int16",
                device=device.get("index"),
            )
            self._stream.start()
        except Exception as exc:  # noqa: BLE001 — best-effort by design
            log.warning("beep player open failed: %s", exc)
            self._stream = None

    def _play(self, buf) -> None:
        if self._stream is None:
            return
        try:
            self._stream.write(buf)
        except Exception as exc:  # noqa: BLE001
            log.warning("beep failed: %s", exc)

    def beep_start(self) -> None:
        self._play(_start_buffer(self._samplerate))

    def beep_stop(self) -> None:
        self._play(_stop_buffer(self._samplerate))

    def beep_error(self) -> None:
        self._play(_error_buffer(self._samplerate))

    def close(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
        except Exception as exc:  # noqa: BLE001
            log.warning("beep player stop failed: %s", exc)
        try:
            self._stream.close()
        except Exception as exc:  # noqa: BLE001
            log.warning("beep player close failed: %s", exc)
        self._stream = None
