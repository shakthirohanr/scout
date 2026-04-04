#!/usr/bin/env python3
"""Small runner for ctf-agent.

Edit the CONFIG block below, then run:

    python run_ctf_agent.py

It wraps the same ctf-solve commands you would type manually.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


MODE = "solve"  # "ctfd", "solve", "solve-local", or "solve-dir"
CHALLENGE_DIR = "./challenges/excellent-crypto-challenge"  # used by "solve" and "solve-local"
CHALLENGES_DIR = "~/ctf/challenges"  # used by "solve-dir" and "ctfd"
CTFD_URL = "https://sillyctf.psuccso.org/"
CTFD_TOKEN = "ctfd_694074c26dde06b1f4c0e2cdee5ef0c8aea1cb2d202b47c8e9164bd2285cbb4b"
MODELS = ["kimi-k2p5-turbo"]
IMAGE = "ctf-sandbox"
MAX_CHALLENGES = 10
NO_SUBMIT = True
VERBOSE = False
COORDINATOR = "kimi"  # "kimi", "claude", or "codex"; only used in ctfd mode
COORDINATOR_MODEL = "kimi-k2p5-turbo"
MSG_PORT = 0


PROJECT_ROOT = Path(__file__).resolve().parent


def build_command() -> list[str]:
    venv_candidates = [
        PROJECT_ROOT / "backend" / ".venv" / "bin" / "python",
        PROJECT_ROOT / ".venv" / "bin" / "python",
    ]
    python_exe = sys.executable
    for project_python in venv_candidates:
        if project_python.exists():
            python_exe = str(project_python)
            break
    cmd = [python_exe, "-m", "backend.cli"]

    if MODE == "ctfd":
        cmd += [
            "run",
            "--ctfd-url",
            CTFD_URL,
            "--ctfd-token",
            CTFD_TOKEN,
            "--challenges-dir",
            CHALLENGES_DIR,
            "--coordinator",
            COORDINATOR,
            "--max-challenges",
            str(MAX_CHALLENGES),
            "--msg-port",
            str(MSG_PORT),
        ]
        if COORDINATOR_MODEL:
            cmd += ["--coordinator-model", COORDINATOR_MODEL]
    elif MODE == "solve":
        cmd += ["solve", CHALLENGE_DIR]
    elif MODE == "solve-local":
        cmd += ["solve-local"]
    elif MODE == "solve-dir":
        cmd += ["solve-dir", CHALLENGES_DIR]
    else:
        raise SystemExit(f"Unknown MODE: {MODE}")

    if IMAGE:
        cmd += ["--image", IMAGE]

    for model in MODELS:
        cmd += ["--models", model]

    if NO_SUBMIT:
        cmd.append("--no-submit")
    if VERBOSE:
        cmd.append("-v")

    return cmd


def main() -> int:
    if MODE in {"solve", "solve-local"} and not Path(CHALLENGE_DIR).exists():
        raise SystemExit(f"Challenge directory not found: {CHALLENGE_DIR}")
    if MODE == "solve-dir" and not Path(CHALLENGES_DIR).exists():
        raise SystemExit(f"Challenges directory not found: {CHALLENGES_DIR}")
    if MODE == "ctfd" and (not CTFD_URL or not CTFD_TOKEN):
        raise SystemExit("Set CTFD_URL and CTFD_TOKEN before running ctfd mode.")
    if MODE == "ctfd" and COORDINATOR != "kimi":
        print("Warning: only KIMI is configured; switching coordinator to kimi.")

    env = os.environ.copy()
    cmd = build_command()
    print("Running:")
    print(" ".join(cmd))
    return subprocess.run(cmd, cwd=PROJECT_ROOT, env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
