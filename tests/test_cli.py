import json
from pathlib import Path

from bench.cli import main
from tests.test_runner import _fake_claude

FIXTURES = Path(__file__).parent / "fixtures"


def test_cli_run_then_score(tmp_path: Path, mini_sut_repo, monkeypatch, capsys):
    repo, commit = mini_sut_repo
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fake")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    common = ["--task", str(FIXTURES / "minitask"), "--sut-repo", str(repo), "--commit", commit]
    code = main(["run", *common, "--condition", "C1", "--rep", "2", "--out", str(tmp_path / "runs"),
                 "--claude-bin", _fake_claude(tmp_path, "ok"), "--plugin-dir", str(tmp_path / "pstack"),
                 "--home", str(tmp_path / "home")])
    assert code == 0
    run_dir = tmp_path / "runs" / "mini-C1-r2"
    assert json.loads((run_dir / "run.json").read_text())["status"] == "completed"
    assert (run_dir / "workspace/backend/app/calc.py").exists()
    assert str(run_dir) in capsys.readouterr().out

    assert main(["score", str(run_dir), *common]) == 0
    assert json.loads((run_dir / "score.json").read_text())["run_id"].startswith("mini-C1-r2-")


def test_cli_run_refuses_existing_run_dir(tmp_path: Path, mini_sut_repo):
    repo, commit = mini_sut_repo
    (tmp_path / "runs" / "mini-C1-r1").mkdir(parents=True)
    code = main(["run", "--task", str(FIXTURES / "minitask"), "--sut-repo", str(repo), "--commit", commit,
                 "--condition", "C1", "--rep", "1", "--out", str(tmp_path / "runs")])
    assert code == 2
