from pathlib import Path

from bench.scoring.testdiff import changed_test_files, collect_nodeids, diff_tests, scoring_env
from tests.scoring.conftest import write

CALC_TEST = "tests/test_calc.py"
NEW_TEST = "from app.calc import is_even\n\n\ndef test_is_even_two():\n    assert is_even(2)\n"


def test_collect_nodeids(trees, mini_task, env):
    snapshot, _ = trees
    assert collect_nodeids(snapshot, mini_task, scoring_env(env)) == {"tests/test_calc.py::test_add"}


def test_added_test_in_new_file(trees, mini_task, env):
    snapshot, final = trees
    write(final, "backend/tests/test_new.py", NEW_TEST)
    diff = diff_tests(snapshot, final, mini_task, scoring_env(env))
    assert diff.added == ["tests/test_new.py::test_is_even_two"]
    assert diff.removed == [] and diff.modified == []


def test_added_test_in_existing_file_counts_as_added(trees, mini_task, env):
    snapshot, final = trees
    path = final / "backend" / CALC_TEST
    path.write_text(path.read_text() + "\n\n" + NEW_TEST.replace("from app.calc import is_even\n", "from app.calc import is_even\n"))
    diff = diff_tests(snapshot, final, mini_task, scoring_env(env))
    assert diff.added == ["tests/test_calc.py::test_is_even_two"]
    assert diff.modified == []


def test_removed_test_detected(trees, mini_task, env):
    snapshot, final = trees
    write(final, "backend/" + CALC_TEST, "def test_other():\n    assert True\n")
    diff = diff_tests(snapshot, final, mini_task, scoring_env(env))
    assert diff.removed == ["tests/test_calc.py::test_add"]
    assert diff.added == ["tests/test_calc.py::test_other"]


def test_modified_assertion_detected(trees, mini_task, env):
    snapshot, final = trees
    path = final / "backend" / CALC_TEST
    path.write_text(path.read_text().replace("assert add(2, 3) == 5", "assert add(2, 3) > 0"))
    assert diff_tests(snapshot, final, mini_task, scoring_env(env)).modified == ["tests/test_calc.py::test_add"]


def test_formatting_only_change_not_modified(trees, mini_task, env):
    snapshot, final = trees
    path = final / "backend" / CALC_TEST
    path.write_text(path.read_text().replace("    assert", "    # checks addition\n\n    assert"))
    assert diff_tests(snapshot, final, mini_task, scoring_env(env)).modified == []


def test_changed_test_files_lists_new_and_edited(trees, mini_task):
    snapshot, final = trees
    write(final, "backend/tests/test_new.py", NEW_TEST)
    path = final / "backend" / CALC_TEST
    path.write_text(path.read_text() + "\n")
    write(final, "backend/app/calc.py", "x = 1\n")
    assert changed_test_files(snapshot, final, mini_task) == [Path("backend/tests/test_calc.py"), Path("backend/tests/test_new.py")]


def test_scoring_env_pins_and_strips(env):
    out = scoring_env({**env, "BENCH_TESTLOG": "/tmp/x", "TZ": "Asia/Taipei"})
    assert "BENCH_TESTLOG" not in out
    assert out["TZ"] == "UTC" and out["PYTHONHASHSEED"] == "0"


def test_changed_test_files_includes_support_files(trees, mini_task):
    """Review Important 3: helper modules and data under the test tree travel with the tests."""
    snapshot, final = trees
    write(final, "backend/tests/helpers.py", "def two():\n    return 2\n")
    write(final, "backend/tests/data/case.json", "{}\n")
    write(final, "backend/tests/__pycache__/x.cpython-312.pyc", "junk")
    assert changed_test_files(snapshot, final, mini_task) == [
        Path("backend/tests/data/case.json"), Path("backend/tests/helpers.py")]
