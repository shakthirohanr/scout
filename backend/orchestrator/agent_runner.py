"""In-process async agent runner — replaces subprocess-based solver execution."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.agents.swarm import ChallengeSwarm
from backend.cost_tracker import CostTracker
from backend.ctfd import CTFdClient
from backend.log_reader import list_trace_summaries, logs_directory
from backend.orchestrator.steering_bus import SteeringBus
from backend.prompts import ChallengeMeta
from backend.solver_base import FLAG_FOUND, SolverResult

__all__ = ["AgentRun", "AgentRunner"]

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AgentRun:
    run_id: str
    challenge_id: str | None
    challenge_dir: str
    challenge_name: str
    model_specs: list[str]
    status: str
    flag: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    exit_code: int | None
    output_log_path: str
    trace_ids: list[str]
    latest_trace_id: str | None
    _task: asyncio.Task | None = field(default=None, repr=False)
    _swarm: ChallengeSwarm | None = field(default=None, repr=False)
    _output_handle: Any = field(default=None, repr=False)

    def snapshot(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "challenge_id": self.challenge_id,
            "challenge_dir": self.challenge_dir,
            "challenge_name": self.challenge_name,
            "model_specs": self.model_specs,
            "status": self.status,
            "flag": self.flag,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "exit_code": self.exit_code,
            "output_log_path": self.output_log_path,
            "trace_ids": self.trace_ids,
            "latest_trace_id": self.latest_trace_id,
        }


def _is_pid_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    import os

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _timestamp_or_zero(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0


def _build_trace_snapshot(
    *,
    trace_ids: list[str] | None = None,
    challenge_id: str | None = None,
    run_started_at: datetime | None = None,
) -> dict[str, Any]:
    from backend.api.services.run_helpers import TERMINAL_TRACE_STATUS_TO_RUN_STATUS

    summaries = list_trace_summaries()
    if trace_ids:
        known_ids = set(trace_ids)
        relevant = [s for s in summaries if s.id in known_ids]
    elif challenge_id:
        relevant = [s for s in summaries if s.challenge_id == challenge_id]
        if run_started_at is not None:
            started_ts = run_started_at.timestamp()
            relevant = [s for s in relevant if _timestamp_or_zero(s.updated_at) >= started_ts]
    else:
        relevant = []

    ordered = sorted(relevant, key=lambda s: _timestamp_or_zero(s.updated_at), reverse=True)
    latest = ordered[0] if ordered else None
    latest_flag = next((s.flag for s in ordered if s.flag), None)
    mapped_status = TERMINAL_TRACE_STATUS_TO_RUN_STATUS.get(latest.status) if latest else None
    return {
        "trace_ids": [s.id for s in ordered],
        "latest_trace_id": latest.id if latest else None,
        "flag": latest_flag,
        "trace_status": mapped_status,
    }


class AgentRunner:
    """Spawns and manages ChallengeSwarm instances as in-process async tasks."""

    def __init__(self, steering_bus: SteeringBus) -> None:
        self._runs: dict[str, AgentRun] = {}
        self._steering_bus = steering_bus
        self._lock = asyncio.Lock()

    async def start(
        self,
        *,
        challenge_id: str | None,
        challenge_dir: str,
        challenge_name: str,
        model_specs: list[str],
        settings: Any,
        no_submit: bool = True,
        trace_ids_before: set[str] | None = None,
    ) -> AgentRun:
        run_id = uuid.uuid4().hex[:12]
        output_log_path = str(logs_directory() / f"api-run-{run_id}.log")
        Path(output_log_path).parent.mkdir(parents=True, exist_ok=True)

        now = datetime.now(UTC)
        run = AgentRun(
            run_id=run_id,
            challenge_id=challenge_id,
            challenge_dir=challenge_dir,
            challenge_name=challenge_name,
            model_specs=model_specs,
            status="starting",
            flag=None,
            created_at=now,
            started_at=now,
            finished_at=None,
            exit_code=None,
            output_log_path=output_log_path,
            trace_ids=[],
            latest_trace_id=None,
        )

        if challenge_id:
            await self._steering_bus.create_channel(challenge_id)

        task = asyncio.create_task(
            self._run_agent(run, settings, no_submit),
            name=f"agent-{run_id}",
        )
        run._task = task

        async with self._lock:
            self._runs[run_id] = run

        return run

    async def _run_agent(
        self,
        run: AgentRun,
        settings: Any,
        no_submit: bool,
    ) -> None:
        meta_path = Path(run.challenge_dir) / "metadata.yml"
        if not meta_path.exists():
            logger.error("No metadata.yml in %s", run.challenge_dir)
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
            run.exit_code = 1
            return

        try:
            meta = ChallengeMeta.from_yaml(meta_path)
        except Exception as exc:
            logger.error("Failed to parse metadata.yml: %s", exc)
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
            run.exit_code = 1
            return

        ctfd = CTFdClient(base_url=None, token="", username="", password="")
        cost_tracker = CostTracker()

        swarm = ChallengeSwarm(
            challenge_dir=run.challenge_dir,
            meta=meta,
            ctfd=ctfd,
            cost_tracker=cost_tracker,
            settings=settings,
            model_specs=run.model_specs,
            no_submit=no_submit,
            challenge_id=run.challenge_id,
        )
        run._swarm = swarm
        run.status = "running"

        steering_task = None
        if run.challenge_id:
            steering_task = asyncio.create_task(
                self._steering_loop(run, swarm),
                name=f"steering-{run.run_id}",
            )

        try:
            result: SolverResult | None = await swarm.run()
            if result and result.status == FLAG_FOUND:
                run.flag = result.flag
                run.status = "solved"
            else:
                run.status = "finished"
            run.exit_code = 0
        except asyncio.CancelledError:
            run.status = "cancelled"
            run.exit_code = -1
        except Exception as exc:
            logger.error("Agent run %s failed: %s", run.run_id, exc, exc_info=True)
            run.status = "failed"
            run.exit_code = 1
        finally:
            run.finished_at = datetime.now(UTC)
            await ctfd.close()

            if steering_task:
                steering_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await steering_task

            if run.challenge_id:
                await self._steering_bus.remove_channel(run.challenge_id)

            self._update_trace_ids(run)

    async def _steering_loop(self, run: AgentRun, swarm: ChallengeSwarm) -> None:
        while run.status in {"starting", "running"}:
            messages = self._steering_bus.recv_all(run.challenge_id or "")
            for msg in messages:
                steering_text = (
                    "Operator steering received. Prioritize this guidance.\n\n"
                    f"[{msg.source}] {msg.message}"
                )
                swarm.steering_messages.append(steering_text)
                if len(swarm.steering_messages) > 20:
                    swarm.steering_messages = swarm.steering_messages[-20:]
                for solver in swarm.solvers.values():
                    solver.bump(steering_text)
                logger.info("Applied steering to %d solver(s)", len(swarm.solvers))
            await asyncio.sleep(1.0)

    def _update_trace_ids(self, run: AgentRun) -> None:
        snapshot = _build_trace_snapshot(
            challenge_id=run.challenge_id,
            run_started_at=run.started_at,
        )
        run.trace_ids = snapshot["trace_ids"]
        run.latest_trace_id = snapshot["latest_trace_id"]
        if snapshot["flag"] and not run.flag:
            run.flag = snapshot["flag"]
        trace_status = snapshot["trace_status"]
        if trace_status and run.status not in {"cancelled", "gave_up"}:
            run.status = trace_status

    async def cancel(self, run_id: str) -> AgentRun:
        async with self._lock:
            run = self._runs.get(run_id)
        if run is None:
            raise KeyError(run_id)

        if run._swarm:
            run._swarm.kill()

        if run._task and not run._task.done():
            run._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await run._task

        run.status = "cancelled"
        run.finished_at = run.finished_at or datetime.now(UTC)
        run.exit_code = run.exit_code or -1
        return run

    async def cancel_for_challenge(self, challenge_id: str) -> list[AgentRun]:
        cancelled: list[AgentRun] = []
        async with self._lock:
            runs = list(self._runs.values())
        for run in runs:
            if run.challenge_id == challenge_id and run.status in {"starting", "running"}:
                try:
                    cancelled.append(await self.cancel(run.run_id))
                except KeyError:
                    continue
        return cancelled

    async def remove_run(self, run_id: str) -> None:
        async with self._lock:
            self._runs.pop(run_id, None)

    async def remove_runs_for_challenge(self, challenge_id: str) -> None:
        async with self._lock:
            to_remove = [rid for rid, run in self._runs.items() if run.challenge_id == challenge_id]
            for rid in to_remove:
                self._runs.pop(rid, None)

    def get_run(self, run_id: str) -> AgentRun | None:
        return self._runs.get(run_id)

    def list_runs(self) -> list[AgentRun]:
        return list(self._runs.values())

    def active_runs_for_challenge(self, challenge_id: str) -> list[AgentRun]:
        return [
            run
            for run in self._runs.values()
            if run.challenge_id == challenge_id and run.status in {"starting", "running"}
        ]

    def has_active_run_for_challenge(self, challenge_id: str) -> bool:
        return any(
            run.challenge_id == challenge_id and run.status in {"starting", "running"}
            for run in self._runs.values()
        )

    async def shutdown(self) -> None:
        for run_id, run in list(self._runs.items()):
            if run.status in {"starting", "running"}:
                self._write_graceful_shutdown_marker(run)
            with contextlib.suppress(Exception):
                await self.cancel(run_id)

    @staticmethod
    def _write_graceful_shutdown_marker(run: AgentRun) -> None:
        import json as _json

        for trace_id in run.trace_ids:
            path = logs_directory() / trace_id
            if not path.is_file():
                continue
            marker = {
                "ts": __import__("time").time(),
                "type": "finish",
                "status": "cancelled",
                "flag": None,
                "confirmed": False,
                "graceful_shutdown": True,
            }
            try:
                with open(path, "a", encoding="utf-8") as handle:
                    handle.write(_json.dumps(marker, ensure_ascii=True) + "\n")
            except Exception:
                continue
