"""Session orchestration for a single clawear recording session.

Wires capture → dispatcher → wav_writer / realtime_sender → event_consumer →
transcript + events_log. Owns the shutdown protocol and exit-code logic.
"""
from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime
from typing import Any, Awaitable, Callable

from .capture import Capture, DeviceNotFoundError, _default_input_stream_factory, _default_query_fn, _default_default_index
from .config import Config
from .events_log import EventsLog
from .output import BeepPlayer, resolve_output_device
from .realtime_client import RealtimeClient, WSProto, _default_ws_factory
from .resampler import Resampler
from .transcript import TranscriptBuilder
from .wav_writer import WavWriter

log = logging.getLogger("ear.session")

# Test-only hooks so tests can trigger synthetic signals without OS signals.
_test_shutdown_event: asyncio.Event | None = None
_test_capture_error: asyncio.Future[str] | None = None
_test_wav_writer: "WavWriter | None" = None  # type: ignore[name-defined]


def _default_default_output_index() -> int:
    import sounddevice
    _, out = sounddevice.default.device
    return int(out)


class _NullBeepPlayer:
    """Null-object stand-in used when output device resolution fails.

    Lets session.run() call player.beep_*() and player.close() unconditionally
    without None-checks, and without a try/except around every call site. The
    alternative — guarding every beep with `if player is not None:` — would
    spread the concern across half a dozen exit paths.
    """

    def beep_start(self) -> None: ...
    def beep_stop(self) -> None: ...
    def beep_error(self) -> None: ...
    def close(self) -> None: ...


def _default_beep_player_factory(device: dict) -> BeepPlayer:
    return BeepPlayer(device)


def _format_session_id(dt: datetime) -> tuple[str, str]:
    """Format an aware datetime as (filename_stem, iso_started_at).

    filename_stem: YYYY-MM-DD_HH-MM-SS in the datetime's local timezone.
    iso_started_at: ISO 8601 with offset (e.g. 2026-04-21T14:12:39+08:00).
    """
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    sid = dt.strftime("%Y-%m-%d_%H-%M-%S")
    started_at = dt.isoformat(timespec="seconds")
    return sid, started_at


def _session_id_now() -> tuple[str, str]:
    return _format_session_id(datetime.now().astimezone())


