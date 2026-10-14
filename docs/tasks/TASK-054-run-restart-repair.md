# TASK-054: Run use case, the Restart repair

- Milestone: M3
- Status: done
- Tests: acceptance
- ADR: ADR-014 (accepted). "Execution (SC-56, SC-58, SC-60, SC-62, SC-65)": "`run` starts with a repair made from the projections". This task adds no port, adapter, dependency, event type, payload or storage change. `RepairResult` is an in-memory result model, not a payload. The answers to the open questions become rows in `docs/decisions.md`.
- Spec impact: wording. Nothing here stops the plan; Open questions 2 to 4 were answered by the human before tests were written (see "Answers" and "Spec gaps").
- Spec sections (spec v1.13, SC-62, SC-82, SC-83):
  - "Execution": "Restart" (steps 1 to 3 and the paragraph after them), "Events of one task" (the removal-warning bullet, the null-`reason` bullet and the `causation_id` bullet), "Base and branches";
  - "Task state machine";
  - "Domain model and storage" › "Streams and actors", "Event payloads" (`AgentRunFinished`).

## Outline item
M3 outline item 1, first of two slices (Open question 1). This task covers only "the repair".

Left for TASK-055:
- the refusals;
- the loop, lowest ready task id first;
- promotion after a pass;
- `--task ID`.

Outline items 2 and 3 are unchanged.

## Objective
Give `app` one function that repairs the approved plan from the projections, as in "Restart", records the repair's events, and returns the repair's warnings as data.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08). Criteria trace to spec headings and SC numbers.

## Scope
In:
- `src/openfactory/app/run.py` (Open question 2):
  - **Entry point.** `repair_plan(plan: PlanRef, *, workspace: WorkspaceManager, runs: Runs, plans: Plans, recorder: EventRecorder) -> RepairResult`. It reads the tasks once with `plans.tasks(plan.id)` and the plan's newest commit once with `plans.latest_commit(plan.id)`.
  - **Step 1.** It works through the tasks in ascending id. A task in `gating` is one "that has a `CommitRecorded`" when `latest_commit` is not `None` and its `task_id` is that task (Open question 3).
    - Record `gating` to `passed`, then call `workspace.remove_worktree(task.id)`; the branch stays.
    - A `GitError` from that call records nothing. It adds `worktree of <task id> not removed: <first line>` to the warnings, and the repair goes on.
  - **Step 2.** Every other task in `running` or `gating`, in ascending id.
    - If `runs.unfinished_run(task.id)` gives a run id, record `AgentRunFinished` on `run:<run id>` with `exit` `error`, `error` `interrupted`, `duration_s` 0, and null `model`, `tokens_in`, `tokens_out` and `cost_usd`.
    - Then record `TaskStateChanged` to `failed` with reason `interrupted`.
  - **Step 3.** Every `pending` task with no dependencies, or whose dependencies are all `passed`, moves to `ready`, in ascending id. A task that step 1 moved to `passed` counts as passed.
    - A private `_promotable(tasks)` gives these ids. TASK-055 reuses it for promotion after a pass.
  - **Event details.**
    - Every event has actor `orchestrator` and a null `causation_id`, including the second event of a task in step 2.
    - Every transition is checked against `TRANSITIONS` through `_Chain.move`, using a chain with no causation for each event.
    - A `TaskStateChanged` other than `interrupted` has a null `reason`.
  - **`RepairResult`** (frozen, `extra="forbid"`):
    - `warnings: list[str]`, in the order they arose;
    - `last_event_ids: dict[str, UUID]`, which maps each task the repair recorded an event for to the id of its last repair event (Open question 4).
- `tests/unit/test_repair_plan.py` (new): in-memory fakes of `Plans`, `Runs`, `WorkspaceManager` and `EventRecorder`.

Out:
- The refusals, the loop, promotion after a pass, `--task` and its refusals (audit F-4). These are TASK-055.
- The `run` command, and writing the warnings to standard error (outline item 2).
- A worktree left by a run killed after `passed` (audit F-7: accepted as harmless).
- Exceptions other than `GitError`, and a recorder that raises.
- The repair does not take `GitProvider` or `AgentExecutor`. The spec's "git failed" refusal covers git commands before the repair, which is TASK-055's job.

## Acceptance criteria
In the fakes, a `GitError` has the text `fatal: boom\nhint: more`. Events are compared in recorded order.

