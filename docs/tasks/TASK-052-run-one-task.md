# TASK-052: Run use case, one task: the sequence from the agent's result

- Milestone: M3
- Status: done
- Tests: acceptance
- ADR: ADR-014 (accepted). "Execution (SC-56, SC-58, SC-60, SC-62, SC-65)" and Consequences: "`app` gets the `run` use case with no I/O of its own". No new port, adapter, dependency, event type, payload or storage change. The module name, the signature, the result model and the answers to the open questions are rows in `docs/decisions.md`.
- Spec impact: wording. Two new items and one known group, none stops the task. One gap (audit F-1) blocks the next slice, not this one (see "Spec gaps").
- Spec sections (spec v1.12, SC-54, SC-58, SC-60): "Execution" › "Per-task sequence", "Base and branches", "The path check", "The commit", "Events of one task", "Adapter interface"; "Task state machine"; "Domain model and storage" › "Streams and actors", "Event payloads"; "Gates and remediation"; "Milestones and definition of done" (item 3)

## Outline item
M3 outline item 1, first of two slices. Left in item 1, planned as TASK-053:
- the soft reset when the branch tip is not `<base>` ("The commit");
- a git command that fails while a task is `running` or `gating` (reason `git: <first line of the error>`);
- "When the worktree cannot be created, no run event is recorded";
- a worktree removal that fails after the task has passed (audit F-1, a spec gap).

Items 2 to 4 are left.

## Objective
Give `app` one function that runs the per-task sequence on one `ready` task and records its events for the four outcomes that follow from the agent's result: passed, failed process, no changes and path violation.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings and to SC-54, SC-58 and SC-60.

## Prerequisite
None. No `claude` call and no git call: the tests use in-memory fakes of the ports.

## Scope
In:
- `src/openfactory/app/run.py` (new). It imports from `openfactory.domain`, `openfactory.ports`, `app/context_pack.py` and `app/planner_prompt.py` (`context_hash`, decision of 2026-10-14). It returns data and prints nothing.
- `run_task(task: Task, plan: PlanRef, spec: SpecSet, *, causation_id: UUID | None = None, git: GitProvider, workspace: WorkspaceManager, executor: AgentExecutor, run_files: RunFiles, runs: Runs, plans: Plans, recorder: EventRecorder) -> TaskRunResult` (Open question 5).
  - `spec` is the stored set of the plan's spec version. The caller (outline item 2) reads it once with `SpecVersions.spec_set`.
  - `causation_id` is the id of the event recorded just before for this task in the same command, or `None`. Outline item 2 decides what it passes.
- `TaskRunResult` (frozen, `extra="forbid"`): `task_id`, `state` (`passed`, `failed` or `escalated`) and `last_event_id` (the last event recorded for the task; for a pass, the `gating` to `passed` event that a promotion points at).
- The sequence, in this order:
  1. Record `ready` to `running`.
  2. `<base>` is `plans.latest_commit(plan.id).sha`, or `git.head_commit()` when the plan has no commit.
  3. `workspace.remove(task.id)`, then `worktree = workspace.create(task.id, base)`.
  4. `pack = build_context_pack(task.contract, spec, git.tracked_files(worktree))`.
  5. `run_id = runs.next_id()`; record `AgentRunStarted`.
  6. `executor.run(task.contract, pack, worktree, Path(".openfactory/runs") / run_id)`; record `AgentRunFinished`.
  7. For `exit` `ok`: record `running` to `gating`, then `changed = git.stage_changes(worktree, base)`.
  8. With changed paths: `violating_paths(changed, task.contract)`, then `GateEvaluated`.
  9. On a pass: `git.commit(worktree, build_commit_message(task.contract, result.summary, run_id, plan.spec_version))`, `CommitRecorded`, `gating` to `passed`, `workspace.remove_worktree(task.id)`.
- A private helper builds every `TaskStateChanged`. It checks `from` to `to` against `TRANSITIONS` before recording, and builds the payload from a dict with the key `from` (as `approve_plan` does).
- The branch name `openfactory/<task id>` is built by the use case (Later line of TASK-045).
- Tests: a new unit file with in-memory fakes of the seven ports.

