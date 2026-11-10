"""Our own trajectory format, plus a converter from Claude Code `--output-format stream-json`.

Scoring and reporting read only this format, so another harness needs only a new converter.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

Kind = Literal["text", "tool_call", "tool_result", "usage", "result", "auto_reply", "system"]
MAIN = "main"


@dataclass
class Event:
    seq: int
    session: int
    agent: str
    kind: Kind
    data: dict = field(default_factory=dict)
    ts: str | None = None


def _content_blocks(message: dict) -> list[dict]:
    content = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [b for b in content or [] if isinstance(b, dict)]


def _events_for(raw: dict) -> list[tuple[str, Kind, dict]]:
    """Map one stream-json object to (agent, kind, data) triples."""
    agent = raw.get("parent_tool_use_id") or MAIN
    kind = raw.get("type")
    message = raw.get("message") if isinstance(raw.get("message"), dict) else {}
    if kind == "assistant":
        out: list[tuple[str, Kind, dict]] = []
        for block in _content_blocks(message):
            btype = block.get("type")
            if btype == "text":
                out.append((agent, "text", {"role": "assistant", "text": block.get("text", "")}))
            elif btype == "thinking":
                out.append((agent, "text", {"role": "assistant", "thinking": True, "text": block.get("thinking", "")}))
            elif btype == "tool_use":
                out.append((agent, "tool_call", {"id": block.get("id"), "name": block.get("name"), "input": block.get("input")}))
        if message.get("usage"):
            out.append((agent, "usage", {"message_id": message.get("id"), "model": message.get("model"), "usage": message["usage"]}))
        return out
    if kind == "user":
        out = []
        for block in _content_blocks(message):
            if block.get("type") == "tool_result":
                out.append((agent, "tool_result", {
                    "tool_use_id": block.get("tool_use_id"),
                    "is_error": bool(block.get("is_error")),
                    "content": block.get("content"),
                }))
            elif block.get("type") == "text":
                out.append((agent, "text", {"role": "user", "text": block.get("text", "")}))
        return out
    if kind == "result":
        return [(MAIN, "result", raw)]
    return [(agent, "system", raw)]


def convert_stream(lines: Iterable[str], session: int, start_seq: int = 0) -> list[Event]:
    events: list[Event] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            events.append(Event(start_seq + len(events), session, MAIN, "text", {"text": line, "unparsed": True}))
            continue
        if not isinstance(raw, dict):
            events.append(Event(start_seq + len(events), session, MAIN, "text", {"text": line, "unparsed": True}))
            continue
        for agent, kind, data in _events_for(raw):
            events.append(Event(start_seq + len(events), session, agent, kind, data, raw.get("timestamp")))
    return events


def usage_by_agent(events: Sequence[Event]) -> dict[str, dict[str, int]]:
    seen: set[str] = set()
    out: dict[str, dict[str, int]] = {}
    for e in events:
        if e.kind != "usage":
            continue
        mid = e.data.get("message_id")
        if mid is not None:
            if mid in seen:
                continue
            seen.add(mid)
        u = e.data.get("usage", {})
        acc = out.setdefault(e.agent, {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0})
        acc["input"] += int(u.get("input_tokens") or 0)
        acc["output"] += int(u.get("output_tokens") or 0)
        acc["cache_read"] += int(u.get("cache_read_input_tokens") or 0)
        acc["cache_creation"] += int(u.get("cache_creation_input_tokens") or 0)
    return out


def totals(events: Sequence[Event]) -> dict:
    out = {"total_cost_usd": 0.0, "num_turns": 0, "input": 0, "output": 0, "cache_read": 0, "cache_creation": 0,
           "models": {}}
    for e in events:
        if e.kind != "result":
            continue
        out["total_cost_usd"] += float(e.data.get("total_cost_usd") or 0.0)
        out["num_turns"] += int(e.data.get("num_turns") or 0)
        u = e.data.get("usage") or {}
        out["input"] += int(u.get("input_tokens") or 0)
        out["output"] += int(u.get("output_tokens") or 0)
        out["cache_read"] += int(u.get("cache_read_input_tokens") or 0)
        out["cache_creation"] += int(u.get("cache_creation_input_tokens") or 0)
        for model, mu in (e.data.get("modelUsage") or {}).items():
            acc = out["models"].setdefault(model, {})
            for key, value in mu.items():
                if isinstance(value, (int, float)):
                    acc[key] = acc.get(key, 0) + value
    return out


def final_text(events: Sequence[Event]) -> str:
    if not events:
        return ""
    last_session = max(e.session for e in events)
    texts = [e.data.get("text", "") for e in events
             if e.session == last_session and e.agent == MAIN and e.kind == "text"
             and e.data.get("role", "assistant") == "assistant" and not e.data.get("thinking")]
    return texts[-1] if texts else ""


def session_id(events: Sequence[Event]) -> str | None:
    for e in reversed(events):
        if e.kind in ("system", "result") and e.data.get("session_id"):
            return e.data["session_id"]
    return None


def bash_commands(events: Sequence[Event]) -> list[str]:
    return [str((e.data.get("input") or {}).get("command", "")) for e in events
            if e.kind == "tool_call" and e.data.get("name") == "Bash"]


def write_jsonl(events: Sequence[Event], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(asdict(e), ensure_ascii=False) + "\n" for e in events)


def read_jsonl(path: Path) -> list[Event]:
    with open(path, encoding="utf-8") as fh:
        return [Event(**json.loads(line)) for line in fh if line.strip()]
