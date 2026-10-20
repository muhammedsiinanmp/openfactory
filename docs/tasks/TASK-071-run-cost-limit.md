# TASK-071: Run use case, the cost limit after each `AgentRunFinished` of a task

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-015 (accepted). It decides `tasks.cost_usd` (projector rule built in TASK-065) and names the cost limit among the M4 work. Its Alternatives reject "A `Runs` read that sums the cost". The task adds no port, adapter, dependency, event type, payload, schema or convention. It reads an existing column through an existing `Plans` read, which ADR-012 allows: that port is read-only. See Design choice 1.
- Spec impact: wording (see Spec gaps)
- Spec sections (spec v1.16; SC-91, SC-107, SC-124):
  - "Metrics", third bullet: "A task's `max_cost_usd` is checked after each run; exceeding it escalates the task. After each `AgentRunFinished` of a task, implementer or reviewer, and before that run's `exit` is looked at, the orchestrator reads the task's `tasks.cost_usd`: the sum of `cost_usd` over the task's finished runs since its last retry by `resolve`, a null counting as 0. If it is greater than `limits.max_cost_usd`, the task goes from its state (`running` or `gating`) to `failed` and then to `escalated`, both with reason `cost limit`; no further gate runs and nothing is committed; after a reviewer run, no `review` `GateEvaluated` is recorded. The check is built in M4, with the retry it limits."
  - "Execution" › "Events of one task": "A task over its cost limit goes from `running` or `gating` to `failed`, then to `escalated`, both with reason `cost limit` (see Metrics)."
  - "Task state machine": "path or secret violations and the cost limit skip the retry and escalate at once, as two events, to `failed` and then to `escalated`"; "The `run` and `resolve` use cases check every transition against `TRANSITIONS` before they record it".
  - "Domain model and storage" › "Ids": "They read the plan and task projections through the `Plans` port: ... the tasks of a plan with their dependencies ...".
  - "Domain model and storage" (projection rules): "On `AgentRunFinished` the projector adds its `cost_usd`, a null counting as 0, to `tasks.cost_usd` of the run's task".

## Outline item
M4 outline item 9, whole.

## Objective
After each `AgentRunFinished` of a task (the implementer's, and each reviewer run's), `run_task` reads the task's `tasks.cost_usd` through `Plans.tasks`. When it is greater than `limits.max_cost_usd`, `run_task` records `failed`, then `escalated`, both with reason `cost limit`, and stops the task.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/domain/plans.py`: `Task` gains `cost_usd: float`, the `tasks.cost_usd` column. It defaults to `0`, so existing `Task(...)` constructions stay valid (Design choice 2).
- `src/openfactory/adapters/sqlite_plans.py`: `tasks(plan_id)` also selects `cost_usd`.
- `src/openfactory/app/run.py`:
  - A private helper `_over_cost_limit(task, plan, plans) -> bool`. It re-reads `plans.tasks(plan.id)`, takes the row of `task.id`, and returns `row.cost_usd > task.contract.limits.max_cost_usd`.
  - `run_task` calls it right after recording each `AgentRunFinished`:
    - after the implementer's: before the `result.exit != "ok"` check;
    - after each reviewer run in `_review_attempt`'s caller: after the first, before the retry decision; after the second, before the verdict is used.
  - When the helper returns true, `run_task` records `chain.move(failed, "cost limit")` and `chain.move(escalated, "cost limit")` through `_Chain` and returns.
- Tests:
  - New tests in `tests/unit/test_run_task.py` with the prefix `test_task071_`.
  - New tests for the `cost_usd` read in `tests/integration/test_sqlite_plans.py`, or a new `tests/integration/test_sqlite_plans_cost.py`, through `SqliteEventRecorder`.
- Test edits that need approval:
  - `tests/unit/test_run_task.py`, mechanical: `FakePlans` gains `tasks(plan_id)`. It returns the task with `cost_usd` either fixed by the test or summed from the `AgentRunFinished` events in `FakeRecorder` (the test-writer chooses). By default the sum stays under the fixture limit of 1.0: 0.25 implementer plus 0.05 per reviewer run.
  - No other edit is expected. `test_run_plan.py` and `test_m3_close.py` stay under their limits (fake `Task`s default to 0; the stand-in envelopes report about 0.04 per run against 1.50).

