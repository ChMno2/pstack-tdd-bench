#!/bin/sh
# Resolve every transitive dependency as of LIMS's last green CI (2026-06-02), so the SUT sees the
# dependency set it was tested with. mutmut 3.7.0 (2026-07-31) is the one package allowed past that date.
set -eu
cd "$(dirname "$0")"
uv pip compile requirements.in \
  --python-version 3.12 --python-platform x86_64-manylinux_2_28 \
  --exclude-newer 2026-06-03T00:00:00Z \
  --exclude-newer-package mutmut=2026-08-01T00:00:00Z \
  --no-header --annotation-style line \
  -o requirements.lock
