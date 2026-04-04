"""Managed solver run lifecycle with process control and DB persistence."""

from __future__ import annotations

import asyncio
import collections
import json
import logging
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.api.database import session_scope
from backend.api.repositories.run_repository import upsert_run
from backend.config import Settings
from backend.log_reader import list_trace_summaries, logs_directory
from backend.run_config import SolverRunConfig, build_cli_command, resolve_workdir
from backend.sandbox import cleanup_challenge_containers


logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


@dataclass(slots=True)
class ManagedRun:
    run_id: str
    config: SolverRunConfig
    command: list[str]
    workdir: str
    output_log_path: str
    trace_ids_before: set[str]
    challenge_id: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: str = "starting"
    pid: int | None = None
    exit_code: int | None = None
    process: subprocess.Popen[str] | None = field(default=None, repr=False)
    _output_handle: Any = field(default=None, repr=False)

    def refresh(self) -> None:
        if not self.process:
            return
        return_code = self.process.poll()
        if return_code is None:
            if self.status == "starting":
                self.status = "running"
            return

        self.exit_code = return_code
        if self.finished_at is None:
            self.finished_at = utcnow()
        if self.status not in {"cancelled", "failed", "finished"}:
            self.status = "finished" if return_code == 0 else "failed"
        if self._output_handle is not None:
            try:
                self._output_handle.close()
            except Exception:
                pass
            self._output_handle = None

    def snapshot(self) -> dict[str, Any]:
        self.refresh()
        trace_ids_after = {
            summary.id
            for summary in list_trace_summaries()
            if summary.id not in self.trace_ids_before
        }
        return {
            "run_id": self.run_id,
            "status": self.status,
            "config": self.config.model_dump(mode="json"),
            "command": self.command,
            "workdir": self.workdir,
            "pid": self.pid,
            "challenge_id": self.challenge_id,
            "created_at": as_iso(self.created_at),
            "started_at": as_iso(self.started_at),
            "finished_at": as_iso(self.finished_at),
            "exit_code": self.exit_code,
            "output_log_path": self.output_log_path,
            "trace_ids": sorted(trace_ids_after),
        }


class RunManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, ManagedRun] = {}

    def _current_trace_ids(self) -> set[str]:
        return {summary.id for summary in list_trace_summaries()}

    def _persist_run(self, run: ManagedRun) -> None:
        snapshot = run.snapshot()
        with session_scope() as session:
            upsert_run(
                session,
                {
                    "id": run.run_id,
                    "challenge_id": run.challenge_id,
                    "mode": run.config.mode,
                    "status": snapshot["status"],
                    "command": snapshot["command"],
                    "workdir": snapshot["workdir"],
                    "pid": snapshot["pid"],
                    "output_log_path": snapshot["output_log_path"],
                    "trace_ids": snapshot["trace_ids"],
                    "exit_code": snapshot["exit_code"],
                    "created_at": run.created_at,
                    "started_at": run.started_at,
                    "finished_at": run.finished_at,
                },
            )

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

    @staticmethod
    def _cleanup_challenge_containers(challenge_path: str | None) -> int:
        if not challenge_path:
            return 0
        try:
            return asyncio.run(cleanup_challenge_containers(challenge_path))
        except Exception as exc:
            logger.warning("Challenge container cleanup failed for %s: %s", challenge_path, exc)
            return 0

    @staticmethod
    def _validate_config(config: SolverRunConfig, settings: Settings) -> None:
        challenge_dir = Path(config.challenge_dir).expanduser().resolve()
        challenges_dir = Path(config.challenges_dir).expanduser().resolve()

        if config.mode in {"solve", "solve-local"}:
            if not challenge_dir.exists():
                raise ValueError(f"Challenge directory not found: {challenge_dir}")
            if not (challenge_dir / "metadata.yml").exists():
                raise ValueError(f"No metadata.yml found in {challenge_dir}")
        elif config.mode == "solve-dir":
            if not challenges_dir.exists():
                raise ValueError(f"Challenges directory not found: {challenges_dir}")
        elif config.mode == "ctfd":
            ctfd_url = config.ctfd_url or settings.ctfd_url
            if not ctfd_url:
                raise ValueError("ctfd mode requires ctfd_url in config or environment")
            if not settings.ctfd_token and not (settings.ctfd_user and settings.ctfd_pass):
                raise ValueError(
                    "ctfd mode requires CTFD_TOKEN or CTFD_USER/CTFD_PASS in environment"
                )

    def start(
        self,
        config: SolverRunConfig,
        settings: Settings,
        challenge_id: str | None = None,
    ) -> dict[str, Any]:
        self._validate_config(config, settings)

        run_id = uuid.uuid4().hex[:12]
        output_log_path = logs_directory() / f"api-run-{run_id}.log"
        output_log_path.parent.mkdir(parents=True, exist_ok=True)
        command = build_cli_command(config, ctfd_url_override=settings.ctfd_url or config.ctfd_url)
        workdir = resolve_workdir(config)

        output_handle = open(output_log_path, "a", encoding="utf-8")
        process = subprocess.Popen(
            command,
            cwd=workdir,
            stdout=output_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )

        run = ManagedRun(
            run_id=run_id,
            config=config,
            command=command,
            workdir=workdir,
            output_log_path=str(output_log_path),
            trace_ids_before=self._current_trace_ids(),
            challenge_id=challenge_id,
            started_at=utcnow(),
            status="running",
            pid=process.pid,
            process=process,
            _output_handle=output_handle,
        )

        with self._lock:
            self._runs[run_id] = run

        self._persist_run(run)
        return run.snapshot()

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            runs = list(self._runs.values())

        snapshots = [run.snapshot() for run in runs]
        for run in runs:
            self._persist_run(run)

        return sorted(
            snapshots,
            key=lambda item: item["started_at"] or item["created_at"],
            reverse=True,
        )

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            run = self._runs.get(run_id)
        if not run:
            raise KeyError(run_id)

        self._persist_run(run)
        return run.snapshot()

    def cancel(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            run = self._runs.get(run_id)
        if not run:
            raise KeyError(run_id)

        run.refresh()
        if run.process and run.process.poll() is None:
            try:
                run.process.send_signal(signal.SIGINT)
                run.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                run.process.terminate()
                try:
                    run.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    run.process.kill()
                    run.process.wait(timeout=5)

        run.status = "cancelled"
        run.finished_at = run.finished_at or utcnow()
        run.exit_code = run.process.poll() if run.process else run.exit_code
        cancelled_snapshot = run.snapshot()
        self._append_cancelled_finish_events(cancelled_snapshot.get("trace_ids", []))
        self._persist_run(run)
        return run.snapshot()

    def terminate_challenge(self, challenge_id: str, challenge_path: str | None = None) -> dict[str, Any]:
        with self._lock:
            runs = [
                run
                for run in self._runs.values()
                if run.challenge_id == challenge_id
            ]

        active_run_ids: list[str] = []
        for run in runs:
            run.refresh()
            if run.status in {"starting", "running"}:
                active_run_ids.append(run.run_id)

        cancelled_runs: list[dict[str, Any]] = []
        for run_id in active_run_ids:
            try:
                cancelled_runs.append(self.cancel(run_id))
            except KeyError:
                continue

        containers_removed = self._cleanup_challenge_containers(challenge_path)
        return {
            "cancelled_runs": cancelled_runs,
            "cancelled_count": len(cancelled_runs),
            "containers_removed": containers_removed,
        }

    def tail_output(self, run_id: str, lines: int = 200) -> dict[str, str]:
        with self._lock:
            run = self._runs.get(run_id)
        if not run:
            raise KeyError(run_id)

        run.refresh()
        path = Path(run.output_log_path)
        if not path.exists():
            content = ""
        else:
            with open(path, encoding="utf-8") as handle:
                content = "".join(collections.deque(handle, maxlen=max(lines, 1)))
        self._persist_run(run)
        return {
            "run_id": run_id,
            "log_path": run.output_log_path,
            "content": content,
        }

    def shutdown(self) -> None:
        with self._lock:
            run_ids = list(self._runs.keys())
        for run_id in run_ids:
            try:
                self.cancel(run_id)
            except Exception:
                pass
