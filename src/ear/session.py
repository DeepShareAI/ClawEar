"""Session orchestration for a single clawear recording session.

Wires capture → dispatcher → wav_writer / realtime_sender → event_consumer →
transcript + events_log. Owns the shutdown protocol and exit-code logic.
"""
from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from .capture import Capture, DeviceNotFoundError, _default_input_stream_factory, _default_query_fn, _default_default_index
from .config import Config
from .events_log import EventsLog
from .realtime_client import RealtimeClient, WSProto, _default_ws_factory
from .resampler import Resampler
from .transcript import TranscriptBuilder
from .wav_writer import WavWriter

log = logging.getLogger("ear.session")

# Test-only hook so tests can trigger a synthetic SIGINT without sending signals.
_test_shutdown_event: asyncio.Event | None = None


def _session_id_now() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    sid = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    started_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    return sid, started_at


async def run(
    config: Config,
    api_key: str,
    device_spec: str | None,
    instructions_override: str | None = None,
    dry_run: bool = False,
    input_stream_factory: Callable[..., Any] = _default_input_stream_factory,
    ws_factory: Callable[[str, dict[str, str]], Awaitable[WSProto]] = _default_ws_factory,
    query_fn: Callable[[], list[dict]] = _default_query_fn,
    default_index: int | Callable[[], int] = _default_default_index,
) -> int:
    """Run one session. Returns an exit code per the design spec."""
    global _test_shutdown_event
    instructions = instructions_override or config.instructions

    session_id, started_at = _session_id_now()
    wav_path = config.recordings_dir / f"{session_id}.wav"
    events_path = config.events_dir / f"{session_id}.jsonl"
    transcript_path = config.transcripts_dir / f"{session_id}.md"

    # Capture + preflight.
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

    print(
        f"Recording from: {info['name']} @ {info['sample_rate']} Hz, "
        f"{info['channels']} channel",
        flush=True,
    )

    if dry_run:
        print("dry-run: not opening WebSocket", flush=True)
        return 0

    # Writers + resampler + realtime client.
    wav = WavWriter(wav_path, sample_rate=info["sample_rate"])
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
    client = RealtimeClient(
        api_key=api_key,
        model=config.openai_model,
        instructions=instructions,
        sample_rate=config.realtime_sample_rate,
        ws_factory=ws_factory,
    )

    wav.open()
    evlog.open()
    transcript.flush(transcript_path)

    try:
        await client.connect()
    except Exception as exc:  # noqa: BLE001
        log.error("realtime connect failed: %s", exc, exc_info=True)
        transcript.set_truncated(f"connect failed: {exc}")
        transcript.flush(transcript_path)
        wav.close()
        evlog.close()
        return 3

    capture.start()

    # State.
    shutdown_event = asyncio.Event()
    _test_shutdown_event = shutdown_event
    realtime_queue: asyncio.Queue[bytes | None] = asyncio.Queue(
        maxsize=config.queue_max_blocks
    )
    realtime_dropped = 0
    response_done_seen = False
    ws_errored = False

    # Install SIGINT.
    loop = asyncio.get_event_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, shutdown_event.set)
    except NotImplementedError:
        # Windows / some test environments. Test-hook above is enough.
        pass

    async def dispatcher_task() -> None:
        nonlocal realtime_dropped
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
                await client.send_audio(resampled)
            except Exception as exc:  # noqa: BLE001
                log.warning("realtime send failed: %s", exc)
                return

    async def event_consumer_task() -> None:
        nonlocal response_done_seen
        async for ev in client.events():
            try:
                evlog.append(ev)
            except Exception as exc:  # noqa: BLE001
                log.warning("events_log append failed: %s", exc)
            et = ev.get("type", "")
            if et == "conversation.item.input_audio_transcription.completed":
                text = ev.get("transcript") or ev.get("text") or ""
                transcript.append_user_turn(text)
                transcript.flush(transcript_path)
            elif et == "response.text.delta":
                delta = ev.get("delta") or ""
                transcript.append_assistant_turn(delta)
                transcript.flush(transcript_path)
            elif et == "response.done":
                response_done_seen = True
                transcript.flush(transcript_path)
            elif et == "error":
                code = ev.get("error", {}).get("code", "unknown")
                transcript.add_note(f"api error: {code}")
                transcript.flush(transcript_path)

    dispatcher = asyncio.create_task(dispatcher_task())
    sender = asyncio.create_task(realtime_sender_task())
    consumer = asyncio.create_task(event_consumer_task())

    # Wait for shutdown OR event consumer completion (natural WS close).
    wait_shutdown = asyncio.create_task(shutdown_event.wait())
    done, _pending = await asyncio.wait(
        {wait_shutdown, consumer},
        return_when=asyncio.FIRST_COMPLETED,
    )

    if consumer in done and not shutdown_event.is_set():
        # WebSocket closed before Ctrl-C.
        if not response_done_seen:
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

    # Force-finalize server side (only if we shut down via SIGINT, not a WS drop).
    if not ws_errored:
        try:
            await client.commit()
            await client.request_response()
        except Exception as exc:  # noqa: BLE001
            log.warning("realtime finalize send failed: %s", exc)
            # Don't mark ws_errored here — the WS may have closed naturally after
            # response.done. Let the consumer result determine final ws_errored state.

    # Wait for consumer ≤5s.
    try:
        await asyncio.wait_for(consumer, timeout=5.0)
    except asyncio.TimeoutError:
        consumer.cancel()

    # Re-evaluate ws_errored based on whether response.done was seen.
    # If the WS closed (consumer exited) without response.done, it's an error.
    if not response_done_seen and not ws_errored:
        ws_errored = True

    # Tally + finalize files.
    total_dropped = capture.dropped_blocks + realtime_dropped
    transcript.set_dropped_blocks(total_dropped)
    if ws_errored:
        transcript.set_truncated("WebSocket error or premature close")
        transcript.add_note("session truncated — WebSocket error or premature close")
    transcript.flush(transcript_path)
    wav.close()
    evlog.close()
    await client.close()

    print(f"wav: {wav_path}", flush=True)
    print(f"md:  {transcript_path}", flush=True)
    print(f"log: {events_path}", flush=True)

    _test_shutdown_event = None
    if ws_errored:
        return 3
    return 0
