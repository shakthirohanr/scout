"""Challenge and CTF import routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.api.database import session_scope
from backend.api.repositories.ctf_repository import list_ctf_sources
from backend.api.schemas import CTFImportRequest, StartChallengeRequest, SteerChallengeRequest
from backend.api.services.catalog_service import (
    delete_challenge as delete_challenge_entry,
)
from backend.api.services.catalog_service import (
    delete_challenge_run_data,
    get_catalog_payload,
    start_challenge_run,
    stop_challenge_run,
)
from backend.api.services.catalog_service import (
    delete_ctf as delete_ctf_entry,
)
from backend.api.services.ctfd_import_service import CTFImportError, import_ctf_challenges
from backend.api.services.mappers import ctf_source_to_dict
from backend.api.state import ORCHESTRATOR
from backend.api.utils import utcnow_iso
from backend.run_config import load_ui_config

router = APIRouter(prefix="/api/v1", tags=["challenges"])


@router.get("/challenges")
def challenges(
    root: str | None = Query(default=None),
    ctf_id: int | None = Query(default=None),
) -> dict[str, Any]:
    config = load_ui_config()
    challenges_root = root or config.challenges_dir
    return get_catalog_payload(
        challenges_root,
        ctf_id=ctf_id,
        orchestrator=ORCHESTRATOR,
    )


@router.post("/challenges/start")
async def start_challenge(request: StartChallengeRequest) -> dict[str, Any]:
    try:
        return await start_challenge_run(
            challenge_id=request.challenge_id,
            launch_solver=request.launch_solver,
            agent_count=request.agent_count,
            orchestrator=ORCHESTRATOR,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Challenge not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/challenges/{challenge_id}/kill")
async def kill_challenge(challenge_id: str) -> dict[str, Any]:
    try:
        return await stop_challenge_run(
            challenge_id=challenge_id,
            orchestrator=ORCHESTRATOR,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Challenge not found.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/challenges/{challenge_id}")
def delete_challenge(challenge_id: str) -> dict[str, Any]:
    try:
        return delete_challenge_entry(
            challenge_id=challenge_id,
            orchestrator=ORCHESTRATOR,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Challenge not found.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/challenges/{challenge_id}/data")
async def delete_challenge_data(challenge_id: str) -> dict[str, Any]:
    try:
        return await delete_challenge_run_data(
            challenge_id=challenge_id,
            orchestrator=ORCHESTRATOR,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Challenge not found.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/challenges/{challenge_id}/steer")
async def steer_challenge(challenge_id: str, request: SteerChallengeRequest) -> dict[str, Any]:
    try:
        payload = await ORCHESTRATOR.steer(
            challenge_id=challenge_id,
            message=request.message,
            source=request.source,
            run_id=request.run_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Challenge not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    payload["generated_at"] = utcnow_iso()
    return payload


@router.get("/ctfs")
def list_ctfs() -> dict[str, Any]:
    with session_scope() as session:
        sources = [
            ctf_source_to_dict(source, challenge_count=int(count))
            for source, count in list_ctf_sources(session)
        ]
    return {
        "ctfs": sources,
        "count": len(sources),
        "generated_at": utcnow_iso(),
    }


@router.delete("/ctfs/{ctf_id}")
def remove_ctf(ctf_id: int) -> dict[str, Any]:
    try:
        return delete_ctf_entry(
            ctf_id=ctf_id,
            orchestrator=ORCHESTRATOR,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="CTF source not found.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/ctfs/import")
async def import_ctf(request: CTFImportRequest) -> dict[str, Any]:
    try:
        response = await import_ctf_challenges(request)
    except CTFImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Import failed: {exc}") from exc

    return response.model_dump(mode="json")
