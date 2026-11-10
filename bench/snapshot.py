"""Build the Snapshot (start state), the Reference Implementation and planted-bug variants."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

from bench.task import Task

FIXED_IDENTITY = {
    "GIT_AUTHOR_NAME": "bench",
    "GIT_AUTHOR_EMAIL": "bench@localhost",
    "GIT_COMMITTER_NAME": "bench",
    "GIT_COMMITTER_EMAIL": "bench@localhost",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
}


class SnapshotError(Exception):
    pass


def _git(cwd: Path, *args: str, data: bytes | None = None) -> bytes:
    env = {**os.environ, **FIXED_IDENTITY, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    proc = subprocess.run(["git", "-C", str(cwd), *args], input=data, capture_output=True, env=env)
    if proc.returncode != 0:
        raise SnapshotError(f"git {' '.join(args)} failed in {cwd}: {proc.stderr.decode(errors='replace')}")
    return proc.stdout


def _ensure_repo(tree: Path) -> None:
    # A tree without its own .git would make `git apply` resolve paths against an enclosing repo.
    if not (tree / ".git").exists():
        _git(tree, "init", "-q", "-b", "main")


def apply_patch(tree: Path, patch: Path) -> None:
    _ensure_repo(tree)
    _git(tree, "apply", "--whitespace=nowarn", str(Path(patch).resolve()))


def build_snapshot(sut_repo: Path, commit: str, task: Task, dest: Path) -> Path:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=False)
    archive = _git(Path(sut_repo), "archive", "--format=tar", commit)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(dest, filter="tar")
    _git(dest, "init", "-q", "-b", "main")
    apply_patch(dest, task.start_patch)
    _git(dest, "add", "-A")
    _git(dest, "commit", "-q", "--no-gpg-sign", "-m", "snapshot")
    return dest


def _copy_tree(src: Path, dest: Path) -> Path:
    dest = Path(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".git"), symlinks=True)
    return dest


def build_reference(snapshot: Path, task: Task, dest: Path) -> Path:
    tree = _copy_tree(snapshot, dest)
    apply_patch(tree, task.reference_patch)
    return tree


def build_planted(reference: Path, task: Task, name: str, dest: Path) -> Path:
    tree = _copy_tree(reference, dest)
    apply_patch(tree, task.planted_patch(name))
    return tree
