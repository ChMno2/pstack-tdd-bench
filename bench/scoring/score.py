"""Aggregate every scoring step for one run into a deterministic score.json."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path

from bench.pins import LIMS_COMMIT
from bench.scoring.adherence import adherence, load_testlog
from bench.scoring.quality import coverage, mutation, planted
from bench.scoring.redgreen import green_check, red_check
from bench.scoring.testdiff import diff_tests, scoring_env
from bench.snapshot import build_reference, build_snapshot
from bench.task import Task
from bench.trajectory import Event, read_jsonl

CONTAMINATION_MARKERS = ("github.com/ChuuuDwarf", "githubusercontent.com/ChuuuDwarf",
                         "Cloud-Native-Development-Project", "git clone")


def contaminated(events: Sequence[Event]) -> bool:
    """True if any tool call looks like it fetched the public LIMS source (the answer to bug-fix tasks)."""
    for e in events:
        if e.kind == "tool_call":
            blob = json.dumps(e.data.get("input"), ensure_ascii=False)
            if any(marker in blob for marker in CONTAMINATION_MARKERS):
                return True
    return False


def score_run(run_dir: Path, task: Task, *, sut_repo: Path, env: Mapping[str, str], commit: str = LIMS_COMMIT) -> dict:
    run_dir = Path(run_dir)
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    trajectory = run_dir / "trajectory.jsonl"
    events = read_jsonl(trajectory) if trajectory.exists() else []
    testlog = load_testlog(run_dir / "testlog.jsonl")
    final = run_dir / "workspace"
    senv = scoring_env(env)
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = build_snapshot(Path(sut_repo), commit, task, Path(tmp) / "snapshot")
        reference = build_reference(snapshot, task, Path(tmp) / "reference")
        diff = diff_tests(snapshot, final, task, senv)
        red = red_check(snapshot, final, task, diff.added, senv)
        green = green_check(reference, final, task, diff.added, senv)
        score = {
            "run_id": run.get("run_id"),
            "status": run.get("status"),
            "testless": not diff.added,
            "tests": asdict(diff),
            "red": asdict(red),
            "green": asdict(green),
            "adherence": asdict(adherence(testlog, set(diff.added), run.get("first_prod_change"))),
            "coverage": coverage(reference, final, task, green.valid, senv),
            "mutation": mutation(reference, final, task, green.valid, len(diff.added), senv, log_dir=run_dir / "scoring"),
            "planted": planted(reference, final, task, green.valid, senv),
            "contaminated": contaminated(events),
            "cost": {key: run.get(key) for key in ("usage_by_agent", "totals", "auto_replies")},
        }
    (run_dir / "score.json").write_text(json.dumps(score, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                                        encoding="utf-8")
    return score
