"""Task definition: one TDD unit of work on the SUT, stored as tasks/<id>/."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

REQUIRED = ("id", "kind", "description", "workdir", "test_command", "modules", "prod_globs", "planted")
KINDS = ("bugfix", "feature")


class TaskError(Exception):
    pass


@dataclass(frozen=True)
class Task:
    id: str
    kind: Literal["bugfix", "feature"]
    description: str
    workdir: str
    test_command: str
    modules: tuple[str, ...]
    prod_globs: tuple[str, ...]
    planted: tuple[str, ...]
    root: Path

    @property
    def start_patch(self) -> Path:
        return self.root / "start.patch"

    @property
    def reference_patch(self) -> Path:
        return self.root / "reference.patch"

    def planted_patch(self, name: str) -> Path:
        return self.root / "planted" / f"{name}.patch"


def load_task(root: Path) -> Task:
    root = Path(root)
    spec_file = root / "task.yaml"
    if not spec_file.is_file():
        raise TaskError(f"{spec_file} not found")
    data = yaml.safe_load(spec_file.read_text(encoding="utf-8")) or {}
    missing = [key for key in REQUIRED if key not in data]
    if missing:
        raise TaskError(f"{spec_file}: missing field(s) {', '.join(missing)}")
    if data["kind"] not in KINDS:
        raise TaskError(f"{spec_file}: kind must be one of {KINDS}, got {data['kind']!r}")
    task = Task(
        id=str(data["id"]),
        kind=data["kind"],
        description=str(data["description"]).strip(),
        workdir=str(data["workdir"]),
        test_command=str(data["test_command"]),
        modules=tuple(data["modules"]),
        prod_globs=tuple(data["prod_globs"]),
        planted=tuple(data["planted"] or ()),
        root=root,
    )
    required_files = [task.start_patch, task.reference_patch] + [task.planted_patch(n) for n in task.planted]
    for path in required_files:
        if not path.is_file():
            raise TaskError(f"{root}: missing {path.relative_to(root)}")
    return task


def task_hash(task: Task) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in task.root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(task.root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
