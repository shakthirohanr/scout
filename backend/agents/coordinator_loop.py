"""Shared coordinator event loop — used by both Claude SDK and Codex coordinators."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from backend.config import Settings
from backend.cost_tracker import CostTracker
from backend.ctfd import CTFdClient
from backend.agents.coordinator_core import do_kill_swarm, do_read_solver_trace
from backend.deps import CoordinatorDeps
from backend.models import DEFAULT_MODELS
from backend.poller import CTFdPoller
from backend.prompts import ChallengeMeta

logger = logging.getLogger(__name__)

# Callable type for a coordinator turn: (message) -> None
TurnFn = Callable[[str], Coroutine[Any, Any, None]]


def build_deps(
    settings: Settings,
    model_specs: list[str] | None = None,
    challenges_root: str = "challenges",
    no_submit: bool = False,
    challenge_dirs: dict[str, str] | None = None,
    challenge_metas: dict[str, ChallengeMeta] | None = None,
) -> tuple[CTFdClient, CostTracker, CoordinatorDeps]:
    """Create CTFd client, cost tracker, and coordinator deps."""
    ctfd = CTFdClient(
        base_url=settings.ctfd_url,
        token=settings.ctfd_token,
        username=settings.ctfd_user,
        password=settings.ctfd_pass,
    )
    cost_tracker = CostTracker()
    specs = model_specs or list(DEFAULT_MODELS)
    Path(challenges_root).mkdir(parents=True, exist_ok=True)

    deps = CoordinatorDeps(
        ctfd=ctfd,
        cost_tracker=cost_tracker,
        settings=settings,
        model_specs=specs,
        challenges_root=challenges_root,
        no_submit=no_submit,
        max_concurrent_challenges=getattr(settings, "max_concurrent_challenges", 10),
        challenge_dirs=challenge_dirs or {},
        challenge_metas=challenge_metas or {},
    )

    # Pre-load already-pulled challenges
    for d in Path(challenges_root).iterdir():
        meta_path = d / "metadata.yml"
        if meta_path.exists():
            meta = ChallengeMeta.from_yaml(meta_path)
            if meta.name not in deps.challenge_dirs:
                deps.challenge_dirs[meta.name] = str(d)
                deps.challenge_metas[meta.name] = meta

    return ctfd, cost_tracker, deps


async def run_event_loop(
    deps: CoordinatorDeps,
    ctfd: CTFdClient,
    cost_tracker: CostTracker,
    turn_fn: TurnFn,
    status_interval: int = 60,
) -> dict[str, Any]:
    """Run the shared coordinator event loop.

    Args:
        deps: Coordinator dependencies (shared state).
        ctfd: CTFd client (for poller).
        cost_tracker: Cost tracker.
        turn_fn: Async function that sends a message to the coordinator LLM.
        status_interval: Seconds between status updates.
    """
    poller = CTFdPoller(ctfd=ctfd, interval_s=5.0)
    await poller.start()

    # Start operator message HTTP endpoint
    msg_server = await _start_msg_server(deps, deps.msg_port)

    logger.info(
        "Coordinator starting: %d models, %d challenges, %d solved",
        len(deps.model_specs),
        len(poller.known_challenges),
        len(poller.known_solved),
    )

    unsolved = poller.known_challenges - poller.known_solved
    initial_msg = (
        f"CTF is LIVE. {len(poller.known_challenges)} challenges, "
        f"{len(poller.known_solved)} solved.\n"
        f"Unsolved: {sorted(unsolved) if unsolved else 'NONE'}\n"
        "Fetch challenges and spawn swarms for all unsolved."
    )

    try:
        await turn_fn(initial_msg)

        # Auto-spawn swarms for unsolved challenges if coordinator LLM didn't
        await _auto_spawn_unsolved(deps, poller)

        last_status = asyncio.get_running_loop().time()

        while True:
            events = []
            evt = await poller.get_event(timeout=5.0)
            if evt:
                events.append(evt)
            events.extend(poller.drain_events())

            # Auto-kill swarms for solved challenges
            for evt in events:
                if evt.kind == "challenge_solved" and evt.challenge_name in deps.swarms:
                    swarm = deps.swarms[evt.challenge_name]
                    if not swarm.cancel_event.is_set():
                        swarm.kill()
                        logger.info("Auto-killed swarm for: %s", evt.challenge_name)

            parts: list[str] = []
            for evt in events:
                if evt.kind == "new_challenge":
                    parts.append(f"NEW CHALLENGE: '{evt.challenge_name}' appeared. Spawn a swarm.")
                    # Auto-spawn for new challenges
                    await _auto_spawn_one(deps, evt.challenge_name)
                elif evt.kind == "challenge_solved":
                    parts.append(f"SOLVED: '{evt.challenge_name}' — swarm auto-killed.")

            # Detect finished swarms
            for name, task in list(deps.swarm_tasks.items()):
                if task.done():
                    parts.append(f"SOLVER FINISHED: Swarm for '{name}' completed. Check results or retry.")
                    deps.swarm_tasks.pop(name, None)

            # Drain solver-to-coordinator messages
            while True:
                try:
                    solver_msg = deps.coordinator_inbox.get_nowait()
                    parts.append(f"SOLVER MESSAGE: {solver_msg}")
                except asyncio.QueueEmpty:
                    break

            # Drain operator messages
            while True:
                try:
                    op_msg = deps.operator_inbox.get_nowait()
                    parts.append(f"OPERATOR MESSAGE: {op_msg}")
                    logger.info("Operator message: %s", op_msg[:200])
                except asyncio.QueueEmpty:
                    break

            # Periodic status update — only when there are active swarms or other events
            now = asyncio.get_running_loop().time()
            if now - last_status >= status_interval:
                last_status = now
                active = [n for n, t in deps.swarm_tasks.items() if not t.done()]
                solved_set = poller.known_solved
                unsolved_set = poller.known_challenges - solved_set
                status_line = (
                    f"STATUS: {len(solved_set)} solved, {len(unsolved_set)} unsolved, "
                    f"{len(active)} active swarms. Cost: ${cost_tracker.total_cost_usd:.2f}"
                )
                # Only send to coordinator if there's something happening
                if active or parts:
                    parts.append(status_line)
                else:
                    logger.info("Event -> coordinator: %s", status_line)

            if parts:
                msg = "\n\n".join(parts)
                logger.info("Event -> coordinator: %s", msg[:200])
                await turn_fn(msg)

    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Coordinator shutting down...")
    except Exception as e:
        logger.error("Coordinator fatal: %s", e, exc_info=True)
    finally:
        await server.stop()
        await poller.stop()
        for swarm in deps.swarms.values():
            swarm.kill()
        for task in deps.swarm_tasks.values():
            task.cancel()
        if deps.swarm_tasks:
            await asyncio.gather(*deps.swarm_tasks.values(), return_exceptions=True)
        cost_tracker.log_summary()
        with contextlib.suppress(Exception):
            await ctfd.close()

    return {
        "results": deps.results,
        "total_cost_usd": cost_tracker.total_cost_usd,
        "total_tokens": cost_tracker.total_tokens,
    }


async def _auto_spawn_one(deps: CoordinatorDeps, challenge_name: str) -> None:
    """Auto-spawn a swarm for a single challenge if not already running."""
    if challenge_name in deps.paused_challenges:
        return
    if challenge_name in deps.swarms:
        return
    active = sum(1 for t in deps.swarm_tasks.values() if not t.done())
    if active >= deps.max_concurrent_challenges:
        return
    try:
        from backend.agents.coordinator_core import do_spawn_swarm
        result = await do_spawn_swarm(deps, challenge_name)
        logger.info("Auto-spawn %s: %s", challenge_name, result[:100])
    except Exception as e:
        logger.warning("Auto-spawn failed for %s: %s", challenge_name, e)


async def _auto_spawn_unsolved(deps: CoordinatorDeps, poller) -> None:
    """Auto-spawn swarms for all unsolved challenges that don't have active swarms."""
    unsolved = poller.known_challenges - poller.known_solved - deps.paused_challenges
    for name in sorted(unsolved):
        await _auto_spawn_one(deps, name)


