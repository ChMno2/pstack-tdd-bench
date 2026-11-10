from pathlib import Path

import pytest

from bench.conditions import (
    CONDITIONS,
    CredentialError,
    build_cli_args,
    build_env,
    render_prompt,
    write_pstack_models,
)
from bench.task import Task

PLUGIN = Path("/opt/pstack")
BASE = {"PATH": "/usr/bin", "CLAUDE_CODE_OAUTH_TOKEN": "tok", "SECRET_THING": "x", "TEST_DATABASE_URL": "pg://t"}


def test_c1_and_c2a_prompts_share_body(mini_task: Task):
    c1 = render_prompt(CONDITIONS["C1"], mini_task)
    c2a = render_prompt(CONDITIONS["C2a"], mini_task)
    assert c2a.endswith(c1)
    assert mini_task.description in c1
    assert mini_task.test_command in c1
    assert "Do not push" in c1


def test_c2a_bugfix_prefix(mini_task: Task):
    c2a = render_prompt(CONDITIONS["C2a"], mini_task)
    assert c2a.startswith("/pstack:poteto-mode Use the Bug fix playbook and the tdd skill.")


def test_c2a_feature_prefix(mini_task: Task):
    feature = Task(**{**mini_task.__dict__, "kind": "feature"})
    assert render_prompt(CONDITIONS["C2a"], feature).startswith("/pstack:poteto-mode Use the Feature playbook.")


def test_args_pin_model_and_disable_tools():
    args = build_cli_args(CONDITIONS["C1"], "do it", plugin_dir=PLUGIN)
    assert args[:3] == ["claude", "-p", "do it"]
    assert args[args.index("--model") + 1] == "claude-sonnet-5-5"
    assert args[args.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in args
    assert args[args.index("--permission-mode") + 1] == "bypassPermissions"
    assert args[args.index("--disallowedTools") + 1] == "WebFetch,WebSearch,AskUserQuestion"


def test_no_bare_flag():
    for cond in CONDITIONS.values():
        assert "--bare" not in build_cli_args(cond, "x", plugin_dir=PLUGIN, resume="s1")


def test_plugin_dir_only_for_pstack():
    assert "--plugin-dir" not in build_cli_args(CONDITIONS["C1"], "x", plugin_dir=PLUGIN)
    args = build_cli_args(CONDITIONS["C2a"], "x", plugin_dir=PLUGIN)
    assert args[args.index("--plugin-dir") + 1] == str(PLUGIN)


def test_resume_flag():
    args = build_cli_args(CONDITIONS["C1"], "go on", plugin_dir=PLUGIN, resume="sess-1", claude_bin="/x/claude")
    assert args[0] == "/x/claude"
    assert args[args.index("--resume") + 1] == "sess-1"


def test_both_credentials_rejected(tmp_path: Path):
    with pytest.raises(CredentialError):
        build_env({**BASE, "ANTHROPIC_API_KEY": "k"}, home=tmp_path)


def test_no_credential_rejected(tmp_path: Path):
    with pytest.raises(CredentialError):
        build_env({"PATH": "/usr/bin"}, home=tmp_path)


def test_env_drops_unlisted_vars_and_pins(tmp_path: Path):
    env = build_env(BASE, home=tmp_path)
    assert "SECRET_THING" not in env
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "tok"
    assert env["TEST_DATABASE_URL"] == "pg://t"
    assert env["HOME"] == str(tmp_path)
    assert env["DISABLE_UPDATES"] == "1"
    assert env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"
    assert env["CLAUDE_CODE_SUBAGENT_MODEL"] == "claude-sonnet-5-5"
    assert env["CLAUDE_CODE_SUBAGENT_MODEL_FORCE"] == "1"
    assert env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "claude-sonnet-5-5"
    assert env["TZ"] == "UTC" and env["PYTHONHASHSEED"] == "0"
    assert env["PYTEST_PLUGINS"] == "benchlog"
    assert (Path(env["PYTHONPATH"]) / "benchlog.py").is_file()


def test_pstack_models_all_roles_same_model(tmp_path: Path):
    """Review Important 8: pstack's Claude Code adapter expects `<model> <effort>` values (e.g. `opus xhigh`)."""
    path = write_pstack_models(tmp_path)
    assert path == tmp_path / ".claude/rules/pstack-models.md"
    text = path.read_text()
    assert not text.startswith("---")
    assert "# budget: large (xhigh)" in text
    role_lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert len(role_lines) == 17
    for line in role_lines:
        _, value = line.split(": ", 1)
        assert {v.strip() for v in value.split(",")} == {"sonnet xhigh"}
    assert "arena runners: sonnet xhigh, sonnet xhigh" in text
