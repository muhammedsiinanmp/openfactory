# TASK-055: Run use case, the loop

- Milestone: M3
- Status: done
- Tests: acceptance
- ADR: ADR-014 (accepted) covers the run use case. This task adds no port, adapter, dependency, event type, payload or storage change. The result model is in memory, not a payload. It reads the existing `SpecVersions.spec_set` and `Plans.approved`. Answers to the open questions become rows in `docs/decisions.md`.
- Spec impact: wording. Nothing stops the plan (see "Spec gaps").
- Spec sections (spec v1.13; SC-55, SC-60, SC-62, SC-72, SC-73, SC-82):
  - "Execution" › "`run`" (all bullets), "Events of one task" (the `causation_id` bullet and the removal-warning bullet), "Restart" (only as the step `run` calls), "Base and branches";
  - "Task state machine";
  - "CLI commands" › "Output", the `run` bullet (only the data the command will need; printing is outline item 2).

## Outline item
M3 outline item 1, second of two slices. TASK-054 did the repair. This task does:
- the refusals;
- the loop, lowest ready task id first;
- promotion after a pass;
- `--task ID`.

Outline items 2 (`run` command) and 3 (M3 close) are unchanged.

## Objective
Give `app` one entry point for `run`. It checks the refusals, repairs the plan, takes `ready` tasks one at a time (lowest id first, or only `--task ID`), promotes `pending` tasks after each pass, and returns refusals, warnings and task results as data.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In: `src/openfactory/app/run.py`.

**Entry point** (names are Open question 1):

```python
run_plan(*, task_id: str | None = None, git: GitProvider, workspace: WorkspaceManager,
         executor: AgentExecutor, run_files: RunFiles, runs: Runs, plans: Plans,
         versions: SpecVersions, recorder: EventRecorder) -> RunReport
```

**Refusals before any event**, in this order:
1. `plans.approved()` is `None`: refusal `no_approved_plan`.
2. `git.head_commit()` is `None`: refusal `no_commit`.
3. `git.head_commit()` raises `GitError`: refusal `git_failed`, carrying the error's first line.

None of the three records an event or calls `WorkspaceManager`. Refusal 1 makes no git call.

**Then:**
- `repair_plan(plan, ...)` runs, unchanged.
- The spec set is read once with `versions.spec_set(plan.spec_version)`: the plan's spec version, whatever the latest approved version is (SC-73).

**Loop, with no `task_id`:**
- Re-read `plans.tasks(plan.id)` (Open question 2).
- Take the `ready` task with the lowest id as a string and call `run_task`. Its `causation_id` is the task's entry in the causation map, else `None`.
- After a pass, record `pending` to `ready` for each id `_promotable` gives, in ascending id. Each points at the passing task's `gating` to `passed` event (`TaskRunResult.last_event_id`). Each promoted task's event id goes into the causation map.
- Repeat until no task is `ready`.
- A task that does not pass does not stop the loop.

**The causation map** starts as `RepairResult.last_event_ids`. This follows the TASK-054 answer 4: a task the repair promoted points its first `ready` to `running` at its last repair event.

**With `task_id`:**
- After the repair, re-read the tasks.
- The plan has no such task: refusal `unknown_task`.
- The task is not `ready`: refusal `not_ready` with its state.
- Otherwise `run_task` runs on it once, and the promotion after a pass is recorded. The promoted tasks are not taken.

**`RunReport`** (frozen, `extra="forbid"`; Open question 3):
- `refusal: RunRefusal | None`, a `StrEnum` with the five values above;
- `detail: str | None`: the git first line, the unknown id, or the state;
- `warnings: list[str]`: the repair's warnings;
- `tasks: list[TaskRunResult]`: in the order taken. Each result keeps its own `warning`, written after its task line (TASK-053 decision).

**Tests:** `tests/unit/test_run_plan.py` (new). It uses in-memory fakes of the eight ports. The fake `Plans` reflects the `TaskStateChanged` events the fake recorder has stored, so re-reads see current states.

Out:
- The `run` command: lines, exit codes, writing the warnings and refusals (outline item 2).
- `repair_plan` and `run_task` behaviour. Both are unchanged.
- The `assert base is not None` in `run_task` is kept. `run_plan` cannot reach it, because refusal `no_commit` comes first.
- Retries and `failed` to `ready` (M4).
- Exceptions other than `GitError`, and a missing stored spec set.

## Acceptance criteria
The fakes give tasks out of id order (Later line, TASK-054 reviewer). In the fakes, a `GitError` has the text `fatal: boom\nhint: more`.