- [ ] **AC1** ("Restart" step 1: "A task in `gating` that has a `CommitRecorded` moves to `passed`, and its worktree is removed"; "Events of one task": "A worktree removal that fails after its task has moved to `passed` (... or step 1 of Restart) changes no state and records no event: `run` writes the warning `worktree of <task id> not removed: <first line of the error>` ... and goes on"; SC-62, SC-82)
  - Setup: a `gating` task that is `latest_commit`'s task.
  - Exactly one event is recorded for it, `gating` to `passed` with a null `reason`.
  - After that event, `remove_worktree` is called once with its id. `remove` is not called.
  - When `remove_worktree` raises:
    - the same single event is recorded;
    - `warnings` is `["worktree of AUTH-002 not removed: fatal: boom"]`;
    - the repair still runs steps 2 and 3.
  - With no failure, `warnings` is empty.
- [ ] **AC2** ("Restart" step 2: "Every other task in `running` or `gating` moves to `failed` with reason `interrupted`. If it has an unfinished run, that run gets `AgentRunFinished` with `exit: error`, `error: interrupted`, `duration_s: 0` and null in the other nullable fields. `AgentRunFinished` is recorded first, then the `TaskStateChanged`"; SC-83)
  - A `running` task with an unfinished run `run_0003` gets two events, in this order:
    - an `AgentRunFinished` on stream `run:run_0003` with exactly that payload;
    - `running` to `failed` with reason `interrupted`.
  - A `running` task with no unfinished run gets only the `failed` event.
  - A `gating` task that is not `latest_commit`'s task gets `gating` to `failed` with reason `interrupted`. This includes the case where the plan has no commit.
- [ ] **AC3** ("Restart" step 3: "Every `pending` task that has no dependencies, or whose dependencies have all passed, moves to `ready`, in ascending task id as strings"; SC-62)
  - Each such task gets `pending` to `ready` with a null `reason`, in ascending id.
  - A dependent of a task that step 1 moved to `passed` is promoted.
  - A `pending` task with a dependency that is not `passed` gets no event. This includes a dependency failed in step 2.
- [ ] **AC4** ("Restart": "in this order"; "Task state machine": every transition checked against `TRANSITIONS`; SC-62)
  - With one task needing each step, all step-1 events come before all step-2 events, and those come before all step-3 events.
  - Tasks in `ready`, `passed`, `failed`, `escalated`, `abandoned` or `invalidated` get no event.
  - A plan that needs no repair records nothing and makes no `WorkspaceManager` call.
- [ ] **AC5** ("Restart": "The events of the repair have no `causation_id`"; "Domain model and storage" › "Streams and actors")
  - Every repair event has actor `orchestrator` and `causation_id` `None`. This includes the `failed` event that follows an `AgentRunFinished`.
  - `TaskStateChanged` events are on `task:<task id>`.
- [ ] **AC6** ("Events of one task": "`causation_id` is the `event_id` of the event recorded just before it for the same task in the same command"; Open question 4)
  - `last_event_ids` maps each task the repair recorded an event for to its last repair event's id: for a step-2 task, the `failed` event.
  - It has no other keys.
  - `app/run.py` still imports nothing from `openfactory.adapters` or `openfactory.cli`. The existing `test_ac6` covers this; every existing test in `tests/unit/test_run_task.py` passes unchanged.

## Architecture rules that apply
- `app` depends on `domain` and `ports` only. It does no I/O and prints nothing; the warnings are returned as data.
- All state changes go through `EventRecorder.record`.
- No new dependency. Fixed tests are not edited.

## Plan
1. Create branch `task/TASK-054-run-restart-repair` from an up-to-date main.
2. Test-writer: write `tests/unit/test_repair_plan.py` with failing tests for AC1 to AC6.
3. In `app/run.py`:
   - add `RepairResult`, `_promotable` and `repair_plan`, reusing `_Chain` and `_first_line`;
   - extend the module docstring to name "Restart".
4. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
5. Update the docs:
   - `docs/architecture.md`: "Run use case" section, plus the lines saying nothing calls `unfinished_run` and the repair does not call `WorkspaceManager` yet;
   - `docs/progress.md`;
   - `docs/decisions.md` rows;
   - this record's Outcome.
6. Commit `feat(app): repair the approved plan before a run` with trailers `Task: TASK-054` and `Milestone: M3`.

## Files expected to change
- `src/openfactory/app/run.py` (about +65 lines)
- `tests/unit/test_repair_plan.py` (new, about +220 lines)
- `docs/architecture.md`
- `docs/progress.md`:
  - Current and Done;
  - the outline: item 1 narrowed to TASK-055's part;
  - Later: the TASK-042 reviewer line on `latest_commit` is taken.
- `docs/decisions.md`
- `docs/tasks/TASK-054-run-restart-repair.md`

Not expected to change: `cli.py`, `domain/`, `ports/`, `adapters/`, existing tests, `pyproject.toml`, `docs/adr/`, `docs/spec/`. Expected size is about 285 lines of code and tests.

## Spec gaps
Spec impact is "wording". No item blocks planning.

