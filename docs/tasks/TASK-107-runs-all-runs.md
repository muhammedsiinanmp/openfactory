# TASK-107: `Runs` read of every run, and its `SqliteRuns` version

- Milestone: M7
- Status: done
- Tests: acceptance
- ADR: ADR-020 (accepted). Its Decision says: "No new port. `Runs` also gives every run with its task id, role, exit, tokens, cost and `duration_s`." Its Consequences say: "`SqliteRuns` gains one read". ADR-012 covers the `Runs` read port and ADR-010 the adapter's own connection. The task adds one method to an existing port and its adapter, as TASK-042, TASK-064 and TASK-100 did. It adds no port, adapter, event type, payload field, table, column, dependency or convention, so no new ADR is needed. The answers to Open questions 1 to 3 get one row in `docs/decisions.md`.
- Spec impact: none
- Spec sections (spec v1.20):
  - "Domain model and storage" (the M7 paragraph after "Ids"): "M7 adds what `stats` and `report` need. `Runs` also gives every run with its task id, role, exit, tokens, cost and `duration_s`." (SC-209)
  - "Domain model and storage" › "Projections", `agent_runs` DDL: `task_id` "null for a planner or classifier run"; `exit`, `tokens_in`, `tokens_out`, `cost_usd`, `duration_s` "null until AgentRunFinished" (tokens and cost also "when the runtime reported none").
  - "Metrics": "A run with no `AgentRunFinished` counts in the number of runs, adds nothing to tokens, cost or duration, and is not in the percentiles." (SC-210) and "A task's figures cover all its runs, those before a `resolve --retry` included" (SC-211).
  - "CLI commands" › "Output", `stats` bullet: "`<runs>`, `<tokens_in>`, `<tokens_out>`, `<cost_usd>`, `<duration_s>` … The percentiles are nearest-rank over the `duration_s` of every run with `exit: ok`". This is the consumer of the read in a later task (item 3). It is quoted here to show which fields the read must carry.

## Outline item
M7 outline item 1 in `docs/progress.md`: "`Runs` read of every run with task id, role, exit, tokens, cost and `duration_s`, and its `SqliteRuns` version (SC-209, ADR-020)". Item 2 (cost attribution) and item 3 (`stats`) consume it. Nothing calls the new read in this task.

