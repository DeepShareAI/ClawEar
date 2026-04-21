"""End-to-end tests for ear.session using both fakes."""
from __future__ import annotations

import asyncio
import wave
from pathlib import Path

import pytest

from ear.config import Config
from ear.session import run
from .fake_realtime import FakeRealtimeWS
from .fake_sounddevice import InputStream, query_devices, default as sd_default


def _silence(n_samples: int) -> bytes:
    return b"\x00\x00" * n_samples


def _fake_default_index() -> int:
    return sd_default.device[0]


async def _drive_session(
    config: Config,
    pcm_blocks: list[bytes],
    ws_script: list[dict],
    sigint_after_blocks: int | None = None,
):
    """Run the session with scripted audio + scripted server events."""
    ws = FakeRealtimeWS()
    captured_stream: list = []

    def input_stream_factory(**kwargs):
        s = InputStream(**kwargs)
        captured_stream.append(s)
        return s

    async def ws_factory(url: str, extra_headers: dict[str, str]) -> FakeRealtimeWS:
        return ws

    async def drive_audio() -> None:
        await asyncio.sleep(0.05)  # let capture start
        for i, blk in enumerate(pcm_blocks):
            captured_stream[0].push_block(blk)
            await asyncio.sleep(0)
            if sigint_after_blocks is not None and i + 1 == sigint_after_blocks:
                # The session installs a SIGINT handler that sets _shutdown_event;
                # we call session.request_shutdown() via attribute on the returned
                # task below — but since run() is one call, we use the test hook
                # in the module: set the global for shutdown.
                from ear import session as sess_mod

                if sess_mod._test_shutdown_event is not None:
                    sess_mod._test_shutdown_event.set()
        for ev in ws_script:
            await ws.push_event(ev)
        await ws.push_close()

    drive = asyncio.create_task(drive_audio())
    rc = await run(
        config=config,
        api_key="sk-test",
        device_spec=None,
        dry_run=False,
        input_stream_factory=input_stream_factory,
        ws_factory=ws_factory,
        query_fn=query_devices,
        default_index=_fake_default_index,
    )
    await drive
    return rc, ws


async def test_happy_path_writes_wav_transcript_and_jsonl(tmp_path: Path):
    cfg = Config(
        log_level="INFO",
        transcripts_dir=tmp_path / "transcripts",
        recordings_dir=tmp_path / "recordings",
        events_dir=tmp_path / "events",
        transcription_model="gpt-4o-transcribe",
        queue_max_blocks=100,
        realtime_sample_rate=24000,
        ws_reconnect=False,
    )
    pcm_blocks = [_silence(320) for _ in range(5)]  # 5 * 20ms at 16k (fake default)
    ws_script = [
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "Hello world.",
        },
    ]
    rc, _ws = await _drive_session(
        cfg, pcm_blocks, ws_script, sigint_after_blocks=5
    )
    assert rc == 0

    wavs = list((tmp_path / "recordings").glob("*.wav"))
    mds = list((tmp_path / "transcripts").glob("*.md"))
    jsonls = list((tmp_path / "events").glob("*.jsonl"))
    assert len(wavs) == 1 and len(mds) == 1 and len(jsonls) == 1

    with wave.open(str(wavs[0]), "rb") as rf:
        assert rf.getframerate() == 16000
        assert rf.getnframes() == 1600

    md_text = mds[0].read_text()
    assert "**User:** Hello world." in md_text
    assert "**Assistant:**" not in md_text
    assert "truncated: false" in md_text

    jsonl_lines = jsonls[0].read_text().splitlines()
    assert len(jsonl_lines) == 1


async def test_sigint_mid_session_marks_truncated_false_on_clean_drain(tmp_path: Path):
    cfg = Config(
        log_level="INFO",
        transcripts_dir=tmp_path / "transcripts",
        recordings_dir=tmp_path / "recordings",
        events_dir=tmp_path / "events",
        transcription_model="gpt-4o-transcribe",
        queue_max_blocks=100,
        realtime_sample_rate=24000,
        ws_reconnect=False,
    )
    pcm_blocks = [_silence(320) for _ in range(3)]
    ws_script = [
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "Partial.",
        },
    ]
    rc, _ws = await _drive_session(
        cfg, pcm_blocks, ws_script, sigint_after_blocks=3
    )
    assert rc == 0
    md = list((tmp_path / "transcripts").glob("*.md"))[0].read_text()
    assert "truncated: false" in md


async def test_ws_mid_session_drop_marks_truncated_true(tmp_path: Path):
    cfg = Config(
        log_level="INFO",
        transcripts_dir=tmp_path / "transcripts",
        recordings_dir=tmp_path / "recordings",
        events_dir=tmp_path / "events",
        transcription_model="gpt-4o-transcribe",
        queue_max_blocks=100,
        realtime_sample_rate=24000,
        ws_reconnect=False,
    )
    pcm_blocks = [_silence(320) for _ in range(2)]
    # Empty script; the driver closes the WS right away → looks like a drop.
    ws_script: list[dict] = []
    rc, _ws = await _drive_session(cfg, pcm_blocks, ws_script, sigint_after_blocks=None)
    # WebSocket closed before we initiated shutdown → session interprets as drop.
    assert rc == 3
    md = list((tmp_path / "transcripts").glob("*.md"))[0].read_text()
    assert "truncated: true" in md
