"""AgentOrchestrator — central point for agent lifecycle and health monitoring."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.api.database import session_scope
from backend.api.repositories.ctf_repository import (
    clear_challenge_session_data,
    get_challenge_by_id,
    sync_challenge_with_run,
)
from backend.api.repositories.run_repository import (
    ACTIVE_RUN_STATUSES,
    delete_runs_for_challenge,
    get_run_by_id,
    list_active_runs,
    upsert_run,
)
from backend.api.repositories.run_repository import (
    list_runs as list_persisted_runs,
)
from backend.api.services.mappers import solver_run_to_dict
from backend.config import Settings, get_settings
from backend.log_reader import list_trace_summaries, logs_directory
from backend.orchestrator.agent_runner import AgentRun, AgentRunner
from backend.orchestrator.steering_bus import SteeringBus
from backend.run_config import load_ui_config
from backend.sandbox import cleanup_challenge_containers

__all__ = ["AgentOrchestrator"]

logger = logging.getLogger(__name__)

HEALTH_CHECK_INTERVAL_S = 5.0
MAX_STUCK_DURATION_S = 600.0
AUTO_KILL_AFTER_FLAG_S = 10.0


class AgentOrchestrator:
    """Central orchestrator for all agent operations.

    Responsibilities:
    - Spawn agents as in-process async tasks (no subprocesses)
    - Periodic health monitoring (stuck detection, auto-kill on flag)
    - Steer running agents via async bus (no file polling)
    - Kill/cancel agents on demand
    - Persist run state to database
    - Clean up orphan containers
    """

    def __init__(self) -> None:
        self.steering_bus = SteeringBus()
        self.agent_runner = AgentRunner(self.steering_bus)
        self._health_task: asyncio.Task | None = None
        self._sync_task: asyncio.Task | None = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True

        from backend.sandbox import cleanup_orphan_containers, configure_semaphore

        settings = get_settings()
        configure_semaphore(settings.max_concurrent_challenges * 4)
        with contextlib.suppress(Exception):
            await cleanup_orphan_containers()

        self._health_task = asyncio.create_task(self._health_loop(), name="orchestrator-health")
        self._sync_task = asyncio.create_task(self._sync_loop(), name="orchestrator-sync")
        logger.info("AgentOrchestrator started")

    async def shutdown(self) -> None:
        if self._health_task:
            self._health_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._health_task
            self._health_task = None

        if self._sync_task:
            self._sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sync_task
            self._sync_task = None

        await self.agent_runner.shutdown()
        self._started = False
        logger.info("AgentOrchestrator shut down")

    # ── Agent lifecycle ────────────────────────────────────────────────

    async def spawn(
        self,
        *,
        challenge_id: str | None,
        challenge_dir: str,
        challenge_name: str,
        model_specs: list[str] | None = None,
        agent_count: int = 1,
        settings: Settings | None = None,
        no_submit: bool = True,
    ) -> list[dict[str, Any]]:
        settings = settings or get_settings()
        config = load_ui_config()
        specs = model_specs or config.models or [settings.default_solver_model]
        count = max(1, agent_count)

        results: list[dict[str, Any]] = []
        for i in range(count):
            trace_ids_before = {s.id for s in list_trace_summaries()}
            run_name = f"{challenge_name}#{i + 1}" if count > 1 else challenge_name

            run = await self.agent_runner.start(
                challenge_id=challenge_id,
                challenge_dir=challenge_dir,
                challenge_name=run_name,
                model_specs=specs,
                settings=settings,
                no_submit=no_submit,
                trace_ids_before=trace_ids_before,
            )
            self._persist_agent_run(run)
            results.append(run.snapshot())

        return results

    async def kill(self, run_id: str) -> dict[str, Any]:
        run = await self.agent_runner.cancel(run_id)
        self._append_cancelled_finish_events(run.trace_ids)
        self._persist_agent_run(run)
        return run.snapshot()

    async def kill_challenge(
        self, challenge_id: str, challenge_path: str | None = None
    ) -> dict[str, Any]:
        cancelled_runs = await self.agent_runner.cancel_for_challenge(challenge_id)
        for run in cancelled_runs:
            self._append_cancelled_finish_events(run.trace_ids)
            self._persist_agent_run(run)

        containers_removed = 0
        if challenge_path:
            with contextlib.suppress(Exception):
                containers_removed = await cleanup_challenge_containers(challenge_path)

        return {
            "cancelled_runs": [r.snapshot() for r in cancelled_runs],
            "cancelled_count": len(cancelled_runs),
            "containers_removed": containers_removed,
        }

    async def steer(
        self,
        challenge_id: str,
        message: str,
        source: str = "operator",
    ) -> dict[str, Any]:
        text = message.strip()
        if not text:
            raise ValueError("message must not be empty")

        active = self.agent_runner.active_runs_for_challenge(challenge_id)
        if not active:
            raise RuntimeError("No active run for this challenge.")

        active_run = max(active, key=lambda r: r.started_at or r.created_at)
        msg = await self.steering_bus.post(
            challenge_id,
            text,
            source=source,
            run_id=active_run.run_id,
        )
        return {
            "run_id": active_run.run_id,
            "challenge_id": challenge_id,
            "queued": text,
            "source": source,
            "created_at": datetime.fromtimestamp(msg.ts, tz=UTC).isoformat(),
        }

    # ── Health monitoring ──────────────────────────────────────────────

    async def _health_loop(self) -> None:
        while True:
            await asyncio.sleep(HEALTH_CHECK_INTERVAL_S)
            try:
                await self._check_agents()
            except Exception as exc:
                logger.warning("Health check error: %s", exc)

    async def _check_agents(self) -> None:
        now = time.time()
        for run in self.agent_runner.list_runs():
            if run.status not in {"starting", "running"}:
                continue

            if run.flag and run.status == "solved":
                elapsed = now - (run.finished_at or datetime.now(UTC)).timestamp()
                if elapsed > AUTO_KILL_AFTER_FLAG_S:
                    logger.info("Auto-killing solved run %s", run.run_id)
                    with contextlib.suppress(Exception):
                        await self.kill(run.run_id)

    # ── DB sync ────────────────────────────────────────────────────────

    async def _sync_loop(self) -> None:
        while True:
            await asyncio.sleep(5.0)
            try:
                self.sync_runs()
            except Exception as exc:
                logger.warning("Sync error: %s", exc)

    def sync_runs(self) -> None:
        for run in self.agent_runner.list_runs():
            self._persist_agent_run(run)

        with session_scope() as session:
            for persisted_run in list_active_runs(session):
                existing = self.agent_runner.get_run(persisted_run.id)
                if existing:
                    continue
                self._sync_detached_run(session, persisted_run)

    def _sync_detached_run(self, session, run) -> None:
        from backend.api.services.run_manager_service import RunManager

        challenge_name = None
        if run.challenge_id:
            challenge = get_challenge_by_id(session, run.challenge_id)
            challenge_name = challenge.name if challenge else None
        snapshot = RunManager._snapshot_persisted_run(run, challenge_name=challenge_name)
        persisted = upsert_run(session, snapshot)
        if persisted.challenge_id:
            sync_challenge_with_run(session, challenge_id=persisted.challenge_id, run=persisted)

    # ── Persistence ────────────────────────────────────────────────────

    @staticmethod
    def _persist_agent_run(run: AgentRun) -> None:
        with session_scope() as session:
            upsert_run(
                session,
                {
                    "id": run.run_id,
                    "challenge_id": run.challenge_id,
                    "mode": "solve",
                    "status": run.status,
                    "command": [],
                    "workdir": run.challenge_dir,
                    "pid": None,
                    "output_log_path": run.output_log_path,
                    "steering_log_path": "",
                    "flag": run.flag,
                    "latest_trace_id": run.latest_trace_id,
                    "trace_ids": run.trace_ids,
                    "exit_code": run.exit_code,
                    "created_at": run.created_at,
                    "started_at": run.started_at,
                    "finished_at": run.finished_at,
                },
            )
            if run.challenge_id:
                persisted = get_run_by_id(session, run.run_id)
                if persisted:
                    sync_challenge_with_run(session, challenge_id=run.challenge_id, run=persisted)

    # ── Data deletion ──────────────────────────────────────────────────

    async def delete_challenge_data(self, challenge_id: str) -> dict[str, Any]:
        self.sync_runs()

        await self.agent_runner.remove_runs_for_challenge(challenge_id)

        with session_scope() as session:
            challenge = get_challenge_by_id(session, challenge_id)
            if challenge is None:
                raise KeyError(challenge_id)
            if challenge.state in ACTIVE_RUN_STATUSES:
                raise RuntimeError("Challenge is still running. Kill it before deleting.")

            challenge_name = challenge.name
            runs = delete_runs_for_challenge(session, challenge_id)
            cleared = clear_challenge_session_data(session, challenge_id)
            challenge_payload = {"challenge": cleared, "deleted_runs": len(runs)}

        files_removed = self._delete_run_artifacts(runs, challenge_name=challenge_name)
        return {
            "challenge": challenge_payload["challenge"],
            "deleted_runs": challenge_payload["deleted_runs"],
            "files_removed": files_removed,
        }

    @staticmethod
    def _delete_run_artifacts(runs: list[Any], challenge_name: str | None = None) -> int:
        removed = 0
        trace_ids_from_runs: set[str] = set()
        for run in runs:
            try:
                trace_ids_from_runs.update(json.loads(run.trace_ids_json or "[]"))
            except Exception:
                continue
            for path_value in (run.output_log_path, run.steering_log_path):
                path = Path(path_value).expanduser()
                if not path_value or not path.exists():
                    continue
                try:
                    path.unlink()
                    removed += 1
                except Exception:
                    continue

        trace_ids = trace_ids_from_runs
        if challenge_name:
            trace_ids.update(
                s.id for s in list_trace_summaries() if s.challenge_name == challenge_name
            )

        for trace_id in trace_ids:
            path = logs_directory() / trace_id
            if not path.exists():
                continue
            try:
                path.unlink()
                removed += 1
            except Exception:
                continue

        return removed

    @staticmethod
    def _append_cancelled_finish_events(trace_ids: list[str]) -> None:
        if not trace_ids:
            return
        for trace_id in trace_ids:
            path = logs_directory() / trace_id
            if not path.is_file():
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue

            has_finish = False
            for line in reversed(lines):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except Exception:
                    continue
                if event.get("type") == "finish":
                    has_finish = True
                break

            if has_finish:
                continue

            finish_event = {
                "ts": time.time(),
                "type": "finish",
                "status": "cancelled",
                "flag": None,
                "confirmed": False,
            }
            try:
                with open(path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(finish_event, ensure_ascii=True) + "\n")
            except Exception:
                continue

    # ── Read operations ────────────────────────────────────────────────

    def list_runs(self) -> list[dict[str, Any]]:
        self.sync_runs()
        with session_scope() as session:
            runs = list_persisted_runs(session)
            return [solver_run_to_dict(run) for run in runs]

    def get_run(self, run_id: str) -> dict[str, Any]:
        active = self.agent_runner.get_run(run_id)
        if active:
            self._persist_agent_run(active)
            return active.snapshot()

        with session_scope() as session:
            persisted = get_run_by_id(session, run_id)
            if persisted is None:
                raise KeyError(run_id)
            return solver_run_to_dict(persisted)

    def has_active_run(self, challenge_id: str) -> bool:
        return self.agent_runner.has_active_run_for_challenge(challenge_id)