Out:
- Retry, `failed` to `ready`, `attempts exhausted`, the failure report and taking a task again (item 10).
- `resolve` (item 11) and `status` (item 12).
- Any change to `repair_plan` (see open question Q1).
- Any change to events, payloads, the schema, the projector, ports' method sets or `cli.py`.

## Acceptance criteria
- [ ] **AC1** ("Metrics": "After each `AgentRunFinished` of a task, implementer or reviewer, and before that run's `exit` is looked at, the orchestrator reads the task's `tasks.cost_usd` ... If it is greater than `limits.max_cost_usd`, the task goes from its state (`running` or `gating`) to `failed` and then to `escalated`, both with reason `cost limit`; no further gate runs and nothing is committed"):
  - When the task's cost after the implementer's `AgentRunFinished` is greater than `max_cost_usd`, the next events are `running` to `failed` then `failed` to `escalated`, both with reason `cost limit`, each pointing at the one before.
  - The result's state is `escalated`. No `running` to `gating`, no `GateEvaluated`, no `GateRunner.run`, no reviewer call, no commit.
  - This holds whatever the run's `exit` is: for an `error` or `timeout` run the reason is `cost limit`, not `run error` or `run timeout`.
- [ ] **AC2** ("Metrics": "after a reviewer run, no `review` `GateEvaluated` is recorded"; "Execution" › "Events of one task": "A task over its cost limit goes from `running` or `gating` to `failed`, then to `escalated`"):
  - When the cost is first over the limit after a reviewer's `AgentRunFinished`, the next events are `gating` to `failed` then `failed` to `escalated`, both `cost limit`.
  - No `review` `GateEvaluated`, no `review.txt` write, no commit.
  - This holds for an approving reply, a rejected first reply (no second reviewer run is started) and an `LLMError`.
- [ ] **AC3** ("Metrics": "... the sum of `cost_usd` over the task's finished runs since its last retry by `resolve` ...", "greater than"):
  - The check compares the value `Plans.tasks` gives after the run's `AgentRunFinished`, so it includes that run's cost and the costs of earlier runs of the task.
  - A sum equal to `max_cost_usd` does not escalate: the task goes on as before this task, and passes when every gate passes.
  - A second reviewer run that takes the sum over the limit escalates as in AC2.
- [ ] **AC4** ("Domain model and storage" › "Ids", "the tasks of a plan"; the `tasks.cost_usd` projection rules):
  - `SqlitePlans.tasks(plan_id)` gives each task's `cost_usd` from the projection.
  - That is 0 for a new task, the sum of its runs' `cost_usd` with nulls as 0 after `AgentRunFinished` events recorded through `SqliteEventRecorder`, and 0 again after a `TaskResolved` `retry`.
- [ ] **AC5** ("Task state machine": "The `run` and `resolve` use cases check every transition against `TRANSITIONS` before they record it"; ADR-011):
  - Both cost-limit moves go through `_Chain.move`.
  - `app/run.py` still imports nothing from `adapters` or `cli`.
  - The suite passes with only the approved test edit listed in Scope.

## Architecture rules that apply
- `app` depends on `domain` and `ports` only; `cli.py` does not change (ADR-011).
- All state changes go through the events table. The check only reads the projection the recorder updated in the same transaction (ADR-010) and never writes it.
- `Plans` stays read-only (ADR-012).

## Plan
1. Create branch `task/TASK-071-run-cost-limit` from an up-to-date main.
2. Test-writer:
   - make the approved `FakePlans` edit;
   - write failing tests for AC1 to AC3 and AC5 in `tests/unit/test_run_task.py`;
   - write the AC4 integration tests.
