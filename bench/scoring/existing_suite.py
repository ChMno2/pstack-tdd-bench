"""The existing test suite as a yardstick.

existing_suite: what the snapshot's own tests cover and kill on the reference, the same for every condition.
increment: what a run's valid new tests add on top of that, combined exactly (union of executed lines, branches
and killed mutants), so a run is not credited for re-testing what the suite already tests.
regression: existing tests that pass on the reference but fail on the run's final code, judged with the
snapshot's versions of the tests so that weakening a test does not hide a regression.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from bench.scoring.quality import CoverageData, run_coverage, run_mutmut
from bench.scoring.redgreen import FAILING, run_nodeids
from bench.scoring.testdiff import SKIP_PARTS, collect_nodeids, is_test_support
from bench.task import Task


def existing_tests(snapshot: Path, task: Task, env: Mapping[str, str]) -> list[str]:
    return sorted(collect_nodeids(snapshot, task, env))


def _test_support_files(tree: Path, task: Task) -> set[Path]:
    root = Path(tree)
    found = set()
    for path in (root / task.workdir).rglob("*"):
        rel = path.relative_to(root)
        if path.is_file() and not SKIP_PARTS & set(rel.parts) and path.suffix != ".pyc" and is_test_support(rel):
            found.add(rel)
    return found


def restore_tests(snapshot: Path, code: Path, task: Task, dest: Path) -> Path:
    """A copy of `code` whose test-support files are exactly the snapshot's: added ones removed, changed ones reset."""
    dest = Path(dest)
    shutil.copytree(code, dest, ignore=shutil.ignore_patterns(".git"), symlinks=True)
    original = _test_support_files(snapshot, task)
    for rel in _test_support_files(dest, task) - original:
        (dest / rel).unlink()
    for rel in original:
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(snapshot) / rel, out)
    return dest


def _files(nodeids: Sequence[str]) -> list[str]:
    return sorted({nid.split("::")[0] for nid in nodeids})


@dataclass
class ExistingSuite:
    tests: int
    outcomes: dict[str, str]
    coverage: CoverageData | None
    killed: set[str] | None
    mutation: dict = field(default_factory=dict)

    def summary(self) -> dict:
        if self.coverage is None:
            cov = {"ok": False, "line": None, "branch": None}
        else:
            cov = {"ok": True, "line": self.coverage.line(), "branch": self.coverage.branch()}
        return {"tests": self.tests, "coverage": cov, "mutation": self.mutation}


def measure_existing_suite(snapshot: Path, reference: Path, task: Task, existing: Sequence[str], env: Mapping[str, str],
                     log_dir: Path | None = None) -> ExistingSuite:
    """Run the existing suite on the reference once under coverage (recording outcomes), then once under mutmut."""
    if not existing:
        return ExistingSuite(0, {}, CoverageData(), set(),
                        {"ok": True, "error": None, "killed": 0, "total": 0, "score": 0.0})
    files = _files(existing)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        log = tmp / "log.jsonl"
        data = run_coverage(restore_tests(snapshot, reference, task, tmp / "cov"), task,
                            [*files, "--continue-on-collection-errors"], env, testlog=log)
        results: dict[str, str] = {}
        if log.exists():
            for line in log.read_text(encoding="utf-8").splitlines():
                results.update(json.loads(line)["results"])
        stats, killed, error = run_mutmut(restore_tests(snapshot, reference, task, tmp / "mut"), task, files, env,
                                          log_dir, "mutmut-existing.log")
    if stats is None:
        mutation = {"ok": False, "error": error, "killed": None, "total": None, "score": None}
    else:
        n_killed = int(stats.get("killed", 0)) + int(stats.get("timeout", 0))
        total = int(stats.get("total", 0))
        mutation = {"ok": True, "error": None, "killed": n_killed, "total": total,
                    "score": n_killed / total if total else 0.0}
    outcomes = {nid: results.get(nid, "error") for nid in existing}
    return ExistingSuite(len(existing), outcomes, data, killed, mutation)


def increment(base: ExistingSuite, data: CoverageData | None, killed: set[str] | None) -> dict:
    if base.coverage is None or data is None:
        cov = {"ok": False, "line": None, "branch": None, "new_lines": None, "new_branches": None}
    else:
        both = base.coverage.union(data)
        cov = {
            "ok": True,
            "line": both.line() - base.coverage.line(),
            "branch": both.branch() - base.coverage.branch(),
            "new_lines": sum(map(len, both.lines.values())) - sum(map(len, base.coverage.lines.values())),
            "new_branches": sum(map(len, both.branches.values())) - sum(map(len, base.coverage.branches.values())),
        }
    if base.killed is None or killed is None:
        mut = {"ok": False, "newly_killed": None, "combined_score": None}
    else:
        total = base.mutation.get("total") or 0
        mut = {"ok": True, "newly_killed": len(killed - base.killed),
               "combined_score": len(base.killed | killed) / total if total else 0.0}
    return {"coverage": cov, "mutation": mut}


def _run_existing(snapshot: Path, code: Path, task: Task, existing: Sequence[str],
                  env: Mapping[str, str]) -> dict[str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        return run_nodeids(restore_tests(snapshot, code, task, Path(tmp) / "tree"), task, existing, env)


def regression(snapshot: Path, reference: Path, final: Path, task: Task, existing: Sequence[str],
               env: Mapping[str, str], reference_outcomes: Mapping[str, str] | None = None) -> dict:
    if reference_outcomes is None:
        reference_outcomes = _run_existing(snapshot, reference, task, existing, env)
    final_outcomes = _run_existing(snapshot, final, task, existing, env) if existing else {}
    return {
        "existing": len(existing),
        "failing": sorted(n for n in existing
                          if reference_outcomes.get(n) == "passed" and final_outcomes.get(n) in FAILING),
        "already_failing": sorted(n for n in existing if reference_outcomes.get(n) in FAILING),
    }
