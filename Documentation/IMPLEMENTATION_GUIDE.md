# Implementation Guide

This document explains how the current CTF agent is implemented, how the major features are wired together, and where to make changes safely.

## 1. System Overview

The project has two main operating styles:

- local solving, where one challenge directory is solved directly
- coordinator mode, where a long-running coordinator watches a CTFd instance and manages challenge swarms

At a high level, the flow is:

1. The CLI builds a `Settings` object and resolves runtime mode.
2. Challenge metadata is loaded from `metadata.yml` or pulled from CTFd.
3. A `ChallengeSwarm` is created for each challenge.
4. Each solver gets its own Docker sandbox and agent backend.
5. Solvers use tools to inspect files, attack services, and submit flags.
6. Findings, traces, and costs are recorded while the coordinator continues to react to events.

## 2. Main Entry Points

### `backend/cli.py`

This is the primary command surface and provides:

- `init`
- `run`
- `solve`
- `solve-local`
- `solve-dir`
- `msg`

Important implementation detail:

- `run`, `solve`, `solve-local`, and `solve-dir` all call `_resolve_single_model_specs()`
- that helper keeps only the first requested model spec
- because of that, the architecture supports multi-model swarms, but the current CLI behavior is effectively single-solver-per-challenge unless the code is changed

### `run_ctf_agent.py`

This is a convenience wrapper around `python -m backend.cli`. It is useful for users who prefer editing constants in a file instead of typing commands manually.

It supports these modes:

- `ctfd`
- `solve`
- `solve-local`
- `solve-dir`

The script builds a CLI command from the `CONFIG`-style constants at the top of the file and then executes it with the project Python interpreter if `.venv/bin/python` exists.

## 3. Configuration Layer

### `backend/config.py`

Configuration is managed through a Pydantic settings object:

- `.env` is loaded automatically
- environment variables override defaults
- CLI flags then override selected values at runtime

Notable configuration groups:

- CTFd connection: `ctfd_url`, `ctfd_token`, `ctfd_user`, `ctfd_pass`
- provider credentials: Anthropic, OpenAI, Gemini, Azure, AWS, Zen, generic OpenAI-compatible, Kimi
- infra: sandbox image, max concurrent challenges, per-challenge attempts, memory limits

The `Settings` object is passed through most runtime components so backend-specific code can resolve models and resource limits without repeatedly reading the environment.

## 4. Challenge Metadata and Prompt Construction

### `backend/prompts.py`

`ChallengeMeta` is the normalized metadata object loaded from `metadata.yml`. It carries:

- challenge name
- category
- points/value
- description
- tags
- connection info
- hints
- solve count

`build_prompt()` generates the solver system prompt from metadata plus runtime facts:

- the container architecture from `uname -m`
- the list of files under `distfiles/`
- whether the solver backend has named tools
- whether `--no-submit` is active

Prompt behavior is category-aware:

- pwn/reverse-style categories are instructed to inspect binaries locally first
- remote services are highlighted and the initial action is guided
- image files are called out explicitly for vision-capable models
- hints are injected if present in metadata
- no-input cases trigger an explicit coordinator notification path

One small but important detail is `_rewrite_connection_info()`:

- `localhost` and `127.0.0.1` are rewritten to `host.docker.internal`
- this makes host services reachable from the Docker sandbox

## 5. Local Challenge Discovery

### `backend/cli.py::_local_challenge_dirs`

Local directory solving scans for `metadata.yml` files:

- if the root itself contains `metadata.yml`, it is treated as one challenge
- otherwise the root is searched recursively
- duplicate directories are deduplicated by resolved path

This is what powers both:

- `solve-dir`
- `run` when no CTFd URL is configured

## 6. CTFd Integration

### `backend/ctfd.py`

`CTFdClient` handles all communication with CTFd. It supports:

- token auth
- username/password login fallback
- CSRF token handling when using session auth
- challenge listing
- solve status lookup
- challenge downloads
- flag submission
- instance start / connection info discovery for dynamic challenges

Key implementation points:

- `is_mock` is true when no `base_url` is set
- in mock mode, submissions are printed and treated as successful enough for dry workflows
- `fetch_challenge_stubs()` is used by the poller for lightweight refreshes
- `fetch_all_challenges()` performs per-challenge detail fetches for richer metadata
- `fetch_solved_names()` resolves team solves when the user is part of a team

The client also includes best-effort instance support:

- it checks challenge detail pages for `connection_info`
- it tries common instance-launch endpoints
- it polls briefly in case instance creation is asynchronous

## 7. Coordinator Runtime

### Files

- `backend/agents/coordinator_loop.py`
- `backend/agents/coordinator_core.py`
- `backend/poller.py`
- `backend/agents/kimi_coordinator.py`
- `backend/agents/claude_coordinator.py`
- `backend/agents/codex_coordinator.py`

### Responsibilities

The coordinator layer is responsible for:

- watching the CTFd event stream via polling
- pulling challenge metadata and files
- spawning challenge swarms
- reading solver traces
- bumping stuck agents with targeted guidance
- accepting operator messages
- exposing a simple dashboard

### Polling

`CTFdPoller` polls every 5 seconds and emits:

- `new_challenge`
- `challenge_solved`

It keeps internal state for:

- known challenges
- known solved challenges

There are safety checks to avoid acting on obviously broken API responses, such as a sudden collapse in challenge count or an empty solved set after a non-empty one.

### Shared Coordinator Loop

`run_event_loop()` is the shared orchestration loop used by all coordinator backends.

It performs these steps:

1. Start the poller.
2. Start the dashboard/operator message HTTP server.
3. Send an initial "CTF is LIVE" message to the coordinator model.
4. Auto-spawn unsolved challenges if the coordinator model does not do so itself.
5. Repeatedly process:
   - CTFd events
   - solver-to-coordinator messages
   - operator messages
   - periodic status updates
6. On shutdown, stop the poller, kill swarms, cancel tasks, and log cost summaries.

### Coordinator Tools

`coordinator_core.py` defines the actual coordinator actions:

- `do_fetch_challenges`
- `do_get_solve_status`
- `do_spawn_swarm`
- `do_check_swarm_status`
- `do_submit_flag`
- `do_kill_swarm`
- `do_bump_agent`
- `do_broadcast`
- `do_read_solver_trace`

The three coordinator backends expose these same operations using different agent runtimes:

- Kimi coordinator via Pydantic AI tools
- Claude coordinator via Claude SDK MCP tools
- Codex coordinator via dynamic JSON-RPC tools

### Auto-Spawning and Capacity

`do_spawn_swarm()` enforces:

- no auto-spawn for paused challenges
- no auto-spawn for OSINT categories
- maximum concurrent challenge count
- auto-pulling challenge files from CTFd if they are not already local

## 8. Challenge Swarm Lifecycle

### `backend/agents/swarm.py`

`ChallengeSwarm` is the per-challenge manager. It owns:

- one logical challenge
- zero or more solver instances
- a shared cancel event
- per-model findings
- message bus state
- submission throttling state

### Solver Backend Selection

`_create_solver()` chooses the solver implementation by provider prefix:

- `claude-sdk/*` -> `ClaudeSolver`
- `codex/*` -> `CodexSolver`
- anything else -> `Solver` (the Pydantic AI implementation)

This lets the swarm mix backend types in principle, although current CLI behavior usually feeds it only one model spec.

### Winner Selection

`run()` starts all solver tasks and waits for the first one to return `FLAG_FOUND`.

When a solver wins:

- the swarm cancel event is set
- pending solver tasks are cancelled
- the winner result is returned

### Bumping and Retry

`_run_solver_loop()` allows repeated attempts without tearing down the entire swarm immediately.

Behavior:

- a solver starts once
- it runs until it finds a flag, gives up, errors, or is cancelled
- good findings are saved and posted to the message bus
- on `GAVE_UP` or recoverable `ERROR`, the solver is bumped with sibling insights and resumed
- cooldown between bumps increases over time, capped at 300 seconds
- three consecutive errors stop further retries

### Quota Fallback

There is a provider fallback map for quota exhaustion:

- subscription-style providers can fall back to API-backed alternatives

When a solver returns `QUOTA_ERROR` and a fallback exists:

- the current sandbox is preserved
- the old solver is stopped without deleting that sandbox
- a new Pydantic AI solver is created with the fallback model spec
- work resumes from the same container state

## 9. Solver Implementation

### Pydantic AI Solver

`backend/agents/solver.py` is the default solver for Kimi, generic OpenAI-compatible models, Google, Azure, Bedrock, and Zen-backed models.

Major responsibilities:

- start the Docker sandbox
- build the prompt
- resolve the model and provider settings
- construct the toolset
- collect messages and usage
- emit traces
- return a `SolverResult`