1. **"Execution" › "Restart"**, "A task in `gating` that has a `CommitRecorded`".
   - Unclear: the spec gives no read for this, and the ports give only `Plans.latest_commit`.
   - Does not block. Execution is a single chain and only one `run` works at a time. A `gating` task can hold a `CommitRecorded` only when `run` was interrupted between `CommitRecorded` and `gating` to `passed`, so that commit has the plan's highest run id. Open question 3.
2. **"Execution" › "Restart"**: the order of tasks within steps 1 and 2 is not stated. Only step 3 says "ascending task id".
   - Does not block. Ascending id is proposed for all three steps, and no event of the repair depends on another task's event.
3. **"Execution" › "Events of one task"**, the `causation_id` bullet, read with "The events of the repair have no `causation_id`".
   - Unclear: whether the first `ready` to `running` of a task promoted in step 3 points at that task's repair event. Literally, the repair event is "the event recorded just before it for the same task in the same command".
   - Does not block this task, which only returns the ids. TASK-055 decides how to use them. Open question 4.
4. **Audit F-1 (2026-10-14)**: "that warning" in "Restart" has no antecedent. This is a known Later line. It is read here as the removal warning of "Events of one task", and is left for a `/spec-change`.

Readings, not gaps:
- In step 1, "its worktree is removed" means `remove_worktree`, which keeps the branch, as in per-task step 6. The branch holds the task's commit.
- An interrupted attempt already counts as an attempt: `ready` to `running` raised `tasks.attempt` (SC-61). The repair adds nothing for it.

## Later lines in `docs/progress.md`: taken or left
- Taken: "`Plans.latest_commit` gives only the plan's newest commit ... the run use case task states that reasoning or adds a per-task read" (TASK-042, reviewer). This record states the reasoning (Spec gap 1).
- Left for TASK-055:
  - "`run_task` on a repo with no commit ... raises `AssertionError`";
  - audit F-4, the `--task` refusal after a warning.
- Left: F-1 wording; F-7, accepted; all others.

## Answers (human, 2026-10-14)
All five proposed answers approved, advisor 5 AGREE:
1. Split: TASK-054 is the repair; TASK-055 the refusals, the loop, promotion after a pass and `--task`.
2. `repair_plan` lives in `app/run.py`.
3. Step 1 uses `Plans.latest_commit(plan.id).task_id`, under the single-chain reasoning; no port change.
4. `RepairResult.last_event_ids` as proposed. The literal reading is settled now: the first `ready` to `running` of a task promoted by the repair has `causation_id` = that task's last repair event id. TASK-055 follows this rule. Recorded in `docs/decisions.md`.
5. Size accepted, no further split.

## Open questions (as planned)
1. **Split of outline item 1.**
   - Proposed: TASK-054 is the repair, and TASK-055 is the refusals, the loop, promotion after a pass and `--task`, reusing `_promotable` and `repair_plan`.
   - Alternative: one task for all of item 1, about 550 lines.
2. **Where `repair_plan` lives.**
   - Proposed: in `app/run.py`, beside `run_task`, reusing the private `_Chain` and `_first_line`. The module grows to about 285 lines, and TASK-055's loop goes there too.
   - Alternative: a new `app/repair.py`, which would make `_Chain` public or duplicate it.
3. **How step 1 finds "a task in `gating` that has a `CommitRecorded`".**
   - Proposed: through `Plans.latest_commit(plan.id).task_id`, under the single-chain reasoning in Spec gap 1. No port change.
   - Alternative: a new per-task read, `Plans.has_commit(task_id)`. It is a port change and edits the exact method-set test.
4. **The ids the repair returns.**
   - Proposed: `RepairResult.last_event_ids` maps each task with a repair event to its last repair event's id. TASK-055 can then choose to point a promoted task's first `ready` to `running` at it, following the literal `causation_id` rule.
   - Alternative: return only `warnings`. TASK-055 then gives the first loop event of a promoted task no causation, which needs a spec reading recorded in `docs/decisions.md`.
5. **Size.** About 285 lines with tests, within the aim. No further split proposed.

## Outcome
Built `RepairResult`, `_promotable` and `repair_plan` in `src/openfactory/app/run.py` (steps 1 to 3 of "Restart", ascending task id, null causation, transitions through `_Chain.move`), and `tests/unit/test_repair_plan.py` (13 tests, written by the test-writer). Step 1 uses `Plans.latest_commit(plan.id).task_id` (no port change). Updated `docs/architecture.md`, `docs/decisions.md` (five rows) and `docs/progress.md`.

- Checks: pytest (1256 tests pass), ruff, pyright and check_docs all green.
- Test edits: none.
- Deviations from the plan: none.
