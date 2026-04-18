"""Challenge catalog service combining local sync and imported CTF data."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from sqlalchemy import delete

from backend.api.database import session_scope
from backend.api.db_models import Challenge
from backend.api.repositories.ctf_repository import (
    get_challenge_by_id,
    get_ctf_source_with_challenges,
    get_or_create_ctf_source,
    list_challenges,
    list_ctf_sources,
    slugify,
    upsert_challenge,
)
from backend.api.repositories.run_repository import ACTIVE_RUN_STATUSES, delete_runs_for_challenge
from backend.api.services.mappers import challenge_to_dict, ctf_source_to_dict
from backend.api.utils import utcnow_iso
from backend.config import get_settings
from backend.local_challenges import list_local_challenges
from backend.orchestrator.orchestrator import AgentOrchestrator
from backend.run_config import load_ui_config

LOCAL_SOURCE_NAME = "Local Challenges"
LOCAL_SOURCE_URL = "local://filesystem"


def _is_under_any(path: Path, roots: list[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def sync_local_catalog(challenges_root: str) -> None:
    root = Path(challenges_root).expanduser().resolve()
    if not root.exists():
        return

    raw_local_items = list_local_challenges(str(root))
    with session_scope() as session:
        imported_ctf_roots: list[Path] = []
        for ctf_source, _ in list_ctf_sources(session):
            if ctf_source.base_url == LOCAL_SOURCE_URL:
                continue
            source_root = Path(ctf_source.challenges_root).expanduser().resolve()
            imported_ctf_roots.append((source_root / ctf_source.slug).resolve())

        local_items = [
            item
            for item in raw_local_items
            if not _is_under_any(Path(item.path).expanduser().resolve(), imported_ctf_roots)
        ]

        source = get_or_create_ctf_source(
            session,
            name=LOCAL_SOURCE_NAME,
            base_url=LOCAL_SOURCE_URL,
            auth_mode="none",
            challenges_root=str(root),
        )

        valid_local_paths = {str(Path(item.path).expanduser().resolve()) for item in local_items}
        if valid_local_paths:
            session.execute(
                delete(Challenge).where(
                    Challenge.ctf_id == source.id,
                    Challenge.path.not_in(valid_local_paths),
                )
            )
        else:
            session.execute(delete(Challenge).where(Challenge.ctf_id == source.id))

        for item in local_items:
            challenge_slug = slugify(item.name)
            upsert_challenge(
                session,
                source=source,
                external_id=None,
                name=item.name,
                challenge_slug=challenge_slug,
                path=str(Path(item.path).expanduser().resolve()),
                category=item.category,
                value=item.value,
                description=item.description,
                connection_info=item.connection_info,
                has_distfiles=item.has_distfiles,
                distfile_count=item.distfile_count,
                solves=0,
            )


def get_catalog_payload(
    challenges_root: str,
    *,
    ctf_id: int | None = None,
    orchestrator: AgentOrchestrator | None = None,
) -> dict[str, Any]:
    sync_local_catalog(challenges_root)
    if orchestrator is not None:
        orchestrator.sync_runs()

    with session_scope() as session:
        sources_with_counts = list_ctf_sources(session)
        challenges = list_challenges(session, ctf_id=ctf_id)

        return {
            "root": str(Path(challenges_root).expanduser().resolve()),
            "count": len(challenges),
            "ctfs": [
                ctf_source_to_dict(source, challenge_count=int(count))
                for source, count in sources_with_counts
            ],
            "catalog": [challenge_to_dict(item) for item in challenges],
            "generated_at": utcnow_iso(),
        }


async def start_challenge_run(
    *,
    challenge_id: str,
    launch_solver: bool,
    agent_count: int = 1,
    orchestrator: AgentOrchestrator = None,
) -> dict[str, Any]:
    settings = get_settings()
    config = load_ui_config()
    orchestrator.sync_runs()

    with session_scope() as session:
        challenge = get_challenge_by_id(session, challenge_id)
        if challenge is None:
            raise KeyError(challenge_id)
        if challenge.state in ACTIVE_RUN_STATUSES:
            raise RuntimeError("Challenge is already running. Kill it before starting again.")
        challenge_payload = challenge_to_dict(challenge)

    run_snapshots = []
    if launch_solver:
        model_specs = config.models or [settings.default_solver_model]
        run_snapshots = await orchestrator.spawn(
            challenge_id=challenge_id,
            challenge_dir=str(challenge_payload["path"]),
            challenge_name=challenge_payload["name"],
            model_specs=model_specs,
            agent_count=max(1, agent_count),
            settings=settings,
            no_submit=config.no_submit,
        )
        challenge_payload = get_challenge_or_none(challenge_id) or challenge_payload

    return {
        "challenge": challenge_payload,
        "runs": run_snapshots,
        "generated_at": utcnow_iso(),
    }


async def stop_challenge_run(
    *,
    challenge_id: str,
    orchestrator: AgentOrchestrator,
) -> dict[str, Any]:
    orchestrator.sync_runs()
    with session_scope() as session:
        challenge = get_challenge_by_id(session, challenge_id)
        if challenge is None:
            raise KeyError(challenge_id)
        challenge_payload = challenge_to_dict(challenge)

    termination = await orchestrator.kill_challenge(
        challenge_id=challenge_id,
        challenge_path=str(challenge_payload["path"]),
    )
    challenge_payload = get_challenge_or_none(challenge_id) or challenge_payload

    return {
        "challenge": challenge_payload,
        "termination": termination,
        "generated_at": utcnow_iso(),
    }


async def delete_challenge_run_data(
    *,
    challenge_id: str,
    orchestrator: AgentOrchestrator,
) -> dict[str, Any]:
    result = await orchestrator.delete_challenge_data(challenge_id)
    challenge_payload = get_challenge_or_none(challenge_id)
    challenge = challenge_payload or (
        challenge_to_dict(result["challenge"]) if result["challenge"] is not None else None
    )
    if challenge is None:
        raise KeyError(challenge_id)

    return {
        "challenge": challenge,
        "deleted_runs": result["deleted_runs"],
        "files_removed": result["files_removed"],
        "generated_at": utcnow_iso(),
    }


def _remove_tree_if_allowed(path: Path, *, allowed_root: Path) -> bool:
    resolved_path = path.expanduser().resolve()
    resolved_root = allowed_root.expanduser().resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        return False

    if not resolved_path.exists():
        return False

    shutil.rmtree(resolved_path, ignore_errors=True)
    return not resolved_path.exists()


def delete_challenge(
    *,
    challenge_id: str,
    orchestrator: AgentOrchestrator,
) -> dict[str, Any]:
    orchestrator.sync_runs()

    with session_scope() as session:
        challenge = get_challenge_by_id(session, challenge_id)
        if challenge is None:
            raise KeyError(challenge_id)
        if challenge.state in ACTIVE_RUN_STATUSES:
            raise RuntimeError("Challenge is still running. Kill it before deleting.")
        if challenge.ctf_source.base_url == LOCAL_SOURCE_URL:
            raise RuntimeError("Local challenges cannot be deleted from the UI.")

        challenge_payload = challenge_to_dict(challenge)
        challenge_name = challenge.name
        challenge_path = Path(challenge.path)
        ctf_root = (
            Path(challenge.ctf_source.challenges_root).expanduser().resolve()
            / challenge.ctf_source.slug
        )

        runs = delete_runs_for_challenge(session, challenge_id)
        session.delete(challenge)
        session.flush()

    files_removed = AgentOrchestrator._delete_run_artifacts(runs, challenge_name=challenge_name)
    directory_removed = _remove_tree_if_allowed(challenge_path, allowed_root=ctf_root)

    return {
        "challenge": challenge_payload,
        "deleted_runs": len(runs),
        "files_removed": files_removed,
        "directory_removed": directory_removed,
        "generated_at": utcnow_iso(),
    }


def delete_ctf(
    *,
    ctf_id: int,
    orchestrator: AgentOrchestrator,
) -> dict[str, Any]:
    orchestrator.sync_runs()

    with session_scope() as session:
        source = get_ctf_source_with_challenges(session, ctf_id)
        if source is None:
            raise KeyError(ctf_id)
        if source.base_url == LOCAL_SOURCE_URL:
            raise RuntimeError("The local challenge source cannot be deleted from the UI.")

        challenges = list(source.challenges)
        active_names = [ch.name for ch in challenges if ch.state in ACTIVE_RUN_STATUSES]
        if active_names:
            raise RuntimeError(
                "One or more challenges are still running. Kill them before deleting this CTF."
            )

        source_payload = ctf_source_to_dict(source, challenge_count=len(challenges))
        runs = []
        for ch in challenges:
            runs.extend(delete_runs_for_challenge(session, ch.id))

        session.delete(source)
        session.flush()

    files_removed = AgentOrchestrator._delete_run_artifacts(runs)
    source_root = Path(str(source_payload["challenges_root"])).expanduser().resolve()
    ctf_root = source_root / str(source_payload["slug"])
    root_removed = _remove_tree_if_allowed(ctf_root, allowed_root=source_root)

    return {
        "ctf": source_payload,
        "deleted_challenges": len(challenges),
        "deleted_runs": len(runs),
        "files_removed": files_removed,
        "root_removed": root_removed,
        "generated_at": utcnow_iso(),
    }


def get_challenge_or_none(challenge_id: str) -> dict[str, Any] | None:
    with session_scope() as session:
        challenge = get_challenge_by_id(session, challenge_id)
        return challenge_to_dict(challenge) if challenge else None
