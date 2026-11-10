"""Experiment conditions: prompt, CLI arguments and environment for one harness session."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from bench.capture.pytest_plugin import plugin_env
from bench.pins import DISALLOWED_TOOLS, MODEL_ID, PSTACK_EFFORT, PSTACK_MODEL, PYTHONHASHSEED, TZ
from bench.task import Task

PROMPTS = Path(__file__).parent / "prompts"
CREDENTIALS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY")
PASSTHROUGH = ("PATH", "LANG", "BENCH_TESTLOG", "TEST_DATABASE_URL", "DATABASE_URL", "REDIS_URL", "JWT_SECRET", "ENV")

# Role lines of pstack's setup-pstack rule (vendor/pstack/skills/setup-pstack/SKILL.md, step 5).
# Value = number of entries, so panel fan-out stays the same as pstack's defaults.
PSTACK_ROLES = {
    "feature, refactoring": 1, "bug-fix": 1, "perf-issue": 1, "hillclimb": 1,
    "judgment and prose": 1, "hardest tasks": 1, "how explorer": 1, "how explainer": 1,
    "why investigators": 1, "why synthesizer": 1, "reflect tooling": 1,
    "reflect judgment, divergent, synthesizer": 1, "arena runners": 2, "arena cross-judge pool": 2,
    "swarm workers": 1, "architect runners": 2, "interrogate reviewers": 2,
}


class CredentialError(Exception):
    pass


@dataclass(frozen=True)
class Condition:
    id: Literal["C1", "C2a"]
    use_pstack: bool


CONDITIONS: dict[str, Condition] = {
    "C1": Condition("C1", use_pstack=False),
    "C2a": Condition("C2a", use_pstack=True),
}


def render_prompt(cond: Condition, task: Task) -> str:
    body = (PROMPTS / "common.md").read_text(encoding="utf-8").format(
        description=task.description, test_command=task.test_command
    )
    if not cond.use_pstack:
        return body
    prefix = (PROMPTS / f"C2a_{task.kind}.md").read_text(encoding="utf-8").strip()
    return f"{prefix}\n\n{body}"


def build_cli_args(
    cond: Condition, prompt: str, *, plugin_dir: Path, resume: str | None = None, claude_bin: str = "claude"
) -> list[str]:
    args = [
        claude_bin, "-p", prompt,
        "--output-format", "stream-json", "--verbose", "--forward-subagent-text",
        "--model", MODEL_ID,
        "--permission-mode", "bypassPermissions",
        "--disallowedTools", ",".join(DISALLOWED_TOOLS),
        "--strict-mcp-config",
    ]
    if cond.use_pstack:
        args += ["--plugin-dir", str(plugin_dir)]
    if resume:
        args += ["--resume", resume]
    return args


def build_env(base: Mapping[str, str], *, home: Path) -> dict[str, str]:
    present = [name for name in CREDENTIALS if base.get(name)]
    if len(present) != 1:
        raise CredentialError(f"exactly one of {CREDENTIALS} must be set, found {present or 'none'}")
    env = {name: base[name] for name in PASSTHROUGH if name in base}
    env[present[0]] = base[present[0]]
    env.update({
        "HOME": str(home),
        "TZ": TZ,
        "PYTHONHASHSEED": PYTHONHASHSEED,
        "DISABLE_UPDATES": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "CLAUDE_CODE_SUBAGENT_MODEL": MODEL_ID,
        "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": MODEL_ID,
        **plugin_env(),
    })
    return env


def write_pstack_models(home: Path, model: str = PSTACK_MODEL, effort: str = PSTACK_EFFORT) -> Path:
    """Single-model pstack rule in the format pstack's Claude Code adapter specifies: `<model> <effort>` per entry."""
    path = Path(home) / ".claude/rules/pstack-models.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    value = f"{model} {effort}"
    lines = [
        "# pstack model configuration. One line per role. Delete a line to fall back to the skill default.",
        "# Written by pstack-tdd-bench for the single-model condition: every role runs on the same model.",
        f"# budget: large ({effort})",
    ]
    lines += [f"{role}: {', '.join([value] * count)}" for role, count in PSTACK_ROLES.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
