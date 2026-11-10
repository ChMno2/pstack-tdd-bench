import json
import shutil
from pathlib import Path

import pytest

from bench.scoring.score import contaminated, score_run
from bench.snapshot import build_snapshot
from bench.trajectory import Event, write_jsonl

NEW_TEST = "from app.calc import clamp, is_even\n\n\ndef test_is_even():\n    assert is_even(2)\n    assert not is_even(3)\n\n\n" \
           "def test_clamp_top():\n    assert clamp(10, 0, 5) == 5\n"
ADDED = ["tests/test_new.py::test_clamp_top", "tests/test_new.py::test_is_even"]


def _bash(cmd: str) -> Event:
    return Event(0, 1, "main", "tool_call", {"id": "t", "name": "Bash", "input": {"command": cmd}})


@pytest.fixture
def run_dir(tmp_path: Path, mini_sut_repo, mini_task) -> Path:
    """A finished TDD-style run: red test logged at t=100, production code first changed at t=200."""
    repo, commit = mini_sut_repo
    rd = tmp_path / "run"
    ws = build_snapshot(repo, commit, mini_task, rd / "workspace")
    (ws / "backend/tests/test_new.py").write_text(NEW_TEST)
    calc = ws / "backend/app/calc.py"
    calc.write_text(calc.read_text().replace("n % 2 == 1", "n % 2 == 0"))
    (rd / "testlog.jsonl").write_text(json.dumps(
        {"ts_start": 99, "ts_end": 100, "results": {"tests/test_new.py::test_is_even": "failed"}, "collect_errors": []}) + "\n")
    (rd / "run.json").write_text(json.dumps({
        "run_id": "mini-C1-r1-x", "status": "completed", "first_prod_change": 200.0, "auto_replies": 0,
        "completion_claim": "Fixed.", "usage_by_agent": {"main": {"output": 7}}, "totals": {"total_cost_usd": 0.01}}))
    write_jsonl([_bash("cd backend && python -m pytest")], rd / "trajectory.jsonl")
    return rd


def _score(run_dir: Path, mini_sut_repo, mini_task, env) -> dict:
    repo, commit = mini_sut_repo
    return score_run(run_dir, mini_task, sut_repo=repo, env=env, commit=commit)


def test_score_json_schema(run_dir, mini_sut_repo, mini_task, env):
    score = _score(run_dir, mini_sut_repo, mini_task, env)
    assert json.loads((run_dir / "score.json").read_text()) == score
    assert set(score) == {"run_id", "status", "testless", "tests", "red", "green", "adherence", "coverage",
                          "mutation", "planted", "contaminated", "cost"}
    assert score["testless"] is False
    assert score["tests"] == {"added": ADDED, "removed": [], "modified": []}
    assert score["red"]["red"] is True
    assert score["green"]["valid"] == ADDED
    assert score["adherence"]["followed"] is True
    assert score["coverage"]["line"] > 0
    assert score["mutation"]["total"] > 0 and score["mutation"]["killed"] > 0
    assert score["planted"] == {"off_by_one": True}
    assert score["contaminated"] is False
    assert score["cost"] == {"usage_by_agent": {"main": {"output": 7}}, "totals": {"total_cost_usd": 0.01},
                             "auto_replies": 0}


def test_testless_run(tmp_path, mini_sut_repo, mini_task, env):
    repo, commit = mini_sut_repo
    rd = tmp_path / "run"
    build_snapshot(repo, commit, mini_task, rd / "workspace")
    (rd / "run.json").write_text(json.dumps({"run_id": "r", "status": "completed", "first_prod_change": None}))
    score = _score(rd, mini_sut_repo, mini_task, env)
    assert score["testless"] is True
    assert score["red"]["red"] is False
    assert score["mutation"] == {"ok": True, "error": None, "killed": 0, "total": 0, "score": 0.0, "per_test": 0.0}
    assert score["adherence"] == {"followed": False, "sessions": 0, "evidence": None, "unmeasured": False}


def test_score_runs_for_failed_run(tmp_path, mini_sut_repo, mini_task, env):
    repo, commit = mini_sut_repo
    rd = tmp_path / "run"
    build_snapshot(repo, commit, mini_task, rd / "workspace")
    (rd / "run.json").write_text(json.dumps({"run_id": "r", "status": "harness_error", "first_prod_change": None}))
    score = _score(rd, mini_sut_repo, mini_task, env)
    assert score["status"] == "harness_error"
    assert (rd / "score.json").exists()


def test_lims_fetch_marks_contaminated():
    assert contaminated([_bash("git clone https://github.com/ChuuuDwarf/Cloud-Native-Development-Project.git")])
    assert contaminated([_bash("curl -s https://raw.githubusercontent.com/ChuuuDwarf/x/main/a.py")])
    assert not contaminated([_bash("cd backend && python -m pytest -q")])
    assert not contaminated([])


def test_rescore_is_byte_identical(run_dir, mini_sut_repo, mini_task, env):
    _score(run_dir, mini_sut_repo, mini_task, env)
    first = (run_dir / "score.json").read_bytes()
    _score(run_dir, mini_sut_repo, mini_task, env)
    assert (run_dir / "score.json").read_bytes() == first


def test_score_ignores_completion_claim(run_dir, mini_sut_repo, mini_task, env):
    before = _score(run_dir, mini_sut_repo, mini_task, env)
    run = json.loads((run_dir / "run.json").read_text())
    run["completion_claim"] = "I wrote 50 excellent tests and everything passes."
    (run_dir / "run.json").write_text(json.dumps(run))
    assert _score(run_dir, mini_sut_repo, mini_task, env) == before


def test_pytest_without_testlog_is_flagged_unmeasured(run_dir, mini_sut_repo, mini_task, env):
    """Review Important 4: the agent ran pytest but nothing was logged -> adherence cannot be judged."""
    (run_dir / "testlog.jsonl").write_text("")
    score = _score(run_dir, mini_sut_repo, mini_task, env)
    assert score["adherence"]["followed"] is False
    assert score["adherence"]["unmeasured"] is True


def test_contamination_found_in_subagent_transcripts(tmp_path):
    """Review Important 7: subagent tool calls live in the copied transcripts, not only in the stream."""
    from bench.scoring.score import contaminated_transcripts

    t = tmp_path / "transcripts/-work/s-1/subagents"
    t.mkdir(parents=True)
    (t / "agent-1.jsonl").write_text(json.dumps({"message": {"content": [{"type": "tool_use", "name": "Bash",
        "input": {"command": "git clone https://github.com/ChuuuDwarf/Cloud-Native-Development-Project"}}]}}) + "\n")
    assert contaminated_transcripts(tmp_path / "transcripts") is True
    (t / "agent-1.jsonl").write_text(json.dumps({"message": {"content": [
        {"type": "text", "text": "see github.com/ChuuuDwarf/Cloud-Native-Development-Project"}]}}) + "\n")
    assert contaminated_transcripts(tmp_path / "transcripts") is False
    assert contaminated_transcripts(tmp_path / "missing") is False