### Tool Wrapping and Loop Detection

`TracingToolset` wraps every tool call and adds:

- step counting
- structured trace logging
- loop detection
- findings injection every 5 steps

Loop handling uses `backend/loop_detect.py`:

- repeated identical tool signatures trigger warnings
- repeated identical tool signatures beyond a threshold force-break the loop by returning a warning instead of continuing normally

### Message History and Bumps

The solver stores its message history and reuses it across turns.

When a bump happens:

- a synthetic user message is appended
- it includes sibling findings
- it explicitly asks for a different approach
- loop detection state is reset

### Structured Output

The expected output type is `FlagFound`, which contains:

- `flag`
- `method`

If `--no-submit` is active, a structured output is enough to end the run successfully. Otherwise, a real CTFd confirmation is the primary success condition.

## 10. Claude and Codex Solver Backends

### Claude Solver

`backend/agents/claude_solver.py` uses Claude's SDK-native tool runtime, but it redirects real work into the Docker container.

Implementation highlights:

- only Bash is effectively allowed for sandbox operations
- host filesystem tools like `Read`, `Write`, `Edit`, `Glob`, and `Grep` are denied
- `submit_flag ...` and `notify_coordinator ...` shell commands are intercepted before execution
- every command is rewritten to `docker exec` into the solver container

This keeps Claude operating through its native tool protocol without giving it direct host access.

### Codex Solver

`backend/agents/codex_solver.py` speaks to `codex app-server` over JSON-RPC.

Implementation highlights:

- dynamic tools are declared at thread start
- tool calls are handled by the Python process and routed into the sandbox or CTFd client
- structured output is enforced through the JSON schema from `backend/output_types.py`
- token usage updates are recorded incrementally

This backend exposes named tools directly, including:

- `bash`
- `read_file`
- `write_file`
- `list_files`
- `submit_flag`
- `web_fetch`
- `webhook_create`
- `webhook_get_requests`
- `view_image`
- `notify_coordinator`

## 11. Docker Sandbox

### `backend/sandbox.py`

Each solver gets a dedicated `DockerSandbox`.

Container behavior:

- image defaults to `ctf-sandbox`
- container starts with `sleep infinity`
- commands are executed with `docker exec`
- the challenge root is not mounted wholesale
- only selected paths are mounted into `/challenge`

Mounted paths:

- host temp workspace -> `/challenge/workspace` (read/write)
- `distfiles/` -> `/challenge/distfiles` (read-only)
- `metadata.yml` -> `/challenge/metadata.yml` (read-only)

Host access helpers:

- `host.docker.internal` is added via `ExtraHosts`
- the sandbox requests `SYS_ADMIN` and `SYS_PTRACE`
- seccomp is relaxed
- `/dev/loop-control` is exposed for tooling that needs it

Resource controls:

- a concurrency semaphore limits parallel container starts
- memory limit is configurable
- CPU is capped at roughly 2 vCPUs

Cleanup behavior:

- `cleanup_orphan_containers()` removes leftover containers labeled `ctf-agent`
- each sandbox deletes its container and workspace on stop

## 12. Solver Tools

### Files

- `backend/tools/sandbox.py`
- `backend/tools/core.py`
- `backend/tools/flag.py`
- `backend/tools/vision.py`

### Available Capabilities

Core operations include:

- shell execution inside the sandbox
- file read/write/list
- flag submission
- web fetching
- webhook.site integration
- inter-solver findings retrieval
- coordinator notification
- image viewing for vision-capable models

Important implementation details:

- tool output is truncated to keep context manageable
- binary file reads return guidance rather than dumping raw bytes
- `web_fetch` rewrites `host.docker.internal` back to `127.0.0.1` for host-side execution
- `view_image` validates extension, magic bytes, and size before passing image bytes to the model

## 13. Cross-Solver Communication

### `backend/message_bus.py`

The message bus is per-challenge and append-only.

It stores:

- findings from solvers
- cursor positions per model

This supports two collaboration patterns:

- passive sharing through `check_findings`
- active broadcasts from the coordinator

Findings are trimmed to a bounded history so the bus does not grow without limit.

## 14. Flag Submission Controls

### `ChallengeSwarm.try_submit_flag()`

Submission is intentionally centralized at the swarm level so solvers do not spam CTFd.

Controls implemented there:

- exact-flag deduplication across all models
- per-model escalating cooldowns after incorrect submissions
- immediate short-circuit after a confirmed flag has already been accepted

Cooldown schedule:

- 0 seconds
- 30 seconds
- 120 seconds
- 300 seconds
- 600 seconds

This protects the team from repeated wrong submissions while still letting solvers keep working.

## 15. Tracing and Cost Tracking

### Tracing

`backend/tracing.py` writes one JSONL file per solver under `logs/`.

Event types include:

- `start`
- `tool_call`
- `tool_result`
- `model_response`
- `usage`
- `bump`
- `error`
- `finish`

The coordinator can read the tail of these traces and summarize recent actions back to the coordinator model.

### Cost Tracking

`backend/cost_tracker.py` tracks token usage and estimated cost by solver.

Implementation details:

- uses `genai-prices` when possible
- falls back to local pricing tables for models that are not recognized
- records cache-read tokens separately
- aggregates totals by agent and by model

## 16. Dashboard and Operator Messaging

### `backend/agents/coordinator_loop.py::_start_msg_server`

Coordinator mode launches a small HTTP server bound to `127.0.0.1`.

It serves:

- `/` -> dashboard UI
- `/api/state` -> active/stopped/success state
- `/api/trace` -> trace excerpts
- `/api/message` -> queue an operator message
- `/api/stop` -> stop a challenge swarm

If `--msg-port 0` is used, the OS picks a free port and the actual URL is logged at startup.

This is why `ctf-msg` is easiest to use when you run the coordinator with a fixed `--msg-port`.

## 17. Model Resolution

### `backend/models.py`

Provider prefixes map to different backends:

- `bedrock/`
- `azure/`
- `fireworks/`
- `zen/`
- `google/`
- `generic-openai/`
- `kimi/`
- `claude-sdk/`
- `codex/`

Provider handling differs:

- Kimi, Fireworks, generic OpenAI-compatible, Azure, Google, Bedrock, and Zen use the Pydantic AI solver
- Claude SDK specs use the Claude solver backend
- Codex specs use the Codex JSON-RPC backend

The current default model list is:

- `Settings().default_solver_model`

That runtime default falls back to `kimi/kimi-k2p5-turbo` when `DEFAULT_SOLVER_MODEL` is unset.

## 18. Current Behavior Notes

These points are worth calling out because they affect how the system behaves in practice today:

- The swarm architecture is multi-model capable, but the CLI currently keeps only the first requested solver model spec.
- `solve-dir` does not run many models against each challenge; it iterates through challenge directories and runs a single solver model for each one.
- `run` falls back to local-directory solving when no CTFd URL is configured.
- The coordinator backend and solver model backend are separate choices. For example, you can use a Kimi coordinator while solving with a different provider, as long as the model spec resolves correctly.
- `ctf-msg` defaults to port `9400`, but coordinator mode defaults to `--msg-port 0`, which means the dashboard/message port is dynamic unless you pin it.

## 19. Safe Extension Points

If you want to extend the project, these are the cleanest starting points:

- add provider/model support in `backend/models.py`
- add or adjust solver tools in `backend/tools/`
- change prompt policy in `backend/prompts.py`
- change swarm retry or cooldown behavior in `backend/agents/swarm.py`
- add dashboard actions in `backend/agents/coordinator_loop.py`
- add new coordinator logic in `backend/agents/coordinator_core.py`

## 20. File Map

Quick reference for the most important implementation files:

- `backend/cli.py` -> CLI entrypoints
- `backend/config.py` -> settings
- `backend/prompts.py` -> metadata and prompt generation
- `backend/ctfd.py` -> CTFd API client
- `backend/poller.py` -> challenge/solve event polling
- `backend/agents/coordinator_loop.py` -> long-running coordinator event loop and dashboard
- `backend/agents/coordinator_core.py` -> coordinator actions
- `backend/agents/swarm.py` -> per-challenge solver orchestration
- `backend/agents/solver.py` -> default Pydantic AI solver
- `backend/agents/claude_solver.py` -> Claude SDK solver
- `backend/agents/codex_solver.py` -> Codex solver
- `backend/sandbox.py` -> Docker sandbox
- `backend/tools/core.py` -> sandbox/tool primitives
- `backend/message_bus.py` -> cross-solver findings
- `backend/tracing.py` -> JSONL traces
- `backend/cost_tracker.py` -> usage and cost aggregation
