"""Click CLI entry point."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click
from rich.console import Console

from backend.config import Settings
from backend.local_challenges import local_challenge_dirs
from backend.models import FALLBACK_DEFAULT_MODEL, default_models

console = Console()


def _make_settings(image: str, ctfd_url: str | None = None, ctfd_token: str | None = None) -> Settings:
    settings = Settings(sandbox_image=image)
    settings.ctfd_url = ctfd_url
    if ctfd_token:
        settings.ctfd_token = ctfd_token
    return settings


def _resolve_single_model_specs(models: tuple[str, ...] | list[str]) -> list[str]:
    specs = list(models) if models else default_models()
    if not specs:
        specs = [FALLBACK_DEFAULT_MODEL]
    if len(specs) > 1:
        console.print(
            f"[yellow]Swarming is disabled here; using only the first model: {specs[0]}[/yellow]"
        )
    return [specs[0]]


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("aiodocker").setLevel(logging.WARNING)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)-8s %(message)s", datefmt="%X"))
    logging.basicConfig(level=level, handlers=[handler], force=True)


@click.group()
def cli():
    """CTF Agent — multi-model solver swarm."""
    pass


@cli.command()
@click.argument("name")
@click.option("--category", default="misc", help="Challenge category")
@click.option("--value", default=500, type=int, help="Challenge value")
@click.option("--description", default="", help="Challenge description")
@click.option("--connection-info", default="", help="Connection info (nc host port / http://...)")
@click.option("--dir", "directory", default=".", help="Output directory")
def init(
    name: str,
    category: str,
    value: int,
    description: str,
    connection_info: str,
    directory: str,
) -> None:
    """Initialize a new challenge directory with metadata.yml template."""
    import yaml
    from pathlib import Path

    path = Path(directory) / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "distfiles").mkdir(exist_ok=True)

    meta = {
        "name": name,
        "category": category,
        "value": value,
        "description": description,
        "connection_info": connection_info,
        "tags": [],
        "hints": [],
        "solves": 0,
    }
    
    meta_path = path / "metadata.yml"
    if meta_path.exists():
        console.print(f"[yellow]metadata.yml already exists in {path}[/yellow]")
    else:
        with open(meta_path, "w") as f:
            yaml.dump(meta, f, sort_keys=False)
        console.print(f"[green]Initialized challenge in {path}[/green]")


@cli.command()
@click.option("--ctfd-url", default=None, help="CTFd URL (overrides .env)")
@click.option("--ctfd-token", default=None, help="CTFd API token (overrides .env)")
@click.option("--offline", is_flag=True, help="Run without CTFd connection (manual mode)")
@click.option("--image", default="ctf-sandbox", help="Docker sandbox image name")
@click.option("--models", multiple=True, help="Model specs (default: DEFAULT_SOLVER_MODEL or kimi/kimi-k2p5-turbo)")
@click.option("--challenge", default=None, help="Solve a single challenge directory")
@click.option("--challenges-dir", default="challenges", help="Directory for challenge files")
@click.option("--no-submit", is_flag=True, help="Dry run — don't submit flags")
@click.option("--coordinator-model", default=None, help="Model for coordinator (default: claude-opus-4-6)")
@click.option("--coordinator", default="kimi", type=click.Choice(["claude", "codex", "kimi"]), help="Coordinator backend")
@click.option("--max-challenges", default=10, type=int, help="Max challenges solved concurrently")
@click.option("--msg-port", default=0, type=int, help="Operator message port (0 = auto)")
@click.option("-v", "--verbose", is_flag=True, help="Verbose logging")
def run(
    ctfd_url: str | None,
    ctfd_token: str | None,
    offline: bool,
    image: str,
    models: tuple[str, ...],
    challenge: str | None,
    challenges_dir: str,
    no_submit: bool,
    coordinator_model: str | None,
    coordinator: str,
    max_challenges: int,
    msg_port: int,
    verbose: bool,
) -> None:
    """Run the solver swarm or coordinator."""
    _setup_logging(verbose)

    settings = _make_settings(image, None if offline else ctfd_url, ctfd_token)
    
    settings.max_concurrent_challenges = max_challenges

    model_specs = _resolve_single_model_specs(models)
    
    if not offline and not settings.ctfd_url and not challenge:
        console.print("[yellow]Warning: No CTFd URL configured and not in offline mode. Defaulting to offline/manual mode.[/yellow]")
        settings.ctfd_url = None

    console.print("[bold]CTF Agent v2[/bold]")
    console.print(f"  Mode: {'Offline/Manual' if not settings.ctfd_url else 'Connected'}")
    if settings.ctfd_url:
        console.print(f"  CTFd: {settings.ctfd_url}")
    console.print(f"  Models: {', '.join(model_specs)}")
    console.print(f"  Image: {settings.sandbox_image}")
    console.print(f"  Max challenges: {max_challenges}")
    console.print()

    if challenge:
        asyncio.run(_run_single(settings, challenge, model_specs, no_submit, max_challenges))
    else:
        if not settings.ctfd_url:
            asyncio.run(_run_local_directory(settings, challenges_dir, model_specs, no_submit, max_challenges))
        else:
            asyncio.run(_run_coordinator(settings, model_specs, challenges_dir, no_submit, coordinator_model, coordinator, max_challenges, msg_port))


@cli.command()
@click.argument("challenge_dir")
@click.option("--image", default="ctf-sandbox", help="Docker sandbox image name")
@click.option("--models", multiple=True, help="Model specs (default: DEFAULT_SOLVER_MODEL or kimi/kimi-k2p5-turbo)")
@click.option("--no-submit", is_flag=True, help="Dry run — don't submit flags")
@click.option("--max-challenges", default=10, type=int, help="Max challenges solved concurrently")
@click.option("-v", "--verbose", is_flag=True, help="Verbose logging")
def solve(
    challenge_dir: str,
    image: str,
    models: tuple[str, ...],
    no_submit: bool,
    max_challenges: int,
    verbose: bool,
) -> None:
    """Solve a single local challenge directory."""
    _setup_logging(verbose)
    settings = _make_settings(image)
    settings.max_concurrent_challenges = max_challenges
    model_specs = _resolve_single_model_specs(models)
    asyncio.run(_run_single(settings, challenge_dir, model_specs, no_submit, max_challenges))


@cli.command(name="solve-local")
@click.option("--image", default="ctf-sandbox", help="Docker sandbox image name")
@click.option("--models", multiple=True, help="Model specs (default: DEFAULT_SOLVER_MODEL or kimi/kimi-k2p5-turbo)")
@click.option("--no-submit", is_flag=True, help="Dry run — don't submit flags")
@click.option("--max-challenges", default=10, type=int, help="Max challenges solved concurrently")
@click.option("-v", "--verbose", is_flag=True, help="Verbose logging")
def solve_local(
    image: str,
    models: tuple[str, ...],
    no_submit: bool,
    max_challenges: int,
    verbose: bool,
) -> None:
    """Solve the current directory as a local challenge."""
    _setup_logging(verbose)
    settings = _make_settings(image)
    settings.max_concurrent_challenges = max_challenges
    model_specs = _resolve_single_model_specs(models)
    asyncio.run(_run_single(settings, ".", model_specs, no_submit, max_challenges))


@cli.command(name="solve-dir")
@click.argument("challenges_root")
@click.option("--image", default="ctf-sandbox", help="Docker sandbox image name")
@click.option("--models", multiple=True, help="Model specs (default: DEFAULT_SOLVER_MODEL or kimi/kimi-k2p5-turbo)")
@click.option("--no-submit", is_flag=True, help="Dry run — don't submit flags")
@click.option("--max-challenges", default=10, type=int, help="Max challenges solved concurrently")
@click.option("-v", "--verbose", is_flag=True, help="Verbose logging")
def solve_dir(
    challenges_root: str,
    image: str,
    models: tuple[str, ...],
    no_submit: bool,
    max_challenges: int,
    verbose: bool,
) -> None:
    """Solve every local challenge directory under a root folder."""
    _setup_logging(verbose)
    settings = _make_settings(image)
    settings.max_concurrent_challenges = max_challenges
    model_specs = _resolve_single_model_specs(models)
    asyncio.run(_run_local_directory(settings, challenges_root, model_specs, no_submit, max_challenges))



async def _run_single(
    settings: Settings,
    challenge_dir: str,
    model_specs: list[str],
    no_submit: bool,
    max_challenges: int,
) -> None:
    """Run a single challenge with a swarm."""
    from backend.agents.swarm import ChallengeSwarm
    from backend.cost_tracker import CostTracker
    from backend.ctfd import CTFdClient
    from backend.prompts import ChallengeMeta
    from backend.sandbox import cleanup_orphan_containers, configure_semaphore

    max_containers = max_challenges * len(model_specs)
    configure_semaphore(max_containers)
    await cleanup_orphan_containers()

    challenge_path = Path(challenge_dir)
    meta_path = challenge_path / "metadata.yml"
    if not meta_path.exists():
        console.print(f"[red]No metadata.yml found in {challenge_dir}[/red]")
        sys.exit(1)

    meta = ChallengeMeta.from_yaml(meta_path)
    console.print(f"[bold]Challenge:[/bold] {meta.name} ({meta.category}, {meta.value} pts)")

    ctfd = CTFdClient(
        base_url=settings.ctfd_url,
        token=settings.ctfd_token,
        username=settings.ctfd_user,
        password=settings.ctfd_pass,
    )
    cost_tracker = CostTracker()

    swarm = ChallengeSwarm(
        challenge_dir=str(challenge_path),
        meta=meta,
        ctfd=ctfd,
        cost_tracker=cost_tracker,
        settings=settings,
        model_specs=model_specs,
        no_submit=no_submit,
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


async def _run_local_directory(
    settings: Settings,
    challenges_root: str,
    model_specs: list[str],
    no_submit: bool,
    max_challenges: int,
) -> None:
    """Solve one local challenge or every challenge directory under a root."""
    challenge_dirs = local_challenge_dirs(challenges_root)
    if not challenge_dirs:
        console.print(f"[red]No challenge directories with metadata.yml found under {challenges_root}[/red]")
        sys.exit(1)

    console.print(f"[bold]Local challenges root:[/bold] {Path(challenges_root).expanduser().resolve()}")
    console.print(f"[bold]Found {len(challenge_dirs)} challenge director{'y' if len(challenge_dirs) == 1 else 'ies'}.[/bold]")

    for idx, challenge_path in enumerate(challenge_dirs, start=1):
        console.print()
        console.print(f"[bold cyan]({idx}/{len(challenge_dirs)})[/bold cyan] Solving {challenge_path.name}")
        await _run_single(settings, str(challenge_path), model_specs, no_submit, max_challenges)


async def _run_coordinator(
    settings: Settings,
    model_specs: list[str],
    challenges_dir: str,
    no_submit: bool,
    coordinator_model: str | None,
    coordinator_backend: str,
    max_challenges: int,
    msg_port: int = 0,
) -> None:
    """Run the full coordinator (continuous until Ctrl+C)."""
    from backend.sandbox import cleanup_orphan_containers, configure_semaphore

    max_containers = max_challenges * len(model_specs)
    configure_semaphore(max_containers)
    await cleanup_orphan_containers()
    console.print(f"[bold]Starting coordinator ({coordinator_backend}, Ctrl+C to stop)...[/bold]\n")

    if coordinator_backend == "codex":
        from backend.agents.codex_coordinator import run_codex_coordinator
        results = await run_codex_coordinator(
            settings=settings,
            model_specs=model_specs,
            challenges_root=challenges_dir,
            no_submit=no_submit,
            coordinator_model=coordinator_model,
            msg_port=msg_port,
        )
    elif coordinator_backend == "kimi":
        from backend.agents.kimi_coordinator import run_kimi_coordinator
        results = await run_kimi_coordinator(
            settings=settings,
            model_specs=model_specs,
            challenges_root=challenges_dir,
            no_submit=no_submit,
            coordinator_model=coordinator_model,
            msg_port=msg_port,
        )
    else:
        from backend.agents.claude_coordinator import run_claude_coordinator
        results = await run_claude_coordinator(
            settings=settings,
            model_specs=model_specs,
            challenges_root=challenges_dir,
            no_submit=no_submit,
            coordinator_model=coordinator_model,
            msg_port=msg_port,
        )

    console.print("\n[bold]Final Results:[/bold]")
    for challenge, data in results.get("results", {}).items():
        console.print(f"  {challenge}: {data.get('flag', 'no flag')}")
    console.print(f"\n[bold]Total cost: ${results.get('total_cost_usd', 0):.2f}[/bold]")


@cli.command()
@click.argument("message")
@click.option("--port", default=9400, type=int, help="Coordinator message port")
@click.option("--host", default="127.0.0.1", help="Coordinator host")
def msg(message: str, port: int, host: str) -> None:
    """Send a message to the running coordinator."""
    import json
    import urllib.request

    body = json.dumps({"message": message}).encode()
    req = urllib.request.Request(
        f"http://{host}:{port}/msg",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            console.print(f"[green]Sent:[/green] {data.get('queued', message[:200])}")
    except Exception as e:
        console.print(f"[red]Failed:[/red] {e}")
        console.print("Is the coordinator running?")
        sys.exit(1)


@cli.command()
@click.option("--host", default="127.0.0.1", help="API bind host")
@click.option("--port", default=8081, type=int, help="API bind port")
@click.option(
    "--cors-origin",
    "cors_origins",
    multiple=True,
    help="Allowed CORS origin. Repeat for multiple origins.",
)
def api(host: str, port: int, cors_origins: tuple[str, ...]) -> None:
    """Start the local solver API for the frontend."""
    from backend.api_server import serve_api

    serve_api(host=host, port=port, cors_origins=list(cors_origins) or None)


if __name__ == "__main__":
    cli()


def main() -> None:
    """Entry point for the ctf-solve console script."""
    cli()
