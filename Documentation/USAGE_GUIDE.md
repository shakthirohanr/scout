# Usage Guide

This guide focuses on how to run the repository as it is implemented today.

Note: run Python and `uv` commands from `backend/` unless a command explicitly wraps `cd backend`.

## 1. Requirements

You need:

- Python 3.14+
- `uv`
- Docker
- at least one working model credential or compatible endpoint

You may also need:

- the `codex` CLI if you want to use `codex/*` solver specs or the Codex coordinator backend
- valid Anthropic credentials if you want to use Claude-backed components

## 2. Initial Setup

### Install dependencies

```bash
(cd backend && uv sync)
```

### Build the sandbox image

The solver runs inside a Docker image named `ctf-sandbox` by default.

```bash
docker build -f sandbox/Dockerfile.sandbox -t ctf-sandbox .
```

### Create `.env`

```bash
cp backend/.env.example backend/.env
```

Minimum connected setup:

```env
CTFD_URL=https://ctf.example.com
CTFD_TOKEN=ctfd_your_api_token_here
OPENAI_API_KEY=...
```

Kimi-style setup:

```env
KIMI_API_KEY=...
KIMI_API_BASE_URL=https://llm.proxies.of.achyuth.dev/v1
```

Generic OpenAI-compatible setup:

```env
GENERIC_OPENAI_BASE_URL=http://localhost:11434/v1
GENERIC_OPENAI_API_KEY=ollama
```

## 3. Challenge Directory Format

Each local challenge directory should contain:

```text
challenge-name/
├── metadata.yml
└── distfiles/
```

Typical `metadata.yml`:

```yaml
name: example-web
category: web
value: 500
description: Find the real flag.
connection_info: http://127.0.0.1:8080
tags: []
hints: []
solves: 0
```

Behavior notes:

- `distfiles/` is mounted read-only into the sandbox
- `metadata.yml` is mounted read-only into the sandbox
- a temporary writable workspace is mounted at `/challenge/workspace`
- local `localhost` and `127.0.0.1` targets are rewritten to `host.docker.internal` for solver prompts

## 4. Creating a New Challenge Folder

Use `init` to scaffold a local challenge:

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

After that, place any provided files under `prob1/distfiles/`.

## 5. Solving One Local Challenge

Run from the repo root:

```bash
uv run ctf-solve solve ./prob1 --models kimi/kimi-k2p5-turbo
```

If you are already inside the challenge directory:

```bash
uv run ctf-solve solve-local --models kimi/kimi-k2p5-turbo
```

Useful flags:

- `--no-submit` keeps the run in dry-run mode
- `-v` enables verbose logging
- `--image` chooses a non-default sandbox image

Example:

```bash
uv run ctf-solve solve ./prob1 --models generic-openai/gpt-4o-mini --no-submit -v
```

## 6. Solving Every Challenge Under a Root

Use `solve-dir` when you have many local challenge directories:

```bash
uv run ctf-solve solve-dir ./challenges --models kimi/kimi-k2p5-turbo
```

What happens:

- the command scans recursively for folders containing `metadata.yml`
- challenges are processed one after another
- each challenge is solved with the selected solver model

## 7. Connected CTFd Coordinator Mode

Use `run` with a CTFd URL and token when you want the agent to watch a live platform:

```bash
uv run ctf-solve run \
  --ctfd-url https://ctf.example.com \
  --ctfd-token ctfd_your_token \
  --challenges-dir challenges \
  --coordinator kimi \
  --max-challenges 10 \
  -v
```

What this mode does:

- starts the poller
- detects new challenges and solves
- auto-pulls challenge metadata and files into `challenges/`
- starts a swarm per challenge, subject to concurrency limits
- exposes a local dashboard/message endpoint

Coordinator choices:

```bash
uv run ctf-solve run --coordinator kimi ...
uv run ctf-solve run --coordinator claude ...
uv run ctf-solve run --coordinator codex ...
```

Coordinator model override:

```bash
uv run ctf-solve run --coordinator kimi --coordinator-model kimi/kimi-k2p5-turbo ...
uv run ctf-solve run --coordinator codex --coordinator-model gpt-5.4 ...
```

## 8. Offline and Fallback Behavior

The local solving commands are already CTFd-free by default:

```bash
uv run ctf-solve solve ./prob1
uv run ctf-solve solve-local
uv run ctf-solve solve-dir ./challenges
```

The `--offline` flag exists on `run` and is useful when you want to force manual/local behavior even though `run` is the entrypoint you are using.

Explicit offline `run`:

```bash
uv run ctf-solve run --challenge ./prob1 --offline
```

Local directory fallback from `run`:

```bash
uv run ctf-solve run --challenges-dir ./challenges --offline
```

Also important:

- if `run` is used without a CTFd URL and without `--challenge`, it falls back to local-directory solving
- in mock or dry-run flows, a discovered flag can still terminate a run without a real server submission

## 9. Sending Operator Messages

Coordinator mode starts a small HTTP server that powers:

- the dashboard
- operator messages
- trace inspection
- challenge stop controls

By default, coordinator mode uses `--msg-port 0`, which means the OS chooses a free port. The actual dashboard URL is logged at startup.

If you want a fixed message port:

```bash
uv run ctf-solve run ... --msg-port 9400
```

Then you can use:

```bash
uv run ctf-msg "Focus on the web challenges first" --port 9400
```

If you leave the port dynamic, use the dashboard URL from the logs instead of assuming `9400`.

## 10. Using `run_ctf_agent.py`

`run_ctf_agent.py` is a wrapper around the CLI.

Open the file and set:

- `MODE`
- `CHALLENGE_DIR`
- `CHALLENGES_DIR`
- `CTFD_URL`
- `CTFD_TOKEN`
- `MODELS`
- `IMAGE`
- `MAX_CHALLENGES`
- `NO_SUBMIT`
- `COORDINATOR`
- `COORDINATOR_MODEL`
- `MSG_PORT`

Then run:

```bash
python run_ctf_agent.py
```

Available `MODE` values:

- `ctfd`
- `solve`
- `solve-local`
- `solve-dir`

This is useful when you want a repeatable launcher without typing long commands every time.

## 11. Model Spec Examples

Examples of solver model specs accepted by the code:

```bash
--models kimi/kimi-k2p5-turbo
--models generic-openai/gpt-4o-mini
--models google/gemini-3-flash-preview
--models azure/gpt-5.4
--models bedrock/us.anthropic.claude-opus-4-6-v1
--models zen/gpt-5.3-codex-spark
```

Examples of special backend solver specs:

```bash
--models codex/gpt-5.4
--models claude-sdk/claude-opus-4-6
```

Important current behavior:

- you can pass `--models` more than once
- the CLI currently keeps only the first model spec and prints a warning if you gave more than one
- the underlying swarm code supports more than one solver model, but the CLI does not currently expose that behavior directly

## 12. Dry Runs and Safe Testing

Use `--no-submit` whenever you want to test prompts, tooling, or end-to-end behavior without affecting the scoreboard.

Examples:

```bash
uv run ctf-solve solve ./prob1 --no-submit -v
uv run ctf-solve solve-dir ./challenges --no-submit
uv run ctf-solve run --ctfd-url https://ctf.example.com --ctfd-token ... --no-submit
```

In this mode:

- the solver still tries to find a real flag
- submission calls return dry-run messages
- structured output can still end a run successfully

## 13. Logs and Traces

Solver traces are written under `logs/` as JSONL files.

Typical filename:

```text
logs/trace-challenge-name-model-id-YYYYMMDD-HHMMSS.jsonl
```

Use cases:

- understand what a solver actually tried
- confirm whether it is looping
- inspect recent tool usage
- help the coordinator craft targeted bumps

The coordinator dashboard can read recent trace lines for active challenges.

## 14. Practical Workflow Examples

### Local web challenge

1. Create the directory with `init`.
2. Put files in `distfiles/`.
3. Set `connection_info` in `metadata.yml`.
4. Run `solve` with `--no-submit` first.
5. Remove `--no-submit` once you are happy with the behavior.

### Batch solving a local archive

1. Put all challenge folders under one root.
2. Ensure each challenge has `metadata.yml`.
3. Run `solve-dir`.
4. Review traces in `logs/` for stuck challenges.

### Live CTFd run

1. Set `CTFD_URL` and `CTFD_TOKEN`.
2. Build the sandbox image.
3. Start `run` with a fixed `--msg-port`.
4. Open the dashboard in a browser.
5. Use `ctf-msg` or the dashboard to steer the coordinator if needed.

## 15. Troubleshooting

### No `metadata.yml` found

The CLI requires `metadata.yml` for local solving. Either:

- run `init` first
- or point the command at a directory that already contains it

### Service reachable on host but not from container

Check:

- the service is actually listening on the host
- `connection_info` points to `127.0.0.1` or `localhost` if it is a host-local service
- Docker is available and the sandbox started correctly

The prompt builder rewrites local addresses to `host.docker.internal`, which is what the container uses.

### `ctf-msg` cannot connect

Most likely causes:

- the coordinator is not running
- the coordinator used an auto-selected port
- you are sending to the wrong port

Fix by starting `run` with a known `--msg-port`.

### Multiple `--models` do not start multiple solvers

That is current CLI behavior. Only the first spec is used unless the CLI code is changed.

### Want richer logs

Add `-v` to CLI commands. That turns on verbose logging and surfaces more runtime detail.