Out (not this task):
- Everything listed under "Outline item" for TASK-053. In this task a `GitError` from any port call propagates, and no test covers one.
- Until TASK-053, a commit made by the agent would survive. Nothing calls `run_task` before then.
- The refusals, the repair, the loop, promotion after a pass and `--task` (outline item 2).
- The `run` command and any `cli.py` wiring (item 3).
- The other four gates, the retry, the cost limit and the rest of escalation (M4).
- `head_commit()` returning `None`: the `repository has no commit` refusal of item 2 makes it unreachable. An `assert`, no test.
- Hardening: a changed path that holds a line break; an `OSError` from `RunFiles.write`; a recorder that raises.

## Acceptance criteria
All headings are under "Execution" unless another section is named. Events are compared in recorded order.

Terms:
- **The sample task** is a `Task` `AUTH-002` in state `ready`, in plan `plan_01` of `sv_01`, with `allowed_paths` `["app/auth/**", "tests/auth/**"]` and the baseline `forbidden_paths`.
- **The fakes** record their calls. By default: `Runs.next_id` gives `run_0002`; `Plans.latest_commit` gives `None`; `GitProvider.head_commit` gives a sha `B`; `stage_changes` gives `["tests/auth/test_login.py", "app/auth/login.py"]`; `commit` gives a sha `C`; the executor gives a `RunResult` with `exit` `ok` and a summary.

- [x] AC1 ("Events of one task": "`TaskStateChanged` `ready` to `running`; `AgentRunStarted`; `AgentRunFinished`; then, when the run's `exit` is `ok`, `running` to `gating`, one `GateEvaluated` per gate run, and ... `CommitRecorded` then `gating` to `passed`"; "Milestones and definition of done" item 3: "a task whose path check passes is committed and moves to `passed`"; "Streams and actors"; SC-54, SC-60):
  - With the defaults, exactly seven events are recorded, in that order, all with actor `orchestrator`.
  - The two run events are on stream `run:run_0002`; the other five are on `task:AUTH-002`.
  - `AgentRunStarted` has `task_id` `AUTH-002`, `role` `implementer`, `runtime` `claude-code` and `context_hash` equal to `context_hash` of the pack the executor received.
  - `AgentRunFinished` holds the seven fields of the `RunResult` other than `summary`.
  - `GateEvaluated` has `run_id` `run_0002`, `gate` `path_check`, `passed` true and `output_path` null. `RunFiles.write` is not called.
  - `CommitRecorded` has `sha` `C`, `run_id` `run_0002`, `branch` `openfactory/AUTH-002`, `spec_version` `sv_01` and `files` `["app/auth/login.py", "tests/auth/test_login.py"]` (sorted).
  - Every `TaskStateChanged` has a null `reason`.
  - The result has `state` `passed` and `last_event_id` the id of the `gating` to `passed` event.
- [x] AC2 ("Events of one task": "`causation_id` is the `event_id` of the event recorded just before it for the same task in the same command; the first event of a task in a command has none"; SC-60):
  - With the defaults, the first event has no `causation_id`. Each later event has the `event_id` of the event before it, run events included.
  - With `causation_id=X`, the first event has `X`.
- [x] AC3 ("Per-task sequence" steps 1 to 3 and 6; "Base and branches": "`<base>` is the `sha` of the `commits` row with the highest run id ... when the plan has no commit, it is the commit `HEAD` of the repo points at when the task starts"; "The context pack": "the tracked files in the worktree"; "Adapter interface": "`output_dir` is the run's directory, `.openfactory/runs/<run id>/`"; "The commit"; SC-58):
  - `workspace.remove("AUTH-002")` is called before `workspace.create("AUTH-002", B)`.
  - With `Plans.latest_commit` giving a commit with sha `L`, `create` and `stage_changes` receive `L`, and `head_commit` is not called.
  - `tracked_files` and `stage_changes` receive the path `create` returned, and the executor receives it as `workdir`.
  - The executor receives the sample contract, the text of `build_context_pack(contract, spec, <the fake's tracked files>)` and `output_dir` `Path(".openfactory/runs/run_0002")`.
  - `commit` receives the worktree path and `build_commit_message(contract, <the summary>, "run_0002", "sv_01")`.
  - `workspace.remove_worktree("AUTH-002")` is called once. `workspace.remove` is called once only, before `create`.
