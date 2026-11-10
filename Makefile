# Common commands. Run `make help` for the list.
REPO  ?= ChMno2/pstack-tdd-bench
TASK  ?= tasks/T00-smoke
COND  ?= C1
REPS  ?= 1
AUTH  ?= subscription
RUN   ?=
DIR   ?=
VENV  := .venv/bin

.DEFAULT_GOAL := help
.PHONY: help install test lint check-task lock run runs download score image

help: ## List the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

install: ## Create .venv (Python 3.12) and install bench with dev tools
	uv venv --python 3.12 .venv
	uv pip install --python $(VENV)/python -e '.[dev]'

test: ## Run bench's own test suite (no database or network needed)
	$(VENV)/pytest -q

lint: ## Lint bench and tests
	$(VENV)/ruff check bench tests

check-task: ## Check that TASK's patches apply to the pinned LIMS (TASK=tasks/<id>)
	$(VENV)/bench check-task --task $(TASK)

lock: ## Regenerate image/requirements.lock (resolved as of LIMS's last green CI)
	image/lock.sh

run: ## Start an experiment batch on GitHub Actions (TASK, COND=C1|C2a, REPS=1-3, AUTH=subscription|api)
	gh workflow run run.yml -R $(REPO) -f task=$(TASK) -f condition=$(COND) -f reps=$(REPS) -f auth=$(AUTH)

runs: ## List the latest experiment batches
	gh run list -R $(REPO) --workflow run.yml --limit 10

download: ## Download a batch's run directories into results/<RUN> (RUN=<run-id>)
	gh run download $(RUN) -R $(REPO) -D results/$(RUN)

score: ## Re-score a downloaded run directory (DIR=<run dir>, TASK=tasks/<id>)
	$(VENV)/bench score $(DIR) --task $(TASK)

image: ## Rebuild and smoke-test the runner image on GitHub Actions
	gh workflow run image.yml -R $(REPO)
