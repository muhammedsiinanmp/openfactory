# TASK-072: Run use case, the retry loop: `failed` to `ready` or `attempts exhausted`, and one line per task

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-015 (accepted). Its "Gates and retry" section says every failure that does not escalate at once "retries while `attempt < max_attempts`, in the same command". This task adds no port, adapter, dependency, event type, payload, schema or convention.
- Spec impact: none
- Spec sections (spec v1.16; SC-89, SC-113):
  - "Gates and remediation" › "Remediation": "after a `failed` event, unless it escalates at once (path violation, secret found, cost limit), the same command moves the task `failed` to `ready`, reason null, pointing at the `failed` event outside the repair ..., when `attempt < limits.max_attempts`; otherwise `failed` to `escalated` with reason `attempts exhausted` ... Every other failure reason retries this way: a failed gate, `run error`, `run timeout`, `no changes`, `git: ...` and `interrupted`. ... A retry starts from `<base>` in a new worktree."
  - "Execution" › "Events of one task": "A `failed` task that does not escalate at once then moves `failed` to `ready`, or `failed` to `escalated` with reason `attempts exhausted` (see Remediation)." Also: "`causation_id` is the `event_id` of the event recorded just before it for the same task in the same command".
  - "Execution" › "`run`": "A task that a failure moved back to `ready` (see Remediation) is taken again in the same invocation by the same rule." Also: "`--task ID` runs that task only, its retries included."
  - "Task state machine": "Failures loop back to `ready` until attempts run out"; "The `run` and `resolve` use cases check every transition against `TRANSITIONS` before they record it".
  - "CLI commands" › "Output": "`run` prints one line per task it took as `task_id  <final state>`, in the order it first took them, where the final state is the task's state when `run` leaves it; a task taken again after a failure still has one line, at the position it was first taken. It exits 0 when every task it took passed, otherwise 1".

## Outline item
M4 outline item 10, first slice (10a). Restart steps 2 and 3 (10b) and the failure report in the context pack (10c) are later tasks.

## Objective
When `run_task` returns a task in `failed`, `run_plan` re-reads the task's `attempt` and settles it:
- `failed` to `ready` with a null reason when `attempt < max_attempts`, then takes it again in the same invocation;
- otherwise `failed` to `escalated` with reason `attempts exhausted`.

