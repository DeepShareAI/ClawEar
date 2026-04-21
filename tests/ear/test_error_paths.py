"""Edge-case coverage for CLI + session error paths (spec §5)."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ear.cli import _cmd_start
from ear.config import Config
from ear.session import run
from .fake_realtime import FakeRealtimeWS
from .fake_sounddevice import InputStream, query_devices, default as sd_default


def _silence(n_samples: int) -> bytes:
    return b"\x00\x00" * n_samples


def _fake_default_index() -> int:
    return sd_default.device[0]


def test_cmd_start_handles_malformed_toml(tmp_path: Path, monkeypatch, capsys):
    """Malformed TOML in the config file must produce a single-line stderr + exit 1."""
    from ear import cli as cli_mod

    def _raise_toml():
        import tomllib
        tomllib.loads("not = valid = toml")

    monkeypatch.setattr(cli_mod, "load_config", _raise_toml)

    class Args:
        device = None
        instructions_file = None
        dry_run = True

    rc = _cmd_start(Args())
    captured = capsys.readouterr()
    assert rc == 1
    assert "config" in captured.err.lower() or "toml" in captured.err.lower()


async def test_session_exit_5_on_unhandled_exception(tmp_path: Path):
    """If session.run() hits an unexpected exception, finalize files and exit 5."""
    cfg = Config(
        log_level="INFO",
        transcripts_dir=tmp_path / "transcripts",
        recordings_dir=tmp_path / "recordings",
        events_dir=tmp_path / "events",
        openai_model="gpt-4o-realtime-preview",
        instructions="x",
        queue_max_blocks=100,
        realtime_sample_rate=24000,
        ws_reconnect=False,
    )

    def exploding_factory(**_kwargs):
        raise RuntimeError("synthetic boom")

    async def ws_factory(url: str, extra_headers: dict[str, str]) -> FakeRealtimeWS:
        return FakeRealtimeWS()

    rc = await run(
        config=cfg,
        api_key="sk-test",
        device_spec=None,
        input_stream_factory=exploding_factory,
        ws_factory=ws_factory,
        query_fn=query_devices,
        default_index=_fake_default_index,
    )
    assert rc == 5
    mds = list((tmp_path / "transcripts").glob("*.md"))
    assert len(mds) == 1
    md = mds[0].read_text()
    assert "fatal:" in md


async def test_session_exit_2_on_capture_fatal_error(tmp_path: Path):
    """Capture signals a fatal device error; session finalizes and returns 2."""
    cfg = Config(
        log_level="INFO",
        transcripts_dir=tmp_path / "transcripts",
        recordings_dir=tmp_path / "recordings",
        events_dir=tmp_path / "events",
        openai_model="gpt-4o-realtime-preview",
        instructions="x",
        queue_max_blocks=100,
        realtime_sample_rate=24000,
        ws_reconnect=False,
    )

    ws = FakeRealtimeWS()
    captured_streams: list = []

    def input_stream_factory(**kwargs):
        s = InputStream(**kwargs)
        captured_streams.append(s)
        return s

    async def ws_factory(url: str, extra_headers: dict[str, str]) -> FakeRealtimeWS:
        return ws

    async def driver():
        await asyncio.sleep(0.05)
        from ear import session as sess_mod
        if sess_mod._test_capture_error is not None:
            sess_mod._test_capture_error.set_result("device disappeared")

    drive = asyncio.create_task(driver())
    rc = await run(
        config=cfg,
        api_key="sk-test",
        device_spec=None,
        input_stream_factory=input_stream_factory,
        ws_factory=ws_factory,
        query_fn=query_devices,
        default_index=_fake_default_index,
    )
    await drive
    assert rc == 2
    md = list((tmp_path / "transcripts").glob("*.md"))[0].read_text()
    assert "truncated: true" in md
    assert "device disappeared" in md


async def test_session_exit_2_via_production_capture_error(tmp_path: Path):
    """End-to-end: pushing a fatal status through the fake produces exit 2
    WITHOUT manipulating the _test_capture_error hook directly.
    This verifies that production code (not the test hook) wires capture.error."""
    cfg = Config(
        log_level="INFO",
        transcripts_dir=tmp_path / "transcripts",
        recordings_dir=tmp_path / "recordings",
        events_dir=tmp_path / "events",
        openai_model="gpt-4o-realtime-preview",
        instructions="x",
        queue_max_blocks=100,
        realtime_sample_rate=24000,
        ws_reconnect=False,
    )

    ws = FakeRealtimeWS()
    captured_streams: list = []

    def input_stream_factory(**kwargs):
        s = InputStream(**kwargs)
        captured_streams.append(s)
        return s

    async def ws_factory(url: str, extra_headers: dict[str, str]) -> FakeRealtimeWS:
        return ws

    async def driver():
        await asyncio.sleep(0.05)
        from .fake_sounddevice import make_fatal_status
        captured_streams[0].push_status(make_fatal_status())

    drive = asyncio.create_task(driver())
    rc = await run(
        config=cfg,
        api_key="sk-test",
        device_spec=None,
        input_stream_factory=input_stream_factory,
        ws_factory=ws_factory,
        query_fn=query_devices,
        default_index=_fake_default_index,
    )
    await drive
    assert rc == 2
    md = list((tmp_path / "transcripts").glob("*.md"))[0].read_text()
    assert "truncated: true" in md
    assert "portaudio fatal status" in md


async def test_session_marks_audio_truncated_on_wav_write_failure(tmp_path: Path):
    """A failing WAV write must flag frontmatter audio_truncated: true but not crash."""
    cfg = Config(
        log_level="INFO",
        transcripts_dir=tmp_path / "transcripts",
        recordings_dir=tmp_path / "recordings",
        events_dir=tmp_path / "events",
        openai_model="gpt-4o-realtime-preview",
        instructions="x",
        queue_max_blocks=100,
        realtime_sample_rate=24000,
        ws_reconnect=False,
    )

    ws = FakeRealtimeWS()
    captured_streams: list = []

    def input_stream_factory(**kwargs):
        s = InputStream(**kwargs)
        captured_streams.append(s)
        return s

    async def ws_factory(url: str, extra_headers: dict[str, str]) -> FakeRealtimeWS:
        return ws

    async def driver():
        await asyncio.sleep(0.05)
        from ear import session as sess_mod
        if sess_mod._test_wav_writer is not None:
            sess_mod._test_wav_writer.close()
        captured_streams[0].push_block(_silence(320))
        await asyncio.sleep(0)
        from ear import session as sess_mod2
        if sess_mod2._test_shutdown_event is not None:
            sess_mod2._test_shutdown_event.set()
        await ws.push_event({"type": "response.done"})
        await ws.push_close()

    drive = asyncio.create_task(driver())
    rc = await run(
        config=cfg,
        api_key="sk-test",
        device_spec=None,
        input_stream_factory=input_stream_factory,
        ws_factory=ws_factory,
        query_fn=query_devices,
        default_index=_fake_default_index,
    )
    await drive
    assert rc == 0
    md = list((tmp_path / "transcripts").glob("*.md"))[0].read_text()
    assert "audio_truncated: true" in md
