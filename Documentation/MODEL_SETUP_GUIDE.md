# Model Setup Guide

This guide explains how to:

- add an API key
- point the app at the provider you want
- choose the exact model string to pass to the solver
- verify that the selected model is the one the agent is actually using

Use this guide when you want to switch away from the default model or add support for your own provider credentials locally.

## 1. Where the app reads API keys from

The settings loader reads environment variables from these files, in this order:

1. `backend/.env`
2. `.env`

In practice, the safest path is:

```bash
cp backend/.env.example backend/.env
```

Then edit `backend/.env` and add only the keys for the provider you plan to use.

## 2. The two things you must configure

There are two separate pieces:

1. credentials and endpoint
2. the model spec passed on the command line

Example:

```env
FIREWORKS_API_KEY=fw_your_key_here
FIREWORKS_API_BASE_URL=https://api.fireworks.ai/inference/v1
```

```bash
uv run ctf-solve solve ./prob1 \
  --models fireworks/accounts/fireworks/models/llama-v3p1-8b-instruct
```

The `.env` file tells the code how to authenticate.

The `--models` value tells the solver which provider backend and model ID to use.

## 3. Model spec format

Solver model specs use this format:

```text
provider/model-id
```

Examples:

```text
kimi/kimi-k2p5-turbo
generic-openai/gpt-4o-mini
google/gemini-3-flash-preview
fireworks/accounts/fireworks/models/llama-v3p1-8b-instruct
claude-sdk/claude-opus-4-6/max
codex/gpt-5.4
```

Important details:

- `provider` selects which backend integration the code uses
- `model-id` is the provider-specific model name
- some model IDs contain `/`, especially Fireworks; keep the full path after the provider prefix
- effort suffixes such as `/max` are only interpreted for `claude-sdk` and `codex`
- a bare `kimi-k2p5-turbo` is accepted and treated as `kimi/kimi-k2p5-turbo`

## 4. Quick provider map

Use this as the short lookup table when wiring up a new model.

| Provider prefix | What to set in `backend/.env` | Example `--models` value |
|---|---|---|
| `kimi` | `KIMI_API_KEY`, optionally `KIMI_API_BASE_URL` | `kimi/kimi-k2p5-turbo` |
| `fireworks` | `FIREWORKS_API_KEY`, optionally `FIREWORKS_API_BASE_URL` | `fireworks/accounts/fireworks/models/llama-v3p1-8b-instruct` |
| `generic-openai` | `GENERIC_OPENAI_BASE_URL`, `GENERIC_OPENAI_API_KEY` | `generic-openai/gpt-4o-mini` |
| `azure` | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` | `azure/gpt-5.4` |
| `google` | `GEMINI_API_KEY` | `google/gemini-3-flash-preview` |
| `bedrock` | AWS credentials or `AWS_BEARER_TOKEN` | `bedrock/us.anthropic.claude-opus-4-6-v1` |
| `claude-sdk` | Anthropic or Claude SDK-compatible local auth | `claude-sdk/claude-opus-4-6/max` |
| `codex` | local Codex CLI auth | `codex/gpt-5.4` |
| `zen` | `OPENCODE_ZEN_API_KEY` | `zen/gpt-5.3-codex-spark` |

## 5. Step-by-step examples

### Fireworks AI

Add this to `backend/.env`:

```env
FIREWORKS_API_BASE_URL=https://api.fireworks.ai/inference/v1
FIREWORKS_API_KEY=your_fireworks_api_key
```

Run a challenge with a Fireworks serverless model:

```bash
uv run ctf-solve solve ./prob1 \
  --models fireworks/accounts/fireworks/models/llama-v3p1-8b-instruct
```

Run a challenge with a Fireworks router model:

```bash
uv run ctf-solve solve ./prob1 \
  --models fireworks/accounts/fireworks/routers/kimi-k2p5-turbo
```

Common mistake:

- do not drop the `fireworks/` prefix
- do not shorten the model ID to only the final segment

Correct:

```text
fireworks/accounts/fireworks/models/llama-v3p1-8b-instruct
```

Incorrect:

```text
llama-v3p1-8b-instruct
fireworks/llama-v3p1-8b-instruct
```

### Kimi

Add this to `backend/.env`:

```env
KIMI_API_BASE_URL=https://llm.proxies.of.achyuth.dev/v1
KIMI_API_KEY=your_kimi_key
```

Then run:

```bash
uv run ctf-solve solve ./prob1 --models kimi/kimi-k2p5-turbo
```

You can also use the bare model name:

```bash
uv run ctf-solve solve ./prob1 --models kimi-k2p5-turbo
```

Explicit `kimi/...` is usually clearer and easier to debug.

### Generic OpenAI-compatible endpoint

Use this when your provider exposes an OpenAI-compatible API and the repo does not have a dedicated provider prefix for it.

Add this to `backend/.env`:

```env
GENERIC_OPENAI_BASE_URL=http://localhost:11434/v1
GENERIC_OPENAI_API_KEY=ollama
```

Then run:

```bash
uv run ctf-solve solve ./prob1 --models generic-openai/gpt-4o-mini
```

This is a good option for local gateways, proxies, and self-hosted endpoints.

### Azure OpenAI

Add this to `backend/.env`:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your_azure_key
```

Then run:

```bash
uv run ctf-solve solve ./prob1 --models azure/gpt-5.4
```