async def run(
    config: Config,
    api_key: str,
    device_spec: str | None,
    dry_run: bool = False,
    input_stream_factory: Callable[..., Any] = _default_input_stream_factory,
    ws_factory: Callable[[str, dict[str, str]], Awaitable[WSProto]] = _default_ws_factory,
    query_fn: Callable[[], list[dict]] = _default_query_fn,
    default_index: int | Callable[[], int] = _default_default_index,
    default_output_index: int | Callable[[], int] = _default_default_output_index,
    beep_player_factory: Callable[[dict], BeepPlayer] = _default_beep_player_factory,
) -> int:
    """Run one session. Returns an exit code per the design spec."""
    global _test_shutdown_event, _test_capture_error, _test_wav_writer

    session_id, started_at = _session_id_now()
    wav_path = config.recordings_dir / f"{session_id}.wav"
    events_path = config.events_dir / f"{session_id}.jsonl"
    transcript_path = config.transcripts_dir / f"{session_id}.md"

    # Initialized outside the main try so the except handler can finalize them.
    wav: WavWriter | None = None
    evlog: EventsLog | None = None
    transcript: TranscriptBuilder | None = None
    client_obj: RealtimeClient | None = None
    # player is initialized to a null object so the outer except handler can
    # always call player.beep_error() / player.close() without a NameError,
    # even if the exception fires before the real player is constructed.
    player: BeepPlayer | _NullBeepPlayer = _NullBeepPlayer()

    # Preflight is a distinct pre-artifact stage that can exit 1 on bad device.
    try:
        capture = Capture(
            device_spec=device_spec,
            queue_max_blocks=config.queue_max_blocks,
            input_stream_factory=input_stream_factory,
            query_fn=query_fn,
            default_index=default_index,
        )
        info = capture.preflight()
    except DeviceNotFoundError as exc:
        print(f"error: {exc}", flush=True)
        return 1
    except Exception as exc:  # noqa: BLE001
        # Preflight failure with no prior artifacts — emit a minimal transcript.
        log.error("preflight failed: %s", exc, exc_info=True)
        minimal = TranscriptBuilder(
            session_id=session_id,
            started_at=started_at,
            device="<unknown>",
            sample_rate=0,
            audio_path=wav_path,
            events_path=events_path,
        )
        minimal.set_truncated(f"fatal: {type(exc).__name__}: {exc}")
        minimal.add_note(f"fatal: {type(exc).__name__}: {exc}")
        minimal.flush(transcript_path)
        return 5

    print(
        f"Recording from: {info['name']} @ {info['sample_rate']} Hz, "
        f"{info['channels']} channel",
        flush=True,
    )

    # Resolve output device (auto-prefers 'javis', falls back to system default).
    # Done after preflight succeeds but before opening WS so a bad output device
    # can't waste a WS connect.
    devices = query_fn()
    resolved_out_idx = (
        default_output_index() if callable(default_output_index) else int(default_output_index)
    )
    try:
        output_device = resolve_output_device(devices, resolved_out_idx)
        player = beep_player_factory(output_device)
    except Exception as exc:  # OutputDeviceNotFoundError or factory errors
        log.warning("beep player unavailable: %s", exc)
        player = _NullBeepPlayer()

    if dry_run:
        print("dry-run: not opening WebSocket", flush=True)
        player.close()
        return 0

    try:
        wav = WavWriter(wav_path, sample_rate=info["sample_rate"])
        _test_wav_writer = wav
        evlog = EventsLog(events_path)
        transcript = TranscriptBuilder(
            session_id=session_id,
            started_at=started_at,
            device=info["name"],
            sample_rate=info["sample_rate"],
            audio_path=wav_path,
            events_path=events_path,
        )
        resampler = Resampler(
            in_rate=info["sample_rate"], out_rate=config.realtime_sample_rate
        )
        client_obj = RealtimeClient(
            api_key=api_key,
            model=config.transcription_model,
            sample_rate=config.realtime_sample_rate,
            ws_factory=ws_factory,
        )

        wav.open()
        evlog.open()
        transcript.flush(transcript_path)

        try:
            await client_obj.connect()
        except Exception as exc:  # noqa: BLE001
            log.error("realtime connect failed: %s", exc, exc_info=True)
            transcript.set_truncated(f"connect failed: {exc}")
            transcript.flush(transcript_path)
            wav.close()
            evlog.close()
            player.beep_error()
            player.close()
            return 3
        player.beep_start()

        capture.start()
        _test_capture_error = capture.error

        shutdown_event = asyncio.Event()
        _test_shutdown_event = shutdown_event
        realtime_queue: asyncio.Queue[bytes | None] = asyncio.Queue(
            maxsize=config.queue_max_blocks
        )
        realtime_dropped = 0
        ws_errored = False
        wav_errored = False

        # SIGINT: first signal → graceful shutdown; second → cancel tasks.
        loop = asyncio.get_event_loop()
        sigint_count = {"n": 0}
        _tasks_for_cancel: list[asyncio.Task] = []

        def _on_sigint() -> None:
            sigint_count["n"] += 1
            if sigint_count["n"] == 1:
                shutdown_event.set()
            else:
                for t in _tasks_for_cancel:
                    t.cancel()

        try:
            loop.add_signal_handler(signal.SIGINT, _on_sigint)
        except NotImplementedError:
            pass

        async def dispatcher_task() -> None:
            nonlocal realtime_dropped, wav_errored
            while True:
                try:
                    block = await capture.blocks.get()
                except asyncio.CancelledError:
                    return
                if block is None:
                    return
                try:
                    wav.append(block)
                except Exception as exc:  # noqa: BLE001
                    log.warning("wav append failed: %s", exc)
                    wav_errored = True
                try:
                    realtime_queue.put_nowait(block)
                except asyncio.QueueFull:
                    try:
                        realtime_queue.get_nowait()
                        realtime_dropped += 1
                    except asyncio.QueueEmpty:
                        pass
                    try:
                        realtime_queue.put_nowait(block)
                    except asyncio.QueueFull:
                        realtime_dropped += 1

        async def realtime_sender_task() -> None:
            while True:
                try:
                    block = await realtime_queue.get()
                except asyncio.CancelledError:
                    return
                if block is None:
                    return
                resampled = resampler.resample(block)
                if not resampled:
                    continue
                try:
                    await client_obj.send_audio(resampled)
                except Exception as exc:  # noqa: BLE001
                    log.warning("realtime send failed: %s", exc)
                    return

        async def event_consumer_task() -> None:
            async for ev in client_obj.events():
                try:
                    evlog.append(ev)
                except Exception as exc:  # noqa: BLE001
                    log.warning("events_log append failed: %s", exc)
                et = ev.get("type", "")
                if et == "conversation.item.input_audio_transcription.completed":
                    text = ev.get("transcript") or ev.get("text") or ""
                    transcript.append_user_turn(text)
                    transcript.flush(transcript_path)
                elif et == "error":
                    code = ev.get("error", {}).get("code", "unknown")
                    transcript.add_note(f"api error: {code}")
                    transcript.flush(transcript_path)

        dispatcher = asyncio.create_task(dispatcher_task())
        sender = asyncio.create_task(realtime_sender_task())
        consumer = asyncio.create_task(event_consumer_task())
        _tasks_for_cancel.extend([dispatcher, sender, consumer])

        # Wait for shutdown OR consumer complete OR capture fatal error.
        wait_shutdown = asyncio.create_task(shutdown_event.wait())
        waitables: set = {wait_shutdown, consumer}
        wait_capture_err: asyncio.Future | None = None
        if capture.error is not None:
            wait_capture_err = capture.error
            waitables.add(wait_capture_err)

        done, _pending = await asyncio.wait(
            waitables, return_when=asyncio.FIRST_COMPLETED
        )

        capture_error_reason: str | None = None
        if wait_capture_err is not None and wait_capture_err in done:
            try:
                capture_error_reason = wait_capture_err.result()
            except Exception as exc:  # noqa: BLE001
                capture_error_reason = str(exc)

        if (
            consumer in done
            and not shutdown_event.is_set()
            and capture_error_reason is None
        ):
            ws_errored = True

        # Stop capture + drain dispatcher.
        capture.stop()
        await capture.blocks.put(None)
        try:
            await asyncio.wait_for(dispatcher, timeout=2.0)
        except asyncio.TimeoutError:
            dispatcher.cancel()

        # Drain sender.
        await realtime_queue.put(None)
        try:
            await asyncio.wait_for(sender, timeout=2.0)
        except asyncio.TimeoutError:
            sender.cancel()

        # Force-finalize server side by committing any buffered audio.
        if not ws_errored and capture_error_reason is None:
            try:
                await client_obj.commit()
            except Exception as exc:  # noqa: BLE001
                log.warning("realtime finalize send failed: %s", exc)

        # Wait for consumer ≤5s.
        try:
            await asyncio.wait_for(consumer, timeout=5.0)
        except asyncio.TimeoutError:
            consumer.cancel()

        # Re-evaluate ws_errored: if neither SIGINT nor capture error initiated
        # shutdown, consumer ending means the socket died on us.
        if (
            capture_error_reason is None
            and not shutdown_event.is_set()
            and consumer.done()
        ):
            ws_errored = True

        # Tally + finalize files.
        total_dropped = capture.dropped_blocks + realtime_dropped
        transcript.set_dropped_blocks(total_dropped)
        if capture_error_reason is not None:
            transcript.set_truncated(f"capture error: {capture_error_reason}")
            transcript.add_note(f"session truncated — {capture_error_reason}")
        elif ws_errored:
            transcript.set_truncated("WebSocket error or premature close")
            transcript.add_note(
                "session truncated — WebSocket error or premature close"
            )
        if wav_errored:
            transcript._frontmatter["audio_truncated"] = True
        transcript.flush(transcript_path)
        wav.close()
        evlog.close()
        await client_obj.close()

        if capture_error_reason is not None or ws_errored:
            player.beep_error()
        else:
            player.beep_stop()
        player.close()

        print(f"wav: {wav_path}", flush=True)
        print(f"md:  {transcript_path}", flush=True)
        print(f"log: {events_path}", flush=True)

        _test_shutdown_event = None
        _test_capture_error = None
        _test_wav_writer = None

        if capture_error_reason is not None:
            return 2
        if ws_errored:
            return 3
        return 0

    except Exception as exc:  # noqa: BLE001
        log.error("session fatal: %s", exc, exc_info=True)
        if transcript is not None:
            transcript.set_truncated(f"fatal: {type(exc).__name__}: {exc}")
            transcript.add_note(f"fatal: {type(exc).__name__}: {exc}")
            try:
                transcript.flush(transcript_path)
            except Exception:
                pass
        else:
            # No transcript object yet — emit a minimal one so there's always SOMETHING on disk.
            minimal = TranscriptBuilder(
                session_id=session_id,
                started_at=started_at,
                device=info["name"],
                sample_rate=info["sample_rate"],
                audio_path=wav_path,
                events_path=events_path,
            )
            minimal.set_truncated(f"fatal: {type(exc).__name__}: {exc}")
            minimal.add_note(f"fatal: {type(exc).__name__}: {exc}")
            minimal.flush(transcript_path)
        if wav is not None:
            try:
                wav.close()
            except Exception:
                pass
        if evlog is not None:
            try:
                evlog.close()
            except Exception:
                pass
        if client_obj is not None:
            try:
                await client_obj.close()
            except Exception:
                pass
        try:
            player.beep_error()
        except Exception:
            pass
        try:
            player.close()
        except Exception:
            pass
        _test_shutdown_event = None
        _test_capture_error = None
        _test_wav_writer = None
        return 5