## Objective
`Runs` gains a read that returns every row of `agent_runs` as a frozen domain model with its run id, task id, role, exit, tokens, cost and `duration_s`. `SqliteRuns` implements it with one `SELECT`.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/domain/agent_run.py`: a new frozen `RunRecord` with `extra="forbid"`. Fields:
  - `id: RunId`
  - `task_id: TaskId | None`
  - `role: RunRole`
  - `exit: RunExit | None`
  - `tokens_in: int | None`
  - `tokens_out: int | None`
  - `cost_usd: float | None`
  - `duration_s: float | None`

  Every field is required, and there is no check across fields. The module docstring is updated to say the module also holds the `Runs` read model.
- `src/openfactory/ports/runs.py`: `all_runs() -> list[RunRecord]`, the third method. It returns every run, finished or not, in ascending run number.
- `src/openfactory/adapters/sqlite_runs.py`: one `SELECT id, task_id, role, exit, tokens_in, tokens_out, cost_usd, duration_s FROM agent_runs ORDER BY CAST(substr(id, 5) AS INTEGER)`. It only reads, caches nothing and keeps its `TYPE_CHECKING` assertion.
- New tests:
  - in `tests/unit/test_runs_port.py` (port shape, model)
  - in `tests/integration/test_sqlite_runs.py`, or a new `tests/integration/test_sqlite_runs_all.py`, built through `SqliteEventRecorder`

Out:
- Cost attribution, `causation_id` chains and `EventStore` reads (item 2).
- `stats` and `report` (items 3 and 4).
- Any change to `app/`, `cli.py`, the projector, payloads, tables or events.

## Acceptance criteria
- [x] **AC1** ("Domain model and storage", M7 paragraph: "`Runs` also gives every run …"; ADR-020 "No new port"):
  - `Runs` has `all_runs() -> list[RunRecord]`, and the port's method set is `next_id`, `unfinished_run`, `all_runs`.
  - `ports/runs.py` imports nothing from `adapters` or `app`.
  - `sqlite_runs.py` still ends with its `TYPE_CHECKING` assertion against `Runs`.
- [x] **AC2** (same paragraph: "with its task id, role, exit, tokens, cost and `duration_s`"; `agent_runs` DDL nullability):
  - `RunRecord` is frozen and rejects unknown fields.
  - It has exactly the fields `id`, `task_id`, `role`, `exit`, `tokens_in`, `tokens_out`, `cost_usd`, `duration_s`, all required. `role` takes only the four `RunRole` values and `exit` only `RunExit` or `None`.
- [x] **AC3** (same paragraph; `agent_runs` DDL "null for a planner or classifier run", "null … when the runtime reported none"). On a database built through `SqliteEventRecorder`:
  - Each finished run's record carries the values of its `AgentRunStarted` and `AgentRunFinished`.
  - Planner and classifier runs have `task_id` `None`. Implementer and reviewer runs have their task id.
  - Tokens or cost the runtime did not report are `None`, not 0.
- [x] **AC4** ("Metrics": "A run with no `AgentRunFinished` counts in the number of runs, adds nothing to tokens, cost or duration"):
  - A run with only `AgentRunStarted` is listed with its id, task id and role, and with `exit`, `tokens_in`, `tokens_out`, `cost_usd` and `duration_s` all `None`.
- [x] **AC5** (same paragraph "every run"; "Metrics": "those before a `resolve --retry` included"):
  - `all_runs()` lists every run once, across tasks and roles, in ascending run number compared as an integer (`run_10000` after `run_9999`).
  - Runs of a task recorded before a `TaskResolved` with `retry` are still listed.
  - An empty log gives `[]`.
  - A run recorded by the recorder after an earlier call shows up on the next call (nothing cached).
- [x] **AC6** (CLAUDE.md architecture rules and "Tests from the test-writer are fixed"):
  - Only `domain/agent_run.py`, `ports/runs.py` and `adapters/sqlite_runs.py` change under `src/`.
  - `SqliteRuns` runs `SELECT` only.
  - `app/`, `cli.py` and the projector are unchanged.
  - The full suite passes, and the only edit to an existing test is the approved one in Open question 6.

## Architecture rules that apply
- `RunRecord` lives in `domain`: pure, no I/O, imports only `openfactory.domain` and pydantic.
- The port is a Protocol and imports only `openfactory.domain`.
- `SqliteRuns` opens its own connection (ADR-010), runs `SELECT` only and keeps its `TYPE_CHECKING` assertion.
- The read decides nothing about attribution or sums. Those stay in the app use cases (items 2 and 3).

## Plan
1. Create branch `task/TASK-107-runs-all-runs` from an up-to-date main.
2. Record the human's answers to the Open questions.
3. Test-writer: write failing tests for AC1 to AC5, and make the approved method-set edit in `tests/unit/test_runs_port.py`.
4. Implement `RunRecord`, the port method and the `SqliteRuns` query.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`: the "Runs port" section (three methods and the new sentence), "SQLite runs" (the new query), the `RunRecord` entry next to `RunResult`, and the wiring paragraph ("`Runs.all_runs` exists for M7 `stats` and `report`; nothing calls it yet").
   - `docs/decisions.md`: one row for the answers to Open questions 1 to 3.
   - `docs/progress.md`: Current, a Done line, item 1 marked done, and the method-set name drift added to the existing TASK-042/TASK-064/TASK-100 Later line about `test_ac1_runs_is_a_protocol_with_only_next_id`.
   - This record's Outcome.
7. Commit `feat(ports): add the Runs read of every run` with trailers `Task: TASK-107` and `Milestone: M7`. Do not push.

