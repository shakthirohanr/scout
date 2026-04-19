import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from backend.api.database import init_database, session_scope
from backend.api.routers.challenges import router as challenges_router
from backend.api.routers.events import router as events_router
from backend.api.routers.runs import router as runs_router
from backend.api.routers.system import router as system_router
from backend.api.routers.traces import router as traces_router
from backend.api.services.system_service import project_version
from backend.api.state import ORCHESTRATOR
from backend.api.utils import utcnow_iso

logger = logging.getLogger(__name__)

DEFAULT_CORS_ORIGINS = [
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:3001",
    "http://localhost:3001",
]


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    await ORCHESTRATOR.start()
    yield
    await ORCHESTRATOR.shutdown()


def create_app(cors_origins: list[str] | None = None) -> FastAPI:
    app = FastAPI(
        title="CTF Agent Solver API",
        version=project_version(),
        description="Local API for configuring, importing, and solving CTF challenges.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or DEFAULT_CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        checks: dict[str, str] = {}
        status = "ok"

        try:
            with session_scope() as session:
                session.execute(text("SELECT 1"))
            checks["db"] = "ok"
        except Exception as exc:
            checks["db"] = f"error: {exc}"
            status = "degraded"

        try:
            import aiodocker

            docker = aiodocker.Docker()
            await docker.version()
            await docker.close()
            checks["docker"] = "ok"
        except Exception as exc:
            checks["docker"] = f"error: {exc}"
            status = "degraded"

        orch_ok = (
            ORCHESTRATOR._health_task is not None
            and not ORCHESTRATOR._health_task.done()
            and ORCHESTRATOR._sync_task is not None
            and not ORCHESTRATOR._sync_task.done()
        )
        checks["orchestrator"] = "ok" if orch_ok else "not running"
        if not orch_ok:
            status = "degraded"

        checks["active_agents"] = str(ORCHESTRATOR.active_agent_count)
        checks["max_agents"] = str(ORCHESTRATOR.max_agent_count)

        code = 200 if status == "ok" else 503
        return JSONResponse(
            status_code=code,
            content={"status": status, "ts": utcnow_iso(), "checks": checks},
        )

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        if not ORCHESTRATOR._ready:
            return JSONResponse(
                status_code=503, content={"status": "not ready", "ts": utcnow_iso()}
            )
        return JSONResponse(status_code=200, content={"status": "ready", "ts": utcnow_iso()})

    app.include_router(system_router)
    app.include_router(challenges_router)
    app.include_router(runs_router)
    app.include_router(traces_router)
    app.include_router(events_router)

    return app
