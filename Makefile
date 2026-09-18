# clinician-standing — developer entry points.
# Every target assumes a Python 3.11 interpreter on PATH.

PYTHON ?= python3.11
VENV   ?= .venv
BIN    := $(VENV)/bin

.DEFAULT_GOAL := help
.PHONY: help install test lint typecheck migrate ingest status clean

help: ## Show this list of targets.
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[1m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create .venv and install the package plus dev tooling, editable.
	$(PYTHON) -m venv $(VENV)
	$(BIN)/python -m pip install --upgrade pip
	$(BIN)/python -m pip install -e ".[dev]"

test: ## Run the test suite (no network, no database).
	$(BIN)/pytest

lint: ## Lint with ruff and check formatting.
	$(BIN)/ruff check src tests
	$(BIN)/ruff format --check src tests

typecheck: ## Static type check the package with mypy.
	$(BIN)/mypy

migrate: ## Apply db/migrations to the linked Supabase project via the supabase CLI.
	@# The CLI only reads supabase/migrations, so point it at db/migrations,
	@# which stays the single source of truth. Run `supabase link` once first.
	@mkdir -p supabase
	@test -e supabase/migrations || ln -s ../db/migrations supabase/migrations
	supabase db push --include-all

ingest: ## Run every enabled connector: download, diff, load evidence.
	$(BIN)/clinician-standing ingest --all

status: ## Print the last run, row counts and freshness for each source.
	$(BIN)/clinician-standing status

clean: ## Remove caches, build output and the virtualenv (leaves storage/ alone).
	rm -rf $(VENV) build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
