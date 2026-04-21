"""Async WebSocket client for OpenAI's transcription-only Realtime session.

- `connect()` opens the socket and sends transcription_session.update.
- `send_audio(pcm)` forwards a PCM16 mono @ sample_rate chunk as base64.
- `commit()` force-flushes the server-side buffer (used at shutdown).
- `events()` yields parsed event dicts until the socket closes.
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol

log = logging.getLogger("ear.realtime_client")


class WSProto(Protocol):
    async def send(self, msg: str) -> None: ...
    async def recv(self) -> str: ...
    async def close(self) -> None: ...


def _default_ws_factory(
    url: str, extra_headers: dict[str, str]
) -> Awaitable[WSProto]:
    import websockets

    return websockets.connect(url, additional_headers=extra_headers)  # type: ignore[return-value]


class RealtimeClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        sample_rate: int,
        ws_factory: Callable[[str, dict[str, str]], Awaitable[WSProto]] = _default_ws_factory,
    ):
        self._api_key = api_key
        self._model = model
        self._sample_rate = sample_rate
        self._ws_factory = ws_factory
        self._ws: WSProto | None = None

    async def connect(self) -> None:
        url = "wss://api.openai.com/v1/realtime?intent=transcription"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        self._ws = await self._ws_factory(url, headers)
        await self._send(
            {
                "type": "transcription_session.update",
                "session": {
                    "input_audio_format": "pcm16",
                    "input_audio_transcription": {"model": self._model},
                    "turn_detection": {"type": "semantic_vad"},
                },
            }
        )
        log.info("realtime transcription session connected model=%s", self._model)

    async def send_audio(self, pcm: bytes) -> None:
        b64 = base64.b64encode(pcm).decode("ascii")
        await self._send({"type": "input_audio_buffer.append", "audio": b64})

    async def commit(self) -> None:
        await self._send({"type": "input_audio_buffer.commit"})

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        if self._ws is None:
            raise RuntimeError("not connected")
        try:
            while True:
                raw = await self._ws.recv()
                yield json.loads(raw)
        except (ConnectionError, OSError) as exc:
            log.info("realtime ws closed: %s", exc)
            return

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            finally:
                self._ws = None

    async def _send(self, payload: dict[str, Any]) -> None:
        if self._ws is None:
            raise RuntimeError("not connected")
        await self._ws.send(json.dumps(payload))