`RunReport.tasks` holds one entry per task, at the position it was first taken, with its final state.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/app/run.py`:
  - A private helper `_settle_failed(task, result, plan, plans, recorder) -> TaskRunResult`. It reads the task's `attempt` from `plans.tasks(plan.id)`, then moves through a `_Chain` whose causation is `result.last_event_id` (the `failed` event): to `ready` (null reason) when `attempt < task.contract.limits.max_attempts`, else to `escalated` with reason `attempts exhausted`. 10b will reuse it for Restart step 3, so its signature should not depend on `run_plan` locals.
  - In `run_plan.take`, a result in state `failed` is settled. A `ready` outcome records the `failed` to `ready` event id in `causes[task.id]`, so the next `ready` to `running` points at it. Results are stored per task id in first-taken order, and a later attempt replaces the entry.
  - Without `--task`, the existing `while ready` loop takes the task again by the lowest-id rule. With `--task`, the named task is taken again while it is `ready`.
- `run_task` is unchanged. It still returns `failed` for one attempt, so `tests/unit/test_run_task.py` needs no edit.
- `cli.py` is unchanged. It already prints one line per `RunReport.tasks` entry and exits 1 when one did not pass.
- Tests: new tests in `tests/unit/test_run_plan.py` with the prefix `test_task072_`.
- Test edits that need approval (all in `tests/unit/test_run_plan.py`):
  - Mechanical: `FakePlans.tasks` also projects `attempt`, adding 1 to the task's initial `attempt` for each `TaskStateChanged` whose `to` is `running`, as the real projector does (SC-61).
  - `test_ac2_failed_and_escalated_tasks_do_not_stop_the_loop`: with the fixture's `max_attempts=2`, `AUTH-001` now ends `escalated` (attempts exhausted), not `failed`. The expected list `[S.failed, S.escalated, S.passed]` becomes `[S.escalated, S.escalated, S.passed]`. `taken()` is unchanged because there is one entry per task.
  - `test_ac3_no_promotion_after_a_task_that_did_not_pass`: the assertion `not [m for m in r.moves() if m[2] == "ready"]` now also catches `AUTH-001`'s `failed` to `ready`. It is narrowed to `pending` to `ready` moves. The intent (no promotion after a task that did not pass) is unchanged.
  - No other edit is expected. `test_cli_run.py` feeds `RunReport`s directly. `test_m3_close.py` has no failure that does not escalate in the loop, and its killed-run flow is settled by the repair, which this task leaves alone.

Out:
- Restart step 2 exceptions (`path_check`, `secret found` from `EventStore`) and step 3 (settling `failed` tasks, `interrupted` included): slice 10b. Until then a task the repair fails as `interrupted` stays `failed`, as today.
- The failure report in the context pack: slice 10c. Until then a retry's context pack is the same as the first attempt's.
- `resolve` (item 11), `status` (item 12), the M4 close test (item 13).
- Any change to `run_task`, `repair_plan`, events, payloads, schema, projector, ports or `cli.py`.

## Acceptance criteria
- [x] **AC1** ("Gates and remediation" › "Remediation": "the same command moves the task `failed` to `ready`, reason null, pointing at the `failed` event ..., when `attempt < limits.max_attempts`"):
  - After `run_task` leaves a task `failed` (for example `run error`, a failed gate, `no changes`, `git: ...`, `review`) and the projected `attempt` is less than `max_attempts`, the next event for the task is `failed` to `ready`, with a null reason, actor `orchestrator`, and `causation_id` the `failed` event's id.
- [x] **AC2** ("Remediation": "otherwise `failed` to `escalated` with reason `attempts exhausted`"):
  - When the projected `attempt` equals `max_attempts`, the next event is `failed` to `escalated` with reason `attempts exhausted`, pointing at the `failed` event.
  - The task is not taken again and its entry's state is `escalated`.
  - A task that `run_task` already escalated (path violation, secret found, cost limit) gets no further move.
- [x] **AC3** ("Execution" › "`run`": "A task that a failure moved back to `ready` ... is taken again in the same invocation by the same rule"; "Events of one task", `causation_id`):
  - Without `--task`, a task moved back to `ready` is taken again by the lowest-id rule, so a lower-id `ready` task goes first.
  - Its new `ready` to `running` points at the `failed` to `ready` event.
  - A task that fails once and then passes ends `passed`, and its dependents are promoted as after any pass.
- [x] **AC4** ("Execution" › "`run`": "`--task ID` runs that task only, its retries included"):
  - With `--task`, the named task is taken again after a `failed` to `ready` until it passes or escalates.
  - No other `ready` task is taken.
- [x] **AC5** ("CLI commands" › "Output": "a task taken again after a failure still has one line, at the position it was first taken", "the final state is the task's state when `run` leaves it"):
  - `RunReport.tasks` has one entry per task taken, in first-taken order, each holding the state and `last_event_id` of its last attempt.
  - Through the `run` command, a task that fails and then passes prints one `task_id  passed` line at its first position.
- [x] **AC6** ("Task state machine": "check every transition against `TRANSITIONS` before they record it"; ADR-011):
  - Both settling moves go through `_Chain.move`.
  - `app/run.py` imports nothing from `adapters` or `cli`.
  - The suite passes with only the approved test edits listed in Scope.

## Architecture rules that apply
- `app` depends on `domain` and `ports` only. `cli.py` does not change (ADR-011).
- All state changes go through the events table. `attempt` is read from the projection the recorder updated in the same transaction (ADR-010).
- `Plans` stays read-only (ADR-012).

## Plan
1. Create branch `task/TASK-072-run-retry-loop` from an up-to-date main.
2. Test-writer:
   - make the approved `FakePlans` `attempt` edit and the two approved assertion edits;
   - write failing tests for AC1 to AC4 and AC6 in `tests/unit/test_run_plan.py`, with a fake executor that fails a task's first N runs and then succeeds;
   - write the AC5 CLI check in `tests/integration/test_cli_run.py` (patched `run_plan` or fakes, as that file already does) or as a `run_plan` report test.
3. Add `_settle_failed` to `run.py`. Use it in `run_plan.take`, keep results per task id in first-taken order, and loop `--task` while the task is `ready`.
4. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
5. Update the living docs and the Outcome.
6. Commit `feat(app): retry a failed task in run until attempts run out` with the trailers `Task: TASK-072` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/app/run.py` (about +40)
- `tests/unit/test_run_plan.py` (approved edits about +10, new tests about +150)
- `tests/integration/test_cli_run.py` (about +20, if AC5 is checked there)
- `docs/architecture.md`: the `run_plan` paragraph gains the settling and the one-entry-per-task rule; the `TaskRunResult` note says `failed` is per attempt.
- `docs/progress.md`: Current is TASK-072; add the Done line; item 10 shrinks to 10b and 10c; add a Later line saying a retry's context pack has no failure report until 10c.
- `docs/tasks/TASK-072-run-retry-loop.md` (this record).

