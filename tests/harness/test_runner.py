import json
import os
import stat
import sys
import time
from pathlib import Path

import pytest

from bench.harness.conditions import CONDITIONS
from bench.harness.runner import RunSpec, needs_decision, run
from bench.task import Task
from bench.task.snapshot import build_snapshot
from tests.conftest import FIXTURES

BASE_ENV = {"PATH": os.environ["PATH"], "CLAUDE_CODE_OAUTH_TOKEN": "fake-token"}


def _fake_claude(tmp_path: Path, scenario: str) -> str:
    path = tmp_path / "bin" / "claude"
    path.parent.mkdir()
    # /bin/sh wrapper: shebang lines cannot hold interpreter paths with spaces.
    path.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "{FIXTURES / "fake_claude.py"}" "{scenario}" "{tmp_path / "state"}" "$@"\n'
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def _spec(tmp_path: Path, mini_sut_repo, mini_task: Task, scenario: str, cond: str = "C1", timeout_s: int = 60):
    repo, commit = mini_sut_repo
    run_dir = tmp_path / "run"
    workspace = build_snapshot(repo, commit, mini_task, run_dir / "workspace")
    return RunSpec(task=mini_task, condition=CONDITIONS[cond], rep=1, run_dir=run_dir, workspace=workspace,
                   plugin_dir=tmp_path / "pstack", home=tmp_path / "home", timeout_s=timeout_s,
                   claude_bin=_fake_claude(tmp_path, scenario))


def _calls(tmp_path: Path) -> list[list[str]]:
    return [json.loads(p.read_text()) for p in sorted((tmp_path / "state").glob("call-*"))]


def test_completed_run_writes_artifacts(tmp_path, mini_sut_repo, mini_task):
    spec = _spec(tmp_path, mini_sut_repo, mini_task, "ok")
    result = run(spec, BASE_ENV)
    run_dir = spec.run_dir
    assert result["status"] == "completed"
    assert result["auto_replies"] == 0
    assert result["completion_claim"] == "Fixed it. All tests pass."
    assert result["exit_codes"] == [0]
    assert result["run_id"].startswith("mini-C1-r1-")
    assert result["fingerprint"]["harness_version"] == "2.1.322"
    assert result["usage_by_agent"]["main"]["output"] == 7
    assert result["first_prod_change"] is not None
    assert json.loads((run_dir / "run.json").read_text()) == result
    assert json.loads((run_dir / "watch.json").read_text()) == {"backend/app/calc.py": result["first_prod_change"]}
    assert (run_dir / "raw/session-1.jsonl").exists()
    assert (run_dir / "trajectory.jsonl").read_text().strip()
    assert (run_dir / "testlog.jsonl").exists()


def test_question_triggers_one_auto_reply(tmp_path, mini_sut_repo, mini_task):
    result = run(_spec(tmp_path, mini_sut_repo, mini_task, "ask_once"), BASE_ENV)
    assert result["status"] == "completed"
    assert result["auto_replies"] == 1
    assert result["completion_claim"] == "Done."
    second = _calls(tmp_path)[1]
    assert second[second.index("--resume") + 1] == "s-1"
    assert second[second.index("-p") + 1] == "請依你的判斷繼續，不要再詢問"


def test_auto_replies_capped_at_three(tmp_path, mini_sut_repo, mini_task):
    result = run(_spec(tmp_path, mini_sut_repo, mini_task, "ask_forever"), BASE_ENV)
    assert result["auto_replies"] == 3
    assert len(_calls(tmp_path)) == 4
    assert result["status"] == "completed"


def test_nonzero_exit_marks_harness_error(tmp_path, mini_sut_repo, mini_task):
    result = run(_spec(tmp_path, mini_sut_repo, mini_task, "crash"), BASE_ENV)
    assert result["status"] == "harness_error"
    assert result["exit_codes"] == [2]


def test_error_result_marks_harness_error(tmp_path, mini_sut_repo, mini_task):
    result = run(_spec(tmp_path, mini_sut_repo, mini_task, "error_result"), BASE_ENV)
    assert result["status"] == "harness_error"


def test_timeout_marks_timeout(tmp_path, mini_sut_repo, mini_task):
    started = time.time()
    result = run(_spec(tmp_path, mini_sut_repo, mini_task, "hang", timeout_s=2), BASE_ENV)
    assert result["status"] == "timeout"
    assert time.time() - started < 20


