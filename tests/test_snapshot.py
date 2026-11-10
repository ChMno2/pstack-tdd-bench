import subprocess
from pathlib import Path

import pytest

from bench.snapshot import SnapshotError, apply_patch, build_planted, build_reference, build_snapshot
from bench.task import Task


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def _calc(tree: Path) -> str:
    return (tree / "backend/app/calc.py").read_text()


def test_snapshot_has_single_commit_and_no_remote(mini_sut_repo, mini_task: Task, tmp_path: Path):
    repo, commit = mini_sut_repo
    snap = build_snapshot(repo, commit, mini_task, tmp_path / "snap")
    assert _git(snap, "rev-list", "--count", "HEAD") == "1"
    assert _git(snap, "remote") == ""
    assert _git(snap, "status", "--porcelain") == ""


def test_snapshot_contains_start_patch(mini_sut_repo, mini_task: Task, tmp_path: Path):
    repo, commit = mini_sut_repo
    snap = build_snapshot(repo, commit, mini_task, tmp_path / "snap")
    assert "return n % 2 == 1" in _calc(snap)


def test_snapshot_commit_is_deterministic(mini_sut_repo, mini_task: Task, tmp_path: Path):
    repo, commit = mini_sut_repo
    a = build_snapshot(repo, commit, mini_task, tmp_path / "a")
    b = build_snapshot(repo, commit, mini_task, tmp_path / "b")
    assert _git(a, "rev-parse", "HEAD") == _git(b, "rev-parse", "HEAD")


def test_reference_applies_reference_patch(mini_sut_repo, mini_task: Task, tmp_path: Path):
    repo, commit = mini_sut_repo
    snap = build_snapshot(repo, commit, mini_task, tmp_path / "snap")
    ref = build_reference(snap, mini_task, tmp_path / "ref")
    assert "return n % 2 == 0" in _calc(ref)
    assert "return n % 2 == 1" in _calc(snap)


def test_planted_applies_on_reference(mini_sut_repo, mini_task: Task, tmp_path: Path):
    repo, commit = mini_sut_repo
    snap = build_snapshot(repo, commit, mini_task, tmp_path / "snap")
    ref = build_reference(snap, mini_task, tmp_path / "ref")
    planted = build_planted(ref, mini_task, "off_by_one", tmp_path / "planted")
    assert "min(x, hi - 1)" in _calc(planted)
    assert "return n % 2 == 0" in _calc(planted)


def test_bad_patch_raises(mini_sut_repo, mini_task: Task, tmp_path: Path):
    repo, commit = mini_sut_repo
    snap = build_snapshot(repo, commit, mini_task, tmp_path / "snap")
    bad = tmp_path / "bad.patch"
    bad.write_text("--- a/nope.py\n+++ b/nope.py\n@@ -1 +1 @@\n-x\n+y\n")
    with pytest.raises(SnapshotError):
        apply_patch(snap, bad)


def test_empty_start_patch_gives_the_sut_as_is(mini_sut_repo, mini_task, tmp_path: Path):
    """Feature tasks often start from the SUT unchanged, so start.patch may be empty."""
    import shutil

    from bench.task import load_task

    repo, commit = mini_sut_repo
    root = tmp_path / "task"
    shutil.copytree(mini_task.root, root)
    (root / "start.patch").write_text("")
    (root / "reference.patch").write_text("")
    task = load_task(root)
    snap = build_snapshot(repo, commit, task, tmp_path / "snap")
    assert "return n % 2 == 0" in _calc(snap)
    assert "return n % 2 == 0" in _calc(build_reference(snap, task, tmp_path / "ref"))
