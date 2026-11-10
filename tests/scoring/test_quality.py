from pathlib import Path

import pytest

from bench.scoring.quality import coverage, mutation, planted
from bench.scoring.testdiff import scoring_env
from bench.snapshot import build_reference
from tests.scoring.conftest import write

STRONG = (
    "from app.calc import add, clamp, is_even\n\n\n"
    "def test_add():\n    assert add(2, 3) == 5\n    assert add(-1, 1) == 0\n\n\n"
    "def test_clamp():\n    assert clamp(10, 0, 5) == 5\n    assert clamp(-3, 0, 5) == 0\n    assert clamp(3, 0, 5) == 3\n\n\n"
    "def test_is_even():\n    assert is_even(2)\n    assert not is_even(3)\n"
)
STRONG_IDS = ["tests/test_new.py::test_add", "tests/test_new.py::test_clamp", "tests/test_new.py::test_is_even"]
WEAK = (
    "from app.calc import add, clamp, is_even\n\n\n"
    "def test_calls():\n    add(1, 2)\n    clamp(1, 0, 5)\n    is_even(4)\n"
)
WEAK_IDS = ["tests/test_new.py::test_calls"]


@pytest.fixture
def reference(trees, mini_task, tmp_path: Path) -> Path:
    snapshot, _ = trees
    return build_reference(snapshot, mini_task, tmp_path / "reference")


def test_coverage_counts_only_task_modules(trees, reference, mini_task, env):
    _, final = trees
    write(final, "backend/tests/test_new.py", "from app.calc import is_even\n\n\ndef test_two():\n    assert is_even(2)\n")
    ids = ["tests/test_new.py::test_two"]
    before = coverage(reference, final, mini_task, ids, scoring_env(env))
    write(reference, "backend/app/other.py", "def f(x):\n    if x:\n        return 1\n    return 2\n")
    after = coverage(reference, final, mini_task, ids, scoring_env(env))
    assert 0.0 < before["line"] < 1.0
    assert before == after


def test_empty_valid_gives_zero(trees, reference, mini_task, env):
    _, final = trees
    assert coverage(reference, final, mini_task, [], scoring_env(env)) == {"ok": True, "line": 0.0, "branch": 0.0}
    assert mutation(reference, final, mini_task, [], 0, scoring_env(env)) == {
        "ok": True, "error": None, "killed": 0, "total": 0, "score": 0.0, "per_test": 0.0}
    assert planted(reference, final, mini_task, [], scoring_env(env)) == {"off_by_one": False}


def test_mutation_kills_with_strong_test(trees, reference, mini_task, env):
    _, final = trees
    write(final, "backend/tests/test_new.py", STRONG)
    result = mutation(reference, final, mini_task, STRONG_IDS, 3, scoring_env(env))
    assert result["total"] > 0
    assert result["killed"] > 0
    assert result["score"] == pytest.approx(result["killed"] / result["total"])
    assert result["per_test"] == pytest.approx(result["killed"] / 3)
    assert result["score"] > 0.5


def test_weak_test_kills_less(trees, reference, mini_task, env):
    _, final = trees
    write(final, "backend/tests/test_new.py", STRONG)
    strong = mutation(reference, final, mini_task, STRONG_IDS, 3, scoring_env(env))
    write(final, "backend/tests/test_new.py", WEAK)
    weak = mutation(reference, final, mini_task, WEAK_IDS, 1, scoring_env(env))
    assert weak["total"] == strong["total"]
    assert weak["score"] < strong["score"]


def test_planted_bug_detected(trees, reference, mini_task, env):
    _, final = trees
    write(final, "backend/tests/test_new.py", STRONG)
    assert planted(reference, final, mini_task, STRONG_IDS, scoring_env(env)) == {"off_by_one": True}
    write(final, "backend/tests/test_new.py", "from app.calc import is_even\n\n\ndef test_two():\n    assert is_even(2)\n")
    assert planted(reference, final, mini_task, ["tests/test_new.py::test_two"], scoring_env(env)) == {"off_by_one": False}


def test_mutation_writes_logs_when_asked(trees, reference, mini_task, env, tmp_path: Path):
    _, final = trees
    write(final, "backend/tests/test_new.py", STRONG)
    logs = tmp_path / "scoring"
    mutation(reference, final, mini_task, STRONG_IDS, 3, scoring_env(env), log_dir=logs)
    text = (logs / "mutmut.log").read_text()
    assert "[mutmut run --max-children 1]" in text and "[mutmut results --all true]" in text
    assert "[setup.cfg]" in text and "only_mutate" in text


def test_percent_in_node_id_does_not_break_mutmut(trees, reference, mini_task, env):
    """Review Important 5: mutmut reads setup.cfg with ConfigParser interpolation, so '%' must be escaped."""
    _, final = trees
    write(final, "backend/tests/test_new.py",
          "import pytest\nfrom app.calc import is_even\n\n\n@pytest.mark.parametrize('n', [2, 4], ids=['50%', '100%'])\n"
          "def test_even(n):\n    assert is_even(n)\n    assert not is_even(n + 1)\n")
    ids = ["tests/test_new.py::test_even[50%]", "tests/test_new.py::test_even[100%]"]
    result = mutation(reference, final, mini_task, ids, 2, scoring_env(env))
    assert result["ok"] is True and result["killed"] > 0


def test_tool_failure_is_visible(trees, reference, mini_task, env):
    """Review Important 5: a crashed tool must not look like a measured zero."""
    from bench.task import Task

    _, final = trees
    write(final, "backend/tests/test_new.py", STRONG)
    broken = Task(**{**mini_task.__dict__, "modules": ("nope/missing.py",)})
    result = mutation(reference, final, broken, STRONG_IDS, 3, scoring_env(env))
    assert result["ok"] is False and result["error"]
    assert result["killed"] is None and result["score"] is None
    cov = coverage(reference, final, mini_task, ["tests/test_new.py::test_does_not_exist"], scoring_env(env))
    assert cov == {"ok": False, "line": None, "branch": None}
