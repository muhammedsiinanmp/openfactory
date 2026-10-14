# TASK-053: Run use case, one task: git failures, the soft reset and a failed removal after a pass

- Milestone: M3
- Status: done
- Tests: acceptance
- ADR: ADR-014 (accepted). "Execution (SC-56, SC-58, SC-60, SC-62, SC-65)" and the reading "no commit of the agent survives: the orchestrator resets the branch to `<base>` with the changes kept". No new port, adapter, dependency, event type, payload or storage change. `TaskRunResult` is an in-memory result model, not a payload. The answers to the open questions become rows in `docs/decisions.md`.
- Spec impact: wording. None of the items stops the plan, but Open questions 1 to 3 need the human's answer before tests are written (see "Spec gaps").
- Spec sections (spec v1.13, SC-56, SC-60, SC-65, SC-82): "Execution" › "Per-task sequence" (steps 1 and 6), "Base and branches", "The commit", "Events of one task" (bullets 4 to 6); "Task state machine"; "Milestones and definition of done" (item 3)

## Outline item
M3 outline item 1, second and last slice (after TASK-052). It covers:
- the soft reset when the branch tip is not `<base>`;
- a git command that fails while a task is `running` or `gating`;
- "when the worktree cannot be created, no run event is recorded";
- a worktree removal that fails after a pass (F-1, settled by SC-82 in v1.13).

Items 2 to 4 are left.

## Objective
Make `run_task` reset an agent's commits away, turn every `GitError` raised while the task is `running` or `gating` into a `failed` task with reason `git: <first line>`, and return a failed worktree removal after a pass as a warning line instead of raising.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08). Criteria trace to spec headings and SC numbers.

## Scope
In:
- `src/openfactory/app/run.py`:
  - **Base read.** It stays after `ready` to `running` is recorded. So a failing `head_commit()` on the repo falls under the `git:` reason (audit F-6 of `docs/spec-audits/2026-10-14-proposal-v1.13.md`). This record states that order.
  - **Soft reset** (Open question 1). After an `ok` exit, `running` to `gating` is recorded. Then `tip = git.head_commit(worktree)`. If `tip != base`, call `git.reset_soft(worktree, base)`. Both happen before `stage_changes`.
  - **Catching `GitError`.** `GitError` is caught around every `GitProvider` and `WorkspaceManager` call made while the task is `running` or `gating`. The task then moves to `failed` with reason `git: <first line of str(error)>`, and no further git call is made. When the failure comes before `AgentRunStarted` (the `head_commit()` base read, `remove`, `create` or `tracked_files`), no run event is recorded and the executor is not called.
  - **Failed removal after a pass.** `remove_worktree` after `gating` to `passed` is wrapped. A `GitError` there records nothing, the state stays `passed`, and the result carries the warning `worktree of <task id> not removed: <first line>` (Open question 3).
  - **New result field.** `TaskRunResult` gains `warning: str | None = None`.
  - **Helper.** A private `_first_line(error)` builds both the reason and the warning.
- `tests/unit/test_run_task.py`:
  - New tests for AC1 to AC5.
  - Edits to its fakes only, as proposed in Open question 2. No existing assertion line changes.

Out:
- Writing the warning to standard error, and its order against the task line. This belongs to `cli.py`, item 3; this record proposes the order (Open question 3).
- Step 1 of the Restart repair, its removal warning, the refusals, the loop and `--task` (item 2). That includes `git failed: <error>` before the repair, and the `--task` refusal after a warning (audit F-4).
- Removing the worktree or branch after a git failure. The next attempt's `remove` does it.
- Skipping `warning:` lines in git's error text (existing Later line, a spec decision).
- An error text whose first line is empty.
- Exceptions other than `GitError`.

## Acceptance criteria
Terms, fakes and the sample task are as in TASK-052. A `GitError` in the fakes has the text `fatal: boom\nhint: more`, so the reason is `git: fatal: boom`.

- [x] **AC1** ("The commit": "if the branch tip is not `<base>` when the agent exits, the orchestrator resets the branch to `<base>` with `git reset --soft`, which keeps the changes staged, so every commit on the branch is the orchestrator's"; SC-65)
  - When `head_commit(<worktree>)` gives a sha `T` ≠ `B`:
    - `reset_soft` is called once with the worktree path and `B`;
    - it comes after `running` to `gating` is recorded, and before `stage_changes` and `commit`;
    - the seven events of TASK-052 AC1 are recorded unchanged.
  - When the tip is `B`, `reset_soft` is not called.
