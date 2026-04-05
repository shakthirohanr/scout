"""Challenge catalog service combining local sync and imported CTF data."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete

from backend.api.database import session_scope
from backend.api.db_models import Challenge
from backend.api.repositories.ctf_repository import (
    get_challenge_by_id,
    get_or_create_ctf_source,
    list_challenges,
    list_ctf_sources,
    slugify,
    upsert_challenge,
)
from backend.api.repositories.run_repository import ACTIVE_RUN_STATUSES
from backend.api.services.mappers import challenge_to_dict, ctf_source_to_dict
from backend.api.services.run_manager_service import RunManager
from backend.config import Settings
from backend.local_challenges import list_local_challenges
from backend.run_config import SolverRunConfig, load_ui_config

LOCAL_SOURCE_NAME = "Local Challenges"
LOCAL_SOURCE_URL = "local://filesystem"


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


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

        valid_local_paths = {
            str(Path(item.path).expanduser().resolve())
            for item in local_items
        }
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
    run_manager: RunManager | None = None,
) -> dict[str, Any]:
    sync_local_catalog(challenges_root)
    if run_manager is not None:
        run_manager.sync_runs()

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


def start_challenge_run(
    *,
    challenge_id: str,
    launch_solver: bool,
    run_manager: RunManager,
) -> dict[str, Any]:
    settings = Settings()
    config = load_ui_config()
    run_manager.sync_runs()

    with session_scope() as session:
        challenge = get_challenge_by_id(session, challenge_id)
        if challenge is None:
            raise KeyError(challenge_id)
        if challenge.state in ACTIVE_RUN_STATUSES:
            raise RuntimeError("Challenge is already running. Kill it before starting again.")
        challenge_payload = challenge_to_dict(challenge)

    run_snapshot = None
    if launch_solver:
        run_config = SolverRunConfig(
            mode="solve",
            challenge_dir=str(challenge_payload["path"]),
            challenges_dir=config.challenges_dir,
            ctfd_url=config.ctfd_url,
            image=config.image,
            models=config.models,
            no_submit=config.no_submit,
            verbose=config.verbose,
            coordinator=config.coordinator,
            coordinator_model=config.coordinator_model,
            max_challenges=config.max_challenges,
            msg_port=config.msg_port,
        )
        run_snapshot = run_manager.start(run_config, settings, challenge_id=challenge_id)
        challenge_payload = get_challenge_or_none(challenge_id) or challenge_payload

    return {
        "challenge": challenge_payload,
        "run": run_snapshot,
        "generated_at": utcnow_iso(),
    }


def stop_challenge_run(
    *,
    challenge_id: str,
    run_manager: RunManager,
) -> dict[str, Any]:
    run_manager.sync_runs()
    with session_scope() as session:
        challenge = get_challenge_by_id(session, challenge_id)
        if challenge is None:
            raise KeyError(challenge_id)
        challenge_payload = challenge_to_dict(challenge)

    termination = run_manager.terminate_challenge(
        challenge_id=challenge_id,
        challenge_path=str(challenge_payload["path"]),
    )
    challenge_payload = get_challenge_or_none(challenge_id) or challenge_payload

    return {
        "challenge": challenge_payload,
        "termination": termination,
        "generated_at": utcnow_iso(),
    }


def delete_challenge_run_data(
    *,
    challenge_id: str,
    run_manager: RunManager,
) -> dict[str, Any]:
    run_manager.sync_runs()
    result = run_manager.delete_challenge_data(challenge_id)
    challenge_payload = get_challenge_or_none(challenge_id)
    challenge = challenge_payload or (
        challenge_to_dict(result["challenge"])
        if result["challenge"] is not None
        else None
    )
    if challenge is None:
        raise KeyError(challenge_id)

    return {
        "challenge": challenge,
        "deleted_runs": result["deleted_runs"],
        "files_removed": result["files_removed"],
        "generated_at": utcnow_iso(),
    }


def get_challenge_or_none(challenge_id: str) -> dict[str, Any] | None:
    with session_scope() as session:
        challenge = get_challenge_by_id(session, challenge_id)
        return challenge_to_dict(challenge) if challenge else None
