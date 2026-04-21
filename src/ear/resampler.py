"""Streaming PCM16 resampler backed by soxr.

Maintains filter state across calls so consecutive chunks concatenate seamlessly.
"""
from __future__ import annotations

import numpy as np
import soxr


class Resampler:
    def __init__(self, in_rate: int, out_rate: int):
        # Use float32 internally to avoid quantisation noise from int16 filter
        # coefficients. QQ quality minimises algorithmic delay (~3 samples at
        # 16k→24k) so the output-length tolerance in tests is easily met.
        self._stream = soxr.ResampleStream(
            in_rate, out_rate, num_channels=1, dtype="float32", quality="QQ"
        )

    def resample(self, pcm: bytes) -> bytes:
        """Resample a chunk of PCM16 mono bytes. Returns the newly produced bytes."""
        if not pcm:
            return b""
        arr_in = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        arr_out = self._stream.resample_chunk(arr_in)
        if arr_out.size == 0:
            return b""
        return arr_out.clip(-32768, 32767).astype(np.int16).tobytes()
