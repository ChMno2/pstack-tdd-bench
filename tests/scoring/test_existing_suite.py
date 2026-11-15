from pathlib import Path

import pytest

from bench.scoring.existing_suite import existing_tests, increment, measure_existing_suite, regression, restore_tests
from bench.scoring.quality import coverage_detail, mutation_detail
from bench.scoring.testdiff import scoring_env
from bench.task.snapshot import build_reference
from tests.scoring.conftest import write

EXISTING = ["tests/test_calc.py::test_add"]
ADD_ONLY = "from app.calc import add\n\n\ndef test_add_again():\n    assert add(1, 1) == 2\n"
ADDS_IS_EVEN = ADD_ONLY + "\n\ndef test_two():\n    assert is_even(2)\n    assert not is_even(3)\n"
ADDS_IS_EVEN = ADDS_IS_EVEN.replace("import add\n", "import add, is_even\n")


@pytest.fixture
def reference(trees, mini_task, tmp_path: Path) -> Path:
    snapshot, _ = trees
    return build_reference(snapshot, mini_task, tmp_path / "reference")


def test_existing_tests_come_from_the_snapshot(trees, mini_task, env):
    snapshot, final = trees
    write(final, "backend/tests/test_new.py", ADD_ONLY)
    assert existing_tests(snapshot, mini_task, scoring_env(env)) == EXISTING


def test_restore_tests_keeps_final_code_with_the_original_tests(trees, mini_task, tmp_path: Path):
    snapshot, final = trees
    write(final, "backend/app/calc.py", "BROKEN = 1\n")
    write(final, "backend/tests/test_calc.py", "def test_add():\n    assert True\n")
    write(final, "backend/tests/conftest.py", "x = 1\n")
    out = restore_tests(snapshot, final, mini_task, tmp_path / "out")
    assert (out / "backend/app/calc.py").read_text() == "BROKEN = 1\n"
    assert (out / "backend/tests/test_calc.py").read_text() == (snapshot / "backend/tests/test_calc.py").read_text()
    assert not (out / "backend/tests/conftest.py").exists()


def test_regression_flags_an_existing_test_the_change_broke(trees, reference, mini_task, env):
    """The agent's code is judged by the snapshot's tests, even if it weakened them."""
    snapshot, final = trees
    calc = final / "backend/app/calc.py"
    calc.write_text(calc.read_text().replace("a + b", "a - b").replace("n % 2 == 1", "n % 2 == 0"))
    write(final, "backend/tests/test_calc.py", "from app.calc import add\n\n\ndef test_add():\n    assert add(2, 3)\n")
    result = regression(snapshot, reference, final, mini_task, EXISTING, scoring_env(env))
    assert result == {"existing": 1, "failing": EXISTING, "already_failing": []}


def test_regression_is_empty_for_a_clean_fix(trees, reference, mini_task, env):
    snapshot, final = trees
    calc = final / "backend/app/calc.py"
    calc.write_text(calc.read_text().replace("n % 2 == 1", "n % 2 == 0"))
    assert regression(snapshot, reference, final, mini_task, EXISTING, scoring_env(env)) == {
        "existing": 1, "failing": [], "already_failing": []}


def test_a_test_already_failing_on_the_reference_is_not_a_regression(trees, mini_task, env, tmp_path: Path):
    snapshot, final = trees
    old = "from app.calc import is_even\n\n\ndef test_three_is_even():\n    assert is_even(3)\n"
    write(snapshot, "backend/tests/test_old.py", old)
    write(final, "backend/tests/test_old.py", old)
    reference = build_reference(snapshot, mini_task, tmp_path / "reference")
    existing = existing_tests(snapshot, mini_task, scoring_env(env))
    result = regression(snapshot, reference, final, mini_task, existing, scoring_env(env))
    assert result == {"existing": 2, "failing": [], "already_failing": ["tests/test_old.py::test_three_is_even"]}


def test_existing_suite_is_measured_on_the_reference(trees, reference, mini_task, env):
    snapshot, _ = trees
    base = measure_existing_suite(snapshot, reference, mini_task, EXISTING, scoring_env(env))
    assert base.outcomes == {"tests/test_calc.py::test_add": "passed"}
    summary = base.summary()
    assert summary["tests"] == 1
    assert 0.0 < summary["coverage"]["line"] < 1.0
    assert summary["mutation"]["ok"] is True
    assert 0 < summary["mutation"]["killed"] < summary["mutation"]["total"]


def test_increment_counts_only_what_the_new_tests_add(trees, reference, mini_task, env):
    snapshot, final = trees
    senv = scoring_env(env)
    base = measure_existing_suite(snapshot, reference, mini_task, EXISTING, senv)
    write(final, "backend/tests/test_new.py", ADDS_IS_EVEN)
    valid = ["tests/test_new.py::test_add_again", "tests/test_new.py::test_two"]
    _, data = coverage_detail(reference, final, mini_task, valid, senv)
    _, killed = mutation_detail(reference, final, mini_task, valid, 2, senv)
    inc = increment(base, data, killed)
    assert inc["coverage"]["new_lines"] == 1  # the body of is_even; add was already covered
    assert inc["coverage"]["line"] == pytest.approx(1 / 6)
    assert inc["mutation"]["newly_killed"] == len(killed - base.killed) > 0
    assert inc["mutation"]["combined_score"] == pytest.approx(len(base.killed | killed) / base.mutation["total"])


def test_tests_that_repeat_the_existing_suite_add_nothing(trees, reference, mini_task, env):
    snapshot, final = trees
    senv = scoring_env(env)
    base = measure_existing_suite(snapshot, reference, mini_task, EXISTING, senv)
    write(final, "backend/tests/test_new.py", ADD_ONLY)
    valid = ["tests/test_new.py::test_add_again"]
    _, data = coverage_detail(reference, final, mini_task, valid, senv)
    _, killed = mutation_detail(reference, final, mini_task, valid, 1, senv)
    inc = increment(base, data, killed)
    assert inc["coverage"]["new_lines"] == 0 and inc["coverage"]["line"] == 0.0
    assert inc["mutation"]["newly_killed"] == 0


def test_no_valid_tests_means_no_increment(trees, reference, mini_task, env):
    snapshot, final = trees
    senv = scoring_env(env)
    base = measure_existing_suite(snapshot, reference, mini_task, EXISTING, senv)
    _, data = coverage_detail(reference, final, mini_task, [], senv)
    _, killed = mutation_detail(reference, final, mini_task, [], 0, senv)
    inc = increment(base, data, killed)
    assert inc["coverage"]["new_lines"] == 0 and inc["mutation"]["newly_killed"] == 0
    assert inc["mutation"]["combined_score"] == pytest.approx(base.mutation["score"])
