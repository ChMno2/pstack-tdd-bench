"""Stand-in for the claude CLI. Emits stream-json shaped like tests/fixtures/stream/*.jsonl."""

import json
import sys
import time
from pathlib import Path


def _emit(obj: dict) -> None:
    print(json.dumps(obj), flush=True)


def _session(sid: str, text: str, *, is_error: bool = False) -> None:
    _emit({"type": "system", "subtype": "init", "session_id": sid, "cwd": "/work"})
    _emit({"type": "assistant", "parent_tool_use_id": None, "session_id": sid, "timestamp": "2026-11-11T00:00:00Z",
           "message": {"id": f"msg-{sid}-{time.time_ns()}", "model": "claude-sonnet-5-5",
                       "content": [{"type": "text", "text": text}],
                       "usage": {"input_tokens": 3, "output_tokens": 7}}})
    _emit({"type": "result", "subtype": "error_during_execution" if is_error else "success", "is_error": is_error,
           "session_id": sid, "num_turns": 1, "total_cost_usd": 0.01,
           "usage": {"input_tokens": 3, "output_tokens": 7}, "modelUsage": {"claude-sonnet-5-5": {"outputTokens": 7}}})


def main(scenario: str, state_dir: str, argv: list[str]) -> None:
    if "--version" in argv:
        print("2.1.322 (Claude Code)")
        return
    state = Path(state_dir)
    state.mkdir(parents=True, exist_ok=True)
    calls = len(list(state.glob("call-*"))) + 1
    (state / f"call-{calls}").write_text(json.dumps(argv))
    resumed = "--resume" in argv
    if scenario == "ok":
        Path("backend/app/calc.py").write_text(Path("backend/app/calc.py").read_text() + "\n# fixed\n")
        _session("s-1", "Fixed it. All tests pass.")
    elif scenario == "ask_once":
        _session("s-1", "Done." if resumed else "I found two options.\n\nShould I also update the docs?")
    elif scenario == "ask_forever":
        _session("s-1", "Which approach do you prefer？")
    elif scenario == "crash":
        _emit({"type": "system", "subtype": "init", "session_id": "s-1"})
        sys.exit(2)
    elif scenario == "error_result":
        _session("s-1", "Usage limit reached", is_error=True)
    elif scenario == "hang":
        _emit({"type": "system", "subtype": "init", "session_id": "s-1"})
        time.sleep(60)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
