# CTF Agent Usage Guide

This guide covers the main ways to use the agent:

- connected CTFd coordinator mode
- single local challenge solving
- solve-local alias from inside the challenge directory
- local directory solving
- manual challenge initialization
- Kimi / OpenAI-compatible API usage
- dry-run and no-submit workflows

Note: run Python and `uv` commands from `backend/` unless a command explicitly wraps `cd backend`.

## 1. First-time setup

### Install dependencies

```bash
(cd backend && uv sync)
```

### Build the sandbox image once

The agent runs each solver inside a Docker container based on the sandbox image. Build it once before the first run:

```bash
docker build -f sandbox/Dockerfile.sandbox -t ctf-sandbox .
```

After that, the agent creates and destroys challenge containers automatically.

### Create your environment file

Copy the example and edit it:

```bash
cp backend/.env.example backend/.env
```

Minimum useful variables:

```env
CTFD_URL=https://ctf.example.com
CTFD_TOKEN=ctfd_your_api_token_here
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
KIMI_API_KEY=sk-...
KIMI_API_BASE_URL=https://llm.proxies.of.achyuth.dev/v1
```

## 2. What the dockerization does

Each solver runs in an isolated container.

Mounted into the container:

- the challenge directory
- `distfiles/` as read-only
- `metadata.yml` as read-only
- a temporary writable workspace at `/challenge/workspace`

The sandbox is started automatically by the code. You do not start per-challenge containers by hand.

## 3. Scenario: connected CTFd coordinator mode

Use this when you want the agent to watch a CTFd instance and spawn swarms automatically.

```bash
uv run ctf-solve run \
  --ctfd-url https://ctf.example.com \
  --ctfd-token ctfd_your_token \
  --challenges-dir challenges \
  --max-challenges 10 \
  -v
```

### What happens

- the poller checks CTFd regularly
- new challenges are pulled into `challenges/`
- a swarm is spawned per challenge
- multiple models race in parallel
- solved challenges are tracked automatically

### Coordinator backend selection

```bash
uv run ctf-solve run --coordinator claude ...
uv run ctf-solve run --coordinator codex ...
```

## 4. Scenario: solve one local challenge directory

Use this when you already have a challenge folder with `metadata.yml`.

```bash
uv run ctf-solve solve ./prob1 --models kimi-k2p5-turbo
```

If you are already inside the challenge directory, use the alias:

```bash
uv run ctf-solve solve-local
```

If the challenge uses a local service, put its address in `metadata.yml` under `connection_info`.

Example structure:

```text
prob1/
├── metadata.yml
└── distfiles/
    └── file.bin
```

## 5. Scenario: solve every challenge under a local root

Use this when you have many challenge folders under one directory.

```bash
uv run ctf-solve solve-dir ./challenges --models kimi-k2p5-turbo
```

The command scans for folders containing `metadata.yml` and solves each one.

Swarming is disabled in this setup: each challenge is solved by one Kimi K2p5 Turbo subagent.

## 6. Scenario: offline/manual mode

If you do not have a CTFd URL, the agent can still solve local challenges.

### Single challenge

```bash
uv run ctf-solve solve ./prob1 --offline
```

Or, from inside the challenge folder:

```bash
uv run ctf-solve solve-local --offline
```

### Local directory

```bash
uv run ctf-solve solve-dir ./challenges --offline
```

### Fallback behavior

The main `run` command now falls back to local-directory solving when no CTFd URL is configured.

## 7. Scenario: initialize a new challenge folder

Use this to prepare a fresh challenge directory.

```bash
uv run ctf-solve init prob1 \
  --category web \
  --value 500 \
  --connection-info "http://127.0.0.1:57540" \
  --description "Challenge description here"
```

This creates:

- `prob1/metadata.yml`
- `prob1/distfiles/`

Then copy any provided files into `distfiles/`.

## 8. Scenario: dry run or no-submit

If you want the agent to solve without actually submitting flags:

```bash
uv run ctf-solve solve ./prob1 --no-submit
```

This is useful for testing prompts, tracing, and cost behavior.

## 9. Scenario: Kimi K2p5 Turbo

This repo supports Kimi through an OpenAI-compatible proxy.

### Example CLI usage

```bash
uv run ctf-solve solve ./prob1 --models kimi-k2p5-turbo
```

### Example `.env`

```env
KIMI_API_KEY=sk-your-key
KIMI_API_BASE_URL=https://llm.proxies.of.achyuth.dev/v1
```

If you prefer the explicit provider form, use:

```bash
uv run ctf-solve solve ./prob1 --models kimi/kimi-k2p5-turbo
```

## 10. Scenario: generic OpenAI-compatible API

Use this for any other OpenAI-compatible endpoint.

```env
GENERIC_OPENAI_BASE_URL=http://localhost:11434/v1
GENERIC_OPENAI_API_KEY=ollama
```

Then run:

```bash
uv run ctf-solve solve ./prob1 --models generic-openai/gpt-4o-mini
```

## 11. Scenario: Fireworks AI

Fireworks exposes an OpenAI-compatible endpoint, but its model IDs usually include path segments.

```env
FIREWORKS_API_BASE_URL=https://api.fireworks.ai/inference/v1
FIREWORKS_API_KEY=your_fireworks_api_key
```

Then run:

```bash
uv run ctf-solve solve ./prob1 --models fireworks/accounts/fireworks/models/llama-v3p1-8b-instruct
```

## 12. Common workflows

### A. Local web challenge with a local service

1. Create the folder with `init`
2. Put the service URL in `metadata.yml`
3. Put files in `distfiles/`
4. Run `solve` or `solve-dir`

### B. CTFd competition run

1. Set `CTFD_URL` and `CTFD_TOKEN`
2. Build the sandbox image
3. Run `ctf-solve run`
4. Let the coordinator pull challenges and spawn swarms

### C. Quick test with one model

```bash
uv run ctf-solve solve ./prob1 --models kimi-k2p5-turbo --no-submit -v
```

Inside the folder:

```bash
uv run ctf-solve solve-local --no-submit -v
```

## 13. Helpful notes

- `connection_info` should use `host.docker.internal` if the service is running on your host machine.
- The agent rewrites local `127.0.0.1` / `localhost` service URLs for container access.
- The sandbox image name defaults to `ctf-sandbox`.
- Multiple models can be passed with repeated `--models` flags.

Example:

```bash
uv run ctf-solve solve ./prob1 \
  --models kimi-k2p5-turbo \
  --models gpt-5.4-mini
```

## 14. Troubleshooting

### Docker image not found

Build the sandbox image first:

```bash
docker build -f sandbox/Dockerfile.sandbox -t ctf-sandbox .
```

### No metadata.yml found

Make sure the challenge folder contains `metadata.yml`.

### CTFd mode fails without URL

Use `solve` or `solve-dir` for local-only workflows, or configure `CTFD_URL`.

### Kimi requests fail

Check that:

- `KIMI_API_KEY` is set
- `KIMI_API_BASE_URL` is correct
- the proxy accepts OpenAI-style `/v1/chat/completions` requests

## 15. Short command summary

```bash
uv sync

docker build -f sandbox/Dockerfile.sandbox -t ctf-sandbox .

uv run ctf-solve init prob1
uv run ctf-solve solve ./prob1
uv run ctf-solve solve-dir ./challenges
uv run ctf-solve run --ctfd-url https://ctf.example.com --ctfd-token TOKEN
```
