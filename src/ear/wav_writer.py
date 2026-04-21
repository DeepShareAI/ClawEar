"""WAV file writer: PCM16 mono at a given sample rate, append-as-you-go."""
from __future__ import annotations

import wave
from pathlib import Path


class WavWriter:
    def __init__(self, path: Path, sample_rate: int):
        self._path = path
        self._sample_rate = sample_rate
        self._wav: wave.Wave_write | None = None

    def open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._wav = wave.open(str(self._path), "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)  # int16
        self._wav.setframerate(self._sample_rate)

    def append(self, pcm: bytes) -> None:
        if self._wav is None:
            raise RuntimeError("WavWriter is not open")
        self._wav.writeframes(pcm)

    def close(self) -> None:
        if self._wav is not None:
            self._wav.close()
            self._wav = None
