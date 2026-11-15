"""pytest plugin `benchlog`, loaded via PYTEST_PLUGINS (see bench.capture.pytest_plugin.plugin_env).

When BENCH_TESTLOG is set, every pytest session appends one JSON line to that file:
{"ts_start", "ts_end", "args", "cwd", "exitstatus", "results": {nodeid: outcome}, "collect_errors": [...],
 "failures": {nodeid: {"when", "exc_type", "message"}}}.
outcome is passed | failed | skipped | error (setup/teardown failures are errors).
failures holds the first failing phase of each failed test: the exception's type name and pytest's crash message,
cut to MESSAGE_LIMIT characters.
"""

from __future__ import annotations

import json
import os
import time

import pytest

MESSAGE_LIMIT = 300


class _Recorder:
    def __init__(self, path: str, config: pytest.Config) -> None:
        self.path = path
        self.config = config
        self.ts_start = time.time()
        self.results: dict[str, str] = {}
        self.collect_errors: list[str] = []
        self.failures: dict[str, dict[str, str]] = {}

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo):
        report = yield
        if report.failed and call.excinfo is not None:
            report.bench_exc_type = call.excinfo.typename
        return report

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
        if report.failed and nodeid not in self.failures:
            crash = getattr(report.longrepr, "reprcrash", None)
            message = getattr(crash, "message", None) or str(report.longrepr)
            self.failures[nodeid] = {
                "when": report.when,
                "exc_type": getattr(report, "bench_exc_type", ""),
                "message": message[:MESSAGE_LIMIT],
            }

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
            "failures": self.failures,
        }
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
            fh.flush()


def pytest_configure(config: pytest.Config) -> None:
    path = os.environ.get("BENCH_TESTLOG")
    if path:
        config.pluginmanager.register(_Recorder(path, config), "benchlog-recorder")