- [x] **AC1** ("Execution" › "`run`": "It refuses with one line on standard error and exits 1, before any event. The refusals, checked in this order: `no approved plan`; `repository has no commit`, when `HEAD` points at no commit; `git failed: <error>`, when a git command fails before the repair, with `<error>` the first line of the failure's text"; SC-72, SC-82)
  - No approved plan gives `no_approved_plan` and makes no git call.
  - `head_commit` `None` gives `no_commit`. This holds even when the plan has a commit.
  - `head_commit` raising gives `git_failed` with `detail` `fatal: boom`.
  - Each of the three records no event, makes no `WorkspaceManager` or executor call, and has empty `warnings` and `tasks`.
- [x] **AC2** ("Execution" › "`run`": "It then repairs the plan"; "repeatedly takes the `ready` task with the lowest task id, as strings, one at a time"; "A task that does not pass does not stop the others"; "works on the approved plan, whatever the latest approved spec version is"; SC-55, SC-73)
  - The repair's events come before any loop event, and its warnings are in `RunReport.warnings`.
  - `ready` tasks are taken in ascending id, each once. This includes tasks given unsorted and a task the repair promoted.
  - A failed or escalated task is followed by the next `ready` task.
  - `tasks` lists the results in the order taken.
  - `run_task` gets the spec set of `plan.spec_version`, even when a newer version is approved.
  - With no `ready` task, `tasks` is empty and no loop event is recorded.
- [x] **AC3** ("Execution" › "`run`": "After a task passes, every `pending` task of the plan whose dependencies have all passed moves to `ready`, in ascending task id as strings, and is taken in the same invocation"; "Events of one task": "a `pending` to `ready` event recorded after a pass ... points at the `gating` to `passed` event of the task that passed")
  - After a pass, each newly promotable task gets `pending` to `ready` with a null `reason`, in ascending id, with `causation_id` the passing task's `last_event_id`.
  - These tasks are then taken in the same call.
  - A task whose dependencies include one that failed is not promoted.
  - No promotion follows a task that did not pass.
- [x] **AC4** ("Events of one task": "`causation_id` is the `event_id` of the event recorded just before it for the same task in the same command; the first event of a task in a command has none"; TASK-054 answer 4)
  - A task promoted by the repair gets `ready` to `running` pointing at its repair `pending` to `ready` event.
  - A task promoted after a pass gets `ready` to `running` pointing at that `pending` to `ready` event.
  - A task that was already `ready`, with no event earlier in the command, gets `ready` to `running` with a null `causation_id`.
- [x] **AC5** ("Execution" › "`run`": "`--task ID` runs that task only. After the repair it refuses with `unknown task <ID>` when the approved plan has no such task, or `<ID> is <state>, not ready`. The tasks its pass makes `ready` are moved to `ready` and not taken")
  - An unknown id gives `unknown_task` with `detail` the id, after the repair's events and with its `warnings` (audit F-4).
  - A task that is not `ready` gives `not_ready` with `detail` its state after the repair. Example: `failed` for a task interrupted in `running`.
  - A refusal leaves `tasks` empty.
  - A `ready` id runs only that task, even when a lower id is `ready`. After its pass, its dependents get their `pending` to `ready` events but are not taken; `tasks` has one entry.
- [x] **AC6** ("Task state machine": "The `run` use case checks every transition against `TRANSITIONS` before it records it"; "Domain model and storage" › "Streams and actors")
  - Every `pending` to `ready` the loop records goes through `_Chain.move`, on `task:<id>` with actor `orchestrator`.
  - `app/run.py` still imports nothing from `openfactory.adapters` or `openfactory.cli`.
  - Every existing test in `tests/unit/test_run_task.py` and `tests/unit/test_repair_plan.py` passes unchanged.

## Architecture rules that apply
- `app` depends on `domain` and `ports` only. It prints nothing; refusals and warnings are returned as data.
- All state changes go through `EventRecorder.record`.
- No new dependency. Fixed tests are not edited.

## Plan
1. Create branch `task/TASK-055-run-loop` from an up-to-date main.
2. Test-writer: write `tests/unit/test_run_plan.py` with failing tests for AC1 to AC6, feeding tasks unsorted.
3. In `app/run.py`:
   - add `RunRefusal`, `RunReport` and `run_plan`, reusing `_Chain`, `_first_line`, `_promotable`, `repair_plan` and `run_task`;
   - extend the module docstring.
4. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
5. Update the docs:
   - `docs/architecture.md`: a new "Run use case: the loop" section, and the lines saying nothing calls `repair_plan` or `run_task` yet;
   - `docs/decisions.md`: rows for the answers;
   - `docs/progress.md`;
   - this record's Outcome.
6. Commit `feat(app): run the ready tasks of the approved plan` with trailers `Task: TASK-055` and `Milestone: M3`.

## Files expected to change
- `src/openfactory/app/run.py` (about +80 lines)
- `tests/unit/test_run_plan.py` (new, about +250 lines)
- `docs/architecture.md`
- `docs/decisions.md`
- `docs/progress.md`:
  - Current and Done;
  - remove outline item 1;
  - Later: the TASK-054 reviewer line is taken, and the TASK-053 `assert base is not None` line is closed by refusal `no_commit`.
