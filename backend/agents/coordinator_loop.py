"""Shared coordinator event loop — used by both Claude SDK and Codex coordinators."""

from __future__ import annotations

import asyncio
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

        last_status = asyncio.get_event_loop().time()

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
            now = asyncio.get_event_loop().time()
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
                    logger.info(f"Event -> coordinator: {status_line}")

            if parts:
                msg = "\n\n".join(parts)
                logger.info("Event -> coordinator: %s", msg[:200])
                await turn_fn(msg)

    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Coordinator shutting down...")
    except Exception as e:
        logger.error("Coordinator fatal: %s", e, exc_info=True)
    finally:
        if msg_server:
            msg_server.close()
            await msg_server.wait_closed()
        await poller.stop()
        for swarm in deps.swarms.values():
            swarm.kill()
        for task in deps.swarm_tasks.values():
            task.cancel()
        if deps.swarm_tasks:
            await asyncio.gather(*deps.swarm_tasks.values(), return_exceptions=True)
        cost_tracker.log_summary()
        try:
            await ctfd.close()
        except Exception:
            pass

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
        logger.info(f"Auto-spawn {challenge_name}: {result[:100]}")
    except Exception as e:
        logger.warning(f"Auto-spawn failed for {challenge_name}: {e}")


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
            "solved": name in deps.results or name in deps.swarms and bool(deps.swarms[name].winner),
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


