from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket

from ...utils.logger import logger


class WebSocketBridge:
    """UIBridge implementation that relays core events to connected browser sessions.

    Core callbacks fire on the BackendServices loop thread; every send is marshalled
    onto the API server loop with ``call_soon_threadsafe``.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, serialize):
        self.loop = loop
        self.serialize = serialize
        self.clients: set[WebSocket] = set()

    # ---- UIBridge protocol -------------------------------------------------
    def schedule_card_update(self, recording) -> None:
        self.emit("recording", self.serialize(recording))

    def schedule_card_remove(self, recordings) -> None:
        self.emit("removed", [rec.rec_id for rec in recordings])

    def schedule_snack(self, text: str, **kw: Any) -> None:
        self.emit("toast", {"text": text})

    def schedule_pubsub(self, topic: str, payload: Any) -> None:
        # Card updates already arrive via schedule_card_update; nothing extra to relay.
        pass

    # ---- fan-out -----------------------------------------------------------
    def emit(self, event: str, data: Any) -> None:
        message = json.dumps({"event": event, "data": data}, ensure_ascii=False, default=str)
        try:
            self.loop.call_soon_threadsafe(self._schedule_broadcast, message)
        except RuntimeError:
            pass  # API loop already closed during shutdown

    def _schedule_broadcast(self, message: str) -> None:
        self.loop.create_task(self._broadcast(message))

    async def _broadcast(self, message: str) -> None:
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(message)
            except Exception as exc:
                logger.debug(f"ws send failed: {exc}")
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)
