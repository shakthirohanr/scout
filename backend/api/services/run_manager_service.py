"""Managed solver run lifecycle with process control and DB persistence."""

from __future__ import annotations

import asyncio
import collections
import contextlib
import json
import logging
import os
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
 
__all__ = ["ManagedRun", "RunManager"]

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
    list_active_runs_for_challenge,
    upsert_run,
)
from backend.api.repositories.run_repository import (
    list_runs as list_persisted_runs,
)
from backend.api.services.mappers import solver_run_to_dict
from backend.api.utils import utcnow
from backend.config import Settings
from backend.log_reader import TraceSummary, list_trace_summaries, logs_directory
from backend.run_config import SolverRunConfig, build_cli_command, resolve_workdir
from backend.sandbox import cleanup_challenge_containers

logger = logging.getLogger(__name__)

TERMINAL_TRACE_STATUS_TO_RUN_STATUS = {
    "solved": "solved",
    "gave_up": "gave_up",
    "cancelled": "cancelled",
    "error": "failed",
}




def as_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _timestamp_or_zero(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0


def _is_pid_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

    return True


def _terminate_pid(pid: int | None) -> None:
    if not pid or pid <= 0:
        return
    if not _is_pid_running(pid):
        return

    signal_plan = (
        (signal.SIGINT, 5.0),
        (signal.SIGTERM, 5.0),
        (signal.SIGKILL, 2.0),
    )
    for sig, timeout_s in signal_plan:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if not _is_pid_running(pid):
                return
            time.sleep(0.1)


def _sort_trace_summaries_by_recency(summaries: list[TraceSummary]) -> list[TraceSummary]:
    return sorted(
        summaries,
        key=lambda summary: _timestamp_or_zero(summary.updated_at),
        reverse=True,
    )


def _build_trace_snapshot(
    *,
    trace_ids_before: set[str] | None = None,
    trace_ids: list[str] | None = None,
    challenge_id: str | None = None,
    challenge_name: str | None = None,
    run_started_at: datetime | None = None,
) -> dict[str, Any]:
    summaries = list_trace_summaries()
    if trace_ids:
        known_ids = set(trace_ids)
        relevant = [summary for summary in summaries if summary.id in known_ids]
    elif challenge_id:
        relevant = [summary for summary in summaries if summary.challenge_id == challenge_id]
        if run_started_at is not None:
            started_ts = run_started_at.timestamp()
            relevant = [
                summary for summary in relevant
                if _timestamp_or_zero(summary.updated_at) >= started_ts
            ]
    elif trace_ids_before is not None:
        relevant = [summary for summary in summaries if summary.id not in trace_ids_before]
    elif challenge_name:
        relevant = [summary for summary in summaries if summary.challenge_name == challenge_name]
    else:
        relevant = []

    ordered = _sort_trace_summaries_by_recency(relevant)
    latest = ordered[0] if ordered else None
    latest_flag = next((summary.flag for summary in ordered if summary.flag), None)
    mapped_status = (
        TERMINAL_TRACE_STATUS_TO_RUN_STATUS.get(latest.status) if latest is not None else None
    )

    return {
        "trace_ids": [summary.id for summary in ordered],
        "latest_trace_id": latest.id if latest else None,
        "flag": latest_flag,
        "trace_status": mapped_status,
    }


@dataclass(slots=True)
class ManagedRun:
    run_id: str
    config: SolverRunConfig
    command: list[str]
    workdir: str
    output_log_path: str
    trace_ids_before: set[str]
    trace_ids: list[str] = field(default_factory=list)
    steering_log_path: str | None = None
    challenge_id: str | None = None
    latest_trace_id: str | None = None
    flag: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: str = "starting"
    pid: int | None = None
    exit_code: int | None = None
    process: subprocess.Popen[str] | None = field(default=None, repr=False)
    _output_handle: Any = field(default=None, repr=False)

    def refresh(self) -> None:
        if self.process:
            return_code = self.process.poll()
            if return_code is None:
                if self.status == "starting":
                    self.status = "running"
                return

            self.exit_code = return_code
            if self.finished_at is None:
                self.finished_at = utcnow()
            if self.status not in {"cancelled", "failed", "finished", "solved", "gave_up"}:
                self.status = "finished" if return_code == 0 else "failed"
            if self._output_handle is not None:
                with contextlib.suppress(Exception):
                    self._output_handle.close()
                self._output_handle = None
            return

        if _is_pid_running(self.pid):
            if self.status == "starting":
                self.status = "running"
            return

        if self.status in ACTIVE_RUN_STATUSES:
            self.status = "finished"
            self.finished_at = self.finished_at or utcnow()

    def snapshot(self) -> dict[str, Any]:
        self.refresh()
        trace_snapshot = _build_trace_snapshot(
            trace_ids=self.trace_ids,
            trace_ids_before=None if self.trace_ids else self.trace_ids_before,
            challenge_id=self.challenge_id,
            run_started_at=self.started_at,
        )
        trace_status = trace_snapshot["trace_status"]
        if trace_status and self.status not in {"cancelled", "gave_up"}:
            self.status = trace_status
            if trace_status not in ACTIVE_RUN_STATUSES:
                self.finished_at = self.finished_at or utcnow()

        # Auto-kill: if a flag was found and the process is still running, terminate it
        if trace_snapshot["flag"] and self.status == "solved" and self.process and self.process.poll() is None:
            logger.info("Flag found for run %s — auto-killing agent process", self.run_id)
            try:
                self.process.send_signal(signal.SIGINT)
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            except Exception as exc:
                logger.warning("Auto-kill failed for run %s: %s", self.run_id, exc)
            self.finished_at = self.finished_at or utcnow()

        self.latest_trace_id = trace_snapshot["latest_trace_id"]
        self.flag = trace_snapshot["flag"]
        self.trace_ids = trace_snapshot["trace_ids"]
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
            "steering_log_path": self.steering_log_path,
            "flag": self.flag,
            "latest_trace_id": self.latest_trace_id,
            "trace_ids": self.trace_ids,
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
            persisted_run = upsert_run(
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
                    "steering_log_path": snapshot["steering_log_path"],
                    "flag": snapshot["flag"],
                    "latest_trace_id": snapshot["latest_trace_id"],
                    "trace_ids": snapshot["trace_ids"],
                    "exit_code": snapshot["exit_code"],
                    "created_at": run.created_at,
                    "started_at": run.started_at,
                    "finished_at": run.finished_at,
                },
            )
            if run.challenge_id:
                sync_challenge_with_run(
                    session,
                    challenge_id=run.challenge_id,
                    run=persisted_run,
                )

    @staticmethod
    def _snapshot_persisted_run(
        run: Any,
        challenge_name: str | None = None,
    ) -> dict[str, Any]:
        trace_ids = json.loads(run.trace_ids_json or "[]")
        trace_snapshot = _build_trace_snapshot(
            trace_ids=trace_ids,
            challenge_id=run.challenge_id,
            run_started_at=run.started_at,
            challenge_name=challenge_name if not trace_ids else None,
        )

        status = str(run.status)
        if status in ACTIVE_RUN_STATUSES and not _is_pid_running(run.pid):
            status = trace_snapshot["trace_status"] or "finished"
        elif trace_snapshot["trace_status"] and status not in {"cancelled", "gave_up"}:
            status = trace_snapshot["trace_status"]

        finished_at = run.finished_at
        if status not in ACTIVE_RUN_STATUSES and finished_at is None:
            finished_at = utcnow()

        return {
            "id": run.id,
            "challenge_id": run.challenge_id,
            "mode": run.mode,
            "status": status,
            "command": json.loads(run.command_json or "[]"),
            "workdir": run.workdir,
            "pid": run.pid if _is_pid_running(run.pid) else None,
            "output_log_path": run.output_log_path,
            "steering_log_path": run.steering_log_path,
            "flag": trace_snapshot["flag"] or run.flag,
            "latest_trace_id": trace_snapshot["latest_trace_id"] or run.latest_trace_id,
            "trace_ids": trace_snapshot["trace_ids"] or trace_ids,
            "exit_code": run.exit_code,
            "created_at": run.created_at,
            "started_at": run.started_at,
            "finished_at": finished_at,
        }

    @staticmethod
    def _persist_detached_run(
        session,
        run: Any,
        challenge_name: str | None = None,
    ) -> dict[str, Any]:
        snapshot = RunManager._snapshot_persisted_run(run, challenge_name=challenge_name)
        persisted_run = upsert_run(session, snapshot)
        if persisted_run.challenge_id:
            sync_challenge_with_run(
                session,
                challenge_id=persisted_run.challenge_id,
                run=persisted_run,
            )
        return solver_run_to_dict(persisted_run)

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
                summary.id
                for summary in list_trace_summaries()
                if summary.challenge_name == challenge_name
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
        steering_log_path = logs_directory() / f"steer-{run_id}.jsonl"
        output_log_path.parent.mkdir(parents=True, exist_ok=True)
        steering_log_path.touch(exist_ok=True)
        command = build_cli_command(config, ctfd_url_override=settings.ctfd_url or config.ctfd_url)
        workdir = resolve_workdir(config)
        trace_ids_before = self._current_trace_ids()

        process_env = os.environ.copy()
        process_env["CTF_AGENT_STEERING_FILE"] = str(steering_log_path)
        if challenge_id:
            process_env["CTF_AGENT_CHALLENGE_ID"] = challenge_id

        output_handle = open(output_log_path, "a", encoding="utf-8")
        try:
            process = subprocess.Popen(
                command,
                cwd=workdir,
                stdout=output_handle,
                stderr=subprocess.STDOUT,
                text=True,
                env=process_env,
            )
        except Exception:
            output_handle.close()
            raise

        run = ManagedRun(
            run_id=run_id,
            config=config,
            command=command,
            workdir=workdir,
            output_log_path=str(output_log_path),
            steering_log_path=str(steering_log_path),
            trace_ids_before=trace_ids_before,
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

    def sync_runs(self) -> None:
        with self._lock:
            in_memory_runs = list(self._runs.values())
            in_memory_run_ids = {run.run_id for run in in_memory_runs}

        for run in in_memory_runs:
            self._persist_run(run)

        with session_scope() as session:
            for persisted_run in list_active_runs(session):
                if persisted_run.id in in_memory_run_ids:
                    continue

                challenge_name = None
                if persisted_run.challenge_id:
                    challenge = get_challenge_by_id(session, persisted_run.challenge_id)
                    challenge_name = challenge.name if challenge else None
                self._persist_detached_run(
                    session,
                    persisted_run,
                    challenge_name=challenge_name,
                )

    def list_runs(self) -> list[dict[str, Any]]:
        self.sync_runs()
        with session_scope() as session:
            runs = list_persisted_runs(session)
            return [solver_run_to_dict(run) for run in runs]

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            run = self._runs.get(run_id)
        if run is not None:
            self._persist_run(run)
            return run.snapshot()

        with session_scope() as session:
            persisted_run = get_run_by_id(session, run_id)
            if persisted_run is None:
                raise KeyError(run_id)

            challenge_name = None
            if persisted_run.challenge_id:
                challenge = get_challenge_by_id(session, persisted_run.challenge_id)
                challenge_name = challenge.name if challenge else None
            return self._persist_detached_run(
                session,
                persisted_run,
                challenge_name=challenge_name,
            )

    def cancel(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            run = self._runs.get(run_id)
        if run is not None:
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
            elif _is_pid_running(run.pid):
                _terminate_pid(run.pid)

            run.status = "cancelled"
            run.finished_at = run.finished_at or utcnow()
            run.exit_code = run.process.poll() if run.process else run.exit_code
            cancelled_snapshot = run.snapshot()
            self._append_cancelled_finish_events(cancelled_snapshot.get("trace_ids", []))
            self._persist_run(run)
            return run.snapshot()

        with session_scope() as session:
            persisted_run = get_run_by_id(session, run_id)
            if persisted_run is None:
                raise KeyError(run_id)

            challenge_name = None
            if persisted_run.challenge_id:
                challenge = get_challenge_by_id(session, persisted_run.challenge_id)
                challenge_name = challenge.name if challenge else None

            _terminate_pid(persisted_run.pid)
            snapshot = self._snapshot_persisted_run(
                persisted_run,
                challenge_name=challenge_name,
            )
            snapshot["status"] = "cancelled"
            snapshot["finished_at"] = snapshot["finished_at"] or utcnow()
            self._append_cancelled_finish_events(snapshot["trace_ids"])
            persisted_run = upsert_run(session, snapshot)
            if persisted_run.challenge_id:
                sync_challenge_with_run(
                    session,
                    challenge_id=persisted_run.challenge_id,
                    run=persisted_run,
                )
            return solver_run_to_dict(persisted_run)

    def terminate_challenge(self, challenge_id: str, challenge_path: str | None = None) -> dict[str, Any]:
        self.sync_runs()
        with session_scope() as session:
            active_runs = list_active_runs_for_challenge(session, challenge_id)

        cancelled_runs: list[dict[str, Any]] = []
        for run in active_runs:
            try:
                cancelled_runs.append(self.cancel(run.id))
            except KeyError:
                continue

        containers_removed = self._cleanup_challenge_containers(challenge_path)
        return {
            "cancelled_runs": cancelled_runs,
            "cancelled_count": len(cancelled_runs),
            "containers_removed": containers_removed,
        }

    def delete_challenge_data(self, challenge_id: str) -> dict[str, Any]:
        self.sync_runs()

        # Evict matching in-memory runs so later syncs cannot recreate deleted DB rows.
        with self._lock:
            for run_id, run in list(self._runs.items()):
                if run.challenge_id == challenge_id:
                    self._runs.pop(run_id, None)

        with session_scope() as session:
            challenge = get_challenge_by_id(session, challenge_id)
            if challenge is None:
                raise KeyError(challenge_id)
            if challenge.state in ACTIVE_RUN_STATUSES:
                raise RuntimeError("Challenge is still running. Kill it before deleting.")

            challenge_name = challenge.name
            runs = delete_runs_for_challenge(session, challenge_id)
            cleared_challenge = clear_challenge_session_data(session, challenge_id)
            challenge_payload = {
                "challenge": cleared_challenge,
                "deleted_runs": len(runs),
            }

        files_removed = self._delete_run_artifacts(runs, challenge_name=challenge_name)
        return {
            "challenge": challenge_payload["challenge"],
            "deleted_runs": challenge_payload["deleted_runs"],
            "files_removed": files_removed,
        }

    def tail_output(self, run_id: str, lines: int = 200) -> dict[str, str]:
        with self._lock:
            run = self._runs.get(run_id)
        if run is not None:
            run.refresh()
            log_path = run.output_log_path
            self._persist_run(run)
        else:
            with session_scope() as session:
                persisted_run = get_run_by_id(session, run_id)
                if persisted_run is None:
                    raise KeyError(run_id)
                log_path = persisted_run.output_log_path

        path = Path(log_path)
        if not path.exists():
            content = ""
        else:
            with open(path, encoding="utf-8") as handle:
                content = "".join(collections.deque(handle, maxlen=max(lines, 1)))
        return {
            "run_id": run_id,
            "log_path": log_path,
            "content": content,
        }

    def steer_challenge(self, challenge_id: str, message: str, source: str = "operator") -> dict[str, Any]:
        text = message.strip()
        if not text:
            raise ValueError("message must not be empty")

        self.sync_runs()
        with session_scope() as session:
            active_runs = list_active_runs_for_challenge(session, challenge_id)
            if not active_runs:
                raise RuntimeError("No active run for this challenge.")

            active_run = max(
                active_runs,
                key=lambda run: run.started_at or run.created_at,
            )
            if not active_run.steering_log_path:
                raise RuntimeError("Steering is not available for the active run.")

            steering_event = {
                "id": uuid.uuid4().hex,
                "ts": time.time(),
                "type": "operator_steer",
                "source": source.strip() or "operator",
                "challenge_id": challenge_id,
                "run_id": active_run.id,
                "message": text,
            }

            steering_path = Path(active_run.steering_log_path)
            steering_path.parent.mkdir(parents=True, exist_ok=True)
            with open(steering_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(steering_event, ensure_ascii=True) + "\n")

            return {
                "run_id": active_run.id,
                "challenge_id": challenge_id,
                "queued": text,
                "source": steering_event["source"],
                "created_at": datetime.fromtimestamp(steering_event["ts"], tz=UTC).isoformat(),
            }

    def shutdown(self) -> None:
        with self._lock:
            run_ids = list(self._runs.keys())
        for run_id in run_ids:
            with contextlib.suppress(Exception):
                self.cancel(run_id)
