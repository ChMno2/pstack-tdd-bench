"""Test adequacy of a run's valid new tests, measured on the reference implementation."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from bench.capture.pytest_plugin import plugin_env
from bench.scoring.redgreen import FAILING, run_nodeids, transplant
from bench.scoring.testdiff import PYTEST_ISOLATION, changed_test_files
from bench.task import Task
from bench.task.snapshot import build_planted

KILLED_STATUSES = ("killed", "timeout")
MUTANT_LINE = re.compile(r"^\s+(\S+): (.+)$")


def _tests_on(reference: Path, final: Path, task: Task, dest: Path) -> Path:
    return transplant(changed_test_files(reference, final, task), final, reference, dest)


@dataclass
class CoverageData:
    """Executed statements and branches per task module, so two test sets can be combined exactly."""

    lines: dict[str, set[int]] = field(default_factory=dict)
    branches: dict[str, set[tuple[int, int]]] = field(default_factory=dict)
    statements: dict[str, int] = field(default_factory=dict)
    branch_total: dict[str, int] = field(default_factory=dict)

    def line(self) -> float:
        total = sum(self.statements.values())
        return sum(len(v) for v in self.lines.values()) / total if total else 0.0

    def branch(self) -> float:
        total = sum(self.branch_total.values())
        return sum(len(v) for v in self.branches.values()) / total if total else 0.0

    def union(self, other: CoverageData) -> CoverageData:
        modules = set(self.statements) | set(other.statements)
        return CoverageData(
            lines={m: self.lines.get(m, set()) | other.lines.get(m, set()) for m in modules},
            branches={m: self.branches.get(m, set()) | other.branches.get(m, set()) for m in modules},
            statements={m: self.statements.get(m) or other.statements.get(m, 0) for m in modules},
            branch_total={m: self.branch_total.get(m) or other.branch_total.get(m, 0) for m in modules},
        )


def run_coverage(tree: Path, task: Task, args: Sequence[str], env: Mapping[str, str],
                 testlog: Path | None = None) -> CoverageData | None:
    """Run pytest with `args` in the tree under coverage of the task's packages; None if no report came out.

    With `testlog`, benchlog also records every test's outcome there.
    """
    packages = sorted({m.split("/")[0] for m in task.modules})
    if testlog is None:
        isolation, run_env = PYTEST_ISOLATION, dict(env)
    else:
        isolation, run_env = ("-p", "no:cacheprovider"), {**env, **plugin_env(), "BENCH_TESTLOG": str(testlog)}
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "cov.json"
        subprocess.run(
            [sys.executable, "-m", "pytest", *args, "-q", *isolation, "--cov-branch",
             *[f"--cov={p}" for p in packages], f"--cov-report=json:{report}", "--cov-report="],
            cwd=Path(tree) / task.workdir, env=run_env, capture_output=True, text=True,
        )
        if not report.exists():
            return None
        files = json.loads(report.read_text())["files"]
    data = CoverageData()
    for m in task.modules:
        if m not in files:
            continue
        f = files[m]
        data.lines[m] = set(f.get("executed_lines", []))
        data.branches[m] = {tuple(b) for b in f.get("executed_branches", [])}
        data.statements[m] = int(f["summary"]["num_statements"])
        data.branch_total[m] = int(f["summary"].get("num_branches", 0))
    return data


def coverage_detail(
    reference: Path, final: Path, task: Task, valid: Sequence[str], env: Mapping[str, str]
) -> tuple[dict, CoverageData | None]:
    """Coverage of the task modules by the valid new tests on the reference, as a summary and as raw data."""
    if not valid:
        return {"ok": True, "line": 0.0, "branch": 0.0}, CoverageData()
    with tempfile.TemporaryDirectory() as tmp:
        tree = _tests_on(reference, final, task, Path(tmp) / "tree")
        data = run_coverage(tree, task, valid, env)
    if data is None:
        return {"ok": False, "line": None, "branch": None}, None
    return {"ok": True, "line": data.line(), "branch": data.branch()}, data


def coverage(reference: Path, final: Path, task: Task, valid: Sequence[str], env: Mapping[str, str]) -> dict:
    return coverage_detail(reference, final, task, valid, env)[0]


def _mutmut_config(workdir: Path, task: Task, selection: Sequence[str]) -> None:
    sources = sorted({m.split("/")[0] for m in task.modules})
    copy = sorted(p.name for p in workdir.iterdir() if p.name not in {*sources, "mutants", "setup.cfg"})

    def block(key: str, values: Sequence[str]) -> str:
        # mutmut reads setup.cfg with ConfigParser interpolation: a literal '%' must be written as '%%'.
        return f"{key} =\n" + "".join(f"    {v.replace('%', '%%')}\n" for v in values)

    (workdir / "setup.cfg").write_text(
        "[mutmut]\n"
        + block("source_paths", sources)
        + block("only_mutate", task.modules)
        + block("also_copy", copy)
        + block("pytest_add_cli_args", PYTEST_ISOLATION)
        + block("pytest_add_cli_args_test_selection", selection)
        + "use_git_change_detection = false\n"
    )


def run_mutmut(
    tree: Path, task: Task, selection: Sequence[str], env: Mapping[str, str],
    log_dir: Path | None = None, log_name: str = "mutmut.log",
) -> tuple[dict | None, set[str] | None, str | None]:
    """Run mutmut over the task modules with the selected tests: (cicd stats, killed mutant names, error)."""
    workdir = Path(tree) / task.workdir
    _mutmut_config(workdir, task, selection)
    log = [f"[setup.cfg]\n{(workdir / 'setup.cfg').read_text()}"]
    run_error = None
    killed: set[str] = set()
    # One worker: parallel workers each run the SUT's session fixtures against the same database,
    # and LIMS's conftest drops and recreates the schema, so races turn survivors into spurious kills.
    for command in (["run", "--max-children", "1"], ["results", "--all", "true"], ["export-cicd-stats"]):
        proc = subprocess.run([sys.executable, "-m", "mutmut", *command], cwd=workdir, env=dict(env),
                              capture_output=True, text=True, check=False)
        log.append(f"[mutmut {' '.join(command)}] exit={proc.returncode}\n{proc.stdout}\n{proc.stderr}")
        if command[0] == "run" and proc.returncode != 0:
            run_error = f"mutmut run exit {proc.returncode}: {proc.stderr.strip().splitlines()[-1:] or ['']}"
        if command[0] == "results":
            for line in proc.stdout.splitlines():
                match = MUTANT_LINE.match(line)
                if match and match.group(2).strip() in KILLED_STATUSES:
                    killed.add(match.group(1))
    if log_dir is not None:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        (Path(log_dir) / log_name).write_text("\n".join(log), encoding="utf-8")
    stats_file = workdir / "mutants/mutmut-cicd-stats.json"
    if not stats_file.exists():
        return None, None, run_error or "mutmut produced no stats"
    return json.loads(stats_file.read_text()), killed, None


def mutation_detail(
    reference: Path,
    final: Path,
    task: Task,
    valid: Sequence[str],
    added_count: int,
    env: Mapping[str, str],
    log_dir: Path | None = None,
) -> tuple[dict, set[str] | None]:
    """killed counts mutmut's killed and timeout outcomes; score = killed / total; per_test = killed / added_count.

    Also returns the names of the killed mutants, so the new tests can be combined with the existing suite.
    """
    if not valid:
        return {"ok": True, "error": None, "killed": 0, "total": 0, "score": 0.0, "per_test": 0.0}, set()
    with tempfile.TemporaryDirectory() as tmp:
        tree = _tests_on(reference, final, task, Path(tmp) / "tree")
        stats, names, error = run_mutmut(tree, task, valid, env, log_dir)
    if stats is None:
        return {"ok": False, "error": error, "killed": None, "total": None, "score": None, "per_test": None}, None
    killed = sum(int(stats.get(k, 0)) for k in KILLED_STATUSES)
    total = int(stats.get("total", 0))
    return {
        "ok": True,
        "error": None,
        "killed": killed,
        "total": total,
        "score": killed / total if total else 0.0,
        "per_test": killed / added_count if added_count else 0.0,
    }, names


def mutation(
    reference: Path,
    final: Path,
    task: Task,
    valid: Sequence[str],
    added_count: int,
    env: Mapping[str, str],
    log_dir: Path | None = None,
) -> dict:
    return mutation_detail(reference, final, task, valid, added_count, env, log_dir)[0]


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
