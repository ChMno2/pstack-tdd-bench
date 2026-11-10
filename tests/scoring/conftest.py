import os
import shutil
from pathlib import Path

import pytest

from bench.task.snapshot import build_snapshot


@pytest.fixture
def trees(tmp_path: Path, mini_sut_repo, mini_task) -> tuple[Path, Path]:
    """(snapshot, final): final starts as a copy of the snapshot; tests edit it like an agent would."""
    repo, commit = mini_sut_repo
    snapshot = build_snapshot(repo, commit, mini_task, tmp_path / "snapshot")
    final = tmp_path / "final"
    shutil.copytree(snapshot, final)
    return snapshot, final


@pytest.fixture
def env() -> dict[str, str]:
    return dict(os.environ)


def write(tree: Path, rel: str, text: str) -> None:
    path = tree / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
