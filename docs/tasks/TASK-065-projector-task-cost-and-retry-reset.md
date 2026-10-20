# TASK-065: Projector rules for the task's cost and the `retry` reset

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-015 (accepted). Its section "Events and tables (SC-90, SC-91)" says: "the projector adds each `AgentRunFinished`'s `cost_usd` (null as 0) to the run's task, found through `agent_runs.task_id`. A `TaskResolved` with `retry` sets `attempt` and `cost_usd` to 0. Both use only event data, so a rebuild stays identical." The task adds no port, adapter, dependency, event type, payload or schema change. ADR-007 (payloads are stable contracts) is untouched.
- Spec impact: none
- Spec sections (spec v1.16; SC-90, SC-91):
  - "Domain model and storage" › "Projection rules": "On `AgentRunFinished` the projector adds its `cost_usd`, a null counting as 0, to `tasks.cost_usd` of the run's task, found through `agent_runs.task_id`; a run with no task adds nothing."
  - "Domain model and storage" › "Projection rules": "A `TaskResolved` whose `decision` is `retry` sets `tasks.attempt` and `tasks.cost_usd` of its task to 0, so a retried task gets a fresh budget. One whose `decision` is `abandon` changes no row; the `TaskStateChanged` that follows it sets the state."
  - "Domain model and storage" › "Projection rules": "A rebuild is identical when, for every projection table, the rows read in primary-key order are equal before and after. The projector therefore uses only data in the event".
  - "Domain model and storage", the `tasks` DDL comment: "`cost_usd REAL NOT NULL DEFAULT 0` -- sum of the task's runs' cost_usd since its last `resolve --retry` (M4)".

## Outline item
M4 outline item 5. Items 9 (the cost limit) and 11 (`resolve`) depend on it.

## Objective
Make the projector keep `tasks.cost_usd` as the sum of the task's runs' `cost_usd`, and have a `TaskResolved` `retry` reset `attempt` and `cost_usd` to 0.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/adapters/sqlite_projector.py`:
  - In the `AgentRunFinishedPayload` branch, after the existing `agent_runs` update, one more statement: `UPDATE tasks SET cost_usd = cost_usd + ? WHERE id = (SELECT task_id FROM agent_runs WHERE id = ?)`, with `payload.cost_usd or 0`. A null `task_id` matches no row.
  - A new `TaskResolvedPayload` branch. When `decision == "retry"` it runs `UPDATE tasks SET attempt = 0, cost_usd = 0 WHERE id = ?`. `abandon` writes nothing.
- Tests: a new `tests/integration/test_sqlite_projector_cost.py`. Use costs that are exact in binary (0.25, 0.5, 0.125) so equality is exact.

Out:
- The cost-limit check in `run` (item 9), the `resolve` use case and command (item 11), and `status` (item 12).
- Any change to `domain/`, `ports/`, `app/` or `cli.py`, the DDL or the payloads.
- A second `AgentRunFinished` for one run, or one whose `run_id` has no `agent_runs` row. The run use case never records either. If the reviewer flags it, it becomes a Later line.

## Acceptance criteria
- [x] **AC1** ("Projection rules": "adds its `cost_usd` ... to `tasks.cost_usd` of the run's task, found through `agent_runs.task_id`"). After a `PlanCreated` and two runs of `AUTH-001` that finish with costs 0.25 and 0.5, `AUTH-001` has `cost_usd` 0.75. `AUTH-002` stays 0. Every other column of both `tasks` rows is unchanged. A finished reviewer run of a task counts the same as an implementer run.
- [x] **AC2** ("Projection rules": "a null counting as 0; a run with no task adds nothing"):
  - A run of `AUTH-001` that finishes with `cost_usd` null leaves the task's `cost_usd` unchanged.
  - A planner run (`task_id` null) that finishes with cost 0.5 leaves every `tasks` row unchanged.
- [x] **AC3** ("Projection rules": "A `TaskResolved` whose `decision` is `retry` sets `tasks.attempt` and `tasks.cost_usd` of its task to 0"):
  - Setup: `AUTH-002` has `attempt` 2 and a non-zero `cost_usd`, and `AUTH-001` has non-zero values too.
  - A `retry` for `AUTH-002` sets its `attempt` and `cost_usd` to 0 and leaves its `state`, `objective`, `contract` and `plan_id` unchanged. `AUTH-001` is unchanged.
  - A later `TaskStateChanged` to `running` and a finished run cost 0.25 give `attempt` 1 and `cost_usd` 0.25.
- [x] **AC4** ("Projection rules": "One whose `decision` is `abandon` changes no row"). With the same setup as AC3 (non-zero `attempt` and `cost_usd`), an `abandon` leaves every projection table unchanged. This extends the existing TASK-058 test, which applies `abandon` only right after `PlanCreated`.
- [x] **AC5** ("Projection rules": "A rebuild is identical ..."). For a log that has a `PlanCreated`, state changes, runs with and without a task and with a null cost, a `retry`, and more runs after it:
  - `rebuild` gives the same `tasks` rows as applying the events one by one.
  - `SqliteEventRecorder.record` of the same events, followed by its `rebuild`, gives those rows too.

## Architecture rules that apply
- Only the projector writes projection tables. It uses only data from the event and the projections: no clock, no file reads.
- The adapter keeps its existing `TYPE_CHECKING` situation. The projector is an internal helper with no port (ADR-009).
- No event, payload, DDL or dependency change.

## Plan
1. Create branch `task/TASK-065-projector-task-cost-and-retry-reset` from an up-to-date main.
2. Test-writer: write failing tests for AC1 to AC5 in `tests/integration/test_sqlite_projector_cost.py`, using the helpers in `test_sqlite_projector_m4.py` and `test_sqlite_projector_runs.py` as models.
3. Add the two statements to `SqliteProjector.apply`.
4. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
5. Update the living docs and the Outcome.
6. Commit `feat(adapters): project the task cost and the retry reset` with the trailers `Task: TASK-065` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/adapters/sqlite_projector.py` (about +15)
- `tests/integration/test_sqlite_projector_cost.py` (new, about 200)
- `docs/architecture.md`, the SQLite projector paragraph: `cost_usd` is now written by the two rules, and `TaskResolved` `retry` resets the task while `abandon` writes nothing.
- `docs/progress.md`: Current: TASK-065; Done: add the line; Outline: mark item 5 done; Later: remove the TASK-058 line "The `tasks.cost_usd` column exists, but no rule writes it ...", because this task takes it.
- `docs/tasks/TASK-065-projector-task-cost-and-retry-reset.md` (this record).

