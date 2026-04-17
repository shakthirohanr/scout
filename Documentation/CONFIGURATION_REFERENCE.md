# Configuration Reference

This document summarizes the runtime knobs exposed by the current codebase.

## 1. Environment Variables

The settings object is defined in `backend/config.py`.

### CTFd

```env
CTFD_URL=
CTFD_USER=admin
CTFD_PASS=admin
CTFD_TOKEN=
```

Notes:

- `CTFD_TOKEN` is the preferred auth path for live use
- username/password fallback exists, but most CTFd deployments are easier to use with a token

### Primary API Keys

```env
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=
```

### Provider-Specific and Optional

```env
AWS_REGION=us-east-1
AWS_BEARER_TOKEN=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
OPENCODE_ZEN_API_KEY=
GENERIC_OPENAI_BASE_URL=
GENERIC_OPENAI_API_KEY=
FIREWORKS_API_BASE_URL=https://api.fireworks.ai/inference/v1
FIREWORKS_API_KEY=
KIMI_API_BASE_URL=https://llm.proxies.of.achyuth.dev/v1
KIMI_API_KEY=
DEFAULT_SOLVER_MODEL=kimi/kimi-k2p5-turbo
```

### Infrastructure

```env
SANDBOX_IMAGE=ctf-sandbox
MAX_CONCURRENT_CHALLENGES=10
MAX_ATTEMPTS_PER_CHALLENGE=3
CONTAINER_MEMORY_LIMIT=16g
```

Notes:

- `MAX_ATTEMPTS_PER_CHALLENGE` exists in settings, but the current retry loop in `ChallengeSwarm` is driven by status and bump logic rather than this value directly
- memory limits are parsed by suffix, for example `16g` or `4096m`

## 2. CLI Commands

## `init`

```bash
uv run ctf-solve init NAME [options]
```

Options:

- `--category`
- `--value`
- `--description`
- `--connection-info`
- `--dir`

Creates a challenge folder with `metadata.yml` and `distfiles/`.

## `run`

```bash
uv run ctf-solve run [options]
```

Options:

- `--ctfd-url`
- `--ctfd-token`
- `--offline`
- `--image`
- `--models`
- `--challenge`
- `--challenges-dir`
- `--no-submit`
- `--coordinator-model`
- `--coordinator`
- `--max-challenges`
- `--msg-port`
- `-v, --verbose`

Behavior:

- runs one challenge directly if `--challenge` is set
- otherwise uses coordinator mode if a CTFd URL is available
- otherwise falls back to local-directory solving

## `solve`

```bash
uv run ctf-solve solve CHALLENGE_DIR [options]
```

Options:

- `--image`
- `--models`
- `--no-submit`
- `--max-challenges`
- `-v, --verbose`

## `solve-local`

```bash
uv run ctf-solve solve-local [options]
```

Runs the current directory as a challenge.

## `solve-dir`

```bash
uv run ctf-solve solve-dir CHALLENGES_ROOT [options]
```

Runs every directory under the root that contains `metadata.yml`.

## `msg`

```bash
uv run ctf-msg "message here" --port 9400
```

This sends a message to the running coordinator dashboard/message endpoint.

## 3. Coordinator Backends

The `--coordinator` flag accepts:

- `kimi`
- `claude`
- `codex`

Backend meaning:

- `kimi` uses a Pydantic AI agent with tool wrappers
- `claude` uses the Claude Agent SDK with MCP tools
- `codex` uses `codex app-server` over JSON-RPC

This choice is separate from solver model specs.

## 4. Solver Model Specs

The code recognizes model specs in the format:

```text
provider/model-id
```

Supported provider prefixes:

- `bedrock`
- `azure`
- `fireworks`
- `zen`
- `google`
- `generic-openai`
- `kimi`
- `claude-sdk`
- `codex`

Special handling:

- bare `kimi-k2p5-turbo` is treated as Kimi by `provider_from_spec()`
- Fireworks model IDs may contain additional `/` path segments, for example `fireworks/accounts/fireworks/models/llama-v3p1-8b-instruct`
- effort suffixes such as `claude-sdk/claude-opus-4-6/max` are parsed by `effort_from_spec()`

Current default solver model list:

```python
default_models() -> [Settings().default_solver_model]
```

## 5. Current Model Selection Behavior

This is important enough to call out separately.

The CLI helper `_resolve_single_model_specs()` currently:

- uses `DEFAULT_SOLVER_MODEL` when no `--models` flag is given
- falls back to `kimi/kimi-k2p5-turbo` if the env value is empty
- keeps only the first model if more than one is provided
- prints a warning when it drops additional specs

So the current behavior is:

- the architecture supports multi-model challenge swarms
- the normal CLI path currently runs one solver model per challenge

## 6. Runtime Paths

### Project paths

- local challenges usually live under `challenges/`
- logs are written under `logs/`
- sandbox image is built from `sandbox/Dockerfile.sandbox`

### In-container paths

- `/challenge/distfiles` -> read-only challenge files
- `/challenge/metadata.yml` -> read-only metadata
- `/challenge/workspace` -> writable scratch space

## 7. Dashboard and Messaging Port

`run` accepts:

```bash
--msg-port INTEGER
```

Behavior:

- `0` means "choose any free port"
- the chosen dashboard port is logged at startup
- `ctf-msg` is easiest to use when you supply a fixed port manually

Recommended pattern:

```bash
uv run ctf-solve run ... --msg-port 9400
uv run ctf-msg "Prioritize easy web challenges" --port 9400
```

## 8. Docker Runtime Behavior

The sandbox currently:

- labels containers with `ctf-agent`
- binds only challenge-specific paths into `/challenge`
- injects `host.docker.internal`
- requests `SYS_ADMIN` and `SYS_PTRACE`
- relaxes seccomp
- gives the container a memory limit and CPU quota

Cleanup helpers:

- orphan containers are removed before major runs
- each sandbox removes its own container and temporary workspace on stop

## 9. Prompt-Related Settings

Prompt behavior is influenced by:

- challenge category
- presence of connection info
- presence of distfiles
- whether the backend has named tools
- whether `--no-submit` is enabled
- detected container architecture

That means changing metadata often has a direct effect on solver behavior, especially:

- `category`
- `description`
- `connection_info`
- `hints`

## 10. `run_ctf_agent.py` Settings Map

The helper script exposes these top-level constants:

- `MODE`
- `CHALLENGE_DIR`
- `CHALLENGES_DIR`
- `CTFD_URL`
- `CTFD_TOKEN`
- `MODELS`
- `IMAGE`
- `MAX_CHALLENGES`
- `NO_SUBMIT`
- `VERBOSE`
- `COORDINATOR`
- `COORDINATOR_MODEL`
- `MSG_PORT`

These map directly to the corresponding CLI behavior and are useful for repeatable local launches.

## 11. Sensible Defaults

For a safe first run:

```env
KIMI_API_KEY=...
KIMI_API_BASE_URL=https://llm.proxies.of.achyuth.dev/v1
```

```bash
uv run ctf-solve solve ./prob1 --models kimi/kimi-k2p5-turbo --no-submit -v
```

For a stable coordinator setup:

```bash
uv run ctf-solve run \
  --ctfd-url https://ctf.example.com \
  --ctfd-token ctfd_your_token \
  --challenges-dir challenges \
  --coordinator kimi \
  --msg-port 9400 \
  -v
```
