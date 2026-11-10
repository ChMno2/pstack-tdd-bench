"""Runner: one Run = one task under one condition, one repetition, possibly several resumed sessions."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from bench.conditions import Condition, build_cli_args, build_env, render_prompt, write_pstack_models
from bench.fingerprint import collect
from bench.pins import AUTO_REPLY, MAX_AUTO_REPLIES, MODEL_ID
from bench.task import Task
from bench.trajectory import Event, convert_stream, final_text, session_id, totals, usage_by_agent, write_jsonl
from bench.watch import ProdWatcher, first_change


def needs_decision(text: str) -> bool:
    paragraphs = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
    return bool(paragraphs) and paragraphs[-1].endswith(("?", "？"))


@dataclass
class RunSpec:
    task: Task
    condition: Condition
    rep: int
    run_dir: Path
    workspace: Path
    plugin_dir: Path
    home: Path
    timeout_s: int = 5400
    claude_bin: str = "claude"
    as_user: str | None = None


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _chown_tree(path: Path, user: str) -> None:
    shutil.chown(path, user=user, group=user)
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            shutil.chown(os.path.join(root, name), user=user, group=user, follow_symlinks=False)


def _prepare(spec: RunSpec, testlog: Path) -> None:
    (spec.run_dir / "raw").mkdir(parents=True, exist_ok=True)
    spec.home.mkdir(parents=True, exist_ok=True)
    testlog.touch()
    if spec.condition.use_pstack:
        write_pstack_models(spec.home, MODEL_ID)
    if spec.as_user:
        _chown_tree(spec.workspace, spec.as_user)
        _chown_tree(spec.home, spec.as_user)
        shutil.chown(testlog, user=spec.as_user, group=spec.as_user)


def run(spec: RunSpec, base_env: Mapping[str, str]) -> dict:
    started_at = _now()
    started = time.monotonic()
    run_id = f"{spec.task.id}-{spec.condition.id}-r{spec.rep}-{started_at.replace('-', '').replace(':', '')}"
    testlog = spec.run_dir / "testlog.jsonl"
    _prepare(spec, testlog)
    env = build_env({**base_env, "BENCH_TESTLOG": str(testlog)}, home=spec.home)
    fingerprint = collect(spec.task, claude_bin=spec.claude_bin, env=base_env)

    events: list[Event] = []
    exit_codes: list[int] = []
    auto_replies = 0
    status = "completed"
    message = render_prompt(spec.condition, spec.task)
    resume: str | None = None

    watcher = ProdWatcher(spec.workspace, spec.task.prod_globs)
    watcher.start()
    try:
        for n in range(1, MAX_AUTO_REPLIES + 2):
            args = build_cli_args(spec.condition, message, plugin_dir=spec.plugin_dir, resume=resume,
                                  claude_bin=spec.claude_bin)
            if spec.as_user:
                args = ["runuser", "-u", spec.as_user, "--", *args]
            raw = spec.run_dir / "raw" / f"session-{n}.jsonl"
            remaining = spec.timeout_s - (time.monotonic() - started)
            with open(raw, "w", encoding="utf-8") as out, open(raw.with_suffix(".stderr"), "w") as err:
                proc = subprocess.Popen(args, cwd=spec.workspace, env=env, stdin=subprocess.DEVNULL,
                                        stdout=out, stderr=err, start_new_session=True)
                try:
                    code = proc.wait(timeout=max(remaining, 0.1))
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, 9)
                    proc.wait()
                    code = None
            session_events = convert_stream(raw.read_text(encoding="utf-8").splitlines(), n, len(events))
            events += session_events
            if code is None:
                status = "timeout"
                break
            exit_codes.append(code)
            if code != 0 or any(e.kind == "result" and e.data.get("is_error") for e in session_events):
                status = "harness_error"
                break
            resume = session_id(events)
            if not needs_decision(final_text(events)) or auto_replies >= MAX_AUTO_REPLIES or resume is None:
                break
            auto_replies += 1
            message = AUTO_REPLY
            events.append(Event(len(events), n + 1, "main", "auto_reply", {"text": AUTO_REPLY}))
    finally:
        watch_log = watcher.stop()

    result = {
        "run_id": run_id,
        "task_id": spec.task.id,
        "condition": spec.condition.id,
        "rep": spec.rep,
        "status": status,
        "exit_codes": exit_codes,
        "auto_replies": auto_replies,
        "completion_claim": final_text(events),
        "usage_by_agent": usage_by_agent(events),
        "totals": totals(events),
        "started_at": started_at,
        "ended_at": _now(),
        "first_prod_change": first_change(watch_log),
        "fingerprint": fingerprint,
    }
    write_jsonl(events, spec.run_dir / "trajectory.jsonl")
    (spec.run_dir / "watch.json").write_text(json.dumps(watch_log, indent=2, sort_keys=True))
    (spec.run_dir / "run.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return result
