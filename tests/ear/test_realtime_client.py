"""Tests for ear.realtime_client."""
from __future__ import annotations

import base64

from ear.realtime_client import RealtimeClient
from .fake_realtime import FakeRealtimeWS


async def test_connect_sends_transcription_session_update_with_correct_payload():
    ws = FakeRealtimeWS()

    async def factory(url: str, extra_headers: dict[str, str]) -> FakeRealtimeWS:
        return ws

    client = RealtimeClient(
        api_key="sk-test",
        model="gpt-4o-transcribe",
        sample_rate=24000,
        ws_factory=factory,
    )
    await client.connect()
    assert len(ws.sent) == 1
    msg = ws.sent[0]
    assert msg["type"] == "transcription_session.update"
    assert msg["session"]["input_audio_format"] == "pcm16"
    assert msg["session"]["input_audio_transcription"]["model"] == "gpt-4o-transcribe"
    assert msg["session"]["turn_detection"] == {"type": "semantic_vad"}
    assert "modalities" not in msg["session"]
    assert "instructions" not in msg["session"]
    await client.close()


async def test_connect_uses_transcription_intent_url_and_headers():
    captured = {}

    async def factory(url: str, extra_headers: dict[str, str]) -> FakeRealtimeWS:
        captured["url"] = url
        captured["headers"] = extra_headers
        return FakeRealtimeWS()

    client = RealtimeClient(
        api_key="sk-abc",
        model="gpt-4o-transcribe",
        sample_rate=24000,
        ws_factory=factory,
    )
    await client.connect()
    assert captured["url"] == "wss://api.openai.com/v1/realtime?intent=transcription"
    assert "model=" not in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer sk-abc"
    assert captured["headers"]["OpenAI-Beta"] == "realtime=v1"
    await client.close()


async def test_send_audio_emits_input_audio_buffer_append_with_base64():
    ws = FakeRealtimeWS()

    async def factory(url: str, extra_headers: dict[str, str]) -> FakeRealtimeWS:
        return ws

    client = RealtimeClient(
        api_key="sk-test",
        model="gpt-4o-transcribe",
        sample_rate=24000,
        ws_factory=factory,
    )
    await client.connect()
    pcm = b"\x01\x02\x03\x04" * 100
    await client.send_audio(pcm)

    assert ws.sent[1]["type"] == "input_audio_buffer.append"
    audio_b64 = ws.sent[1]["audio"]
    assert base64.b64decode(audio_b64) == pcm
    await client.close()


async def test_commit_emits_input_audio_buffer_commit_only():
    ws = FakeRealtimeWS()

    async def factory(url: str, extra_headers: dict[str, str]) -> FakeRealtimeWS:
        return ws

    client = RealtimeClient(
        api_key="sk-test",
        model="gpt-4o-transcribe",
        sample_rate=24000,
        ws_factory=factory,
    )
    await client.connect()
    await client.commit()

    types = [m["type"] for m in ws.sent[1:]]
    assert types == ["input_audio_buffer.commit"]
    assert not hasattr(client, "request_response")
    await client.close()


async def test_events_iterator_yields_parsed_event_dicts():
    ws = FakeRealtimeWS()

    async def factory(url: str, extra_headers: dict[str, str]) -> FakeRealtimeWS:
        return ws

    client = RealtimeClient(
        api_key="sk-test",
        model="gpt-4o-transcribe",
        sample_rate=24000,
        ws_factory=factory,
    )
    await client.connect()
    await ws.push_event(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "hello world",
        }
    )
    await ws.push_event({"type": "transcription_session.updated"})
    await ws.push_close()

    collected: list[dict] = []
    async for ev in client.events():
        collected.append(ev)
    assert [e["type"] for e in collected] == [
        "conversation.item.input_audio_transcription.completed",
        "transcription_session.updated",
    ]
    await client.close()
