import contextlib
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.database import init_database
from backend.api.routers.challenges import router as challenges_router
from backend.api.routers.runs import router as runs_router
from backend.api.routers.system import router as system_router
from backend.api.routers.traces import router as traces_router
from backend.api.services.system_service import project_version
from backend.api.state import RUN_MANAGER
from backend.api.utils import utcnow_iso

DEFAULT_CORS_ORIGINS = [
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:3001",
    "http://localhost:3001",
]




@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_database()
    RUN_MANAGER.sync_runs()
    yield
    # Shutdown
    RUN_MANAGER.shutdown()


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
    def healthz() -> dict[str, str]:
        return {"status": "ok", "ts": utcnow_iso()}

    app.include_router(system_router)
    app.include_router(challenges_router)
    app.include_router(runs_router)
    app.include_router(traces_router)

    return app
