"""Output device resolution and lifecycle beep playback.

Mirrors capture.py for the output side. Exposes resolve_output_device
(auto-prefers 'javis' then falls back to system default output) and
BeepPlayer (see subsequent tasks).
"""
from __future__ import annotations

import logging
from typing import Any, Callable

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
