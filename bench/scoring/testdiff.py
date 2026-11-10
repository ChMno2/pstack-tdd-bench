"""Which tests a run added, removed or changed, compared with the snapshot."""

from __future__ import annotations

import ast
import fnmatch
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from bench.pins import PYTHONHASHSEED, TZ
from bench.task import Task

TEST_FILE_PATTERNS = ("test_*.py", "*_test.py", "conftest.py")
PYTEST_ISOLATION = ("-p", "no:benchlog", "-p", "no:cacheprovider")


def scoring_env(base: Mapping[str, str]) -> dict[str, str]:
    env = {k: v for k, v in base.items() if k != "BENCH_TESTLOG"}
    env["TZ"] = TZ
    env["PYTHONHASHSEED"] = PYTHONHASHSEED
    return env


def collect_nodeids(tree: Path, task: Task, env: Mapping[str, str]) -> set[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *PYTEST_ISOLATION],
        cwd=Path(tree) / task.workdir, env=dict(env), capture_output=True, text=True,
    )
    return {line.strip() for line in proc.stdout.splitlines() if "::" in line and not line.startswith(("ERROR", " "))}


@dataclass
class TestDiff:
    __test__ = False  # not a pytest test class
    added: list[str]
    removed: list[str]
    modified: list[str]


def _function_dump(tree: Path, task: Task, nodeid: str) -> str | None:
    file_part, *names = nodeid.split("::")
    names = [re.sub(r"\[.*\]$", "", n) for n in names]
    path = Path(tree) / task.workdir / file_part
    try:
        node: ast.AST = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None
    for name in names:
        body = getattr(node, "body", [])
        match = next((n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                      and n.name == name), None)
        if match is None:
            return None
        node = match
    return ast.dump(node)


def diff_tests(snapshot: Path, final: Path, task: Task, env: Mapping[str, str]) -> TestDiff:
    before = collect_nodeids(snapshot, task, env)
    after = collect_nodeids(final, task, env)
    modified = []
    for nodeid in sorted(before & after):
        a, b = _function_dump(snapshot, task, nodeid), _function_dump(final, task, nodeid)
        if a is not None and b is not None and a != b:
            modified.append(nodeid)
    return TestDiff(added=sorted(after - before), removed=sorted(before - after), modified=modified)


def _is_test_file(path: Path) -> bool:
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in TEST_FILE_PATTERNS)


def changed_test_files(snapshot: Path, final: Path, task: Task) -> list[Path]:
    snapshot, final = Path(snapshot), Path(final)
    changed = []
    for path in (final / task.workdir).rglob("*.py"):
        rel = path.relative_to(final)
        if ".git" in rel.parts or not _is_test_file(path):
            continue
        original = snapshot / rel
        if not original.exists() or original.read_bytes() != path.read_bytes():
            changed.append(rel)
    return sorted(changed)
