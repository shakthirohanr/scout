# Documentation

This folder contains project documentation that is aligned with the current codebase.

## Documents

- [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md)
  Deep dive into architecture, feature implementation, solver lifecycle, coordinator flow, sandboxing, tracing, and extension points.

- [USAGE_GUIDE.md](USAGE_GUIDE.md)
  Practical setup and operation guide for local solving, directory solving, CTFd coordinator mode, operator messaging, and the `run_ctf_agent.py` helper.

- [CONFIGURATION_REFERENCE.md](CONFIGURATION_REFERENCE.md)
  Reference for environment variables, CLI flags, model spec formats, runtime paths, and important behavior notes.

## Recommended Reading Order

1. Start with [USAGE_GUIDE.md](USAGE_GUIDE.md) if you want to run the agent.
2. Read [CONFIGURATION_REFERENCE.md](CONFIGURATION_REFERENCE.md) if you need to change providers, images, or runtime limits.
3. Read [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) if you want to understand or modify the internals.

## Scope

These documents describe the implementation that exists in the repository today, including a few current behavior notes that are easy to miss from the top-level README alone:

- local and coordinator entrypoints currently normalize solver model selection to a single model spec at the CLI layer
- the default solver model list is currently Kimi-only
- the dashboard/operator message port is dynamic unless you set `--msg-port` explicitly

That means these docs are intended to be accurate to the present code, not to an older or aspirational architecture description.
