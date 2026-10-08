# OpenFactory — Spec Control Plane

Spec-driven control plane that plans, executes, gates and traces AI agent work.
Phase 1 = local CLI vertical slice. See docs/spec/phase1-spec.md.

## Source of truth
- docs/spec/phase1-spec.md is AUTHORITATIVE. Never edit it. If the spec seems wrong,
  incomplete or contradictory, STOP and ask me. Do not work around it.
- Accepted ADRs in docs/adr/ are binding.
- If code and spec disagree, the spec wins.

## Commands
- Install: `uv sync`
- Tests: `uv run pytest -q`
- Lint/format: `uv run ruff check --fix . && uv run ruff format .`
- Doc check: `uv run python scripts/check_docs.py`

## Architecture rules
- src/openfactory/domain: pure models and rules. No I/O, no imports from adapters/app.
- src/openfactory/ports: Protocol interfaces only.
- src/openfactory/adapters: SQLite, git, Claude Code. Implement ports.
- All LLM calls go through `claude -p`. Never add the Anthropic SDK or read ANTHROPIC_API_KEY.
- src/openfactory/app: use cases, depends on domain + ports only.
- All state changes go through the events table. Never write projections directly.
- All LLM output is validated by a Pydantic model before use.

## Workflow
- One task per session. Start with /next-task.
- Every task has a record in docs/tasks/ BEFORE code is written.
- Tests first: write failing tests from acceptance criteria, then implement.
- Every test linked to a requirement carries @pytest.mark.req("REQ-...").
- Do not expand scope. Anything outside the current task goes in progress.md under "Later".
- Every task runs on its own branch: task/<TASK-ID>-<slug>, created from an up-to-date main.
- Commit subjects follow Conventional Commits: feat|fix|test|docs|refactor|chore(scope): summary
- Never commit to main. Never push. The human pushes and opens PRs.

## Definition of done (all required)
1. Tests pass, ruff clean, check_docs passes.
2. Task record updated with outcome.
3. Living docs touched by the change are updated in the same commit.
4. progress.md updated.
5. Commit message ends with trailers:
   Task: <task id>
   Milestone: <M1..M7>

## Never
- Edit docs/spec/, .env, or files in docs/generated/ by hand.
- git push, force-push, or rewrite history.
- Add a dependency without recording why in docs/decisions.md.