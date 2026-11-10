import json
from pathlib import Path

import pytest


@pytest.fixture
def log_path(pytester, monkeypatch) -> Path:
    path = pytester.path / "testlog.jsonl"
    monkeypatch.setenv("BENCH_TESTLOG", str(path))
    return path


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_session_line_written(pytester, log_path):
    pytester.makepyfile(test_x="def test_ok():\n    assert True\n\ndef test_bad():\n    assert False\n")
    pytester.runpytest_subprocess()
    (line,) = _lines(log_path)
    assert line["results"] == {"test_x.py::test_ok": "passed", "test_x.py::test_bad": "failed"}
    assert line["exitstatus"] == 1
    assert line["ts_start"] <= line["ts_end"]
    assert line["collect_errors"] == []
    assert isinstance(line["args"], list)
    assert line["cwd"] == str(pytester.path)


def test_noop_without_env(pytester, monkeypatch):
    monkeypatch.delenv("BENCH_TESTLOG", raising=False)
    pytester.makepyfile(test_y="def test_ok():\n    assert True\n")
    pytester.runpytest_subprocess()
    assert not list(pytester.path.glob("*.jsonl"))


def test_collection_error_recorded(pytester, log_path):
    pytester.makepyfile(test_broken="import module_that_does_not_exist\n\ndef test_a():\n    pass\n")
    pytester.runpytest_subprocess()
    (line,) = _lines(log_path)
    assert line["collect_errors"] == ["test_broken.py"]
    assert line["results"] == {}


def test_setup_error_is_error(pytester, log_path):
    pytester.makepyfile(
        test_fx="import pytest\n\n@pytest.fixture\ndef boom():\n    raise RuntimeError('x')\n\n"
        "def test_uses_boom(boom):\n    pass\n"
    )
    pytester.runpytest_subprocess()
    (line,) = _lines(log_path)
    assert line["results"] == {"test_fx.py::test_uses_boom": "error"}


def test_two_sessions_append_two_lines(pytester, log_path):
    pytester.makepyfile(test_z="def test_ok():\n    assert True\n")
    pytester.runpytest_subprocess()
    pytester.runpytest_subprocess()
    assert len(_lines(log_path)) == 2
