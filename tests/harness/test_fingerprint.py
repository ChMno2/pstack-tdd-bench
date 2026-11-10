import stat
from pathlib import Path

import pytest

from bench.harness.fingerprint import KEYS, collect
from bench.task import Task, task_hash


@pytest.fixture
def fake_claude(tmp_path: Path) -> str:
    path = tmp_path / "claude"
    path.write_text("#!/bin/sh\necho '2.1.322 (Claude Code)'\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


ENV = {
    "GITHUB_SHA": "abc123",
    "BENCH_IMAGE_DIGEST": "ghcr.io/x@sha256:1",
    "BENCH_POSTGRES_DIGEST": "postgres@sha256:2",
    "BENCH_REDIS_DIGEST": "redis@sha256:3",
}


def test_all_keys_present(mini_task: Task, fake_claude: str):
    fp = collect(mini_task, claude_bin=fake_claude, env=ENV)
    assert set(fp) == set(KEYS)
    assert fp["harness"] == "claude-code"
    assert fp["model"] == "claude-sonnet-5-5"
    assert fp["pstack_commit"] == "c742dd61706fbacc1b95f1a20b7b988cf096ce6c"
    assert fp["lims_commit"] == "227be16e3365e9956da0dec8efa987db3e0f3e4f"
    assert fp["bench_commit"] == "abc123"
    assert fp["image_digest"] == "ghcr.io/x@sha256:1"
    assert fp["task_hash"] == task_hash(mini_task)
    assert fp["tz"] == "UTC" and fp["pythonhashseed"] == "0"


def test_version_parsed_from_cli(mini_task: Task, fake_claude: str):
    assert collect(mini_task, claude_bin=fake_claude, env=ENV)["harness_version"] == "2.1.322"


def test_missing_digest_is_unknown(mini_task: Task, fake_claude: str):
    fp = collect(mini_task, claude_bin=fake_claude, env={})
    assert fp["image_digest"] == fp["postgres_digest"] == fp["redis_digest"] == "unknown"
    assert len(fp["bench_commit"]) == 40


def test_missing_cli_is_unknown(mini_task: Task, tmp_path: Path):
    assert collect(mini_task, claude_bin=str(tmp_path / "nope"), env=ENV)["harness_version"] == "unknown"
