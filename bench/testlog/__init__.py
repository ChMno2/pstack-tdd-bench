"""pytest plugin that logs every test session for TDD-adherence scoring.

The plugin is a standalone module (benchlog.py, stdlib + pytest only) loaded through PYTEST_PLUGINS,
so it also loads in a virtualenv the agent creates itself, where bench is not installed.
"""

from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent


def plugin_env() -> dict[str, str]:
    return {"PYTHONPATH": str(PLUGIN_DIR), "PYTEST_PLUGINS": "benchlog"}
