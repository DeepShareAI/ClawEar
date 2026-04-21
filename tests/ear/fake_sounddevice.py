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

    def push_status(self, status: object) -> None:
        """Invoke the callback with a synthetic status object (and no PCM data)."""
        if not self._started:
            raise RuntimeError("stream not started")
        empty = np.zeros((0, self.channels), dtype=np.int16)
        self.callback(empty, 0, None, status)


class _FakeStatus:
    """Fake sounddevice.CallbackFlags subset. Truthy if any flag is set."""
    def __init__(
        self,
        input_overflow: bool = False,
        input_underflow: bool = False,
        output_underflow: bool = False,
        output_overflow: bool = False,
        priming_output: bool = False,
    ):
        self.input_overflow = input_overflow
        self.input_underflow = input_underflow
        self.output_underflow = output_underflow
        self.output_overflow = output_overflow
        self.priming_output = priming_output

    def __bool__(self) -> bool:
        return any(
            [
                self.input_overflow,
                self.input_underflow,
                self.output_underflow,
                self.output_overflow,
                self.priming_output,
            ]
        )

    def __repr__(self) -> str:
        flags = [
            n
            for n, v in [
                ("input_overflow", self.input_overflow),
                ("input_underflow", self.input_underflow),
                ("output_underflow", self.output_underflow),
                ("output_overflow", self.output_overflow),
                ("priming_output", self.priming_output),
            ]
            if v
        ]
        return f"FakeStatus({','.join(flags) or 'none'})"


def make_fatal_status() -> _FakeStatus:
    return _FakeStatus(output_underflow=True)


def make_recoverable_status() -> _FakeStatus:
    return _FakeStatus(input_overflow=True)


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
