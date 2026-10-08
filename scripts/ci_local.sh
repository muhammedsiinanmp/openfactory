#!/usr/bin/env bash
# Runs exactly what CI runs. Used by CI, the pre-push hook, and Claude before committing.
set -euo pipefail

step() { printf '\n→ %s\n' "$*"; }

step "uv sync --locked"
uv sync --locked

step "ruff check"
uv run ruff check .

step "ruff format --check"
uv run ruff format --check .

step "pyright"
uv run pyright

step "pytest"
uv run pytest -q

step "doc check"
uv run python scripts/check_docs.py

if command -v gitleaks >/dev/null 2>&1; then
  step "gitleaks"
  gitleaks detect --source . --no-banner --redact
else
  step "gitleaks not installed locally, skipping (CI runs it). Install with: brew install gitleaks"
fi

printf '\n✓ All CI checks passed.\n'