- [x] **AC2** ("Events of one task": "A git command that fails while a task is `running` or `gating` moves the task to `failed` with reason `git: <first line of the error>`, and `run` goes on to the next task. When the worktree cannot be created, no run event is recorded"; SC-60)
  - This covers a `GitError` from any one of:
    - `head_commit()` on the repo, when the plan has no commit;
    - `workspace.remove`;
    - `workspace.create`;
    - `tracked_files`.
  - For each, exactly two events are recorded: `ready` to `running`, then `running` to `failed` with reason `git: fatal: boom`.
  - There is no `AgentRunStarted` or `AgentRunFinished`, and the executor is not called.
  - `run_task` returns, with `state` `failed`, `last_event_id` the id of the `failed` event, and `warning` `None`.
- [x] **AC3** (same bullet; "Per-task sequence" step 4; SC-60)
  - This covers a `GitError` from any one of:
    - `head_commit(<worktree>)` (the tip read);
    - `reset_soft` (with tip `T`);
    - `stage_changes`;
    - `commit`.
  - For each, the events end with `running` to `gating`, then `gating` to `failed` with reason `git: fatal: boom`.
  - There is no `CommitRecorded`, and `remove_worktree` is not called.
  - For `commit` only, the one `GateEvaluated` (`passed` true) comes before the `failed` event.
  - The result has `state` `failed`.
- [x] **AC4** ("Events of one task": "A worktree removal that fails after its task has moved to `passed` (step 6 of the per-task sequence ...) changes no state and records no event: `run` writes the warning `worktree of <task id> not removed: <first line of the error>` ... and goes on"; SC-82)
  - When `remove_worktree` raises:
    - exactly the seven events of TASK-052 AC1 are recorded;
    - `run_task` returns `state` `passed`, with `last_event_id` the `gating` to `passed` event;
    - `warning` is `worktree of AUTH-002 not removed: fatal: boom`.
  - With the defaults, `warning` is `None`.
- [x] **AC5** ("Events of one task": "`causation_id` is the `event_id` of the event recorded just before it for the same task"; "Task state machine": "The `run` use case checks every transition against `TRANSITIONS` before it records it"; SC-60)
  - In AC2 and AC3, the `failed` event's `causation_id` is the event before it.
  - Every existing test in `tests/unit/test_run_task.py` passes. Only the fakes were edited, as listed in Open question 2.
  - `app/run.py` still imports nothing from `openfactory.adapters` or `openfactory.cli`.

## Architecture rules that apply
- `app` depends on `domain` and `ports` only, does no I/O, and prints nothing. The warning is returned as data.
- All state changes go through `EventRecorder.record`, with each transition checked against `TRANSITIONS` by `_Chain.move`.
- No new dependency. Fixed tests are not weakened. Every fake edit is reported in Outcome and checked by the reviewer.

## Plan
1. Create branch `task/TASK-053-run-one-task-git-failures` from an up-to-date main.
2. Test-writer: edit the fakes in `tests/unit/test_run_task.py` (Open question 2), then add failing tests for AC1 to AC5.
3. Change `app/run.py`:
   - add the tip read and the reset;
   - add the `GitError` handling for the `running` and `gating` phases;
   - add the guarded `remove_worktree`;
   - add `TaskRunResult.warning` and `_first_line`;
   - update the module docstring (it says "A `GitError` from a port call propagates").
4. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
5. Update the living docs, the decisions rows and the Outcome. Commit `feat(app): fail a task on a git error and reset agent commits` with trailers `Task: TASK-053` and `Milestone: M3`.

## Files expected to change
- `src/openfactory/app/run.py` (about +45 lines)
- `tests/unit/test_run_task.py` (fakes about +20 lines; new tests about +170 lines)
- `docs/architecture.md` (section "Run use case: one task")
- `docs/progress.md` (Current; Done; outline item 1 removed; Later lines)
- `docs/decisions.md` (rows for Open questions 1 to 3 and for the F-5 and F-6 readings)
- `docs/tasks/TASK-053-run-one-task-git-failures.md` (this record)

Not expected to change: `cli.py`, `domain/`, `ports/`, `adapters/`, other tests, `pyproject.toml`, `docs/adr/`, `docs/spec/`. Expected size is about 235 lines of code and tests.

## Spec gaps
Spec impact is "wording". No item blocks planning, but each needs the human's answer (Open questions) before tests are written.

1. **"Execution" › "The commit"**, "if the branch tip is not `<base>` when the agent exits".
   - Unclear: whether this applies to every exit or only to `exit: ok`. Also unclear: whether the check runs before the path check, or only just before the commit of a pass.
   - With an `error` or `timeout` exit, a git failure in the reset would collide with the `run error` / `run timeout` reason.
   - Does not block: every reading makes the passed branch hold only the orchestrator's commit. Open question 1.
