import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from bench.pins import REPO_ROOT
from bench.task import Task, TaskError, load_task, task_hash

FIXTURES = Path(__file__).parent / "fixtures"


def _copy_task(tmp_path: Path) -> Path:
    dest = tmp_path / "task"
    shutil.copytree(FIXTURES / "minitask", dest)
    return dest


def _edit_yaml(root: Path, **changes) -> None:
    data = yaml.safe_load((root / "task.yaml").read_text())
    for key, value in changes.items():
        if value is None:
            data.pop(key)
        else:
            data[key] = value
    (root / "task.yaml").write_text(yaml.safe_dump(data, allow_unicode=True))


def test_load_valid_task(mini_task: Task):
    assert mini_task.id == "mini"
    assert mini_task.kind == "bugfix"
    assert mini_task.workdir == "backend"
    assert mini_task.test_command == "cd backend && python -m pytest"
    assert mini_task.modules == ("app/calc.py",)
    assert mini_task.prod_globs == ("backend/app/**/*.py",)
    assert mini_task.planted == ("off_by_one",)
    assert "is_even" in mini_task.description
    assert mini_task.root == FIXTURES / "minitask"


def test_missing_field_raises(tmp_path: Path):
    root = _copy_task(tmp_path)
    _edit_yaml(root, workdir=None)
    with pytest.raises(TaskError, match="workdir"):
        load_task(root)


def test_invalid_kind_raises(tmp_path: Path):
    root = _copy_task(tmp_path)
    _edit_yaml(root, kind="refactor")
    with pytest.raises(TaskError, match="kind"):
        load_task(root)


def test_missing_patch_raises(tmp_path: Path):
    root = _copy_task(tmp_path)
    (root / "reference.patch").unlink()
    with pytest.raises(TaskError, match="reference.patch"):
        load_task(root)


def test_missing_planted_patch_raises(tmp_path: Path):
    root = _copy_task(tmp_path)
    (root / "planted" / "off_by_one.patch").unlink()
    with pytest.raises(TaskError, match="off_by_one"):
        load_task(root)


def test_hash_changes_when_file_changes(tmp_path: Path):
    root = _copy_task(tmp_path)
    before = task_hash(load_task(root))
    assert before == task_hash(load_task(root))
    (root / "start.patch").write_text((root / "start.patch").read_text() + "\n")
    assert task_hash(load_task(root)) != before


def test_smoke_task_loads():
    task = load_task(REPO_ROOT / "tasks/T00-smoke")
    assert task.kind == "bugfix"
    subprocess.run(
        ["git", "-C", str(REPO_ROOT / "sut/lims"), "apply", "--check", str(task.root / "start.patch")],
        check=True,
    )
