"""End-to-end tests for ear.session using both fakes."""
from __future__ import annotations

import asyncio
import wave
from dataclasses import dataclass, field
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


@dataclass
class FakeBeepPlayer:
    calls: list[str] = field(default_factory=list)

    def beep_start(self) -> None:
        self.calls.append("beep_start")

    def beep_stop(self) -> None:
        self.calls.append("beep_stop")

    def beep_error(self) -> None:
        self.calls.append("beep_error")

    def close(self) -> None:
        self.calls.append("close")


async def _drive_session(
    config: Config,
    pcm_blocks: list[bytes],
    ws_script: list[dict],
    sigint_after_blocks: int | None = None,
    beep_player: FakeBeepPlayer | None = None,
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
                from ear import session as sess_mod
                if sess_mod._test_shutdown_event is not None:
                    sess_mod._test_shutdown_event.set()
        for ev in ws_script:
            await ws.push_event(ev)
        await ws.push_close()

    drive = asyncio.create_task(drive_audio())

    player = beep_player if beep_player is not None else FakeBeepPlayer()

    def beep_player_factory(device: dict):
        return player

    rc = await run(
        config=config,
        api_key="sk-test",
        device_spec=None,
        dry_run=False,
        input_stream_factory=input_stream_factory,
        ws_factory=ws_factory,
        query_fn=query_devices,
        default_index=_fake_default_index,
        beep_player_factory=beep_player_factory,
    )
    await drive
    return rc, ws, player


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
    rc, _ws, _ = await _drive_session(
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
    rc, _ws, _ = await _drive_session(
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
    rc, _ws, _ = await _drive_session(cfg, pcm_blocks, ws_script, sigint_after_blocks=None)
    # WebSocket closed before we initiated shutdown → session interprets as drop.
    assert rc == 3
    md = list((tmp_path / "transcripts").glob("*.md"))[0].read_text()
    assert "truncated: true" in md


@pytest.mark.asyncio
async def test_beep_lifecycle_happy_path(tmp_path: Path):
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
    pcm_blocks = [_silence(320) for _ in range(5)]
    ws_script = [
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "Hello world.",
        },
    ]
    rc, _ws, player = await _drive_session(cfg, pcm_blocks, ws_script, sigint_after_blocks=5)
    assert rc == 0
    # beep_start fires after WS connect succeeds; beep_stop fires in clean shutdown;
    # close fires last. No beep_error on the happy path.
    assert "beep_start" in player.calls
    assert "beep_stop" in player.calls
    assert "beep_error" not in player.calls
    assert "close" in player.calls
    # Ordering: beep_start BEFORE beep_stop BEFORE close.
    assert player.calls.index("beep_start") < player.calls.index("beep_stop") < player.calls.index("close")


@pytest.mark.asyncio
async def test_beep_lifecycle_ws_error(tmp_path: Path):
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
    pcm_blocks = [_silence(320) for _ in range(5)]
    # Empty ws_script — the drive_audio helper calls ws.push_close() after the
    # (empty) event loop, so the consumer exits before shutdown_event is set.
    ws_script: list[dict] = []
    rc, _ws, player = await _drive_session(cfg, pcm_blocks, ws_script, sigint_after_blocks=None)
    assert rc == 3  # ws error path
    assert "beep_start" in player.calls
    assert "beep_error" in player.calls
    assert "beep_stop" not in player.calls
    assert "close" in player.calls
    assert player.calls.index("beep_start") < player.calls.index("beep_error") < player.calls.index("close")


@pytest.mark.asyncio
async def test_beep_not_fired_on_preflight_failure(tmp_path: Path):
    """Device-not-found before any stream opens — no beep_* should fire."""
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
    # device_spec="nonexistent" will cause DeviceNotFoundError at preflight.
    player = FakeBeepPlayer()

    def beep_player_factory(device: dict):
        return player

    async def ws_factory(url: str, extra_headers: dict[str, str]):
        raise AssertionError("WS factory should not be called on preflight failure")

    rc = await run(
        config=cfg,
        api_key="sk-test",
        device_spec="nonexistent",
        dry_run=False,
        input_stream_factory=InputStream,
        ws_factory=ws_factory,
        query_fn=query_devices,
        default_index=_fake_default_index,
        beep_player_factory=beep_player_factory,
    )
    assert rc == 1
    assert player.calls == []  # zero beeps, zero close — player was never built


@pytest.mark.asyncio
async def test_beep_lifecycle_capture_error(tmp_path: Path):
    """Mid-session capture fatal error → exit 2, fires beep_error (not beep_stop)."""
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
    ws = FakeRealtimeWS()
    captured_stream: list = []

    def input_stream_factory(**kwargs):
        s = InputStream(**kwargs)
        captured_stream.append(s)
        return s

    async def ws_factory(url: str, extra_headers: dict[str, str]) -> FakeRealtimeWS:
        return ws

    async def drive_audio() -> None:
        await asyncio.sleep(0.05)
        # Set capture error future after one block — simulates PortAudio fatal status.
        captured_stream[0].push_block(_silence(320))
        await asyncio.sleep(0)
        from ear import session as sess_mod
        if sess_mod._test_capture_error is not None and not sess_mod._test_capture_error.done():
            sess_mod._test_capture_error.set_result("input overflow (synthetic)")

    drive = asyncio.create_task(drive_audio())
    player = FakeBeepPlayer()

    def beep_player_factory(device: dict):
        return player

    rc = await run(
        config=cfg,
        api_key="sk-test",
        device_spec=None,
        dry_run=False,
        input_stream_factory=input_stream_factory,
        ws_factory=ws_factory,
        query_fn=query_devices,
        default_index=_fake_default_index,
        beep_player_factory=beep_player_factory,
    )
    await drive

    assert rc == 2  # capture-error exit
    assert "beep_start" in player.calls
    assert "beep_error" in player.calls
    assert "beep_stop" not in player.calls
    assert "close" in player.calls
    assert player.calls.index("beep_start") < player.calls.index("beep_error") < player.calls.index("close")


@pytest.mark.asyncio
async def test_beep_lifecycle_fatal_exception(tmp_path: Path):
    """A fatal exception after WS connect → exit 5, fires beep_error."""
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

    def exploding_input_stream_factory(**kwargs):
        """Raises on the call from capture.start() — this propagates uncaught through
        capture.start() into session.py's outer except, triggering exit 5.
        Note: preflight() does NOT call the factory, only start() does.
        """
        raise RuntimeError("synthetic fatal: input_stream_factory failed at start()")

    async def ws_factory(url: str, extra_headers: dict[str, str]):
        # WS connect must succeed so beep_start fires before the fatal exception.
        return FakeRealtimeWS()

    player = FakeBeepPlayer()

    def beep_player_factory(device: dict):
        return player

    rc = await run(
        config=cfg,
        api_key="sk-test",
        device_spec=None,
        dry_run=False,
        input_stream_factory=exploding_input_stream_factory,
        ws_factory=ws_factory,
        query_fn=query_devices,
        default_index=_fake_default_index,
        beep_player_factory=beep_player_factory,
    )

    assert rc == 5  # fatal-exception exit
    # beep_start fires after WS connect; the factory exception at capture.start()
    # propagates to the outer except handler which calls beep_error + close.
    assert "beep_start" in player.calls
    assert "beep_error" in player.calls
    assert "close" in player.calls
    assert "beep_stop" not in player.calls
    assert player.calls.index("beep_start") < player.calls.index("beep_error")
