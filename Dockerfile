FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git curl build-essential libssl-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY backend/pyproject.toml backend/uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

COPY backend/ ./

ENV PYTHONUNBUFFERED=1
ENV CTF_AGENT_CHALLENGES_DIR=/challenges
ENV CTF_AGENT_LOGS_DIR=/app/logs

EXPOSE 8081

CMD ["uv", "run", "python", "-m", "backend.cli"]