def _dashboard_html() -> str:
        return """<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>CTF Agent Dashboard</title>
    <style>
        :root { color-scheme: dark; }
        body { margin: 0; font-family: Inter, system-ui, sans-serif; background: #0b1020; color: #e7ecff; }
        header { padding: 20px 24px; border-bottom: 1px solid #24304f; background: linear-gradient(180deg, #101a33, #0b1020); }
        h1 { margin: 0 0 8px; font-size: 22px; }
        .sub { color: #9db0df; font-size: 13px; }
        main { display: grid; grid-template-columns: 1.3fr 1fr; gap: 16px; padding: 16px; }
        .card { background: #111a30; border: 1px solid #24304f; border-radius: 14px; padding: 14px; box-shadow: 0 10px 30px rgba(0,0,0,.25); }
        .stats { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 10px; }
        .pill { padding: 6px 10px; border-radius: 999px; background: #172342; border: 1px solid #2d3a5f; color: #d6defd; font-size: 12px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid #24304f; font-size: 13px; vertical-align: top; }
        th { color: #97aae0; font-weight: 600; }
        button { background: #2d66ff; color: white; border: 0; border-radius: 10px; padding: 8px 12px; cursor: pointer; font-weight: 600; }
        button.secondary { background: #22304f; }
        button.danger { background: #ba3f3f; }
        button:disabled { opacity: .5; cursor: not-allowed; }
        select, textarea, input { width: 100%; box-sizing: border-box; background: #0c1326; color: #e7ecff; border: 1px solid #2a3960; border-radius: 10px; padding: 8px; }
        textarea { min-height: 84px; resize: vertical; }
        pre { white-space: pre-wrap; word-break: break-word; background: #0c1326; border: 1px solid #2a3960; border-radius: 12px; padding: 12px; min-height: 220px; max-height: 500px; overflow: auto; }
        .grid { display: grid; gap: 12px; }
        .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .muted { color: #9db0df; }
        .flag { color: #72f1b8; font-weight: 700; }
        .small { font-size: 12px; }
        .challenge-name { font-weight: 700; }
    </style>
</head>
<body>
    <header>
        <h1>CTF Agent Dashboard</h1>
        <div class="sub">Stop specific challenges, inspect traces, and watch solved flags appear here.</div>
        <div id="stats" class="stats"></div>
    </header>

    <main>
        <section class="card">
            <div class="row" style="justify-content: space-between; margin-bottom: 10px;">
                <strong>Active swarms</strong>
                <div class="row">
                    <button class="secondary" onclick="refreshState()">Refresh</button>
                    <button class="secondary" onclick="loadTrace()">Load trace</button>
                </div>
            </div>
            <table>
                <thead>
                    <tr><th>Challenge</th><th>Status</th><th>Actions</th></tr>
                </thead>
                <tbody id="activeRows"><tr><td colspan="3" class="muted">Loading…</td></tr></tbody>
            </table>
            <div style="margin-top: 14px;">
                <strong>Stopped / paused</strong>
                <table style="margin-top: 10px;">
                    <thead>
                        <tr><th>Challenge</th><th>Status</th><th>Actions</th></tr>
                    </thead>
                    <tbody id="stoppedRows"><tr><td colspan="3" class="muted">Loading…</td></tr></tbody>
                </table>
            </div>
            <div style="margin-top: 14px;">
                <div class="row">
                    <div style="flex: 1; min-width: 220px;">
                        <label class="small muted">Trace challenge</label>
                        <select id="traceChallenge" onchange="loadTrace()"></select>
                    </div>
                    <div style="width: 180px;">
                        <label class="small muted">Model</label>
                        <select id="traceModel" onchange="loadTrace()"></select>
                    </div>
                    <div style="width: 90px;">
                        <label class="small muted">Last N</label>
                        <input id="traceCount" type="number" min="1" max="200" value="30" onchange="loadTrace()" />
                    </div>
                </div>
            </div>
            <pre id="traceBox">Select a challenge to view its latest trace.</pre>
        </section>

        <section class="grid">
            <div class="card">
                <strong>Results / flags</strong>
                <div id="results" class="grid" style="margin-top: 10px;"></div>
            </div>
            <div class="card">
                <strong>Send operator message</strong>
                <p class="muted small">Message goes directly to the coordinator inbox.</p>
                <textarea id="messageBox" placeholder="Tell the coordinator what to do next…"></textarea>
                <div class="row" style="margin-top: 10px;">
                    <button onclick="sendMessage()">Send</button>
                    <span id="messageStatus" class="muted small"></span>
                </div>
            </div>
            <div class="card">
                <strong>All known challenges</strong>
                <div id="knownList" class="grid" style="margin-top: 10px;"></div>
            </div>
        </section>
    </main>

    <script>
        let lastState = null;

        function esc(s) {
            return String(s ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
        }

        async function refreshState() {
            const resp = await fetch('/api/state');
            const state = await resp.json();
            lastState = state;

            const stats = document.getElementById('stats');
            stats.innerHTML = `
                <span class="pill">Active: ${state.active_count}</span>
                <span class="pill">Stopped: ${state.stopped_count || 0}</span>
                <span class="pill">Solved: ${state.solved_count}</span>
                <span class="pill">Capacity: ${state.max_concurrent_challenges}</span>
            `;

            const activeRows = document.getElementById('activeRows');
            if (!state.active.length) {
                activeRows.innerHTML = '<tr><td colspan="3" class="muted">No active swarms.</td></tr>';
            } else {
                activeRows.innerHTML = state.active.map(item => {
                    const winner = item.status && item.status.winner ? `<span class="flag">${esc(item.status.winner)}</span>` : '—';
                    const models = item.models.length ? item.models.join(', ') : '—';
                    return `
                        <tr>
                            <td>
                                <div class="challenge-name">${esc(item.challenge)}</div>
                                <div class="small muted">${esc(item.category || '')} ${item.value ? `• ${item.value} pts` : ''}</div>
                                <div class="small muted">Models: ${esc(models)}</div>
                            </td>
                            <td>
                                <div>Winner: ${winner}</div>
                                <div class="small muted">Cancelled: ${item.status.cancelled ? 'yes' : 'no'}</div>
                            </td>
                            <td>
                                <div class="row">
                                    <button class="danger" onclick="stopChallenge(${JSON.stringify(item.challenge)})">Stop</button>
                                    <button class="secondary" onclick="setTraceTarget(${JSON.stringify(item.challenge)})">Trace</button>
                                </div>
                            </td>
                        </tr>`;
                }).join('');
            }

            const stoppedRows = document.getElementById('stoppedRows');
            if (!state.stopped.length) {
                stoppedRows.innerHTML = '<tr><td colspan="3" class="muted">No stopped swarms.</td></tr>';
            } else {
                stoppedRows.innerHTML = state.stopped.map(item => {
                    const models = item.models.length ? item.models.join(', ') : '—';
                    return `
                        <tr>
                            <td>
                                <div class="challenge-name">${esc(item.challenge)}</div>
                                <div class="small muted">${esc(item.category || '')} ${item.value ? `• ${item.value} pts` : ''}</div>
                                <div class="small muted">Models: ${esc(models)}</div>
                            </td>
                            <td>
                                <div class="muted">Paused / cancelled</div>
                            </td>
                            <td>
                                <div class="row">
                                    <button class="secondary" disabled>Stopped</button>
                                    <button class="secondary" onclick="setTraceTarget(${JSON.stringify(item.challenge)})">Trace</button>
                                </div>
                            </td>
                        </tr>`;
                }).join('');
            }

            const known = document.getElementById('knownList');
            known.innerHTML = state.known.map(item => {
                const solved = item.solved ? '<span class="flag">solved</span>' : '<span class="muted">unsolved</span>';
                return `<div class="row" style="justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #24304f;">
                    <div><strong>${esc(item.challenge)}</strong> <span class="muted small">(${esc(item.category || 'unknown')}${item.value ? `, ${item.value} pts` : ''})</span>${item.paused ? ' <span class="muted small">• paused</span>' : ''}</div>
                    <div>${solved}</div>
                </div>`;
            }).join('') || '<div class="muted">No challenge metadata loaded yet.</div>';

            const results = document.getElementById('results');
            const resultEntries = Object.entries(state.results || {});
            results.innerHTML = resultEntries.length ? resultEntries.map(([name, info]) => {
                const flag = info && info.flag ? `<span class="flag">${esc(info.flag)}</span>` : '—';
                const submit = info && info.submit ? esc(info.submit) : '—';
                return `<div style="padding: 10px; background: #0c1326; border: 1px solid #2a3960; border-radius: 12px;">
                    <div><strong>${esc(name)}</strong></div>
                    <div class="small">Flag: ${flag}</div>
                    <div class="small muted">${submit}</div>
                </div>`;
            }).join('') : '<div class="muted">No solved flags yet.</div>';

            const traceChallenge = document.getElementById('traceChallenge');
            const currentChallenge = traceChallenge.value || (state.active[0] && state.active[0].challenge) || '';
            traceChallenge.innerHTML = ['<option value="">Select a challenge</option>']
                .concat(state.active.map(item => `<option value="${esc(item.challenge)}">${esc(item.challenge)}</option>`))
                .join('');
            if (currentChallenge) traceChallenge.value = currentChallenge;

            const modelSet = new Set();
            state.active.forEach(item => (item.models || []).forEach(m => modelSet.add(m)));
            const traceModel = document.getElementById('traceModel');
            const currentModel = traceModel.value || Array.from(modelSet)[0] || '';
            traceModel.innerHTML = Array.from(modelSet).length ? Array.from(modelSet).map(m => `<option value="${esc(m)}">${esc(m)}</option>`).join('') : '<option value="">No models</option>';
            if (currentModel) traceModel.value = currentModel;
        }

        function setTraceTarget(challenge) {
            const sel = document.getElementById('traceChallenge');
            sel.value = challenge;
            loadTrace();
        }

        async function stopChallenge(challenge) {
            await fetch('/api/stop', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({challenge})
            });
            await refreshState();
        }

        async function loadTrace() {
            const challenge = document.getElementById('traceChallenge').value;
            const model = document.getElementById('traceModel').value;
            const last_n = document.getElementById('traceCount').value || 30;
            if (!challenge || !model) {
                document.getElementById('traceBox').textContent = 'Select a challenge and model to view trace output.';
                return;
            }
            const resp = await fetch(`/api/trace?challenge=${encodeURIComponent(challenge)}&model=${encodeURIComponent(model)}&last_n=${encodeURIComponent(last_n)}`);
            const data = await resp.json();
            document.getElementById('traceBox').textContent = data.trace || data.error || 'No trace data.';
        }

        async function sendMessage() {
            const message = document.getElementById('messageBox').value;
            const resp = await fetch('/api/message', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message})
            });
            const data = await resp.json();
            document.getElementById('messageStatus').textContent = data.ok ? 'Queued.' : (data.error || 'Failed');
            document.getElementById('messageBox').value = '';
        }

        refreshState();
        setInterval(refreshState, 5000);
    </script>
</body>
</html>"""


