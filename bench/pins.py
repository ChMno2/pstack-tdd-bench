"""Pinned versions and fixed experiment constants. Every value here is part of the environment fingerprint."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

LIMS_COMMIT = "227be16e3365e9956da0dec8efa987db3e0f3e4f"
PSTACK_COMMIT = "c742dd61706fbacc1b95f1a20b7b988cf096ce6c"
CLAUDE_CODE_VERSION = "2.1.322"
MODEL_ID = "claude-sonnet-5-5"

AUTO_REPLY = "請依你的判斷繼續，不要再詢問"
MAX_AUTO_REPLIES = 3
REPS = 3
FLAKY_RERUNS = 3

TZ = "UTC"
PYTHONHASHSEED = "0"
DISALLOWED_TOOLS = ("WebFetch", "WebSearch", "AskUserQuestion")