Not expected to change: `domain/`, `ports/`, `app/`, `cli.py`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, `docs/decisions.md`.

Expected size: about 215 lines with tests, about 15 of them in `src/`.

## Spec gaps
None. "Projection rules" gives both rules, including the null and no-task cases. It also settles the old pre-M4 database question raised in TASK-058's record ("A database made before M4 is discarded").

## Open questions
All three answered as proposed (approved 2026-10-20).
1. Where the `retry` reset lives. Proposed: in the projector, now, as outline item 5 and ADR-015 say; item 11 (`resolve`) only records the event.
2. Whether a reviewer run's cost counts toward the task. Proposed: yes; the spec says "the run's task, found through `agent_runs.task_id`" with no role filter, and the DDL comment says "sum of the task's runs' cost_usd". AC1 pins this.
3. The float-sum test values. Proposed: exactly representable costs (0.25, 0.5, 0.125) compared with `==`.

## Outcome
Done. `SqliteProjector.apply` gained two rules:
- `AgentRunFinished`: after the `agent_runs` update, `UPDATE tasks SET cost_usd = cost_usd + ? WHERE id = (SELECT task_id FROM agent_runs WHERE id = ?)` with `cost_usd or 0`; a run with no task matches no row.
- `TaskResolved`: `retry` runs `UPDATE tasks SET attempt = 0, cost_usd = 0 WHERE id = ?`; `abandon` writes nothing.

Tests: new `tests/integration/test_sqlite_projector_cost.py`, 9 tests for AC1 to AC5; 8 failed before the implementation. No existing test was edited. Full suite: 1424 passed; ruff, pyright and check_docs clean.

Docs: `docs/architecture.md` (SQLite projector paragraph), `docs/progress.md` (Current, Done, outline item 5 removed, the TASK-058 Later line on `cost_usd` removed).
