"""Validate a task directory against the pinned SUT before it is used in an experiment."""

from __future__ import annotations

import tempfile
from pathlib import Path

from bench.task import Task
from bench.task.snapshot import SnapshotError, build_planted, build_reference, build_snapshot


def _first_line(exc: Exception) -> str:
    text = str(exc).strip()
    return text.splitlines()[-1] if text else repr(exc)


def check_task(task: Task, *, sut_repo: Path, commit: str) -> list[str]:
    """Return human-readable problems; an empty list means the task is usable."""
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        try:
            snapshot = build_snapshot(sut_repo, commit, task, tmp / "snapshot")
        except SnapshotError as exc:
            return [f"start.patch does not apply to the SUT at {commit[:7]}: {_first_line(exc)}"]
        try:
            reference = build_reference(snapshot, task, tmp / "reference")
        except SnapshotError as exc:
            return [f"reference.patch does not apply to the snapshot: {_first_line(exc)}"]
        for name in task.planted:
            try:
                build_planted(reference, task, name, tmp / f"planted-{name}")
            except SnapshotError as exc:
                problems.append(f"planted/{name}.patch does not apply to the reference: {_first_line(exc)}")
        for module in task.modules:
            if not (reference / task.workdir / module).is_file():
                problems.append(f"module {module} not found under {task.workdir}/ in the reference")
        if not any(any(reference.glob(pattern)) for pattern in task.prod_globs):
            problems.append(f"prod_globs {list(task.prod_globs)} match no file in the reference")
    return problems
