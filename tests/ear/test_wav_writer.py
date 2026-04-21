"""Tests for ear.wav_writer."""
import wave
from pathlib import Path

from ear.wav_writer import WavWriter


def _silence_pcm16(n_samples: int) -> bytes:
    return b"\x00\x00" * n_samples


def test_open_write_close_produces_readable_wav(tmp_path: Path):
    p = tmp_path / "out.wav"
    w = WavWriter(p, sample_rate=16000)
    w.open()
    w.append(_silence_pcm16(1600))  # 100ms at 16kHz
    w.append(_silence_pcm16(1600))  # another 100ms
    w.close()

    with wave.open(str(p), "rb") as rf:
        assert rf.getframerate() == 16000
        assert rf.getnchannels() == 1
        assert rf.getsampwidth() == 2
        assert rf.getnframes() == 3200
        assert rf.readframes(3200) == _silence_pcm16(3200)


def test_append_before_open_raises(tmp_path: Path):
    w = WavWriter(tmp_path / "x.wav", sample_rate=16000)
    try:
        w.append(b"\x00\x00")
    except RuntimeError as exc:
        assert "not open" in str(exc)
        return
    raise AssertionError("expected RuntimeError")


def test_close_without_open_is_noop(tmp_path: Path):
    w = WavWriter(tmp_path / "x.wav", sample_rate=16000)
    w.close()  # must not raise


def test_close_is_idempotent(tmp_path: Path):
    p = tmp_path / "out.wav"
    w = WavWriter(p, sample_rate=16000)
    w.open()
    w.append(_silence_pcm16(160))
    w.close()
    w.close()  # second call must not raise


def test_parent_dir_is_created(tmp_path: Path):
    p = tmp_path / "nested" / "dir" / "out.wav"
    w = WavWriter(p, sample_rate=24000)
    w.open()
    w.append(_silence_pcm16(240))
    w.close()
    assert p.exists()