2. **"Execution" › "Events of one task"**, "`run` writes the warning ..." (audit F-5 of 2026-10-14; SC-82: "The spec does not name the layer that writes the warning").
   - Unclear: the form in which the use case returns the warning, and its order against the `task_id  passed` line. The two are on different streams.
   - Does not block: Open question 3.
3. **Audit F-6.** A git command after the repair while a task is still `ready` falls under no rule.
   - Settled for this task by order: the base is read after `ready` to `running` is recorded, so the `git:` reason applies. AC2 asserts it. No spec change.

Readings, not gaps:
- A `GitError` from `tracked_files` comes before `AgentRunStarted`, so like a failed `create` it leaves no run event. This follows from the order of steps 1 to 3.
- After a git failure the use case makes no further git call. The worktree and branch are removed by the next attempt's `remove` (step 1).
- `str(GitError)` is never empty (port docstring), so `_first_line` needs no fallback.

## Later lines in `docs/progress.md`: taken or left
- Taken, removed at close: "Until TASK-053 `run_task` lets every `GitError` propagate and does not reset a branch the agent committed on".
- Taken: the v1.13 audit's F-5 and F-6, which that Later line assigns to TASK-053. F-4 stays for item 2. F-1 ("that warning" wording) stays.
- Left: "`git warning:` line becomes `<error>`" (a spec decision); "`WorkspaceManager.remove` fails when the human's checkout is on `openfactory/<id>`"; the TASK-052 reviewer line on `test_ac5`; `gates/__init__.py`; all others.

## Open questions
1. **Where the soft reset goes.**
   - Proposed: only after an `ok` exit, after `running` to `gating` is recorded, and before `stage_changes`. It then also covers no-changes and escalated branches, which fits ADR-014's "every commit on a task branch is its own". A failure in it is a `gating` failure.
   - Alternative A: on every exit. Rejected because a reset failure after an `error` exit conflicts with `run error`.
   - Alternative B: only on a pass, just before `commit`. Fewer git calls, but an escalated branch keeps the agent's commit.
2. **Edits to the fixed TASK-052 fakes.** Needed: in `test_ac3_base_is_the_plans_latest_commit_when_it_has_one`, `FakeGit.head_commit` returns `BASE` for every call and `reset_soft` raises, so any tip read breaks the test (via `reset_soft` and `head_calls == 0`). Proposed changes, all to fakes, with no assertion line changed:
   - `FakeGit.head_commit` counts only repo reads (`worktree is None`) in `head_calls`. A worktree read returns a configurable `tip`, which defaults to the base the test runs with (`LATEST` when `latest` is set, else `BASE`).
   - `FakeGit.reset_soft` records its calls instead of raising.
   - `FakeGit` and `FakeWorkspace` take an optional "raise `GitError` from method X".
   Alternative: change the `head_calls == 0` assertion line to count repo reads (same intent, but edits an assertion).
3. **Form of the warning.**
   - Proposed: `TaskRunResult.warning: str | None = None` holds the whole line; `cli.py` writes it verbatim. For F-5, `cli.py` (item 3) writes a task's warning to standard error right after printing that task's line on standard output; recorded in `docs/decisions.md`, no test here.
   - Alternative: `worktree_error: str | None` with only the first line, and `cli.py` builds the sentence.
4. **Size.** About 235 lines with tests, within the aim. No split proposed.

Answers (human, 2026-10-14; advisor 4 AGREE of 4): all four proposed answers approved. Q1 records the narrowing to `exit: ok` explicitly in its `docs/decisions.md` row. Q2: the fake-only edit is approved, with a one-line comment on `head_calls` saying it counts repo reads only.

## Outcome
**Result.** 1244 tests pass; ruff, pyright and check_docs are clean. `run_task` fails a task with reason `git: <first line>` on a `GitError` while `running` or `gating`, soft-resets the branch to `<base>` after an `ok` exit when the tip differs, and returns a failed `remove_worktree` after a pass as `TaskRunResult.warning`. The four open questions were answered as proposed; the rows are in `docs/decisions.md`.

**Edits to the fixed TASK-052 tests** (fakes only, approved by the human; no existing assertion line changed):
- `head_calls` counts only repo reads (`worktree is None`), with a comment saying so.
- A worktree `head_commit` returns a configurable `tip`, defaulting to the base of the test.
- `reset_soft` records its calls instead of raising.
- `fail_in` options on `FakeGit` and `FakeWorkspace` raise `GitError` from a named method.
- A `Run` helper with the keyword arguments `tip`, `git_fails_in` and `workspace_fails_in`.
- `GitError`, `TIP` and `BOOM` added.

**AC5 imports.** No separate test was added for "`app/run.py` imports nothing from `adapters` or `cli`": the existing `test_ac6` covers it.