def test_c2a_writes_pstack_models(tmp_path, mini_sut_repo, mini_task):
    spec = _spec(tmp_path, mini_sut_repo, mini_task, "ok", cond="C2a")
    run(spec, BASE_ENV)
    assert (spec.home / ".claude/rules/pstack-models.md").exists()
    first = _calls(tmp_path)[0]
    assert first[first.index("--plugin-dir") + 1] == str(spec.plugin_dir)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Should I continue?", True),
        ("要繼續嗎？", True),
        ("Here is my plan.\n\nWhich option do you want?\n", True),
        ("Is this right? I fixed it and the tests pass.", False),
        ("Done.", False),
        ("", False),
    ],
)
def test_needs_decision_cases(text, expected):
    assert needs_decision(text) is expected


def test_chown_tree_handles_symlinks_without_root(tmp_path):
    """Regression: shutil.chown(follow_symlinks=...) does not exist on Python 3.12 (found in the CI dry run)."""
    import getpass

    from bench.harness.runner import _chown_tree

    tree = tmp_path / "ws"
    (tree / "pkg").mkdir(parents=True)
    (tree / "pkg/a.py").write_text("x = 1\n")
    (tree / "link.py").symlink_to("pkg/a.py")
    (tree / "dangling.py").symlink_to("missing.py")
    _chown_tree(tree, getpass.getuser())
    assert (tree / "pkg/a.py").stat().st_uid == os.getuid()


def _all_bytes(root):
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            yield path, path.read_bytes()


def test_credentials_are_redacted_everywhere_in_the_run_dir(tmp_path, mini_sut_repo, mini_task):
    """Review Critical 1: artifacts are public, so no credential may survive in raw output, logs or workspace."""
    spec = _spec(tmp_path, mini_sut_repo, mini_task, "leak")
    result = run(spec, BASE_ENV)
    assert result["status"] == "completed"
    leaks = [str(p) for p, data in _all_bytes(spec.run_dir) if b"fake-token" in data]
    assert leaks == []
    assert not (spec.run_dir / "workspace/.git").exists()
    history = (spec.run_dir / "workspace-git.patch").read_text()
    assert "debug [REDACTED]" in history and "leak.txt" in history
    assert (spec.run_dir / "workspace/backend/leak.txt").read_text() == "token=[REDACTED]\n"


def test_processes_left_by_the_agent_are_killed(tmp_path, mini_sut_repo, mini_task):
    """Review Important 6: nothing the agent started may keep running into scoring."""
    result = run(_spec(tmp_path, mini_sut_repo, mini_task, "orphan"), BASE_ENV)
    pid = int((tmp_path / "state/orphan.pid").read_text())
    deadline = time.time() + 5
    alive = True
    while alive and time.time() < deadline:
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
        except ProcessLookupError:
            alive = False
    assert not alive
    assert result["leftover_processes"] is None  # only counted when running as a separate user


def test_claude_transcripts_are_copied(tmp_path, mini_sut_repo, mini_task):
    """Review Important 7: subagent transcripts must reach the run dir for traceability and contamination checks."""
    spec = _spec(tmp_path, mini_sut_repo, mini_task, "transcript")
    run(spec, BASE_ENV)
    assert (spec.run_dir / "transcripts/-work/s-1/subagents/agent-1.jsonl").exists()


def test_truncated_utf8_output_still_produces_run_json(tmp_path, mini_sut_repo, mini_task):
    """A SIGKILL can cut a multi-byte character; the run must still be recorded and scored."""
    spec = _spec(tmp_path, mini_sut_repo, mini_task, "badbytes")
    result = run(spec, BASE_ENV)
    assert result["status"] == "completed"
    assert (spec.run_dir / "run.json").exists()


def test_reaping_failure_still_writes_run_json(tmp_path, mini_sut_repo, mini_task, monkeypatch):
    """Found in the container dry run: a missing pgrep must not cost the run its run.json."""
    import bench.harness.runner as runner_mod

    def broken(user):
        raise FileNotFoundError("pgrep")

    monkeypatch.setattr(runner_mod, "_reap_user", broken)
    spec = _spec(tmp_path, mini_sut_repo, mini_task, "ok")
    result = run(spec, BASE_ENV)
    assert (spec.run_dir / "run.json").exists()
    assert result["leftover_processes"] is None
    assert "pgrep" in result["error"]
