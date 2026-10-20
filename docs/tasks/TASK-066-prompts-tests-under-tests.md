# TASK-066: Prompts state that tests go under `tests/` with `req` markers

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-015 (accepted). Its Consequences say: "The planner prompt changes (SC-93), so later planner runs have a new `context_hash`." The two decisions already have rows in `docs/decisions.md`: 2026-10-15, SC-93 (spec v1.14) and 2026-10-15, SC-110 (spec v1.15). The task adds no port, adapter, dependency, event type, payload or schema change, and no new convention.
- Spec impact: none
- Spec sections (spec v1.16; SC-93, SC-110):
  - "Task contract" › "Planning": "The prompt states the path pattern syntax. It also states that every task adds tests under `tests/` that carry a `req` marker for each of its requirements, so its `allowed_paths` covers the test files it writes."
  - "Execution" › "The context pack": "the implementer's instructions, which require every new test to be under `tests/` and to carry a `req` marker, forbid `git commit`, and tell the agent to leave no file outside `allowed_paths`, by-products of the tools it runs included (for example `__pycache__/`);"
  - "Gates and remediation" › "The pytest gate and `req` markers" (the reason, not built here): the gate collects only `tests/`, and fails "when, for a requirement in the contract, no collected test that carries its `req` marker is in a file among the path check's changed paths."

## Outline item
M4 outline item 6. Nothing depends on it. Item 7 (the deterministic gates in `run`) does not need it.

## Objective
Have the planner prompt say that every task adds tests under `tests/` with a `req` marker for each of its requirements, covered by its `allowed_paths`. Have the implementer's instructions in the context pack say that every new test goes under `tests/`.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/app/planner_prompt.py`: one new bullet in the `Rules:` block of `_INSTRUCTIONS`. Suggested text: "Every task adds tests under `tests/` that carry a `req` marker for each of its requirements, for example `@pytest.mark.req("REQ-AUTH-001")`, so its `allowed_paths` covers the test files it writes." The module docstring gains one clause on it.
- `src/openfactory/app/context_pack.py`: the existing `req` marker bullet of `_INSTRUCTIONS` also requires the test to be under `tests/`. Suggested text: "Every new test is under `tests/` and carries a `req` marker naming the requirement it covers, for example `@pytest.mark.req("REQ-AUTH-001")`."
- Tests: new tests in `tests/unit/test_planner_prompt.py` and `tests/unit/test_context_pack.py`, with names prefixed `test_task066_`.

Out:
- Any plan check that rejects a contract whose `allowed_paths` does not cover `tests/`. Decision SC-93 says "No new plan check".
- Gates, the tag rule, `run` wiring (items 7 and later), and the failure report in the pack (item 10).
- Any change to the path pattern block, the section layout, `context_hash`, `domain/`, `ports/`, `adapters/` or `cli.py`.

## Acceptance criteria
- [ ] **AC1** (SC-93; "Task contract" › "Planning": "It also states that every task adds tests under `tests/` that carry a `req` marker for each of its requirements, so its `allowed_paths` covers the test files it writes"). The first prompt from `build_planner_prompt` has an instruction line that names `tests/`, the `req` marker, "each of its requirements" and `allowed_paths`. This holds with no requirements, with requirements, and with an empty tracked file list.
- [ ] **AC2** (SC-93; same text). The retry prompt (`rejections` non-empty) holds the same line, so both planner calls of one `plan` state it.
- [ ] **AC3** (SC-110; "Execution" › "The context pack": "require every new test to be under `tests/` and to carry a `req` marker"). The text from `build_context_pack` has an instruction line that requires every new test to be under `tests/` and to carry a `req` marker. The existing instructions still forbid `git commit` and still name `allowed_paths` and `__pycache__/`. The existing `test_context_pack.py` assertions on them still pass.
- [ ] **AC4** ("Task contract" › "Planning": "The prompt states the path pattern syntax", and "Execution" › "The context pack"). The rest of both texts is unchanged. The two path pattern conformance tests in `tests/unit/test_spec_conformance.py` still pass. Equal arguments still give equal texts and equal `context_hash`. No existing test is edited.

## Architecture rules that apply
- Both modules stay pure and import only `openfactory.domain` (the existing import tests hold this).
- No LLM call, event, port or adapter change. Later planner and implementer runs get a new `context_hash`. No test pins a hash literal: `test_m2_close.py` and `test_m3_close.py` compare the hash with the bytes the stand-in received.

## Plan
1. Create branch `task/TASK-066-prompts-tests-under-tests` from an up-to-date main.
2. Test-writer: write failing tests for AC1 to AC3 in `tests/unit/test_planner_prompt.py` and `tests/unit/test_context_pack.py`. Find the instruction line by its content (for example the line that holds both `tests/` and `req`), not by fixed wording. AC4 rests on the existing tests.
3. Add the planner bullet and change the implementer bullet in the two `_INSTRUCTIONS` texts.
4. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
5. Update the living docs and the Outcome.
6. Commit `feat(app): say tests go under tests/ in the planner prompt and context pack` with the trailers `Task: TASK-066` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/app/planner_prompt.py` (about +3)
- `src/openfactory/app/context_pack.py` (about +1/-1)
- `tests/unit/test_planner_prompt.py` (about +35)
- `tests/unit/test_context_pack.py` (about +20)
- `docs/architecture.md`: the `planner_prompt.py` paragraph and the `context_pack.py` paragraph, which list what the instructions say.
- `docs/progress.md`: Current: TASK-066; Done: add the line; Outline: remove item 6.
- `docs/tasks/TASK-066-prompts-tests-under-tests.md` (this record).

Not expected to change: `domain/`, `ports/`, `adapters/`, `cli.py`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, `docs/decisions.md` (the SC-93 and SC-110 rows already exist).

Expected size: about 60 lines with tests, about 5 of them in `src/`.

## Spec gaps
None. "Planning" and "The context pack" each say what the text must state, and leave the wording to the code.

## Open questions
Settled by the human on 2026-10-20: both proposed answers accepted.
1. Whether the implementer's instruction should also say "a `req` marker for each of the contract's requirements, in a file you change" (what the tag rule checks). Proposed: no. "The context pack" asks only for "under `tests/`" and "a `req` marker". If the first real `run` shows agents missing a requirement, it becomes a Later line.
2. Where the planner sentence goes. Proposed: a bullet in the existing `Rules:` block, after "Every task passes the gates named below, and no task may change a forbidden path."

## Outcome
Done.
- `planner_prompt.py`: new `Rules:` bullet after the gates bullet; the module docstring mentions it.
- `context_pack.py`: the `req` marker bullet now reads "Every new test is under `tests/` and carries a `req` marker ...".
- Tests: 4 added (`test_task066_` prefix) in `tests/unit/test_planner_prompt.py` and `tests/unit/test_context_pack.py`. No test edits were made.
- Checks: 1428 tests pass; ruff, pyright and check_docs clean.
