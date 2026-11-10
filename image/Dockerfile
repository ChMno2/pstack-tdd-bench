# Pinned runner image for pstack-tdd-bench. Agent, scoring and LIMS backend tests all run inside it.
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

LABEL org.opencontainers.image.source="https://github.com/ChMno2/pstack-tdd-bench"

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=UTC \
    PYTHONHASHSEED=0 \
    PIP_NO_CACHE_DIR=1 \
    DISABLE_UPDATES=1 \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl ca-certificates util-linux bash \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI, exact version, copied out of root's home so the unprivileged agent user can run it.
ARG CLAUDE_CODE_VERSION=2.1.322
RUN curl -fsSL https://claude.ai/install.sh | bash -s "${CLAUDE_CODE_VERSION}" \
    && cp -L /root/.local/bin/claude /usr/local/bin/claude \
    && chmod 755 /usr/local/bin/claude \
    && rm -rf /root/.local/share/claude /root/.local/bin/claude \
    && claude --version | grep -q "^${CLAUDE_CODE_VERSION}"

# LIMS backend dependencies (pinned by the LIMS commit) plus scoring tools.
COPY sut/lims/backend/requirements.txt sut/lims/backend/requirements-dev.txt /tmp/lims/
RUN pip install -r /tmp/lims/requirements.txt -r /tmp/lims/requirements-dev.txt mutmut==3.8.1

# bench itself, so its pytest plugin (benchlog) auto-loads for every pytest run in the container.
COPY pyproject.toml /opt/bench-src/
COPY bench /opt/bench-src/bench
RUN pip install /opt/bench-src && rm -rf /opt/bench-src

# Unmodified pstack (Claude Code tree), readable by the agent.
COPY vendor/pstack /opt/pstack

RUN useradd --create-home --shell /bin/bash agent
