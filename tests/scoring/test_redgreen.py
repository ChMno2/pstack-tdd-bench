from pathlib import Path

from bench.scoring.redgreen import green_check, red_check, run_nodeids, transplant
from bench.scoring.testdiff import scoring_env
from bench.snapshot import build_reference
from tests.scoring.conftest import write

PASS_ON_SNAPSHOT = "from app.calc import add\n\n\ndef test_add_ones():\n    assert add(1, 1) == 2\n"
FAIL_ON_SNAPSHOT = "from app.calc import is_even\n\n\ndef test_is_even_two():\n    assert is_even(2)\n"


def test_transplant_overrides_files(trees, tmp_path: Path):
    snapshot, final = trees
    write(final, "backend/tests/test_new.py", PASS_ON_SNAPSHOT)
    write(final, "backend/app/calc.py", "BROKEN = True\n")
    out = transplant([Path("backend/tests/test_new.py")], final, snapshot, tmp_path / "out")
    assert (out / "backend/tests/test_new.py").read_text() == PASS_ON_SNAPSHOT
    assert "def add" in (out / "backend/app/calc.py").read_text()
    assert not (out / ".git").exists()


def test_run_nodeids_outcomes(trees, mini_task, env):
    snapshot, _ = trees
    write(snapshot, "backend/tests/test_mix.py", PASS_ON_SNAPSHOT + "\n\n" + FAIL_ON_SNAPSHOT.split("\n\n\n")[1])
    out = run_nodeids(snapshot, mini_task, ["tests/test_mix.py::test_add_ones", "tests/test_mix.py::test_is_even_two",
                                            "tests/test_missing.py::test_x"], scoring_env(env))
    assert out == {"tests/test_mix.py::test_add_ones": "passed", "tests/test_mix.py::test_is_even_two": "failed",
                   "tests/test_missing.py::test_x": "error"}


def test_red_when_new_test_fails_on_snapshot(trees, mini_task, env):
    snapshot, final = trees
    write(final, "backend/tests/test_new.py", FAIL_ON_SNAPSHOT)
    write(final, "backend/app/calc.py", (final / "backend/app/calc.py").read_text().replace("== 1", "== 0"))
    result = red_check(snapshot, final, mini_task, ["tests/test_new.py::test_is_even_two"], scoring_env(env))
    assert result.red is True
    assert result.outcomes == {"tests/test_new.py::test_is_even_two": "failed"}


def test_not_red_when_all_pass(trees, mini_task, env):
    snapshot, final = trees
    write(final, "backend/tests/test_new.py", PASS_ON_SNAPSHOT)
    assert red_check(snapshot, final, mini_task, ["tests/test_new.py::test_add_ones"], scoring_env(env)).red is False


def test_no_added_tests_is_not_red(trees, mini_task, env):
    snapshot, final = trees
    result = red_check(snapshot, final, mini_task, [], scoring_env(env))
    assert result.red is False and result.outcomes == {}


def test_collection_error_counts_as_red(trees, mini_task, env):
    snapshot, final = trees
    write(final, "backend/app/newmod.py", "def f():\n    return 1\n")
    write(final, "backend/tests/test_feat.py", "from app.newmod import f\n\n\ndef test_f():\n    assert f() == 1\n")
    result = red_check(snapshot, final, mini_task, ["tests/test_feat.py::test_f"], scoring_env(env))
    assert result.red is True
    assert result.outcomes == {"tests/test_feat.py::test_f": "error"}


def test_green_valid_and_failing_split(trees, mini_task, env, tmp_path: Path):
    snapshot, final = trees
    reference = build_reference(snapshot, mini_task, tmp_path / "reference")
    write(final, "backend/tests/test_new.py",
          FAIL_ON_SNAPSHOT + "\n\ndef test_wrong():\n    assert is_even(3)\n")
    result = green_check(reference, final, mini_task,
                         ["tests/test_new.py::test_is_even_two", "tests/test_new.py::test_wrong"], scoring_env(env))
    assert result.valid == ["tests/test_new.py::test_is_even_two"]
    assert result.failing == ["tests/test_new.py::test_wrong"]
    assert result.flaky == []


def test_flaky_test_detected(trees, mini_task, env, tmp_path: Path):
    snapshot, final = trees
    reference = build_reference(snapshot, mini_task, tmp_path / "reference")
    write(final, "backend/tests/test_flaky.py",
          "from pathlib import Path\n\n\ndef test_flaky():\n    p = Path(__file__).with_name('count.txt')\n"
          "    n = int(p.read_text()) if p.exists() else 0\n    p.write_text(str(n + 1))\n    assert n % 2 == 0\n")
    result = green_check(reference, final, mini_task, ["tests/test_flaky.py::test_flaky"], scoring_env(env))
    assert result.flaky == ["tests/test_flaky.py::test_flaky"]
    assert result.valid == [] and result.failing == []


HELPER_TEST = "from app.calc import is_even\nfrom tests.helpers import two\n\n\ndef test_two_is_even():\n    assert is_even(two())\n"


def test_tests_using_a_new_helper_module_score_normally(trees, mini_task, env, tmp_path: Path):
    """Review Important 3: a valid test that imports a new helper must not become a false red / failing test."""
    snapshot, final = trees
    reference = build_reference(snapshot, mini_task, tmp_path / "reference")
    write(final, "backend/tests/helpers.py", "def two():\n    return 2\n")
    write(final, "backend/tests/test_helper.py", HELPER_TEST)
    ids = ["tests/test_helper.py::test_two_is_even"]
    assert red_check(snapshot, final, mini_task, ids, scoring_env(env)).outcomes == {ids[0]: "failed"}
    assert green_check(reference, final, mini_task, ids, scoring_env(env)).valid == ids
