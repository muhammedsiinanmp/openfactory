# TASK-073: Run use case, Restart steps 2 and 3: the `path_check` and `secret found` exceptions and settling `failed` tasks

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-015 (accepted). Its decision says "The failure report reads the task's last `failed` reason and its gate results from the task's stream through the existing `EventStore` port", which "is not" the projection-read case ADR-012 rejected. Its "Gates and retry" section says "Restart settles `failed` tasks, escalating those whose last `failed` reason escalates at once". This task adds no port, adapter, dependency, event type, payload, schema or convention. It only passes the existing `EventStore` port to `repair_plan` and `run_plan`.
- Spec impact: none
- Spec sections (spec v1.16; SC-112, SC-120):
  - "Execution" › "Restart", step 2: "Every other task in `running` or `gating` moves to `failed` with reason `interrupted`, except a `gating` task whose `GateEvaluated` events recorded after its last `running` to `gating` include a failed `path_check`, which moves to `failed` with reason `path_check`, and one whose events since then include a failed `gitleaks`, which moves to `failed` with reason `secret found` (any failed `gitleaks` result counts as a finding here, since `GateEvaluated` cannot tell them apart). These events are read from the task's stream through the `EventStore` port, as in step 3."
  - "Execution" › "Restart", step 3: "Every `failed` task, including those step 2 just failed, is settled, in ascending task id as strings: one whose last `failed` reason escalates at once (`path_check`, `secret found`, `cost limit`) moves to `escalated` with that escalation's reason (`path violation`, `secret found`, `cost limit`); the others follow the attempts rule of Remediation. The reason is read from the task's stream through the `EventStore` port."
  - "Execution" › "Restart", after the steps: "The events of the repair have no `causation_id` ... An interrupted attempt counts as an attempt."
  - "Gates and remediation" › "Remediation": "moves the task `failed` to `ready`, reason null, pointing at the `failed` event outside the repair (the repair's events have no `causation_id`), when `attempt < limits.max_attempts`; otherwise `failed` to `escalated` with reason `attempts exhausted` ... Every other failure reason retries this way: ... and `interrupted`."
  - "Execution" › "Events of one task": "The repair's events count as events of the same command, so the first event `run` records for a task the repair touched points at that task's last repair event."
  - "Execution" › "`run`": "A task that a failure moved back to `ready` (see Remediation) is taken again in the same invocation by the same rule"; "`<ID> is <state>, not ready`; these two refusals come after the repair".
  - "Task state machine": "The `run` and `resolve` use cases check every transition against `TRANSITIONS` before they record it".

## Outline item
M4 outline item 10, second slice (10b). The failure report in the context pack (10c) is the next task.

