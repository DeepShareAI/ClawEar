"""CoreAudio input capture via sounddevice.

- Opens an InputStream with the device's native sample rate.
- PortAudio delivers PCM blocks on its own thread; we hop to the asyncio
  loop via call_soon_threadsafe and enqueue on a bounded asyncio.Queue
  with drop-oldest on full.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

log = logging.getLogger("ear.capture")


class DeviceNotFoundError(RuntimeError):
    pass


def _default_query_fn() -> list[dict]:
    import sounddevice  # deferred import: only real runtime needs it

    return list(sounddevice.query_devices())


def _default_default_index() -> int:
    import sounddevice

    inp, _ = sounddevice.default.device
    return int(inp)


def _default_input_stream_factory(**kwargs: Any):
    import sounddevice

    return sounddevice.InputStream(**kwargs)


def resolve_device(
    spec: str | None, devices: list[dict], default_input: int
) -> dict:
    """Pick an input device: substring match if `spec` is given, else the system default."""
    inputs = [d for d in devices if d.get("max_input_channels", 0) > 0]
    if spec is None:
        if default_input < 0 or default_input >= len(devices):
            raise DeviceNotFoundError(
                "No default input device available; pass --device to specify one."
            )
        candidate = devices[default_input]
        if candidate.get("max_input_channels", 0) <= 0:
            raise DeviceNotFoundError(
                f"Default device {candidate['name']!r} has no input channels."
            )
        return candidate
    for d in inputs:
        if spec.lower() in d["name"].lower():
            return d
    raise DeviceNotFoundError(
        f"No input device matches {spec!r}. Available: "
        + ", ".join(d["name"] for d in inputs)
    )


class Capture:
    def __init__(
        self,
        device_spec: str | None,
        queue_max_blocks: int,
        input_stream_factory: Callable[..., Any] = _default_input_stream_factory,
        query_fn: Callable[[], list[dict]] = _default_query_fn,
        default_index: int | Callable[[], int] = _default_default_index,
    ):
        self._device_spec = device_spec
        self._queue_max_blocks = queue_max_blocks
        self._input_stream_factory = input_stream_factory
        self._query_fn = query_fn
        self._default_index = default_index
        self._stream: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.blocks: asyncio.Queue[bytes] = asyncio.Queue(maxsize=queue_max_blocks)
        self.dropped_blocks: int = 0
        self._resolved: dict | None = None
        self.error: asyncio.Future[str] | None = None

    @staticmethod
    def list_devices(query_fn: Callable[[], list[dict]] = _default_query_fn) -> list[dict]:
        return [d for d in query_fn() if d.get("max_input_channels", 0) > 0]

    def preflight(self) -> dict:
        """Resolve the device without opening the stream. Returns {name, sample_rate, channels}."""
        devices = self._query_fn()
        default = (
            self._default_index()
            if callable(self._default_index)
            else self._default_index
        )
        info = resolve_device(self._device_spec, devices, default)
        self._resolved = info
        return {
            "name": info["name"],
            "sample_rate": int(info["default_samplerate"]),
            "channels": min(int(info.get("max_input_channels", 1)), 1) or 1,
        }

    def start(self) -> None:
        info = self.preflight()
        self._loop = asyncio.get_event_loop()
        self.error = self._loop.create_future()
        sample_rate = info["sample_rate"]
        blocksize = int(sample_rate * 0.020)  # ~20ms blocks
        self._stream = self._input_stream_factory(
            samplerate=sample_rate,
            blocksize=blocksize,
            device=self._resolved["name"] if self._resolved else None,
            channels=1,
            dtype="int16",
            callback=self._callback,
        )
        try:
            self._stream.start()
        except Exception as exc:  # noqa: BLE001
            log.error("capture start() failed: %s", exc, exc_info=True)
            # The error Future was created above this call, so it exists.
            if self.error is not None and not self.error.done():
                self.error.set_result(f"stream start failed: {exc}")
            # Don't re-raise; session will observe capture.error and exit cleanly.
            return
        log.info(
            "capture started device=%r rate=%d blocksize=%d",
            info["name"], sample_rate, blocksize,
        )

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
            finally:
                try:
                    self._stream.close()
                except Exception:  # noqa: BLE001
                    pass
                self._stream = None
        log.info("capture stopped dropped=%d", self.dropped_blocks)

    # asyncio thread.
    def _set_error(self, reason: str) -> None:
        if self.error is not None and not self.error.done():
            self.error.set_result(reason)

    # PortAudio thread.
    def _callback(self, indata, frames: int, time_info, status) -> None:
        # Input-overflow and input-underflow are recoverable — one brief glitch.
        # Anything else we treat as fatal (e.g., device removed).
        if status:
            recoverable = getattr(status, "input_overflow", False) or getattr(
                status, "input_underflow", False
            )
            if recoverable and not any(
                getattr(status, attr, False)
                for attr in (
                    "output_underflow",
                    "output_overflow",
                    "priming_output",
                )
            ):
                log.warning("portaudio recoverable status: %s", status)
            else:
                # Fatal. Trip the error Future from the asyncio loop.
                reason = f"portaudio fatal status: {status}"
                if self._loop is not None and self.error is not None:
                    self._loop.call_soon_threadsafe(self._set_error, reason)
                return  # don't enqueue the bad block
        pcm = bytes(indata)
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._enqueue, pcm)

    # asyncio thread (via call_soon_threadsafe).
    def _enqueue(self, pcm: bytes) -> None:
        try:
            self.blocks.put_nowait(pcm)
        except asyncio.QueueFull:
            try:
                self.blocks.get_nowait()
                self.dropped_blocks += 1
            except asyncio.QueueEmpty:
                pass
            try:
                self.blocks.put_nowait(pcm)
            except asyncio.QueueFull:
                # Extremely unlikely given single-threaded loop, but guard anyway.
                self.dropped_blocks += 1