## Files expected to change
- `src/openfactory/domain/agent_run.py` (about +20)
- `src/openfactory/ports/runs.py` (about +8)
- `src/openfactory/adapters/sqlite_runs.py` (about +20)
- `tests/unit/test_runs_port.py` and `tests/integration/test_sqlite_runs*.py` (about +170 together)
- `docs/architecture.md`, `docs/decisions.md`, `docs/progress.md`, this record

Not expected to change: `app/`, `cli.py`, the projector, payloads, `docs/spec/`, `docs/adr/`.

## Spec gaps
None. A reading note, not a gap: "every run with its task id, role, …" names the run itself, so the run id is part of each item. Item 2 needs it to match the `run_id` of the `AgentRunStarted` events found through `causation_id` chains.

## Open questions (each with a proposed answer)
1. **Method name.** Proposed: `all_runs() -> list[RunRecord]`, with no argument. Alternatives: `runs()` reads oddly as `runs.runs()`, and `every_run()`.
2. **Model name and place.** Proposed: `RunRecord` in `domain/agent_run.py`, next to `RunResult`, the other per-run model. This follows how `CommitRef` and `GateResultRef` sit in `domain/plans.py` for the `Plans` reads. Alternative: a new `domain/runs.py`.
3. **Fields.** Proposed: exactly the spec's list plus the run id: `id`, `task_id`, `role`, `exit`, `tokens_in`, `tokens_out`, `cost_usd`, `duration_s`. Leave out `model`, `runtime`, `context_hash`, `started_at` and `ended_at`: no M7 output names them (YAGNI). Alternative: also `model`, if you want per-model figures later. The spec asks for none.
4. **How an unfinished run shows.** Proposed: `exit` is `None`, mirroring the column that is null until `AgentRunFinished`. There is no separate `finished` flag. The `stats` code then treats `exit is None` as unfinished: it counts the run and adds 0 to the sums. Since `stats` uses only `exit: ok` for percentiles, this falls out naturally.
5. **Order.** Proposed: ascending run number as an integer, the order `next_id` and `unfinished_run` already use. `stats` sorts its own lines, so the order is only for determinism.
6. **Edit to an existing test (needs your approval):** in `tests/unit/test_runs_port.py::test_ac1_runs_is_a_protocol_with_only_next_id`, the exact method set gains `all_runs`. The name is kept, as in TASK-042, TASK-064 and TASK-100, and the name drift is noted in the existing Later line.
   - The in-memory `FakeRuns` classes in 8 test files need no change. Pyright checks only `src` (`[tool.pyright] include = ["src"]`), and no current code calls the new method.
7. **Cross-field check.** Proposed: none on `RunRecord`, for example "`exit` None implies the figures are None". The projector owns that link, as for `RunResult` and `GateOutput`.

## Answers (human, 2026-10-25)
All seven proposed answers approved as written, including the test edit in question 6. Question 2 also updates the `domain/agent_run.py` module docstring (advisor note).

## Outcome
- Added `RunRecord` to `src/openfactory/domain/agent_run.py` (module docstring updated), `Runs.all_runs() -> list[RunRecord]` to `src/openfactory/ports/runs.py`, and the one-`SELECT` version to `src/openfactory/adapters/sqlite_runs.py`. Nothing else under `src/` changed; nothing calls the new read.
- New tests: AC1 and AC2 as new functions in `tests/unit/test_runs_port.py`; AC3 to AC5 in `tests/integration/test_sqlite_runs_all.py`. The only edit to an existing test is the approved one: `all_runs` added to the exact method set in `tests/unit/test_runs_port.py::test_ac1_runs_is_a_protocol_with_only_next_id` (name kept).
- Full suite: 2087 passed. ruff, pyright and `check_docs` are clean.
- No mechanical test fixes were needed.
- Answers 1 to 3 are one row in `docs/decisions.md`. `docs/architecture.md` and `docs/progress.md` updated (the Later line now lists three names).