3. Add `cost_usd` to `Task` and to the `SqlitePlans.tasks` select.
4. Add `_over_cost_limit` to `run.py` and call it at the three points: after the implementer finish, after the first reviewer finish, after the second reviewer finish.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the living docs and the Outcome.
7. Commit `feat(app): escalate a task over its cost limit in run` with the trailers `Task: TASK-071` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/domain/plans.py` (about +2)
- `src/openfactory/adapters/sqlite_plans.py` (about +3)
- `src/openfactory/app/run.py` (about +25)
- `tests/unit/test_run_task.py` (approved edit about +15, new tests about +150)
- `tests/integration/test_sqlite_plans.py`, or new `tests/integration/test_sqlite_plans_cost.py` (about +50)
- `docs/architecture.md`:
  - the `Task` bullet gains `cost_usd`;
  - the `run_task` paragraph gains the cost check.
- `docs/progress.md`: Current is TASK-071; add the Done line; remove item 9 from the outline; add Later lines for G1 and Q1.
- `docs/decisions.md`: rows for G1 (read through `Plans.tasks`) and Design choice 2 (the default), if approved.
- `docs/tasks/TASK-071-run-cost-limit.md` (this record).

Not expected to change: `ports/`, `cli.py`, the projector, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 245 lines with tests, about 30 of them in `src/`.

## Spec gaps
- **G1 (wording, does not block). "Metrics", "the orchestrator reads the task's `tasks.cost_usd`".**
  - Unclear: the sentence names no read for it. "Domain model and storage" › "Ids" lists every `Plans` read, and none is "the cost of a task". ADR-015 adds only "the last gate result of a task" to `Plans`.
  - Proposed reading: read it through the listed "tasks of a plan" read, since `Task` is "one row of the `tasks` projection". `Task` gains `cost_usd` and `Plans` gets no new method.
  - Why it does not block: the read is already in the spec's list, and behaviour is fully fixed by "Metrics". Only the text naming the read is missing.

## Open questions (for the human, not assumed)
- **Q1. "Metrics" against "Execution" › "Restart" step 2.**
  - The repair records an `AgentRunFinished` of a task (`error: interrupted`), which literally falls under "After each `AgentRunFinished` of a task". Restart step 2 instead fixes the move as `failed` with reason `interrupted`.
  - This task leaves `repair_plan` unchanged. The repair's finish has a null `cost_usd`, so it adds 0 and cannot itself cross the limit.
  - One case escapes: a `run` killed after an `AgentRunFinished` that crossed the limit but before the check recorded `failed`. That task is repaired as `interrupted` and retried by item 10, and the next run's check catches it, one run late.
  - Confirm that Restart's explicit rule wins, or whether item 10 should settle it. It does not block this task.
  - **Answer (human, 2026-10-20):** Restart step 2's explicit rule wins; `repair_plan` is unchanged. The repair's own `AgentRunFinished` adds 0 and cannot cross the limit. The killed-before-check case is a crash-window gap, not a rule conflict: it ends as either one more implementer run past the budget or `attempts exhausted`. Recorded as a Later line for item 10 or a later `/spec-change`.

## Answers at planning (human, 2026-10-20)
- Design choices 1, 2 and 4 approved as written. The `docs/decisions.md` row for Design choice 1 says it extends the 2026-10-11 (TASK-025) row that lists `Task`'s fields.
- The `FakePlans` test edit in Scope is approved.

## Design choices to confirm at planning
1. Read the cost through `Plans.tasks` and a `cost_usd` field on `Task`, not a new `Plans` method such as `task_cost(task_id)`. A new method would be a read outside the spec's list in "Ids" and outside ADR-015.
2. `Task.cost_usd` defaults to `0`, unlike the other `Task` fields. This keeps the `Task(...)` constructions in about ten test files unedited. The column is `NOT NULL DEFAULT 0`, so the adapter always sets it. If the human prefers a required field, the record grows by mechanical edits across those files.
3. The check re-reads `plans.tasks(plan.id)` up to three times per task (after the implementer and after each reviewer run). It relies on the recorder applying each event in the same transaction (ADR-010), which `run_plan` already relies on when it re-reads after each task.
4. When the cost is over the limit after a failed implementer process, the reason is `cost limit`, not `run error` or `run timeout`. This follows "before that run's `exit` is looked at".

## Outcome
- `Task.cost_usd: float = 0` added in `domain/plans.py`; `SqlitePlans.tasks` selects `cost_usd`; `app/run.py` gains `_over_cost_limit`, called after the implementer's `AgentRunFinished` (before the exit check) and after each reviewer run, escalating `failed` then `escalated` with reason `cost limit` through `_Chain`.
- Tests: `test_task071_*` in `tests/unit/test_run_task.py`; new `tests/integration/test_sqlite_plans_cost.py`.
- Test edits: only the approved `FakePlans` edit in `tests/unit/test_run_task.py`; the test-writer added `prior_cost` and `late_cost` to `FakePlans`. No other test edited.
- Docs: `docs/architecture.md`, `docs/decisions.md` (three rows for Design choices 1, 2 and 4), `docs/progress.md` (Later lines for G1 and the crash window were already added). No ADR needed.
