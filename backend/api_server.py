"""HTTP API entrypoint for the modular backend architecture."""

from __future__ import annotations

import uvicorn

from backend.api.app import create_app


app = create_app()


def serve_api(host: str = "127.0.0.1", port: int = 8081, cors_origins: list[str] | None = None) -> None:
    uvicorn.run(create_app(cors_origins=cors_origins), host=host, port=port, log_level="info")


def main() -> None:
    serve_api()