def _dashboard_state(deps: CoordinatorDeps) -> dict[str, Any]:
    active: list[dict[str, Any]] = []
    stopped: list[dict[str, Any]] = []
    for name, swarm in deps.swarms.items():
        meta = deps.challenge_metas.get(name)
        status = swarm.get_status()
        row = {
            "challenge": name,
            "category": getattr(meta, "category", ""),
            "value": getattr(meta, "value", 0),
            "models": list(getattr(swarm, "model_specs", []) or []),
            "status": status,
            "result": deps.results.get(name),
        }
        if swarm.cancel_event.is_set() or name in deps.paused_challenges:
            stopped.append(row)
        else:
            active.append(row)

    active.sort(key=lambda item: item["challenge"].lower())
    stopped.sort(key=lambda item: item["challenge"].lower())

    known: list[dict[str, Any]] = []
    for name, meta in sorted(deps.challenge_metas.items()):
        known.append({
            "challenge": name,
            "category": getattr(meta, "category", ""),
            "value": getattr(meta, "value", 0),
            "solved": (name in deps.results) or (name in deps.swarms and bool(deps.swarms[name].winner)),
            "paused": name in deps.paused_challenges,
        })

    return {
        "max_concurrent_challenges": deps.max_concurrent_challenges,
        "active_count": len(active),
        "stopped_count": len(stopped),
        "solved_count": len(deps.results),
        "active": active,
        "stopped": stopped,
        "known": known,
        "results": deps.results,
    }


