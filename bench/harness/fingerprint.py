"""Environment fingerprint: every version identifier that determines a run's or a score's outcome."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping

from bench.pins import LIMS_COMMIT, MODEL_ID, PSTACK_COMMIT, PYTHONHASHSEED, REPO_ROOT, TZ
from bench.task import Task, task_hash

KEYS = (
    "harness", "harness_version", "model", "pstack_commit", "lims_commit", "bench_commit",
    "image_digest", "postgres_digest", "redis_digest", "task_hash", "tz", "pythonhashseed",
)


def _claude_version(claude_bin: str) -> str:
    try:
        out = subprocess.run([claude_bin, "--version"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    match = re.search(r"\d+\.\d+\.\d+", out)
    return match.group(0) if match else "unknown"


def _bench_commit(env: Mapping[str, str]) -> str:
    if env.get("GITHUB_SHA"):
        return env["GITHUB_SHA"]
    try:
        return subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def collect(task: Task, *, claude_bin: str, env: Mapping[str, str]) -> dict[str, str]:
    return {
        "harness": "claude-code",
        "harness_version": _claude_version(claude_bin),
        "model": MODEL_ID,
        "pstack_commit": PSTACK_COMMIT,
        "lims_commit": LIMS_COMMIT,
        "bench_commit": _bench_commit(env),
        "image_digest": env.get("BENCH_IMAGE_DIGEST") or "unknown",
        "postgres_digest": env.get("BENCH_POSTGRES_DIGEST") or "unknown",
        "redis_digest": env.get("BENCH_REDIS_DIGEST") or "unknown",
        "task_hash": task_hash(task),
        "tz": TZ,
        "pythonhashseed": PYTHONHASHSEED,
    }
