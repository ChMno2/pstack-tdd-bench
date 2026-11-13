"""Runner: one Run = one task under one condition, one repetition, possibly several resumed sessions."""

from __future__ import annotations

import json
import os
import pwd
import shutil
import signal
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from bench.capture.trajectory import (
    Event,
    convert_stream,
    final_text,
    session_id,
    totals,
    usage_by_agent,
    write_jsonl,
)
from bench.capture.watch import ProdWatcher, first_change
from bench.harness.conditions import (
    CREDENTIALS,
    Condition,
    build_cli_args,
    build_env,
    render_prompt,
    write_pstack_models,
)
from bench.harness.fingerprint import collect
from bench.pins import AUTO_REPLY, MAX_AUTO_REPLIES
from bench.task import Task


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


def _owner(user: str) -> tuple[int, int]:
    entry = pwd.getpwnam(user)
    return entry.pw_uid, entry.pw_gid


def _chown_tree(path: Path, user: str) -> None:
    uid, gid = _owner(user)
    os.chown(path, uid, gid)
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            os.lchown(os.path.join(root, name), uid, gid)  # never follow symlinks out of the tree


def _prepare(spec: RunSpec, testlog: Path) -> None:
    (spec.run_dir / "raw").mkdir(parents=True, exist_ok=True)
    spec.home.mkdir(parents=True, exist_ok=True)
    testlog.touch()
    if spec.condition.use_pstack:
        write_pstack_models(spec.home)
    if spec.as_user:
        _chown_tree(spec.workspace, spec.as_user)
        _chown_tree(spec.home, spec.as_user)
        os.chown(testlog, *_owner(spec.as_user))


REDACTED = b"[REDACTED]"


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _reap_user(user: str | None) -> int | None:
    """Kill everything still running as the agent user; return how many processes were left behind."""
    if not user:
        return None
    found = subprocess.run(["pgrep", "-u", user], capture_output=True, text=True, check=False).stdout.split()
    subprocess.run(["pkill", "-KILL", "-u", user], capture_output=True, check=False)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not subprocess.run(["pgrep", "-u", user], capture_output=True, check=False).stdout.strip():
            break
        time.sleep(0.2)
    return len(found)


def _export_workspace_git(spec: RunSpec) -> None:
    """Keep the agent's commits as a text patch (redactable), then drop .git: compressed objects cannot be redacted."""
    git_dir = spec.workspace / ".git"
    if not git_dir.exists():
        return
    log = subprocess.run(
        ["git", "-c", "safe.directory=*", "-C", str(spec.workspace), "log", "-p", "--all", "--format=fuller"],
        capture_output=True, check=False,
    ).stdout
    (spec.run_dir / "workspace-git.patch").write_bytes(log)
    shutil.rmtree(git_dir)


def _redact(root: Path, secrets: list[str]) -> None:
    needles = [s.encode() for s in secrets]
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        data = path.read_bytes()
        if any(n in data for n in needles):
            for n in needles:
                data = data.replace(n, REDACTED)
            path.write_bytes(data)


def _finalize(spec: RunSpec, testlog: Path, secrets: list[str]) -> None:
    transcripts = spec.home / ".claude" / "projects"
    if transcripts.is_dir():
        shutil.copytree(transcripts, spec.run_dir / "transcripts", dirs_exist_ok=True, symlinks=True)
    _export_workspace_git(spec)
    _redact(spec.run_dir, secrets)
    if spec.as_user:
        os.chown(testlog, 0, 0)
        testlog.chmod(0o644)


def run(spec: RunSpec, base_env: Mapping[str, str]) -> dict:
    started_at = _now()
    started = time.monotonic()
    run_id = f"{spec.task.id}-{spec.condition.id}-r{spec.rep}-{started_at.replace('-', '').replace(':', '')}"
    testlog = spec.run_dir / "testlog.jsonl"
    _prepare(spec, testlog)
    env = build_env({**base_env, "BENCH_TESTLOG": str(testlog)}, home=spec.home)
    secrets = [env[name] for name in CREDENTIALS if len(env.get(name, "")) >= 8]
    fingerprint = collect(spec.task, claude_bin=spec.claude_bin, env=base_env)

    events: list[Event] = []
    exit_codes: list[int] = []
    auto_replies = 0
    status = "completed"
    error: str | None = None
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
            with open(raw, "wb") as out, open(raw.with_suffix(".stderr"), "wb") as err:
                proc = subprocess.Popen(args, cwd=spec.workspace, env=env, stdin=subprocess.DEVNULL,
                                        stdout=out, stderr=err, start_new_session=True)
                try:
                    code = proc.wait(timeout=max(remaining, 0.1))
                except subprocess.TimeoutExpired:
                    code = None
                _kill_group(proc.pid)  # also after a normal exit: background children must not outlive the session
                proc.wait()
            lines = raw.read_text(encoding="utf-8", errors="replace").splitlines()
            session_events = convert_stream(lines, n, len(events))
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
    except Exception as exc:  # the agent may already have run: record what we have instead of losing the run
        status, error = "harness_error", repr(exc)
    finally:
        watch_log = watcher.stop()
    try:
        leftover = _reap_user(spec.as_user)
    except OSError as exc:
        leftover, error = None, error or f"reaping agent processes failed: {exc!r}"

    result = {
        "run_id": run_id,
        "task_id": spec.task.id,
        "condition": spec.condition.id,
        "rep": spec.rep,
        "status": status,
        "error": error,
        "exit_codes": exit_codes,
        "auto_replies": auto_replies,
        "leftover_processes": leftover,
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
    _finalize(spec, testlog, secrets)
    return json.loads((spec.run_dir / "run.json").read_text())
