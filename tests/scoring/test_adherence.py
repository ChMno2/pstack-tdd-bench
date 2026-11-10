from pathlib import Path

from bench.scoring.adherence import adherence, load_testlog

A = "tests/test_t.py::test_a"


def _session(ts_end: float, results: dict | None = None, collect_errors: list | None = None) -> dict:
    return {"ts_start": ts_end - 1, "ts_end": ts_end, "results": results or {}, "collect_errors": collect_errors or []}


def test_red_before_prod_change_is_followed():
    s = _session(10, {A: "failed"})
    result = adherence([s], {A}, 20.0)
    assert result.followed is True and result.sessions == 1 and result.evidence == s


def test_red_only_after_prod_change_is_not_followed():
    result = adherence([_session(30, {A: "failed"})], {A}, 20.0)
    assert result.followed is False and result.evidence is None


def test_passing_new_test_before_change_is_not_followed():
    assert adherence([_session(10, {A: "passed"})], {A}, 20.0).followed is False


def test_empty_testlog_is_not_followed():
    result = adherence([], {A}, 20.0)
    assert result.followed is False and result.sessions == 0


def test_no_prod_change_any_red_counts():
    assert adherence([_session(99, {A: "error"})], {A}, None).followed is True


def test_collection_error_of_new_test_file_counts():
    assert adherence([_session(10, collect_errors=["tests/test_t.py"])], {A}, 20.0).followed is True


def test_nodeid_with_rootdir_prefix_matches():
    assert adherence([_session(10, {"backend/" + A: "failed"})], {A}, 20.0).followed is True
    assert adherence([_session(10, collect_errors=["backend/tests/test_t.py"])], {A}, 20.0).followed is True


def test_missing_file_is_empty(tmp_path: Path):
    assert load_testlog(tmp_path / "nope.jsonl") == []


def test_bad_lines_skipped(tmp_path: Path):
    path = tmp_path / "log.jsonl"
    path.write_text('{"ts_end": 1, "results": {}}\nnot json\n\n{"ts_end": 2, "results": {}}\n')
    assert [s["ts_end"] for s in load_testlog(path)] == [1, 2]
