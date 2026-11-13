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
    env = {k: v for k, v in base.items() if k not in ("BENCH_TESTLOG", "PYTEST_PLUGINS")}
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


SUPPORT_DIR_PATTERNS = ("**/tests/**", "**/test/**")
SKIP_PARTS = {".git", "__pycache__", ".pytest_cache", "mutants"}


def _is_test_support(rel: Path) -> bool:
    """Test files plus everything under a tests/ directory (helpers, factories, __init__, data files)."""
    if any(fnmatch.fnmatch(rel.name, pattern) for pattern in TEST_FILE_PATTERNS):
        return True
    return any(fnmatch.fnmatch("/" + rel.as_posix(), pattern) for pattern in SUPPORT_DIR_PATTERNS)


def changed_test_files(snapshot: Path, final: Path, task: Task) -> list[Path]:
    """Added or changed test-support files (relative to the tree root) that scoring must carry onto other trees."""
    snapshot, final = Path(snapshot), Path(final)
    changed = []
    for path in (final / task.workdir).rglob("*"):
        rel = path.relative_to(final)
        if not path.is_file() or SKIP_PARTS & set(rel.parts) or path.suffix == ".pyc" or not _is_test_support(rel):
            continue
        original = snapshot / rel
        if not original.exists() or original.read_bytes() != path.read_bytes():
            changed.append(rel)
    return sorted(changed)