class DashboardServer:
    """Encapsulates the coordinator dashboard HTTP server logic."""

    def __init__(self, deps: CoordinatorDeps):
        self.deps = deps
        self._server: asyncio.Server | None = None
        self._template_path = Path(__file__).parent.parent / "templates" / "dashboard.html"

    async def start(self, port: int) -> None:
        """Start the dashboard server on 127.0.0.1:port."""
        try:
            self._server = await asyncio.start_server(self._handle_client, "127.0.0.1", port)
            actual_port = self._server.sockets[0].getsockname()[1]
            logger.warning("Dashboard listening on http://127.0.0.1:%s", actual_port)
        except OSError as e:
            logger.warning("Could not start dashboard: %s", e)

    async def stop(self) -> None:
        """Stop the dashboard server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _send(self, writer: asyncio.StreamWriter, status: str, content_type: str, body: str) -> None:
        payload = body.encode("utf-8")
        headers = [
            f"HTTP/1.1 {status}",
            f"Content-Type: {content_type}",
            f"Content-Length: {len(payload)}",
            "Cache-Control: no-store",
            "Connection: close",
            "\r\n",
        ]
        writer.write("\r\n".join(headers).encode("ascii") + payload)

    async def _read_body(self, reader: asyncio.StreamReader, headers: dict[str, str]) -> bytes:
        content_length = int(headers.get("content-length", 0))
        if content_length <= 0:
            return b""
        return await asyncio.wait_for(reader.read(content_length), timeout=5)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line_bytes = await asyncio.wait_for(reader.readline(), timeout=5)
            if not request_line_bytes:
                return

            headers: dict[str, str] = {}
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5)
                if line in (b"\r\n", b"\n", b""):
                    break
                if b":" in line:
                    k, v = line.decode("ascii", errors="replace").split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            parts = request_line_bytes.decode("ascii", errors="ignore").split()
            if len(parts) < 2:
                return
            method, target = parts[0], parts[1]
            url = urlparse(target)
            path = url.path or "/"
            query = parse_qs(url.query)

            await self._dispatch(method, path, query, headers, reader, writer)
            await writer.drain()
        except (asyncio.TimeoutError, ConnectionResetError):
            pass
        except Exception as e:
            logger.debug("Dashboard handle error: %s", e)
        finally:
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()

    async def _dispatch(
        self,
        method: str,
        path: str,
        query: dict[str, list[str]],
        headers: dict[str, str],
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ) -> None:
        if method == "GET" and path == "/":
            if self._template_path.exists():
                body = self._template_path.read_text(encoding="utf-8")
            else:
                body = "<h1>Dashboard Template Missing</h1>"
            await self._send(writer, "200 OK", "text/html; charset=utf-8", body)

        elif method == "GET" and path == "/api/state":
            body = json.dumps(_dashboard_state(self.deps), indent=2)
            await self._send(writer, "200 OK", "application/json", body)

        elif method == "GET" and path == "/api/trace":
            challenge = query.get("challenge", [""])[0]
            model = query.get("model", [""])[0]
            last_n_str = query.get("last_n", ["30"])[0]
            try:
                last_n = int(last_n_str)
            except ValueError:
                last_n = 30

            if not challenge or not model:
                body = json.dumps({"error": "challenge and model are required"}, indent=2)
                await self._send(writer, "400 Bad Request", "application/json", body)
            else:
                trace_text = await do_read_solver_trace(self.deps, challenge, model, last_n)
                body = json.dumps({"challenge": challenge, "model": model, "trace": trace_text}, indent=2)
                await self._send(writer, "200 OK", "application/json", body)

        elif method == "POST" and path == "/api/message":
            body_bytes = await self._read_body(reader, headers)
            try:
                data = json.loads(body_bytes or b"{}")
                message = str(data.get("message", "")).strip()
            except Exception:
                message = (body_bytes or b"").decode("utf-8", errors="replace").strip()

            if not message:
                body = json.dumps({"error": "message required"}, indent=2)
                await self._send(writer, "400 Bad Request", "application/json", body)
            else:
                self.deps.operator_inbox.put_nowait(message)
                body = json.dumps({"ok": True, "queued": message[:200]}, indent=2)
                await self._send(writer, "200 OK", "application/json", body)

        elif method == "POST" and path == "/api/stop":
            body_bytes = await self._read_body(reader, headers)
            try:
                data = json.loads(body_bytes or b"{}")
                challenge = str(data.get("challenge", "")).strip()
            except Exception:
                challenge = ""

            if not challenge:
                body = json.dumps({"error": "challenge required"}, indent=2)
                await self._send(writer, "400 Bad Request", "application/json", body)
            else:
                result = await do_kill_swarm(self.deps, challenge)
                await self._send(writer, "200 OK", "application/json", json.dumps({"ok": True, "result": result}, indent=2))

        else:
            body = json.dumps({"error": "not found"}, indent=2)
            await self._send(writer, "404 Not Found", "application/json", body)


async def _start_msg_server(deps: CoordinatorDeps, port: int = 0) -> DashboardServer | None:
    """Start a tiny dashboard server for operator messages and swarm control."""
    server = DashboardServer(deps)
    await server.start(port)
    return server