async def _start_msg_server(deps: CoordinatorDeps, port: int = 0) -> asyncio.Server | None:
    """Start a tiny dashboard server for operator messages and swarm control."""

    async def _send(writer: asyncio.StreamWriter, status: str, content_type: str, body: str) -> None:
        writer.write(
            f"HTTP/1.1 {status}\r\nContent-Type: {content_type}\r\nContent-Length: {len(body.encode())}\r\nCache-Control: no-store\r\n\r\n{body}".encode()
        )

    async def _read_body(reader: asyncio.StreamReader, headers: dict[str, str]) -> bytes:
        content_length = int(headers.get("content-length", 0))
        if content_length <= 0:
            return b""
        return await asyncio.wait_for(reader.read(content_length), timeout=5)

    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=5)
            headers: dict[str, str] = {}
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5)
                if line in (b"\r\n", b"\n", b""):
                    break
                if b":" in line:
                    k, v = line.decode().split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            parts = request_line.decode(errors="ignore").split()
            method = parts[0] if len(parts) >= 1 else ""
            target = parts[1] if len(parts) >= 2 else "/"
            url = urlparse(target)
            path = url.path or "/"
            query = parse_qs(url.query)

            if method == "GET" and path == "/":
                body = _dashboard_html()
                await _send(writer, "200 OK", "text/html; charset=utf-8", body)

            elif method == "GET" and path == "/api/state":
                body = json.dumps(_dashboard_state(deps), indent=2)
                await _send(writer, "200 OK", "application/json", body)

            elif method == "GET" and path == "/api/trace":
                challenge = query.get("challenge", [""])[0]
                model = query.get("model", [""])[0]
                last_n = int(query.get("last_n", ["30"])[0])
                if not challenge or not model:
                    body = json.dumps({"error": "challenge and model are required"}, indent=2)
                    await _send(writer, "400 Bad Request", "application/json", body)
                else:
                    trace_text = await do_read_solver_trace(deps, challenge, model, last_n)
                    body = json.dumps({"challenge": challenge, "model": model, "trace": trace_text}, indent=2)
                    await _send(writer, "200 OK", "application/json", body)

            elif method == "POST" and path == "/api/message":
                body_bytes = await _read_body(reader, headers)
                try:
                    data = json.loads(body_bytes or b"{}")
                    message = str(data.get("message", "")).strip()
                except Exception:
                    message = (body_bytes or b"").decode("utf-8", errors="replace").strip()

                if not message:
                    body = json.dumps({"error": "message required"}, indent=2)
                    await _send(writer, "400 Bad Request", "application/json", body)
                else:
                    deps.operator_inbox.put_nowait(message)
                    body = json.dumps({"ok": True, "queued": message[:200]}, indent=2)
                    await _send(writer, "200 OK", "application/json", body)

            elif method == "POST" and path == "/api/stop":
                body_bytes = await _read_body(reader, headers)
                challenge = ""
                try:
                    data = json.loads(body_bytes or b"{}")
                    challenge = str(data.get("challenge", "")).strip()
                except Exception:
                    challenge = ""
                if not challenge:
                    body = json.dumps({"error": "challenge required"}, indent=2)
                    await _send(writer, "400 Bad Request", "application/json", body)
                else:
                    body = await do_kill_swarm(deps, challenge)
                    await _send(writer, "200 OK", "application/json", json.dumps({"ok": True, "result": body}, indent=2))

            else:
                body = json.dumps({"error": "not found"}, indent=2)
                await _send(writer, "404 Not Found", "application/json", body)

            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    try:
        server = await asyncio.start_server(_handle, "127.0.0.1", port)
        actual_port = server.sockets[0].getsockname()[1]
        logger.warning(f"Dashboard listening on http://127.0.0.1:{actual_port}")
        return server
    except OSError as e:
        logger.warning(f"Could not start dashboard endpoint: {e}")
        return None
