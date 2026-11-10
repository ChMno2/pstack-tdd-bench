"""Test adequacy of a run's valid new tests, measured on the reference implementation."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from bench.scoring.redgreen import FAILING, run_nodeids, transplant
from bench.scoring.testdiff import PYTEST_ISOLATION, changed_test_files
from bench.snapshot import build_planted
from bench.task import Task


def _tests_on(reference: Path, final: Path, task: Task, dest: Path) -> Path:
    return transplant(changed_test_files(reference, final, task), final, reference, dest)


def coverage(reference: Path, final: Path, task: Task, valid: Sequence[str], env: Mapping[str, str]) -> dict:
    if not valid:
        return {"line": 0.0, "branch": 0.0}
    packages = sorted({m.split("/")[0] for m in task.modules})
    with tempfile.TemporaryDirectory() as tmp:
        tree = _tests_on(reference, final, task, Path(tmp) / "tree")
        report = Path(tmp) / "cov.json"
        subprocess.run(
            [sys.executable, "-m", "pytest", *valid, "-q", *PYTEST_ISOLATION, "--cov-branch",
             *[f"--cov={p}" for p in packages], f"--cov-report=json:{report}", "--cov-report="],
            cwd=tree / task.workdir, env=dict(env), capture_output=True, text=True,
        )
        files = json.loads(report.read_text())["files"] if report.exists() else {}
    stats = [files[m]["summary"] for m in task.modules if m in files]
    statements = sum(s["num_statements"] for s in stats)
    branches = sum(s.get("num_branches", 0) for s in stats)
    return {
        "line": sum(s["covered_lines"] for s in stats) / statements if statements else 0.0,
        "branch": sum(s.get("covered_branches", 0) for s in stats) / branches if branches else 0.0,
    }


def _mutmut_config(workdir: Path, task: Task, valid: Sequence[str]) -> None:
    sources = sorted({m.split("/")[0] for m in task.modules})
    copy = sorted(p.name for p in workdir.iterdir() if p.name not in {*sources, "mutants", "setup.cfg"})

    def block(key: str, values: Sequence[str]) -> str:
        return f"{key} =\n" + "".join(f"    {v}\n" for v in values)

    (workdir / "setup.cfg").write_text(
        "[mutmut]\n"
        + block("source_paths", sources)
        + block("only_mutate", task.modules)
        + block("also_copy", copy)
        + block("pytest_add_cli_args", PYTEST_ISOLATION)
        + block("pytest_add_cli_args_test_selection", valid)
        + "use_git_change_detection = false\n"
    )


def mutation(
    reference: Path,
    final: Path,
    task: Task,
    valid: Sequence[str],
    added_count: int,
    env: Mapping[str, str],
    log_dir: Path | None = None,
) -> dict:
    """killed counts mutmut's killed and timeout outcomes; score = killed / total; per_test = killed / added_count."""
    if not valid:
        return {"killed": 0, "total": 0, "score": 0.0, "per_test": 0.0}
    with tempfile.TemporaryDirectory() as tmp:
        tree = _tests_on(reference, final, task, Path(tmp) / "tree")
        workdir = tree / task.workdir
        _mutmut_config(workdir, task, valid)
        log = [f"[setup.cfg]\n{(workdir / 'setup.cfg').read_text()}"]
        # One worker: parallel workers each run the SUT's session fixtures against the same database,
        # and LIMS's conftest drops and recreates the schema, so races turn survivors into spurious kills.
        for command in (["run", "--max-children", "1"], ["results", "--all", "true"], ["export-cicd-stats"]):
            proc = subprocess.run([sys.executable, "-m", "mutmut", *command], cwd=workdir, env=dict(env),
                                  capture_output=True, text=True, check=False)
            log.append(f"[mutmut {' '.join(command)}] exit={proc.returncode}\n{proc.stdout}\n{proc.stderr}")
        if log_dir is not None:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            (Path(log_dir) / "mutmut.log").write_text("\n".join(log), encoding="utf-8")
        stats_file = workdir / "mutants/mutmut-cicd-stats.json"
        stats = json.loads(stats_file.read_text()) if stats_file.exists() else {}
    killed = int(stats.get("killed", 0)) + int(stats.get("timeout", 0))
    total = int(stats.get("total", 0))
    return {
        "killed": killed,
        "total": total,
        "score": killed / total if total else 0.0,
        "per_test": killed / added_count if added_count else 0.0,
    }


def planted(reference: Path, final: Path, task: Task, valid: Sequence[str], env: Mapping[str, str]) -> dict[str, bool]:
    if not valid:
        return {name: False for name in task.planted}
    detected = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name in task.planted:
            buggy = build_planted(reference, task, name, Path(tmp) / f"{name}-code")
            tree = _tests_on(buggy, final, task, Path(tmp) / f"{name}-tree")
            detected[name] = any(o in FAILING for o in run_nodeids(tree, task, valid, env).values())
    return detected
