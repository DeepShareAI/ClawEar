"""Tests for ear.resampler."""
import numpy as np

from ear.resampler import Resampler


def _make_pcm16(n: int, seed: int = 0) -> bytes:
    """n samples of pseudo-random int16 PCM."""
    rng = np.random.default_rng(seed)
    arr = rng.integers(-10000, 10000, size=n, dtype=np.int16)
    return arr.tobytes()


def test_silence_in_silence_out():
    r = Resampler(in_rate=16000, out_rate=24000)
    silence = b"\x00\x00" * 1600  # 100ms at 16k
    out = r.resample(silence)
    # Output should be ~1.5x input sample count; all zeros.
    assert len(out) > 0
    arr = np.frombuffer(out, dtype=np.int16)
    assert np.all(arr == 0)


def test_16k_to_24k_output_length_ratio():
    r = Resampler(in_rate=16000, out_rate=24000)
    # 10 chunks of 20ms each = 200ms total.
    total_in_samples = 0
    total_out_samples = 0
    for _ in range(10):
        pcm = _make_pcm16(320)  # 20ms at 16k
        total_in_samples += 320
        out = r.resample(pcm)
        total_out_samples += len(out) // 2
    # 1.5x expected; allow small window for filter delay.
    expected = total_in_samples * 24000 // 16000
    assert abs(total_out_samples - expected) < 50


def test_48k_to_24k_output_length_ratio():
    r = Resampler(in_rate=48000, out_rate=24000)
    total_in = 0
    total_out = 0
    for _ in range(10):
        pcm = _make_pcm16(960)  # 20ms at 48k
        total_in += 960
        out = r.resample(pcm)
        total_out += len(out) // 2
    expected = total_in * 24000 // 48000
    assert abs(total_out - expected) < 50


def test_many_chunks_does_not_accumulate_state_unbounded():
    """Feed 5 seconds of audio; each call returns only the newly resampled bytes."""
    r = Resampler(in_rate=16000, out_rate=24000)
    for _ in range(250):  # 250 * 20ms = 5s
        pcm = _make_pcm16(320)
        out = r.resample(pcm)
        # Each chunk's output is bounded (~480 samples = 960 bytes, plus small filter delay).
        assert len(out) < 2000


def test_passthrough_when_rates_equal():
    """If in_rate == out_rate, we still go through soxr; output should equal input numerically."""
    r = Resampler(in_rate=24000, out_rate=24000)
    pcm = _make_pcm16(480)
    out = r.resample(pcm)
    # Allow slight delay; accumulate across two calls.
    out += r.resample(_make_pcm16(480, seed=1))
    # Total output samples should match total input samples within small filter delay.
    assert abs(len(out) // 2 - 960) < 50
