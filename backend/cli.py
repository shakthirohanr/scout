"""Application entry point — starts the API server with the agent orchestrator."""

from __future__ import annotations

import logging

from backend.config import get_settings


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    for noisy in ("httpx", "httpcore", "botocore", "urllib3", "aiodocker"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)-8s %(message)s", datefmt="%X")
    )
    logging.basicConfig(level=level, handlers=[handler], force=True)


def main() -> None:
    settings = get_settings()
    _setup_logging(settings.verbose)
    from backend.api_server import serve_api

    serve_api(host=settings.api_host, port=settings.api_port, cors_origins=None)


if __name__ == "__main__":
    main()
