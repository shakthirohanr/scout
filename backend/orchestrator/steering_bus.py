"""Async steering bus — replaces file-based operator steering with in-process queues."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass

__all__ = ["SteeringMessage", "SteeringBus"]


@dataclass(slots=True)
class SteeringMessage:
    id: str
    ts: float
    source: str
    challenge_id: str | None
    run_id: str | None
    message: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ts": self.ts,
            "source": self.source,
            "challenge_id": self.challenge_id,
            "run_id": self.run_id,
            "message": self.message,
        }


class SteeringBus:
    """Per-challenge async steering channel.

    Each active challenge gets a dedicated queue.  The orchestrator posts
    steering messages here; the AgentRunner reads them and injects them
    into the ChallengeSwarm via ``swarm.steering_messages``.
    """

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[SteeringMessage]] = {}
        self._lock = asyncio.Lock()

    async def create_channel(self, challenge_id: str) -> None:
        async with self._lock:
            if challenge_id not in self._queues:
                self._queues[challenge_id] = asyncio.Queue()

    async def remove_channel(self, challenge_id: str) -> None:
        async with self._lock:
            self._queues.pop(challenge_id, None)

    async def post(
        self,
        challenge_id: str,
        message: str,
        *,
        source: str = "operator",
        run_id: str | None = None,
    ) -> SteeringMessage:
        async with self._lock:
            queue = self._queues.get(challenge_id)
        if queue is None:
            raise RuntimeError(f"No steering channel for challenge {challenge_id}")

        msg = SteeringMessage(
            id=uuid.uuid4().hex,
            ts=time.time(),
            source=source,
            challenge_id=challenge_id,
            run_id=run_id,
            message=message,
        )
        await queue.put(msg)
        return msg

    def try_recv(self, challenge_id: str) -> SteeringMessage | None:
        queue = self._queues.get(challenge_id)
        if queue is None:
            return None
        try:
            return queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def recv_all(self, challenge_id: str) -> list[SteeringMessage]:
        queue = self._queues.get(challenge_id)
        if queue is None:
            return []
        messages: list[SteeringMessage] = []
        while True:
            try:
                messages.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return messages

    def has_channel(self, challenge_id: str) -> bool:
        return challenge_id in self._queues

    def active_channels(self) -> list[str]:
        return list(self._queues.keys())
