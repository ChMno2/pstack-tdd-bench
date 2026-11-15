"""Red check (new tests fail on the snapshot) and green check (new tests pass on the reference)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from bench.capture.pytest_plugin import plugin_env
from bench.pins import FLAKY_RERUNS
from bench.scoring.testdiff import changed_test_files
from bench.task import Task

FAILING = ("failed", "error")
# Exception types that mean "the test's expectation disagrees with the code", as opposed to the test crashing.
EXPECTATION_FAILURES = ("AssertionError", "Failed")


def transplant(files: Sequence[Path], src: Path, target: Path, dest: Path) -> Path:
    dest = Path(dest)
    shutil.copytree(target, dest, ignore=shutil.ignore_patterns(".git"), symlinks=True)
    for rel in files:
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(src) / rel, out)
    return dest


def run_nodeids_detail(
    tree: Path, task: Task, nodeids: Sequence[str], env: Mapping[str, str]
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Run exactly these tests once; return (outcomes, failures) as benchlog recorded them.

    A test that never produced a result (e.g. its file failed to import) is "error" and has no failure entry.
    """
    if not nodeids:
        return {}, {}
    cwd = Path(tree) / task.workdir
    # Run whole files: one unknown node ID makes pytest abort the entire invocation.
    files = sorted({nid.split("::")[0] for nid in nodeids if (cwd / nid.split("::")[0]).is_file()})
    results: dict[str, str] = {}
    failures: dict[str, dict[str, str]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "log.jsonl"
        if files:
            subprocess.run(
                [sys.executable, "-m", "pytest", *files, "-q",
                 "-p", "no:cacheprovider", "--continue-on-collection-errors"],
                cwd=cwd, env={**env, **plugin_env(), "BENCH_TESTLOG": str(log)}, capture_output=True, text=True,
            )
        if log.exists():
            for line in log.read_text(encoding="utf-8").splitlines():
                entry = json.loads(line)
                results.update(entry["results"])
                failures.update(entry.get("failures", {}))
    wanted = set(nodeids)
    return ({nodeid: results.get(nodeid, "error") for nodeid in nodeids},
            {nodeid: info for nodeid, info in failures.items() if nodeid in wanted})


def run_nodeids(tree: Path, task: Task, nodeids: Sequence[str], env: Mapping[str, str]) -> dict[str, str]:
    """Run exactly these tests once. A test that never produced a result (e.g. its file failed to import) is "error"."""
    return run_nodeids_detail(tree, task, nodeids, env)[0]


def invalid_reason(outcome: str, failure: Mapping[str, str] | None, tree: Path) -> dict[str, str]:
    """Why a new test did not pass on the reference, in a form that is identical across scorings.

    category: assertion (its expectation disagrees with the reference), exception (it crashed while running),
    setup (a fixture failed), skipped, or not_run (no result at all, e.g. its file does not import).
    """
    if outcome == "skipped":
        return {"category": "skipped", "message": ""}
    if not failure:
        return {"category": "not_run", "message": ""}
    if failure.get("when") != "call":
        category = "setup"
    elif failure.get("exc_type") in EXPECTATION_FAILURES:
        category = "assertion"
    else:
        category = "exception"
    message = failure.get("message", "").replace(str(tree), "<tree>")
    return {"category": category, "message": re.sub(r"0x[0-9a-fA-F]+", "0x?", message)}


@dataclass
class RedResult:
    red: bool
    outcomes: dict[str, str]


@dataclass
class GreenResult:
    valid: list[str]
    failing: list[str]
    flaky: list[str]
    reasons: dict[str, dict[str, str]] = field(default_factory=dict)


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

    Always passed = valid, never passed = failing, mixed = flaky. Every failing or flaky test gets a reason,
    taken from its first run that did not pass.
    """
    if not added:
        return GreenResult([], [], [])
    with tempfile.TemporaryDirectory() as tmp:
        tree = transplant(changed_test_files(reference, final, task), final, reference, Path(tmp) / "tree")
        runs = [run_nodeids_detail(tree, task, added, env) for _ in range(reruns)]
        valid, failing, flaky = [], [], []
        reasons: dict[str, dict[str, str]] = {}
        for nodeid in sorted(added):
            passed = [outcomes[nodeid] == "passed" for outcomes, _ in runs]
            if all(passed):
                valid.append(nodeid)
                continue
            (failing if not any(passed) else flaky).append(nodeid)
            outcomes, failures = runs[passed.index(False)]
            reasons[nodeid] = invalid_reason(outcomes[nodeid], failures.get(nodeid), tree)
    return GreenResult(valid, failing, flaky, reasons)
