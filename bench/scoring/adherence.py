"""TDD adherence: did a new test fail before production code was first modified?"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

FAILING = ("failed", "error")


def load_testlog(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    sessions = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            sessions.append(data)
    return sessions


@dataclass
class Adherence:
    followed: bool
    sessions: int
    evidence: dict | None


def _same(logged: str, wanted: str) -> bool:
    # The agent may run pytest from another directory, which prefixes node IDs with the rootdir path.
    return logged == wanted or logged.endswith("/" + wanted)


def _red(session: dict, added: set[str]) -> bool:
    for nodeid, outcome in (session.get("results") or {}).items():
        if outcome in FAILING and any(_same(nodeid, a) for a in added):
            return True
    files = {a.split("::")[0] for a in added}
    return any(_same(err, f) for err in session.get("collect_errors") or [] for f in files)


def adherence(testlog: Sequence[dict], added: set[str], first_prod_change: float | None) -> Adherence:
    for session in testlog:
        before_change = first_prod_change is None or float(session.get("ts_end", 0)) <= first_prod_change
        if before_change and _red(session, added):
            return Adherence(True, len(testlog), session)
    return Adherence(False, len(testlog), None)