- `docs/tasks/TASK-055-run-loop.md`

Not expected to change: `cli.py`, `domain/`, `ports/`, `adapters/`, existing tests, `pyproject.toml`, `docs/adr/`, `docs/spec/`. Expected size is about 330 lines of code and tests.

## Spec gaps
Spec impact is "wording". No item blocks.

1. **"Execution" › "`run`"**: "refuses with one line on standard error and exits 1, before any event" (audit F-4).
   - Unclear: the `--task` refusals come "After the repair". So the repair's events are already recorded, and its removal warning may already be on standard error, giving two lines.
   - Does not block. The sentence is read as covering the first three refusals only. The `--task` refusals keep the repair's events and warnings (AC5). F-4 proposed no spec change.
2. **"Execution" › "`run`"**: "`repository has no commit`, when `HEAD` points at no commit".
   - Unclear: the text does not say whether this applies when the plan already has a commit (its `<base>` then comes from `commits`, not `HEAD`).
   - Does not block. It is read literally: the check always runs. This also closes the Later line on `assert base is not None` in `run_task`.
3. **"Events of one task"**, the `causation_id` bullet.
   - Settled by the TASK-054 answer 4. AC4 applies it. Listed so it is not raised again.

Readings, not gaps:
- "takes ... one at a time" with "A task that does not pass does not stop the others": `failed` stays `failed` until M4, so each task is taken at most once per invocation and the loop ends.
- "`<ID> is <state>, not ready`": `<state>` is the state after the repair.

## Later lines in `docs/progress.md`: taken or left
- Taken:
  - feed tasks unsorted in loop tests (TASK-054, reviewer);
  - audit F-4, recorded here (Spec gap 1, AC5);
  - `run_task` `assert base is not None` on a repo with no commit (TASK-053, reviewer), closed by refusal `no_commit` (Spec gap 2).
- Left: the TASK-053 reviewer line on no further git call after a `GitError`; F-1 wording; all others.

## Open questions
1. **Names.** Proposed: `run_plan`, `RunReport` and `RunRefusal`, all in `app/run.py`. `RunResult` is avoided because the domain already uses it for an agent run.
2. **How the loop sees states after events.** Proposed: re-read `plans.tasks(plan.id)` after the repair and after each task. The recorder updates the projections in the same transaction (ADR-010), so the projections stay the source. The test fake `Plans` derives states from the fake recorder's `TaskStateChanged` events. Alternative: track states in memory, which needs `RepairResult` to return the repaired tasks; that is a change to a TASK-054 model.
3. **Refusal shape.** Proposed: an enum plus a `detail` string, with the lines built in `cli.py` (outline item 2), as `prepare_plan` / `PlanRefusal` do. Alternative: the use case returns the finished refusal line.
4. **`no_commit` when the plan has a commit.** Proposed: always checked, the literal reading (Spec gap 2).
5. **`--task` refusals after the repair.** Proposed: the repair's events stay recorded and its warnings are returned with the refusal (F-4). The command task then writes the warnings before the refusal line.
6. **Size.** About 330 lines, a little over the ~300 aim. Proposed: keep one task. A split (refusals and loop, then `--task`) would put about 100 lines in a second task that reuses the same fakes.

Answers (human, 2026-10-14; advisor 6 AGREE of 6): all six proposed answers accepted.

## Outcome
- `RunRefusal`, `RunReport` and `run_plan` added to `src/openfactory/app/run.py`, reusing `_Chain`, `_first_line`, `_promotable`, `repair_plan` and `run_task`. All six open questions were answered as proposed (2026-10-14); rows are in `docs/decisions.md`.
- `tests/unit/test_run_plan.py` (new, 17 tests) covers AC1 to AC6. No test-writer test was edited; no existing test changed.
- `run_plan` asserts the stored spec set of the plan's spec version is not `None`; a missing spec set stays out of scope.
- After review (non-blocking notes, applied at the human's "do as you would do"): the `not_ready` detail is `task.state.value`, a plain string; the two untested points (repair warnings on a `--task` refusal, the spec set assert) are Later lines in `docs/progress.md`.
- Test-writer's stated gaps: the AC5 unknown-task test does not assert the repair warnings; AC6 `_Chain.move` is checked by observable result only (events on `task:<id>`, actor `orchestrator`).
- Docs: `docs/architecture.md` (new "Run use case: the loop"; stale "nothing calls it" lines fixed), `docs/decisions.md`, `docs/progress.md`.
- Later lines: the TASK-054 reviewer "unsorted" line is taken; the TASK-053 `assert base is not None` line is closed by refusal `no_commit`.
- ADR: none needed.
