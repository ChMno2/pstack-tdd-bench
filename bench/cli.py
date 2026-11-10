"""bench run / bench score."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from bench.conditions import CONDITIONS
from bench.pins import LIMS_COMMIT, REPO_ROOT
from bench.runner import RunSpec, run
from bench.scoring.score import score_run
from bench.snapshot import build_snapshot
from bench.task import load_task
from bench.task_check import check_task


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--task", required=True, type=Path)
    p.add_argument("--sut-repo", type=Path, default=REPO_ROOT / "sut/lims")
    p.add_argument("--commit", default=LIMS_COMMIT)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bench")
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="run one task under one condition once")
    _common(r)
    r.add_argument("--condition", required=True, choices=sorted(CONDITIONS))
    r.add_argument("--rep", required=True, type=int)
    r.add_argument("--out", required=True, type=Path)
    r.add_argument("--plugin-dir", type=Path, default=REPO_ROOT / "vendor/pstack")
    r.add_argument("--home", type=Path, default=Path(os.path.expanduser("~")))
    r.add_argument("--claude-bin", default="claude")
    r.add_argument("--timeout", type=int, default=5400)
    r.add_argument("--as-user")
    s = sub.add_parser("score", help="score a finished run directory")
    s.add_argument("run_dir", type=Path)
    _common(s)
    c = sub.add_parser("check-task", help="check that a task's patches apply to the pinned SUT")
    _common(c)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    task = load_task(args.task)
    if args.command == "check-task":
        problems = check_task(task, sut_repo=args.sut_repo, commit=args.commit)
        for problem in problems:
            print(f"PROBLEM: {problem}")
        if problems:
            return 1
        print(f"OK: {task.id}")
        return 0
    if args.command == "run":
        cond = CONDITIONS[args.condition]
        run_dir = args.out / f"{task.id}-{cond.id}-r{args.rep}"
        if run_dir.exists():
            print(f"refusing to overwrite existing run directory {run_dir}", file=sys.stderr)
            return 2
        workspace = build_snapshot(args.sut_repo, args.commit, task, run_dir / "workspace")
        spec = RunSpec(task=task, condition=cond, rep=args.rep, run_dir=run_dir, workspace=workspace,
                       plugin_dir=args.plugin_dir, home=args.home, timeout_s=args.timeout,
                       claude_bin=args.claude_bin, as_user=args.as_user)
        result = run(spec, os.environ)
        print(f"{run_dir} status={result['status']}")
        return 0
    score_run(args.run_dir, task, sut_repo=args.sut_repo, env=os.environ, commit=args.commit)
    print(args.run_dir / "score.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
