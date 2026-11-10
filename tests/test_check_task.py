import shutil
from pathlib import Path

import yaml

from bench.cli import main
from bench.task import load_task
from bench.task_check import check_task

FIXTURES = Path(__file__).parent / "fixtures"


def _copy(tmp_path: Path) -> Path:
    dest = tmp_path / "task"
    shutil.copytree(FIXTURES / "minitask", dest)
    return dest


def _edit(root: Path, **changes) -> None:
    data = yaml.safe_load((root / "task.yaml").read_text())
    data.update(changes)
    (root / "task.yaml").write_text(yaml.safe_dump(data))


def test_valid_task_has_no_problems(mini_sut_repo, mini_task):
    repo, commit = mini_sut_repo
    assert check_task(mini_task, sut_repo=repo, commit=commit) == []


def test_start_patch_that_does_not_apply_is_reported(tmp_path, mini_sut_repo):
    repo, commit = mini_sut_repo
    root = _copy(tmp_path)
    (root / "start.patch").write_text((root / "start.patch").read_text().replace("n % 2 == 0", "n % 3 == 0"))
    problems = check_task(load_task(root), sut_repo=repo, commit=commit)
    assert len(problems) == 1 and "start.patch" in problems[0]


def test_planted_patch_that_does_not_apply_is_reported(tmp_path, mini_sut_repo):
    repo, commit = mini_sut_repo
    root = _copy(tmp_path)
    p = root / "planted/off_by_one.patch"
    p.write_text(p.read_text().replace("min(x, hi))", "min(x, top))"))
    problems = check_task(load_task(root), sut_repo=repo, commit=commit)
    assert len(problems) == 1 and "off_by_one" in problems[0]


def test_missing_module_and_unmatched_globs_are_reported(tmp_path, mini_sut_repo):
    repo, commit = mini_sut_repo
    root = _copy(tmp_path)
    _edit(root, modules=["app/nope.py"], prod_globs=["frontend/**/*.ts"])
    problems = check_task(load_task(root), sut_repo=repo, commit=commit)
    assert any("app/nope.py" in p for p in problems)
    assert any("prod_globs" in p for p in problems)


def test_cli_check_task_exit_codes(tmp_path, mini_sut_repo, capsys):
    repo, commit = mini_sut_repo
    common = ["--sut-repo", str(repo), "--commit", commit]
    assert main(["check-task", "--task", str(FIXTURES / "minitask"), *common]) == 0
    assert "OK" in capsys.readouterr().out
    root = _copy(tmp_path)
    _edit(root, modules=["app/nope.py"])
    assert main(["check-task", "--task", str(root), *common]) == 1
