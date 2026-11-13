"""Record when production files are first modified, independent of the harness."""

from __future__ import annotations

import fnmatch
import hashlib
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

DEFAULT_EXCLUDE = ("**/tests/**", "**/test_*.py")


class ProdWatcher:
    def __init__(
        self,
        root: Path,
        include: Sequence[str],
        exclude: Sequence[str] = DEFAULT_EXCLUDE,
        interval: float = 1.0,
    ) -> None:
        self.root = Path(root)
        self.include = tuple(include)
        self.exclude = tuple(exclude)
        self.interval = interval
        self._baseline: dict[str, str] = {}
        self._log: dict[str, float] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _excluded(self, rel: str) -> bool:
        # Leading "/" lets "**/tests/**" also match a top-level tests/ directory.
        return any(fnmatch.fnmatch("/" + rel, pattern) for pattern in self.exclude)

    def _scan(self) -> dict[str, str]:
        found: dict[str, str] = {}
        for pattern in self.include:
            for path in self.root.glob(pattern):
                rel = path.relative_to(self.root).as_posix()
                if rel in found or not path.is_file() or self._excluded(rel):
                    continue
                try:
                    found[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
                except OSError:
                    continue
        return found

    def _tick(self) -> None:
        now = time.time()
        current = self._scan()
        for rel in current.keys() | self._baseline.keys():
            if rel not in self._log and current.get(rel) != self._baseline.get(rel):
                self._log[rel] = now

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            self._tick()

    def start(self) -> None:
        self._baseline = self._scan()
        self._thread = threading.Thread(target=self._loop, name="prod-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> dict[str, float]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self._tick()
        return dict(self._log)


def first_change(log: Mapping[str, float]) -> float | None:
    return min(log.values()) if log else None