Use the deployment-compatible model name your Azure endpoint expects.

### Google

Add this to `backend/.env`:

```env
GEMINI_API_KEY=your_gemini_key
```

Then run:

```bash
uv run ctf-solve solve ./prob1 --models google/gemini-3-flash-preview
```

### Claude SDK

The `claude-sdk` provider is different from the OpenAI-compatible backends. It uses the Claude solver backend rather than the Pydantic OpenAI path.

Example:

```bash
uv run ctf-solve solve ./prob1 --models claude-sdk/claude-opus-4-6/max
```

If you use this path, make sure the Claude tooling is already authenticated in your environment.

### Codex

The `codex` provider also uses its own backend instead of the OpenAI-compatible path.

Example:

```bash
uv run ctf-solve solve ./prob1 --models codex/gpt-5.4
```

If you use this path, make sure the local Codex tooling is installed and authenticated.

## 6. Which command actually uses the model

For local solving:

```bash
uv run ctf-solve solve ./prob1 --models PROVIDER/MODEL
uv run ctf-solve solve-local --models PROVIDER/MODEL
uv run ctf-solve solve-dir ./challenges --models PROVIDER/MODEL
```

For coordinator mode:

```bash
uv run ctf-solve run \
  --ctfd-url https://ctf.example.com \
  --ctfd-token ctfd_token_here \
  --models PROVIDER/MODEL
```

Important distinction:

- `--models` controls solver models
- `--coordinator` controls which coordinator backend is used
- `--coordinator-model` overrides the coordinator model when that backend supports it

Example:

```bash
uv run ctf-solve run \
  --ctfd-url https://ctf.example.com \
  --ctfd-token ctfd_token_here \
  --coordinator kimi \
  --coordinator-model kimi/kimi-k2p5-turbo \
  --models fireworks/accounts/fireworks/models/llama-v3p1-8b-instruct
```

That means:

- the coordinator uses Kimi
- the per-challenge solver uses Fireworks

## 7. How to switch the default model

If you always want to pass a model explicitly, use `--models` on every run.

If you want to change the default used when `--models` is omitted, set `DEFAULT_SOLVER_MODEL` in `backend/.env`.

Current default:

```env
DEFAULT_SOLVER_MODEL=kimi/kimi-k2p5-turbo
```

Example change:

```env
DEFAULT_SOLVER_MODEL=fireworks/accounts/fireworks/routers/kimi-k2p5-turbo
```

This affects any command path that does not explicitly pass `--models`.

## 8. How to verify the configured model is being used

Use verbose mode:

```bash
uv run ctf-solve solve ./prob1 \
  --models fireworks/accounts/fireworks/models/llama-v3p1-8b-instruct \
  --no-submit \
  -v
```

Then check the logs for the model name in lines like:

```text
[prob1/<model-name>] Solver started
[prob1/<model-name>] Agent requesting model...
```

You can also inspect trace files under `logs/` or the dashboard trace view.

## 9. How to list all available Fireworks models

If you have `FIREWORKS_API_KEY` configured in `backend/.env`, the backend can query Fireworks directly and return the live model catalog.

Start the API server:

```bash
uv run ctf-api
```

Then request:

```bash
curl http://127.0.0.1:8081/api/v1/models/fireworks
```

The response includes:

- whether Fireworks is configured
- the base URL being used
- the total number of models returned
- the full model list from Fireworks

Each model entry includes fields such as:

- `id`
- `owned_by`
- `kind`
- `context_length`
- `supports_chat`
- `supports_tools`
- `supports_image_input`

If you only want the model IDs:

```bash
curl -s http://127.0.0.1:8081/api/v1/models/fireworks | jq -r '.models[].id'
```

This is the closest equivalent to an opencode-style "available models" list for Fireworks in this repo.

## 10. Common mistakes

### I added the key but the app still says connection error

Check:

- the key was added to `backend/.env` or `.env`
- the provider base URL is correct
- the endpoint is reachable from your machine
- the provider prefix in `--models` matches the credential variables you set

Example mismatch:

- you set `FIREWORKS_API_KEY`
- but you run `--models generic-openai/gpt-4o-mini`

That will use the generic OpenAI config, not the Fireworks config.

### I passed multiple `--models` flags and only one ran

That is current behavior in the normal CLI path. The architecture supports more than one model, but the usual CLI flow keeps only the first solver spec.

### My Fireworks model string is being rejected

Keep the full path after the provider prefix:

```text
fireworks/accounts/fireworks/models/llama-v3p1-8b-instruct
```

Do not shorten it unless Fireworks itself provides a shorter model ID that your endpoint accepts.

### I changed `OPENAI_API_KEY` but nothing happened

Some providers use their own dedicated variables first:

- Fireworks uses `FIREWORKS_API_KEY`
- Kimi uses `KIMI_API_KEY`
- Azure uses `AZURE_OPENAI_API_KEY`
- Generic OpenAI-compatible uses `GENERIC_OPENAI_API_KEY`

Some backends may fall back to `OPENAI_API_KEY`, but relying on the dedicated variable is clearer and safer.

## 11. Recommended workflow

1. Copy `backend/.env.example` to `backend/.env`.
2. Fill in only the provider variables you need.
3. Pick the exact `provider/model-id` string.
4. Run one local challenge with `--no-submit -v`.
5. Confirm the trace shows the expected model.
6. Move on to `solve-dir` or `run` once the single-challenge test works.
