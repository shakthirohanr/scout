"""FastAPI app factory for modular backend architecture."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.database import init_database
from backend.api.routers.challenges import router as challenges_router
from backend.api.routers.runs import router as runs_router
from backend.api.routers.system import router as system_router
from backend.api.routers.traces import router as traces_router
from backend.api.services.system_service import project_version
from backend.api.state import RUN_MANAGER


DEFAULT_CORS_ORIGINS = [
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:3001",
    "http://localhost:3001",
]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_app(cors_origins: list[str] | None = None) -> FastAPI:
    app = FastAPI(
        title="CTF Agent Solver API",
        version=project_version(),
        description="Local API for configuring, importing, and solving CTF challenges.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or DEFAULT_CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def _startup() -> None:
        init_database()

    @app.on_event("shutdown")
    def _shutdown() -> None:
        RUN_MANAGER.shutdown()

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "ts": _utcnow_iso()}

    app.include_router(system_router)
    app.include_router(challenges_router)
    app.include_router(runs_router)
    app.include_router(traces_router)

    return app
