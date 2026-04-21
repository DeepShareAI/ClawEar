"""In-memory fake of the OpenAI Realtime WebSocket surface used by ear.realtime_client.

Protocol subset:
- client sends JSON text frames.
- server sends JSON text frames.

This fake stores every sent message and emits scripted events when the client
calls `recv()`.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeRealtimeWS:
    sent: list[dict] = field(default_factory=list)
    _outbox: asyncio.Queue = field(default_factory=lambda: asyncio.Queue())
    closed: bool = False

    async def send(self, msg: str) -> None:
        if self.closed:
            raise ConnectionError("closed")
        self.sent.append(json.loads(msg))

    async def recv(self) -> str:
        if self.closed and self._outbox.empty():
            raise ConnectionError("closed")
        ev = await self._outbox.get()
        if ev is _CLOSE_SENTINEL:
            self.closed = True
            raise ConnectionError("closed")
        return json.dumps(ev)

    async def close(self) -> None:
        self.closed = True

    # Test-only helpers.
    async def push_event(self, event: dict[str, Any]) -> None:
        await self._outbox.put(event)

    async def push_close(self) -> None:
        await self._outbox.put(_CLOSE_SENTINEL)


_CLOSE_SENTINEL: Any = object()


def fake_ws_factory(url: str, extra_headers: dict[str, str]) -> FakeRealtimeWS:
    """Drop-in for a websocket-connect factory. Returns a ready-to-use fake."""
    return FakeRealtimeWS()
