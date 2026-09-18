# clinician-standing — developer entry points.
# Every target assumes a Python 3.11 interpreter on PATH.

PYTHON ?= python3.11
VENV   ?= .venv
BIN    := $(VENV)/bin

.DEFAULT_GOAL := help
.PHONY: help install install-s3 lock test test-db lint typecheck migrate ingest status clean

help: ## Show this list of targets.
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[1m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create .venv and install the package plus dev tooling, editable.
	$(PYTHON) -m venv $(VENV)
	$(BIN)/python -m pip install --upgrade pip
	$(BIN)/python -m pip install -e ".[dev]"

install-s3: ## Add the boto3 extra, needed when STORAGE_PATH is an s3:// URI.
	$(BIN)/python -m pip install -e ".[dev,s3]"

lock: ## Regenerate the hashed lockfiles from pyproject (needs uv on PATH).
	@# Universal resolution: one file carries every platform's wheel hashes with
	@# markers, so plain `pip install --require-hashes` works on Linux CI and on a
	@# Windows dev box from the same file. Re-run this whenever pyproject's
	@# dependencies change, and commit the result.
	uv pip compile --universal --generate-hashes pyproject.toml -o requirements.txt
	uv pip compile --universal --generate-hashes --extra s3 --extra dev \
	  pyproject.toml -o requirements-dev.txt

test: ## Run the test suite (no network, no database).
	$(BIN)/pytest -m "not network and not database"

test-db: ## Run the database-backed tests. Needs TEST_DATABASE_URL.
	@test -n "$$TEST_DATABASE_URL" || { \
	  echo "TEST_DATABASE_URL is not set. Point it at a THROWAWAY cluster with"; \
	  echo "every migration in db/migrations applied -- these tests write rows."; \
	  exit 2; }
	$(BIN)/pytest -m database

lint: ## Lint with ruff and check formatting.
	$(BIN)/ruff check src tests
	$(BIN)/ruff format --check src tests

typecheck: ## Static type check the package with mypy.
	$(BIN)/mypy

migrate: ## Apply db/migrations to the linked Supabase project via the supabase CLI.
	@# The CLI only reads supabase/migrations, so point it at db/migrations,
	@# which stays the single source of truth. Run `supabase link` once first.
	@#
	@# Migrations need DDL rights, so they run as the superuser -- the CLI's own
	@# linked credential, or MIGRATION_DATABASE_URL for the psql path in
	@# db/README.md. DATABASE_URL is the ingest role (app_ingest) and cannot do
	@# this, deliberately. Keeping them apart is what 0011_ingest_role.sql is for.
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