## Objective
`repair_plan` reads each task's stream through `EventStore`. It uses the stream to fail an interrupted `gating` task with `path_check` or `secret found` when its current gating already recorded such a failure. It then settles every `failed` task in ascending id: it escalates those whose last `failed` reason escalates at once and puts the others through `_settle_failed`'s attempts rule.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/app/run.py`:
  - `repair_plan` and `run_plan` gain a required keyword `events: EventStore` (`ports/event_store.py`). They only call `events.read(f"task:<id>")` and never `append`.
  - Step 2: for an uncommitted `gating` task, take the `GateEvaluated` events of its stream recorded after its last `TaskStateChanged` whose `to` is `gating`. If one has `gate` `path_check` and `passed` false, the reason is `path_check`. If one has `gate` `gitleaks` and `passed` false, the reason is `secret found`. Otherwise, and always for a `running` task, the reason is `interrupted`. The unfinished-run `AgentRunFinished` rule and its order are unchanged.
  - Step 3 is new, between step 2 and the promotion step. For every task now `failed`, in ascending id, read the `reason` of the last `TaskStateChanged` in its stream whose `to` is `failed`:
    - `path_check` moves `failed` to `escalated` with reason `path violation`;
    - `secret found` moves `failed` to `escalated` with reason `secret found`;
    - `cost limit` moves `failed` to `escalated` with reason `cost limit`;
    - any other reason goes through `_settle_failed` with no causation.
  - Every step-3 event has a null `causation_id`, updates `last_event_ids` and updates the repair's local task states.
  - `_settle_failed` is generalised so the repair can reuse it. New signature: `_settle_failed(task, causation_id: UUID | None, plan, plans, recorder) -> TaskRunResult`. It still reads `attempt` from `plans.tasks(plan.id)`, and its `_Chain` starts from state `failed`. `run_plan.take` passes `result.last_event_id`, so the events it records do not change.
  - The module docstring and the `repair_plan` docstring now cover steps 1 to 4.
- `src/openfactory/cli.py`: `run` opens `SqliteEventStore` on the same database, with `closing`, and passes it as `events=`. It is not added to `_Adapters`.
- Tests:
  - New tests with the prefix `test_task073_` in `tests/unit/test_repair_plan.py`, plus one or two in `tests/unit/test_run_plan.py`.
  - A fake `EventStore`, `FakeEvents(recorder, seeded=())`, whose `read(stream)` returns the seeded events and then the recorder's events of that stream, and whose `append` raises `AssertionError`.
- Test edits that need approval:
  - Mechanical:
    - Every `repair_plan(...)` call (the `Repair` helper) and every `run_plan(...)` call (`Run`, `test_ac2_repair_warnings_are_returned`, `_run_with_failing_removal`, `Retry`, `test_task072_ac2_already_escalated_task_gets_no_further_move`) gains `events=FakeEvents(recorder)`.
    - The `Repair` helper gains an optional `seeded` argument.
  - `tests/unit/test_repair_plan.py`. The fixtures use `attempt=0` and `max_attempts=2`, so a task step 2 fails as `interrupted` now also gets `failed` to `ready` (null reason):
    - `test_ac1_removal_failure_warns_and_goes_on`: add `("AUTH-003", "failed", "ready", None)` after AUTH-003's `failed` move.
    - `test_ac2_running_task_with_unfinished_run`: `first, second = r.events` becomes `first, second, third = r.events`, and the expected moves gain the `failed` to `ready` move.
    - `test_ac2_running_task_without_run_gets_only_failed`: `len(r.events) == 1` becomes `2`, and the moves gain `failed` to `ready`.
    - `test_ac2_gating_task_without_its_commit_fails`: the `no_commit.moves()` exact list gains `failed` to `ready`.
    - `test_ac3_promotes_pending_tasks_in_ascending_id`: AUTH-005 changes from `S.failed` to `S.escalated`. It must stay a dependency that has not passed, and a `failed` task is now settled.
    - `test_ac3_dependent_of_task_failed_in_step_2_is_not_promoted`: the moves gain `("AUTH-001", "failed", "ready", None)`. AUTH-002 is still not promoted.
    - `test_ac4_steps_run_in_order`: `["AUTH-003", "AUTH-002", "AUTH-001"]` becomes `["AUTH-003", "AUTH-002", "AUTH-002", "AUTH-001"]`.
    - `test_ac4_other_states_and_clean_plan_record_nothing`: drop `_task("AUTH-003", S.failed)`, since `failed` is no longer a state the repair leaves alone.
    - `test_ac5_events_are_orchestrator_with_no_causation`: `len(r.events) == 4` becomes `5`.
    - `test_ac6_last_event_ids_map_each_touched_task_to_its_last_event`: AUTH-001 maps to `r.events[2]` (its `failed` to `ready`) and AUTH-004 maps to `r.events[3]`.
  - `tests/unit/test_run_plan.py`:
    - `test_ac2_repair_first_then_ascending_loop_including_repair_promoted`: AUTH-005 is now repaired to `ready` and taken. `taken()` becomes `["AUTH-002", "AUTH-003", "AUTH-004", "AUTH-005"]` with four `passed`. `moves()[:3]` is AUTH-005 `running` to `failed` (`interrupted`), AUTH-005 `failed` to `ready`, then AUTH-003 `pending` to `ready`. `executor.calls` gains AUTH-005.
    - `test_ac2_no_ready_task_records_nothing`: AUTH-002 changes from `S.failed` to `S.escalated`.
    - `test_ac3_dependents_promoted_in_ascending_id_and_taken`: AUTH-009 changes from `S.failed` to `S.escalated`.
    - `test_ac5_unknown_task_keeps_repair_events_and_warnings`: the moves gain `("AUTH-001", "failed", "ready", None)` after AUTH-001's `failed` move.
    - `test_ac5_not_ready_reports_state_after_repair`: AUTH-001 gets `attempt=2` through `model_copy`, so the repair escalates it (`attempts exhausted`). `detail` changes from `"failed"` to `"escalated"`. The intent, a `--task` refusal that reports the state after the repair, is kept.
  - `tests/integration/test_m3_close.py`: no edit expected. Its killed runs stop before `gating` to `passed` with a `CommitRecorded`, so step 1 passes the task. If it fails, stop and report; do not edit it.

Out:
- The failure report in the context pack (10c).
- The cost-limit crash window (progress.md Later, TASK-071). Spec v1.16 repairs it as `interrupted`, and this task does not read `tasks.cost_usd` in the repair.
- `resolve` (item 11), `status` (item 12), the M4 close test (item 13).
- Any change to `run_task`, events, payloads, schema, projector, ports or adapters.
- A `failed` task with no `failed` event in its stream cannot happen, so it is not handled specially. It falls to the attempts rule and has no test.

## Acceptance criteria
- [x] **AC1** ("Restart", step 2, the `path_check` exception):
  - An uncommitted `gating` task has a `GateEvaluated` with gate `path_check` and `passed` false after its last `running` to `gating`. It moves `gating` to `failed` with reason `path_check`.
  - A failed `path_check` before that last `running` to `gating` (an earlier attempt) does not count, so that task gets `interrupted`.
  - A `running` task always gets `interrupted`.
- [x] **AC2** ("Restart", step 2, the `secret found` exception):
  - An uncommitted `gating` task has a `GateEvaluated` with gate `gitleaks` and `passed` false after its last `running` to `gating`. It moves to `failed` with reason `secret found`, whatever the other gates recorded.
  - With no such event the reason is `interrupted`.
  - The gate events are read through `EventStore.read("task:<id>")`, and the repair never calls `EventStore.append`.
- [x] **AC3** ("Restart", step 3, escalating at once):
  - A `failed` task whose last `failed` reason in its stream is `path_check`, `secret found` or `cost limit` moves `failed` to `escalated` with reason `path violation`, `secret found` or `cost limit`.
  - This covers a task step 2 just failed and a task already `failed` before the run, read from seeded stream events.
  - No `failed` to `ready` is recorded for such a task.
- [x] **AC4** ("Restart", step 3, the attempts rule; "Remediation"; "An interrupted attempt counts as an attempt"):
  - Every other `failed` task, `interrupted` included, moves `failed` to `ready` with a null reason when its projected `attempt < max_attempts`, otherwise `failed` to `escalated` with `attempts exhausted`.
  - This uses `_settle_failed`.
  - Tasks are settled in ascending task id, after all step-2 events and before any `pending` to `ready`.
  - Every step-3 event has actor `orchestrator` and a null `causation_id`.
  - A dependent of a task settled to `ready` or `escalated` is not promoted.
- [x] **AC5** ("Events of one task": "the first event `run` records for a task the repair touched points at that task's last repair event"; "`run`": "taken again in the same invocation"; the `--task` refusals):
  - A task the repair settled to `ready` is taken by `run_plan` in the same invocation, and its `ready` to `running` points at the repair's `failed` to `ready`.
  - `--task` on a task the repair escalated refuses `not_ready` with detail `escalated`, keeping the repair's events.
  - `last_event_ids` maps each settled task to its step-3 event.
  - `cli.py`'s `run` passes a `SqliteEventStore` on the project database as `events`.
- [x] **AC6** ("Task state machine"; ADR-011):
  - Every repair move, step 3 included, goes through `_Chain.move`.
  - `app/run.py` imports nothing from `adapters` or `cli`, and `EventStore` comes from `ports`.
  - The suite passes with only the approved test edits listed in Scope.

## Architecture rules that apply
- `app` depends on `domain` and `ports` only. `cli.py` alone imports `SqliteEventStore` (ADR-011).
- All state changes go through `EventRecorder.record`. `EventStore` is only read here (ADR-001, ADR-010).
- `attempt` comes from the `Plans` projection (ADR-012). Failure reasons and gate results, which no projection holds, come from the task's stream (ADR-015).

## Plan
1. Create branch `task/TASK-073-restart-settle-failed` from an up-to-date main.
2. Test-writer:
   - add `FakeEvents` and make the approved mechanical and assertion edits;
   - write failing `test_task073_` tests for AC1 to AC4 and AC6 in `tests/unit/test_repair_plan.py`, seeding `GateEvaluated` and `TaskStateChanged` events (including an earlier attempt's failed `path_check` for AC1);
   - write the AC5 tests in `tests/unit/test_run_plan.py`.
3. Generalise `_settle_failed` (causation and a start from `failed`) and update its caller in `run_plan.take`.
4. Add the step-2 stream read and step 3 to `repair_plan`. Thread `events` through `run_plan`. Wire `SqliteEventStore` in `cli.py`'s `run`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the living docs and the Outcome.
7. Commit `feat(app): settle failed tasks in the Restart repair` with the trailers `Task: TASK-073` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/app/run.py` (about +55)
- `src/openfactory/cli.py` (about +5)
- `tests/unit/test_repair_plan.py` (approved edits about +25, new tests about +120)
- `tests/unit/test_run_plan.py` (approved edits about +20, new tests about +40)
- `docs/architecture.md`: the `repair_plan` paragraph covers steps 2 and 3 and the `events` parameter; the `run_plan` signature; the `run` command wiring of `SqliteEventStore`; the `EventStore` callers line (repair as a reader).
- `docs/progress.md`:
  - Current is TASK-073, with a Done line;
  - item 10 shrinks to 10c;
  - the TASK-072 Later line drops its "stays `failed` until 10b" half;
  - the cost-limit crash-window line stays.
