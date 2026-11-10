import json
from pathlib import Path

from bench.trajectory import (
    Event,
    bash_commands,
    convert_stream,
    final_text,
    read_jsonl,
    session_id,
    totals,
    usage_by_agent,
    write_jsonl,
)

STREAM = Path(__file__).parent / "fixtures/stream"
SUB = "toolu_01NVXnmNBYwevT3HCTYGwBk4"


def _load(name: str, session: int = 1, start_seq: int = 0) -> list[Event]:
    return convert_stream((STREAM / f"{name}.jsonl").read_text().splitlines(), session, start_seq)


def _assistant(msg_id: str, content: list, output_tokens: int = 5, parent=None) -> str:
    return json.dumps({
        "type": "assistant", "parent_tool_use_id": parent, "timestamp": "2026-11-11T00:00:00Z",
        "message": {"id": msg_id, "content": content, "usage": {"input_tokens": 1, "output_tokens": output_tokens}},
    })


def test_simple_stream_kinds():
    events = _load("simple")
    assert [e.kind for e in events] == ["system", "system", "text", "usage", "result"]
    assert [e.seq for e in events] == list(range(5))
    assert all(e.session == 1 for e in events)
    assert events[2].data["text"].strip().lower().startswith("ok")
    assert events[2].ts == events[3].ts is not None


def test_subagent_events_attributed():
    events = _load("subagent")
    sub_texts = [e.data["text"] for e in events if e.agent == SUB and e.kind == "text"]
    assert "ok" in [t.strip().lower() for t in sub_texts]
    calls = [e for e in events if e.kind == "tool_call"]
    assert calls[0].agent == "main" and calls[0].data["id"] == SUB
    results = [e for e in events if e.kind == "tool_result"]
    assert results[0].data["tool_use_id"] == SUB


def test_usage_by_agent_on_real_stream():
    usage = usage_by_agent(_load("subagent"))
    assert set(usage) == {"main", SUB}
    assert usage["main"]["output"] == 16 + 3
    assert usage[SUB]["output"] == 4
    assert usage[SUB]["cache_creation"] == 33567


def test_usage_dedup_by_message_id():
    lines = [_assistant("m1", [{"type": "text", "text": "a"}]), _assistant("m1", [{"type": "text", "text": "b"}])]
    assert usage_by_agent(convert_stream(lines, 1))["main"]["output"] == 5


def test_final_text_is_last_main_text():
    events = _load("subagent")
    assert final_text(events).strip().lower() == "done"
    later = convert_stream([_assistant("m9", [{"type": "text", "text": "second session"}])], 2, len(events))
    assert final_text(events + later) == "second session"


def test_unparsable_line_kept():
    (event,) = convert_stream(["this is not json"], 1)
    assert event.kind == "text"
    assert event.data == {"text": "this is not json", "unparsed": True}


def test_bash_commands_extracted():
    line = _assistant("m2", [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls -la"}}])
    assert bash_commands(convert_stream([line], 1)) == ["ls -la"]


def test_session_id_and_totals():
    events = _load("subagent")
    assert session_id(events) == json.loads((STREAM / "subagent.jsonl").read_text().splitlines()[0])["session_id"]
    t = totals(events)
    assert t["num_turns"] == 2
    assert t["total_cost_usd"] > 0
    assert {"claude-sonnet-5-5", "claude-haiku-5-5"} <= set(t["models"])


def test_jsonl_roundtrip(tmp_path: Path):
    events = _load("subagent")
    write_jsonl(events, tmp_path / "t.jsonl")
    assert read_jsonl(tmp_path / "t.jsonl") == events
