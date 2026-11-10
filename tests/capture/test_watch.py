import time
from pathlib import Path

import pytest

from bench.capture.watch import ProdWatcher, first_change

INCLUDE = ("backend/app/**/*.py",)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / "backend/app/tests").mkdir(parents=True)
    (tmp_path / "backend/app/a.py").write_text("x = 1\n")
    (tmp_path / "backend/app/test_b.py").write_text("def test_b(): pass\n")
    (tmp_path / "backend/app/tests/test_c.py").write_text("def test_c(): pass\n")
    return tmp_path


def _watcher(root: Path) -> ProdWatcher:
    w = ProdWatcher(root, INCLUDE, interval=0.05)
    w.start()
    time.sleep(0.1)
    return w


def test_modified_file_recorded_once(tree: Path):
    w = _watcher(tree)
    before = time.time()
    (tree / "backend/app/a.py").write_text("x = 2\n")
    time.sleep(0.2)
    second = time.time()
    (tree / "backend/app/a.py").write_text("x = 3\n")
    time.sleep(0.2)
    log = w.stop()
    assert list(log) == ["backend/app/a.py"]
    assert before <= log["backend/app/a.py"] <= second


def test_new_and_deleted_files_recorded(tree: Path):
    w = _watcher(tree)
    (tree / "backend/app/new.py").write_text("y = 1\n")
    (tree / "backend/app/a.py").unlink()
    time.sleep(0.2)
    log = w.stop()
    assert set(log) == {"backend/app/new.py", "backend/app/a.py"}


def test_test_files_excluded(tree: Path):
    w = _watcher(tree)
    (tree / "backend/app/test_b.py").write_text("def test_b(): assert 1\n")
    (tree / "backend/app/tests/test_c.py").write_text("def test_c(): assert 1\n")
    time.sleep(0.2)
    assert w.stop() == {}


def test_change_in_last_interval_caught_by_stop(tree: Path):
    w = ProdWatcher(tree, INCLUDE, interval=5.0)
    w.start()
    (tree / "backend/app/a.py").write_text("x = 9\n")
    assert set(w.stop()) == {"backend/app/a.py"}


def test_no_change_returns_empty(tree: Path):
    w = _watcher(tree)
    assert w.stop() == {}


def test_first_change():
    assert first_change({}) is None
    assert first_change({"a": 5.0, "b": 3.0}) == 3.0
