"""pytest plugin `benchlog`, loaded via PYTEST_PLUGINS (see bench.testlog.plugin_env).

When BENCH_TESTLOG is set, every pytest session appends one JSON line to that file:
{"ts_start", "ts_end", "args", "cwd", "exitstatus", "results": {nodeid: outcome}, "collect_errors": [...]}.
outcome is passed | failed | skipped | error (setup/teardown failures are errors).
"""

from __future__ import annotations

import json
import os
import time

import pytest


class _Recorder:
    def __init__(self, path: str, config: pytest.Config) -> None:
        self.path = path
        self.config = config
        self.ts_start = time.time()
        self.results: dict[str, str] = {}
        self.collect_errors: list[str] = []

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        if report.failed:
            self.collect_errors.append(report.nodeid)

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        nodeid = report.nodeid
        if report.when == "call":
            self.results[nodeid] = report.outcome
        elif report.failed:
            self.results[nodeid] = "error"
        elif report.when == "setup" and report.skipped:
            self.results[nodeid] = "skipped"

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        params = self.config.invocation_params
        line = {
            "ts_start": self.ts_start,
            "ts_end": time.time(),
            "args": list(params.args),
            "cwd": str(params.dir),
            "exitstatus": int(exitstatus),
            "results": self.results,
            "collect_errors": self.collect_errors,
        }
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
            fh.flush()


def pytest_configure(config: pytest.Config) -> None:
    path = os.environ.get("BENCH_TESTLOG")
    if path:
        config.pluginmanager.register(_Recorder(path, config), "benchlog-recorder")
