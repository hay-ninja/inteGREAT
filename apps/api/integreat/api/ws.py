"""WebSocket fan-out. Every published event is first persisted to the timeline (PRD FR-09)."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from ..models import IntegreatEvent
from ..storage.db import Store


class Hub:
    def __init__(self, store: Store):
        self.store = store
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def publish(self, ev: IntegreatEvent) -> IntegreatEvent:
        ev = self.store.append_event(ev)
        for q in list(self._subs[ev.project_id]):
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:
                pass  # slow client; it can resync from the timeline via ?after_seq
        return ev

    def subscribe(self, project_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subs[project_id].add(q)
        return q

    def unsubscribe(self, project_id: str, q: asyncio.Queue) -> None:
        self._subs[project_id].discard(q)
