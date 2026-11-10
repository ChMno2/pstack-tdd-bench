import shutil
import subprocess
from pathlib import Path

import pytest

from bench.task import Task, load_task

FIXTURES = Path(__file__).parent / "fixtures"

pytest_plugins = ["pytester"]


def _git(repo: Path, *args: str) -> str:
    env = {
        "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@localhost",
        "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@localhost",
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
        "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
    }
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env).stdout


@pytest.fixture
def mini_sut_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "minisut"
    shutil.copytree(FIXTURES / "minisut", repo)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "minisut")
    return repo, _git(repo, "rev-parse", "HEAD").strip()


@pytest.fixture
def mini_task() -> Task:
    return load_task(FIXTURES / "minitask")
