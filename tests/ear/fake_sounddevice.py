"""In-memory fake of the sounddevice API subset used by ear.capture."""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class FakeDeviceInfo:
    name: str
    max_input_channels: int
    default_samplerate: float


# Module-level state that tests manipulate.
_devices: list[FakeDeviceInfo] = []
_default_input_index: int = -1


def set_devices(devices: list[FakeDeviceInfo], default_input: int = 0) -> None:
    global _devices, _default_input_index
    _devices = list(devices)
    _default_input_index = default_input


def query_devices() -> list[dict]:
    """Match sounddevice.query_devices() with no args — returns a list of dicts."""
    return [
        {
            "name": d.name,
            "max_input_channels": d.max_input_channels,
            "default_samplerate": d.default_samplerate,
        }
        for d in _devices
    ]


class _Default:
    @property
    def device(self) -> tuple[int, int]:
        return (_default_input_index, -1)


default = _Default()


@dataclass
class FakeInputStream:
    samplerate: int
    blocksize: int
    device: int | str | None
    channels: int
    dtype: str
    callback: Callable[..., None]
    _started: bool = False
    _closed: bool = False
    pushed_blocks: list[bytes] = field(default_factory=list)

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def close(self) -> None:
        self._closed = True

    def __enter__(self) -> "FakeInputStream":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()
        self.close()

    # Test-only API.
    def push_block(self, pcm: bytes) -> None:
        """Invoke the registered callback with the given PCM16 bytes."""
        if not self._started:
            raise RuntimeError("stream not started")
        arr = np.frombuffer(pcm, dtype=np.int16).reshape(-1, self.channels)
        self.pushed_blocks.append(pcm)
        self.callback(arr, arr.shape[0], None, None)


def InputStream(
    *,
    samplerate: int,
    blocksize: int,
    device: int | str | None,
    channels: int,
    dtype: str,
    callback: Callable[..., None],
) -> FakeInputStream:
    return FakeInputStream(
        samplerate=samplerate,
        blocksize=blocksize,
        device=device,
        channels=channels,
        dtype=dtype,
        callback=callback,
    )