Not expected to change: `ports/`, `adapters/`, `cli.py`, `domain/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 220 lines with tests, about 40 of them in `src/`.

## Design choices to confirm at planning
1. Settle in `run_plan` (`take`), not inside `run_task`. `run_task` stays "one attempt", its 30+ tests stay unedited, and 10b can reuse the helper for Restart step 3. The events are the same either way: the `failed` to `ready` or `attempts exhausted` move follows the `failed` event and points at it.
2. Read `attempt` by re-reading `plans.tasks(plan.id)` after the `failed` event, as TASK-071 reads `cost_usd`. Do not compute `task.attempt + 1` locally. The spec's rule is stated on `attempt`, which is the projected column.
3. A later attempt's `TaskRunResult` replaces the first one's in `RunReport.tasks` (same position). That way the `warning` that `cli.py` prints is the final attempt's, which is the only attempt that can pass.

## Open questions
None blocking. The spec settles this slice. A retry's context pack without the failure report is a deliberate gap between slices (10c), not a spec question.

## Outcome
`_settle_failed(task, result, plan, plans, recorder)` was added to `src/openfactory/app/run.py`. `run_plan.take` settles every `failed` result from `run_task` and records the `failed` to `ready` event id in the causation map. Results are kept per task id in first-taken order, and `RunReport.tasks` is their values. With `--task`, the named task is taken while it is `ready`. `run_task`, `cli.py`, ports, adapters and domain are unchanged, and the `TaskRunResult` docstring now says `failed` is one attempt.

Test edits: only the three approved ones listed under Scope (`FakePlans.tasks` projects `attempt`; `test_ac2_failed_and_escalated_tasks_do_not_stop_the_loop` expects `[S.escalated, S.escalated, S.passed]`; `test_ac3_no_promotion_after_a_task_that_did_not_pass` narrowed to `pending` to `ready` moves). 10 new `test_task072_` tests in `tests/unit/test_run_plan.py`.

Notes:
- AC5 is covered as a `run_plan` report test, because `tests/integration/test_cli_run.py` feeds `RunReport`s directly and `cli.py` is unchanged.
- AC6's test is a source-text check (the settling moves go through `_Chain.move`; `app/run.py` imports nothing from `adapters` or `cli`).
- Until 10b a task the repair fails as `interrupted` stays `failed`; until 10c a retry's context pack has no failure report. Both are in progress.md under Later.
- Reviewer: approve, no blocking issues. Its note on two stale `docs/architecture.md` lines (the causation map, "that task runs once") was applied. Its notes on a behavioural AC6 check and an AC5 case where a retried task keeps its position after a later task ran are in progress.md under Later.