- `docs/tasks/TASK-073-restart-settle-failed.md` (this record).

Not expected to change: `ports/`, `adapters/`, `domain/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, `tests/integration/test_m3_close.py`.

Expected size: about 285 lines with tests, about 60 of them in `src/`.

## Design choices to confirm at planning
1. **`events: EventStore` is a required keyword of both `repair_plan` and `run_plan`,** as `gates` and `llm` were added. `cli.py` opens `SqliteEventStore` only in `run`, not in `_open_adapters`, so other commands open nothing new. Each recorder `record` commits in its own transaction (ADR-010), so a second connection sees the repair's step-2 events before step 3 reads them.
2. **`_settle_failed` takes `causation_id: UUID | None` instead of a `TaskRunResult`, and its chain starts from `failed`.** The repair needs a null causation. The repair's local states, not a re-read projection, say the task is `failed`. `attempt` is still read from `plans.tasks`; the repair records no `to running`, so its value is unchanged within the repair.
3. **Step 3 reads the reason from the stream for every `failed` task,** including those step 2 just failed, as the spec says. It does not reuse step 2's local reason.

## Open questions
None blocking. Spec v1.16 settles both steps. The spec-wording items already in Later about Restart's step order (TASK-054) and "that warning" (F-1) do not affect this slice.

## Outcome
Done on branch `task/TASK-073-restart-settle-failed`; commit pending. Final checks: 1541 passed, ruff, pyright and check_docs clean.

Implementation:
- `repair_plan` and `run_plan` take a required `events: EventStore`; the repair only calls `read`.
- Step 2: `_interrupted_reason` reads a `gating` task's stream after its last move to `gating` and gives `path_check`, `secret found` or `interrupted`. Step 3 reads the last `failed` reason; `_ESCALATES_AT_ONCE` maps `path_check`, `secret found` and `cost limit` to `path violation`, `secret found` and `cost limit`. Both validate payloads with `GateEvaluatedPayload.model_validate` and `TaskStateChangedPayload.model_validate`.
- `_settle_failed(task, causation_id, plan, plans, recorder)` starts its `_Chain` from `failed`; `run_plan.take` passes `result.last_event_id`, the repair passes `None`.
- `cli.py` `run` opens `SqliteEventStore` with `closing` beside `_open_adapters`; it is not in `_Adapters`.
- No ADR, decisions row or dependency was needed.

Test edits:
- (a) The mechanical and assertion edits listed in Scope, made by the test-writer, plus two extras by the test-writer: `FakeEvents` keeps a `reads` list, and `test_ac2_running_task_with_unfinished_run` gained `assert third.type == "TaskStateChanged"`.
- (b) One non-mechanical edit, approved by the human on 2026-10-21: in `test_task073_ac5_settled_to_ready_is_taken_pointing_at_the_repair_event`, `assert back.causation_id == r.move_event("AUTH-001", "running", "failed").event_id` became `assert back.causation_id is None`. Spec "Restart" says the repair's events have no `causation_id`, and AC4's test asserts that.
