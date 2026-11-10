"""Red check (new tests fail on the snapshot) and green check (new tests pass on the reference)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from bench.capture.pytest_plugin import plugin_env
from bench.pins import FLAKY_RERUNS
from bench.scoring.testdiff import changed_test_files
from bench.task import Task

FAILING = ("failed", "error")


def transplant(files: Sequence[Path], src: Path, target: Path, dest: Path) -> Path:
    dest = Path(dest)
    shutil.copytree(target, dest, ignore=shutil.ignore_patterns(".git"), symlinks=True)
    for rel in files:
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(src) / rel, out)
    return dest


def run_nodeids(tree: Path, task: Task, nodeids: Sequence[str], env: Mapping[str, str]) -> dict[str, str]:
    """Run exactly these tests once. A test that never produced a result (e.g. its file failed to import) is "error"."""
    if not nodeids:
        return {}
    cwd = Path(tree) / task.workdir
    # Run whole files: one unknown node ID makes pytest abort the entire invocation.
    files = sorted({nid.split("::")[0] for nid in nodeids if (cwd / nid.split("::")[0]).is_file()})
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "log.jsonl"
        if files:
            subprocess.run(
                [sys.executable, "-m", "pytest", *files, "-q",
                 "-p", "no:cacheprovider", "--continue-on-collection-errors"],
                cwd=cwd, env={**env, **plugin_env(), "BENCH_TESTLOG": str(log)}, capture_output=True, text=True,
            )
        results: dict[str, str] = {}
        if log.exists():
            for line in log.read_text(encoding="utf-8").splitlines():
                results.update(json.loads(line)["results"])
    return {nodeid: results.get(nodeid, "error") for nodeid in nodeids}


@dataclass
class RedResult:
    red: bool
    outcomes: dict[str, str]


@dataclass
class GreenResult:
    valid: list[str]
    failing: list[str]
    flaky: list[str]


def red_check(snapshot: Path, final: Path, task: Task, added: Sequence[str], env: Mapping[str, str]) -> RedResult:
    if not added:
        return RedResult(False, {})
    with tempfile.TemporaryDirectory() as tmp:
        tree = transplant(changed_test_files(snapshot, final, task), final, snapshot, Path(tmp) / "tree")
        outcomes = run_nodeids(tree, task, added, env)
    return RedResult(any(o in FAILING for o in outcomes.values()), outcomes)


def green_check(
    reference: Path, final: Path, task: Task, added: Sequence[str], env: Mapping[str, str], reruns: int = FLAKY_RERUNS
) -> GreenResult:
    """Run the new tests `reruns` times in one transplanted tree.

    Always passed = valid, never passed = failing, mixed = flaky.
    """
    if not added:
        return GreenResult([], [], [])
    with tempfile.TemporaryDirectory() as tmp:
        tree = transplant(changed_test_files(reference, final, task), final, reference, Path(tmp) / "tree")
        runs = [run_nodeids(tree, task, added, env) for _ in range(reruns)]
    valid, failing, flaky = [], [], []
    for nodeid in sorted(added):
        passed = [r[nodeid] == "passed" for r in runs]
        (valid if all(passed) else failing if not any(passed) else flaky).append(nodeid)
    return GreenResult(valid, failing, flaky)
