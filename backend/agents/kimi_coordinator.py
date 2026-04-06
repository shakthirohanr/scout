"""Kimi coordinator — uses a Pydantic AI model with the shared event loop."""

from __future__ import annotations

import logging
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.usage import UsageLimits

from backend.agents.coordinator_core import (
    do_broadcast,
    do_bump_agent,
    do_check_swarm_status,
    do_fetch_challenges,
    do_get_solve_status,
    do_kill_swarm,
    do_read_solver_trace,
    do_spawn_swarm,
    do_submit_flag,
)
from backend.agents.coordinator_loop import build_deps, run_event_loop
from backend.config import Settings
from backend.deps import CoordinatorDeps
from backend.models import resolve_model, resolve_model_settings

logger = logging.getLogger(__name__)

COORDINATOR_PROMPT = """\
You are a CTF competition coordinator running for the ENTIRE duration of a live competition.
Your job is to maximize the number of challenges solved.

Strategy:
- Spawn a swarm for each unsolved challenge, prioritizing easy ones first
- Use read_solver_trace to monitor what each solver is doing and where it's stuck
- When agents are stuck, read their traces, then craft targeted bumps with specific technical guidance
- Use broadcast to share cross-solver insights (e.g. flag format discovery, shared vulnerabilities)

CRITICAL RULES:
- NEVER kill a swarm. Solvers will keep trying indefinitely with different approaches.
  Even when stuck, they often unstick themselves after several bumps. Your job is to
  HELP them, not give up on them. The only time a swarm should die is when the flag is
  confirmed correct.
- When a solver seems stuck, bump it with very specific technical guidance based on
  its trace. Tell it exactly what to try next — specific tools, techniques, approaches.
- Cost is not a concern. Keep all swarms running.

You will receive event messages. Respond with tool calls to manage the competition.
"""


def _build_coordinator_toolset(deps: CoordinatorDeps) -> FunctionToolset[CoordinatorDeps]:
    async def fetch_challenges(ctx: RunContext[CoordinatorDeps]) -> str:
        return await do_fetch_challenges(ctx.deps)

    async def get_solve_status(ctx: RunContext[CoordinatorDeps]) -> str:
        return await do_get_solve_status(ctx.deps)

    async def spawn_swarm(ctx: RunContext[CoordinatorDeps], challenge_name: str) -> str:
        return await do_spawn_swarm(ctx.deps, challenge_name)

    async def check_swarm_status(ctx: RunContext[CoordinatorDeps], challenge_name: str) -> str:
        return await do_check_swarm_status(ctx.deps, challenge_name)

    async def submit_flag(ctx: RunContext[CoordinatorDeps], challenge_name: str, flag: str) -> str:
        return await do_submit_flag(ctx.deps, challenge_name, flag)

    async def kill_swarm(ctx: RunContext[CoordinatorDeps], challenge_name: str) -> str:
        return await do_kill_swarm(ctx.deps, challenge_name)

    async def bump_agent(
        ctx: RunContext[CoordinatorDeps],
        challenge_name: str,
        model_spec: str,
        insights: str,
    ) -> str:
        return await do_bump_agent(ctx.deps, challenge_name, model_spec, insights)

    async def broadcast(ctx: RunContext[CoordinatorDeps], challenge_name: str, message: str) -> str:
        return await do_broadcast(ctx.deps, challenge_name, message)

    async def read_solver_trace(
        ctx: RunContext[CoordinatorDeps],
        challenge_name: str,
        model_spec: str,
        last_n: int = 20,
    ) -> str:
        return await do_read_solver_trace(ctx.deps, challenge_name, model_spec, last_n)

    return FunctionToolset(
        tools=[
            fetch_challenges,
            get_solve_status,
            spawn_swarm,
            check_swarm_status,
            submit_flag,
            kill_swarm,
            bump_agent,
            broadcast,
            read_solver_trace,
        ],
        max_retries=4,
    )


async def run_kimi_coordinator(
    settings: Settings,
    model_specs: list[str] | None = None,
    challenges_root: str = "challenges",
    no_submit: bool = False,
    coordinator_model: str | None = None,
    msg_port: int = 0,
) -> dict[str, Any]:
    """Run a Kimi-based coordinator with the shared event loop."""
    ctfd, cost_tracker, deps = build_deps(
        settings, model_specs, challenges_root, no_submit,
    )
    deps.msg_port = msg_port

    model_spec = coordinator_model or "kimi/kimi-k2p5-turbo"
    if "/" not in model_spec:
        model_spec = f"kimi/{model_spec}"

    model = resolve_model(model_spec, settings)
    model_settings = resolve_model_settings(model_spec)
    toolset = _build_coordinator_toolset(deps)

    agent = Agent(
        model,
        deps_type=CoordinatorDeps,
        system_prompt=COORDINATOR_PROMPT,
        model_settings=model_settings,
        toolsets=[toolset],
        output_type=str,
    )

    history = None

    async def turn_fn(msg: str) -> None:
        nonlocal history
        logger.debug("Coordinator query: %s", msg[:200])
        result = await agent.run(
            msg,
            deps=deps,
            message_history=history,
            usage_limits=UsageLimits(request_limit=None),
        )
        history = result.all_messages()

        output = getattr(result, "output", "")
        if isinstance(output, str) and output.strip():
            logger.info("Kimi coordinator output: %s", output[:500])

        logger.info("Kimi coordinator turn done (messages=%d)", len(history or []))

    return await run_event_loop(deps, ctfd, cost_tracker, turn_fn)
