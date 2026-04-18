"""CLI entry point — config driven via backend/agent-config.yaml."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from rich.console import Console

from backend.config import Settings, get_settings
from backend.local_challenges import local_challenge_dirs

console = Console()


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    for noisy in ("httpx", "httpcore", "botocore", "urllib3", "aiodocker"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)-8s %(message)s", datefmt="%X"))
    logging.basicConfig(level=level, handlers=[handler], force=True)


async def _run_single(settings: Settings, challenge_dir: str) -> None:
    from backend.agents.swarm import ChallengeSwarm
    from backend.cost_tracker import CostTracker
    from backend.ctfd import CTFdClient
    from backend.prompts import ChallengeMeta
    from backend.sandbox import cleanup_orphan_containers, configure_semaphore

    max_containers = settings.max_concurrent_challenges * len(settings.models)
    configure_semaphore(max_containers)
    await cleanup_orphan_containers()

    challenge_path = Path(challenge_dir).expanduser().resolve()
    meta_path = challenge_path / "metadata.yml"
    if not meta_path.exists():
        console.print(f"[red]No metadata.yml found in {challenge_path}[/red]")
        sys.exit(1)

    meta = ChallengeMeta.from_yaml(meta_path)
    console.print(f"[bold]Challenge:[/bold] {meta.name} ({meta.category}, {meta.value} pts)")

    ctfd = CTFdClient(base_url=None, token="", username="", password="")
    cost_tracker = CostTracker()

    swarm = ChallengeSwarm(
        challenge_dir=str(challenge_path),
        meta=meta,
        ctfd=ctfd,
        cost_tracker=cost_tracker,
        settings=settings,
        model_specs=settings.models,
        no_submit=settings.no_submit,
    )

    try:
        result = await swarm.run()
        from backend.solver_base import FLAG_FOUND
        if result and result.status == FLAG_FOUND:
            console.print(f"\n[bold green]FLAG FOUND:[/bold green] {result.flag}")
        else:
            console.print("\n[bold red]No flag found.[/bold red]")
        console.print("\n[bold]Cost Summary:[/bold]")
        for agent_name in cost_tracker.by_agent:
            console.print(f"  {agent_name}: {cost_tracker.format_usage(agent_name)}")
        console.print(f"  [bold]Total: ${cost_tracker.total_cost_usd:.2f}[/bold]")
    finally:
        await ctfd.close()


async def _run_local_directory(settings: Settings, challenges_root: str) -> None:
    challenge_dirs = local_challenge_dirs(challenges_root)
    if not challenge_dirs:
        console.print(f"[red]No challenge directories with metadata.yml found under {challenges_root}[/red]")
        sys.exit(1)

    console.print(f"[bold]Found {len(challenge_dirs)} challenge director{'y' if len(challenge_dirs) == 1 else 'ies'}.[/bold]")
    for idx, challenge_path in enumerate(challenge_dirs, start=1):
        console.print()
        console.print(f"[bold cyan]({idx}/{len(challenge_dirs)})[/bold cyan] Solving {challenge_path.name}")
        await _run_single(settings, str(challenge_path))


def main() -> None:
    """Entry point invoked by `uv run ctf-api` subprocess or directly."""
    # Accept a bare 'run' token written by build_cli_command without crashing.
    args = [a for a in sys.argv[1:] if a != "run"]
    if args:
        console.print(f"[yellow]Warning: unexpected arguments ignored: {args}[/yellow]")

    settings = get_settings()
    _setup_logging(settings.verbose)

    from backend.api_server import serve_api
    serve_api(host=settings.api_host, port=settings.api_port, cors_origins=None)


if __name__ == "__main__":
    main()
