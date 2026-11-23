"""Asyncio event bus: hospital events are published here and consumed by the Event Watcher with no
user prompt. Handlers run in a worker thread so the API (and SSE stream) stay responsive."""
from __future__ import annotations

import asyncio
import time
import uuid


class EventBus:
    def __init__(self) -> None:
        self.queue: asyncio.Queue | None = None
        self.history: list[dict] = []
        self._task: asyncio.Task | None = None
        self.results: dict[str, dict] = {}

    async def start(self) -> None:
        if self.queue is None:
            self.queue = asyncio.Queue()
            self._task = asyncio.create_task(self._consume())

    async def publish(self, event: dict) -> str:
        event = {**event, "event_id": event.get("event_id") or "EV-" + uuid.uuid4().hex[:6].upper(), "ts": time.time()}
        self.history.append(event)
        await self.start()
        await self.queue.put(event)
        return event["event_id"]

    async def _consume(self) -> None:
        from backend.agents.event_watcher import handle_event_sync

        while True:
            ev = await self.queue.get()
            try:
                self.results[ev["event_id"]] = await asyncio.to_thread(handle_event_sync, ev)
            except Exception as e:  # noqa: BLE001
                self.results[ev["event_id"]] = {"error": str(e)}
            finally:
                self.queue.task_done()


event_bus = EventBus()