- [x] AC4 ("Events of one task": "A run whose `exit` is `error` or `timeout` goes `running` to `failed` with no gate; the reason is `run error` or `run timeout`"; "The agent call": "the task fails, and `run` goes on"; SC-60):
  - With a `RunResult` of `exit` `error`: four events: `ready` to `running`, `AgentRunStarted`, `AgentRunFinished` (with the result's `exit` and `error`), and `running` to `failed` with reason `run error`.
  - With `exit` `timeout`, the reason is `run timeout`.
  - In both, `stage_changes`, `commit`, `RunFiles.write` and `remove_worktree` are not called, and the result has `state` `failed`.
- [x] AC5 ("The path check": "A run that changed no path is a failed attempt: no `GateEvaluated` is recorded and nothing is committed"; "A path is a violation when ..."; "When the check fails, the gate's output file lists the violating paths, one per line, and `output_path` holds its path"; "Events of one task", second and third bullets; "Gates and remediation": "The file is `.openfactory/runs/<run id>/<gate>.txt`, written through the `RunFiles` port"; SC-58, SC-60):
  - With `stage_changes` giving `[]`: the events end with `running` to `gating`, then `gating` to `failed` with reason `no changes`. There is no `GateEvaluated`, `commit` is not called, and the result has `state` `failed`.
  - With `stage_changes` giving `["app/auth/login.py", "README.md", "specs/requirements.yaml"]`:
    - `RunFiles.write` is called once with `run_0002`, `path_check.txt` and the text `README.md\nspecs/requirements.yaml\n` (Open question 3).
    - `GateEvaluated` has `passed` false and `output_path` the POSIX form of the path `write` returned.
    - Then `gating` to `failed` with reason `path_check`, then `failed` to `escalated` with reason `path violation`.
    - There is no `CommitRecorded`, `commit` is not called, and the result has `state` `escalated`.
- [x] AC6 ("Task state machine": "The `run` use case checks every transition against `TRANSITIONS` before it records it"; CLAUDE.md "Architecture rules": "src/openfactory/app: use cases, depends on domain + ports only"):
  - With the sample task in state `pending`, `run_task` raises `ValueError` and records no event (Open question 4).
  - `app/run.py` imports nothing from `openfactory.adapters` or `openfactory.cli` (checked with `ast`).
  - Every existing test passes unchanged.

## Architecture rules that apply
- `app` depends on `domain` and `ports` only, and does no I/O of its own.
- All state changes go through `EventRecorder.record`; payloads are built through the payload models.
- No new dependency. No `req` markers on OpenFactory's own tests.
- Existing tests are fixed: none is edited.
- No hardening beyond what the spec asks.

## Plan
1. Create branch `task/TASK-052-run-one-task` from an up-to-date main.
2. Write failing tests in `tests/unit/test_run_task.py` (new) for AC1 to AC6, with the fakes in the file.
3. Add `app/run.py`: `TaskRunResult`, the event helper, the transition helper, `run_task`.
4. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
5. Update the living docs, the rows in `docs/decisions.md` and the Outcome. Commit `feat(app): run the per-task sequence on one task` with trailers `Task: TASK-052` and `Milestone: M3`.

## Files expected to change
- `src/openfactory/app/run.py` (new, about 160 lines)
- `tests/unit/test_run_task.py` (new, about 300 lines, fakes included)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-052-run-one-task.md` (this record; Outcome at close)

Not expected to change: `cli.py`, everything under `domain/`, `ports/` and `adapters/`, `app/context_pack.py`, `app/planner_prompt.py`, every existing test, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 450 lines with tests, over the usual aim (Open question 2).

## Living docs to update
- `docs/architecture.md`: new section "Run use case: one task" (`app/run.py`); the "nothing calls them yet" sentences of "Data flow" for the ports and helpers `run_task` now calls.
- `docs/progress.md`: Current, Done, outline item 1 reworded to what TASK-053 holds, and the Later lines below.
- `docs/decisions.md`: rows for the answered open questions, the branch name built by the use case, and the split of item 1.
- `CHANGELOG.md` and `README.md`: no change (nothing a user sees).

## New dependencies
None.

## Spec gaps
Spec impact is "wording". Items 1 to 3 do not stop this task. Item 4 is a gap that blocks TASK-053.

1. "Execution" › "The path check", "the gate's output file lists the violating paths, one per line".
   - Missing: the order of the lines, and whether the last line ends with a line break.
   - Does not block: every reading lists the same paths. Answered by Open question 3.
2. "Task state machine", "The `run` use case checks every transition against `TRANSITIONS` before it records it".
   - Missing: what happens when the check fails.
   - Does not block: correct code never reaches it. Answered by Open question 4.
3. "Task contract" › "Path patterns" (Later lines of TASK-039, "look before the M3 run use case").
   - `.env` does not match `.env/keys.txt`, and `app/auth/**` matches a file named `app/auth`.
   - Looked at: a file under a directory named `.env` is still a violation unless an `allowed_paths` pattern matches it, so the baseline's hole opens only when the planner allows that path.
   - Does not block: `run_task` calls `violating_paths` as it stands. The lines stay open.
4. Gap, blocks TASK-053 only: "Execution" › "Per-task sequence" step 6 ("moves the task to `passed` and removes the worktree") with "Events of one task" ("A git command that fails while a task is `running` or `gating` moves the task to `failed`") and "Restart" step 1. Audit F-1 of `docs/spec-audits/2026-10-13-proposal-v1.12.md`, with the advisor's Q1.
   - Missing: what `run` does when the worktree removal fails after the task is `passed`. The task is neither `running` nor `gating`, and `TRANSITIONS` has no `passed` to `failed`.
   - Does not block this task: here every `GitError` propagates and no test covers one. It needs a decision before TASK-053 is planned (Open question 1).

Readings, not gaps (each follows from the text as written):
- "for the same task in the same command" covers the two run events, which are on stream `run:<run id>`: the chain runs through all events of the task, as the events of `plan` do.
- `<base>` is read after `ready` to `running` is recorded ("when the task starts").
- `running` to `gating` is recorded before the path check runs.
- `CommitRecorded.files` is `sorted(changed paths)` ("sorted as strings").
- `output_dir` is built by the use case as `Path(".openfactory/runs") / run_id`, and the worktree path is the one `create` returned (decisions of 2026-10-13 and 2026-10-14).

Already recorded and not for this task: F-2 (order of the two repair events, item 2) and F-3 (the `run` table row and the `failed` state line, item 3).

## Later lines in `docs/progress.md`: taken or left
- **F-1 (audit of 2026-10-13).** Not taken. It is in item 1's scope through step 6 and in item 2's through the repair. It blocks TASK-053. Reword at save to "before TASK-053 is planned".
- **"`.openfactory/runs` is a literal in two places" (TASK-047).** Taken as decided: the use case holds the literal, and AC3 fixes the value. The M3 close test half stays.
- **"`WorkspaceManager.create` returns the path but not the branch name" (TASK-045).** Taken: the use case builds `openfactory/<task id>` (AC1). Remove at close.
- **"`context_hash` lives in `app/planner_prompt.py`" (TASK-031, TASK-050).** Taken as decided: imported from there. The line stays for M6.
- **"A caller that omits the path to `GitProvider.tracked_files`" (TASK-043).** Taken: AC3 asserts the path. Remove at close.
- **"`Plans.latest_commit` gives only the plan's newest commit" (TASK-042).** Left: it concerns the repair, step 1 (item 2). Here `latest_commit` is used only for `<base>`, which is its definition.
- **"Order of path check output lines" (TASK-039).** Taken: Open question 3. Reword at close with the answer.
- **The two path pattern wording lines (TASK-039).** Looked at (Spec gaps item 3), left open.
- **"`FilesystemRunFiles.write` does not catch `OSError`" (TASK-046).** Left.
- **Every other Later line:** left.
- **To add at close:**
  - "Until TASK-053 `run_task` lets every `GitError` propagate and does not reset a branch the agent committed on (TASK-052, planner)".
  - "The spec does not say what a failed `TRANSITIONS` check does; `run_task` raises `ValueError` (TASK-052, planner)".

## Open questions
Answered 2026-10-14: the human approved the proposed answer to each of the five. The advisor agreed with all five. Of its refinements: the order of the path check file's lines is fixed by no test (Q3, the AC5 fixture gives the same text sorted or not); the AC6 test matches on the `ValueError` message that names `from` and `to` (Q4); `causation_id` keeps its `None` default as proposed (Q5). For Q1 the reason "removed before the task's next attempt" is dropped (a passed task has no next attempt), and the layer that writes the warning is left to TASK-053.

1. **F-1: a worktree removal that fails after its task has passed (step 6 and the repair).** Needed before TASK-053, not for this task.
   - Proposed: the advisor's answer. The failure changes no state; `run` writes a warning log line and goes on, in both places. No new exit path, and the leftover directory is removed before the task's next attempt anyway.
   - Alternative: the audit's fix, extended to step 6: `run` ends with `git failed: <error>`, exit 1. It stops the loop over a leftover directory.
   - Either way the spec text needs a `/spec-change`.
2. **The split and the size.**
   - Proposed: as planned, with four outcomes here (about 450 lines with tests) and git failures, the soft reset and F-1 in TASK-053.
   - Alternative: cut the path violation and no-changes outcomes (AC5) out as well. But `run_task` would then have no defined behaviour for a run that changed nothing or broke the path rules, so I do not recommend it.
3. **The path check's output file.**
   - Proposed: the violating paths in the order `violating_paths` returns them (the order git printed the changed paths), each followed by `\n`.
   - Alternative: sorted as strings, as `CommitRecorded.files` is.
4. **A transition that `TRANSITIONS` does not allow.**
   - Proposed: the helper raises `ValueError` naming `from` and `to`, before recording. It is a programming error, not an outcome of `run`, and has no output line.
   - Alternative: a named exception in `domain/states.py`. That is more code for a case no caller handles.
5. **Signature and module.**
   - Proposed: `run_task` in `app/run.py` as under Scope. The caller passes the plan's `PlanRef` and stored `SpecSet` (read once per `run`) and the `causation_id` for the first event. The result carries `last_event_id`.
   - Alternative: `run_task` takes `SpecVersions` and reads the spec set per task. That is one more port and a repeated read.

## Outcome
Built `run_task(task, plan, spec, *, causation_id=None, git, workspace, executor, run_files, runs, plans, recorder) -> TaskRunResult` in the new `src/openfactory/app/run.py`, with frozen `TaskRunResult` (`task_id`, `state`, `last_event_id`) and a private `_Chain` that records every event of the task with actor `orchestrator`, each pointing at the one before it, and whose `move` checks `TRANSITIONS` from the task's current state and raises `ValueError` (`<task id>: no transition from <from> to <to>`) before recording. The four outcomes (passed, failed process, no changes, path violation) are covered.

- Tests: new `tests/unit/test_run_task.py` with 11 tests and in-memory fakes of the seven ports. Full suite 1232 passed; ruff, pyright and check_docs clean.
- Deviations from the plan: none.
- Test edits: no test from the test-writer was edited; no existing test changed.
- Living docs: new section "Run use case: one task" and the "nothing calls them yet" sentences in `docs/architecture.md`; six rows in `docs/decisions.md`; `docs/progress.md` (Current, Done, outline item 1, Later lines). `CHANGELOG.md` and `README.md` unchanged (nothing a user sees).
- Follow-ups, all in the Later lines of `docs/progress.md`: TASK-053 (soft reset, git failures, no run event when the worktree cannot be created, F-1); F-1 answer given and its `/spec-change` needed before TASK-053 is planned; `src/openfactory/gates/__init__.py` still exists against ADR-014; the spec wording lines for the path check file and the failed `TRANSITIONS` check.
