from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Deque, Dict, Optional
from uuid import uuid4

import httpx

from .config import Settings


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ReplicationEvent:
    id: str
    tipo: str
    payload: Dict
    criado_em: str

    def to_dict(self) -> Dict:
        return asdict(self)


class ReplicaSynchronizer:
    """Fila assíncrona responsável por entregar eventos entre os nós."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.pending: Dict[str, Deque[ReplicationEvent]] = {
            peer: deque() for peer in settings.peers
        }
        self._client: Optional[httpx.AsyncClient] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._flush_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._task:
            return
        self._client = httpx.AsyncClient(timeout=10)
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._client:
            await self._client.aclose()
            self._client = None

    async def broadcast(self, tipo: str, payload: Dict) -> ReplicationEvent:
        event = ReplicationEvent(id=str(uuid4()), tipo=tipo, payload=payload, criado_em=_utcnow())
        for peer in self.settings.peers:
            self.pending.setdefault(peer, deque()).append(event)
        await self._flush_pending()
        return event

    async def _run_loop(self) -> None:
        while self._running:
            await self._flush_pending()
            await asyncio.sleep(self.settings.replication_retry_seconds)

    async def _flush_pending(self) -> None:
        if not self.settings.peers:
            return
        async with self._flush_lock:
            for peer in self.settings.peers:
                await self._flush_peer(peer)

    async def _flush_peer(self, peer: str) -> None:
        queue = self.pending.setdefault(peer, deque())
        while queue:
            event = queue[0]
            success = await self._send_event(peer, event)
            if not success:
                break
            queue.popleft()

    async def _send_event(self, peer: str, event: ReplicationEvent) -> bool:
        if not self._client:
            return False
        url = peer.rstrip("/") + "/replica/event"
        try:
            response = await self._client.post(
                url,
                json=event.to_dict(),
                headers={"X-Replica-Token": self.settings.replication_token},
            )
            response.raise_for_status()
            return True
        except Exception:
            return False

    def status(self) -> Dict:
        return {
            "peers": self.settings.peers,
            "pending": {peer: len(queue) for peer, queue in self.pending.items()},
        }
