# TASK-057: M3 close integration test

- Milestone: M3
- Status: done
- Tests: integration-only. The deliverable is one integration test file over code that is already built and tested per command, use case and adapter; no production code is expected to change. TASK-019 and TASK-038 are the precedents. See Open question 5.
- ADR: none. Existing ADRs already cover this:
  - ADR-010 (accepted) puts `rebuild()` on the adapter for tests and close tasks.
  - ADR-002 (accepted) defines an identical rebuild.
  - ADR-011 covers `cli.py` tested through `CliRunner` and a child process.
  - ADR-014 covers the run use case and its ports.
  - ADR-005 says no test in the default run starts `claude`.
  - No new port, adapter, dependency, event type, payload, storage change or production convention. The interrupt mechanism and the locked-worktree technique become rows in `docs/decisions.md`.
- Spec impact: wording. These are existing, non-blocking items (audit F-4 and F-1 of 2026-10-14); this record holds the F-4 note the audit asks for (see "Spec gaps").
- Spec sections (spec v1.13):
  - "Purpose and demo scenario": demo step 4; the success criterion "Every state change can be reconstructed from the event log".
  - "Domain model and storage": "Projections", "Projection rules", "Streams and actors", "Event payloads" (`AgentRunStarted`, `AgentRunFinished`, `GateEvaluated`, `CommitRecorded`).
  - "Task state machine".
  - "Execution": "`run`", "Per-task sequence", "Base and branches", "The context pack" (the hash only), "The agent call", "The path check", "The commit", "Events of one task", "Restart", "Adapter interface" (`transcript.json`).
  - "Gates and remediation": "Gate output is stored as a file ... `.openfactory/runs/<run id>/<gate>.txt`".
  - "Traceability" › "Commit trailers".
  - "CLI commands" › "Output": the `run` bullet and the bullet on the two output streams.
  - "Milestones and definition of done": milestone 3, and "Phase 1 is done when": "Killing the process mid-run and restarting resumes from the event log without duplicate commits".

## Outline item
M3 outline item 1, whole and last. Closing it completes M3 (subject to Open question 3).

## Objective
Add one integration test file that does three things through the real Typer app and real adapters, on a sample git repo with a stand-in `claude` first on `PATH`:
- runs `run` end to end;
- kills a `run` mid-task and restarts it without a second commit;
- shows the nine projection tables identical after `SqliteEventRecorder.rebuild()`.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08). Criteria trace to spec headings.

## Scope
In:
- **New test file.** `tests/integration/test_m3_close.py`, with its helpers, spec texts and stand-in script defined in the file, as in `test_m2_close.py`.
- **The sample repo.** Made under `tmp_path` with the real `git init`, then `app/main.py` added and committed, so `HEAD` exists.
  - Local config: `user.name`, `user.email` and `commit.gpgsign false`.
  - Then `init`, `specs/requirements.yaml` and one ADR are written, followed by `approve spec`, `plan` and `approve plan`.
  - Removed from the environment: `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `ANTHROPIC_API_KEY`, `GIT_AUTHOR_*` and `GIT_COMMITTER_*` (Later line, TASK-044).
- **The stand-in `claude`.** One script first on `PATH`, serving both adapters.
  - With `--json-schema` in its arguments it is the planner. It prints `tests/fixtures/claude_envelope.json` with `structured_output` replaced by the plan below.
  - Otherwise it is the implementer. It takes the task id from the name of its working directory and acts per task (below). It prints `tests/fixtures/claude_agent_envelope.json` with `result` replaced by a per-task summary.
  - Every start appends one JSON line to a log file named by an environment variable: role, working directory, and the SHA-256 of standard input.
- **The real wiring.** `GitCli`, `GitWorktree`, `ClaudeCodeExecutor` and `FilesystemRunFiles`, reached only through `openfactory.cli.app`.
- **The rebuild** is called on the adapter.
- **The interrupted run** is `run` in a child process, `[sys.executable, "-c", <script>, "run"]`, as in `test_m2_close.py` AC6 and `test_cli_run.py` AC4. The script wraps `SqliteEventRecorder.record` so that it sends `SIGKILL` to its own process when asked to record `TaskStateChanged` `gating` to `passed` for `AUTH-001`, then calls `app()` (Open question 2).

Out:
- Any change under `src/`. If an assertion that traces to spec text fails, that is a defect: stop and report it with the spec text it breaks. Do not fix it here and do not weaken the test.
- A test that starts the real `claude` (ADR-005). The real run is a manual step (Open question 3).
- A kill during the agent call ("Restart" step 2) and a kill around `git commit`. Unit tests cover step 2 (TASK-054), and in M3 neither can lead to a second commit, because a `failed` task is not retried until M4.
- Retries, `failed` to `ready`, the other four gates, the cost limit (M4).
- Editing any existing test file.
- Releasing 0.3.0.

## Sample plan and flows
The ids, dependencies, paths and agent behaviour below are fixed, because the criteria depend on them. Objectives, statements and summaries are the test's choice.

Spec: `components: [auth]`. `REQ-AUTH-001` has criteria `AC-AUTH-001-1` and `AC-AUTH-001-2` and `constrained_by: [ADR-001]`. `ADR-001` is accepted.

The planner reply has three tasks. Each has `components: [auth]`, `role: implementer`, `allowed_paths: [app/]` and `requirements: [REQ-AUTH-001]`.

| Task | Depends on | Criteria | Stand-in implementer |
| --- | --- | --- | --- |
| `AUTH-001` | none | `AC-AUTH-001-1` | writes `app/login.py` |
| `AUTH-002` | `AUTH-001` | `AC-AUTH-001-2` | writes `app/otp.py`, then runs `git add -A` and `git commit -m "agent commit"` in its worktree |
| `AUTH-003` | none | `AC-AUTH-001-1` | writes `app/x.py` and `notes/todo.md` |

Run ids: planner `run_0001`.

**Flow A, uninterrupted:** setup, then one `run`.
- Expected order taken: `AUTH-001`, `AUTH-002` (promoted after `AUTH-001` passes), then `AUTH-003`.
- Implementer runs: `run_0002`, `run_0003`, `run_0004`.

**Flow B, interrupted:**
1. Setup, then `run` in the killed child.
2. The log ends with `CommitRecorded` of `AUTH-001`; `AUTH-001` is in `gating`.
3. Then `run` again through `CliRunner`.

## Acceptance criteria
A snapshot is every row of the nine projection tables read with `SELECT *`, each table ordered by its primary key (`gate_results` by `run_id, gate`; `commits` by `sha`).

- [x] **AC1** ("CLI commands" › "Output": "`run` prints one line per task it took as `task_id  <final state>`, in the order it took them ... It exits 0 when every task it took passed, otherwise 1"; "Execution" › "`run`": lowest ready id first, the promotion "taken in the same invocation", "A task that does not pass does not stop the others"; "The agent call"; "Event payloads": `context_hash`). Flow A:
  - `run` prints exactly `AUTH-001  passed`, `AUTH-002  passed`, `AUTH-003  escalated`.
  - Standard error is empty and the exit code is 1.
  - The stand-in was started as implementer three times, in that task order.
  - Each start's working directory was `<repo>/.openfactory/worktrees/<task id>`.
  - Each start's standard-input hash equals the `context_hash` of that run's `AgentRunStarted`.
- [x] **AC2** ("Base and branches"; "The commit": "no commit of the agent survives" (`--no-verify` is not exercised: the sample repo has no hooks); "Traceability" › "Commit trailers"; "Per-task sequence" step 6: "removes the worktree; the branch stays"). After flow A, read with real `git`:
  - `openfactory/AUTH-001` is one commit above the initial commit.
  - `openfactory/AUTH-002` is one commit above `AUTH-001`'s; no commit with subject `agent commit` is reachable from it.
  - `openfactory/AUTH-003`'s tip is `AUTH-002`'s commit, so nothing was committed for it.
  - Each of the two commits has a full message (`%B`) equal to the expected text: subject `<id>: <objective>`, the summary, then the five trailers `Task`, `Requirements`, `Acceptance-Criteria`, `Agent-Run`, `Spec-Version: sv_01`.
  - `git log --format=%(trailers:only)` gives those five lines.
  - Each commit changes only its own file (`app/login.py`, `app/otp.py`).
  - The worktree directories of `AUTH-001` and `AUTH-002` are gone.
  - The human's checkout has the same `HEAD` sha and branch as before, and no `app/login.py`.
- [x] **AC3** ("Events of one task", the order and `causation_id` bullets; "Streams and actors"; "Projections"; "Gates and remediation": "`.openfactory/runs/<run id>/<gate>.txt`"; "Adapter interface": "`<output_dir>/transcript.json`"; "The path check"). After flow A:
  - **Event count and types.** `run` added 22 events. Per task, the types are:
    - `ready`→`running`, `AgentRunStarted`, `AgentRunFinished`, `running`→`gating`, `GateEvaluated`;
    - then `CommitRecorded` and `gating`→`passed` (for `AUTH-001` and `AUTH-002`);
    - or `gating`→`failed` with reason `path_check` and `failed`→`escalated` with reason `path violation` (for `AUTH-003`);
    - plus one `pending`→`ready` of `AUTH-002` between the `AUTH-001` and `AUTH-002` groups.
  - **Actor and causation.** Every event has actor `orchestrator`. Each points at the event before it for the same task, and the first of each task has none. `AUTH-002`'s `pending`→`ready` points at `AUTH-001`'s `gating`→`passed`.
  - `tasks`: `passed`, `passed`, `escalated`, each with `attempt` 1.
  - `agent_runs`: `run_0002`..`run_0004` with their `task_id`, role `implementer`, exit `ok`.
  - `gate_results`: three `path_check` rows. Two are `passed` 1 with `output_path` null. `run_0004`'s is `passed` 0 with `output_path` `.openfactory/runs/run_0004/path_check.txt`.
  - `commits`: two rows whose `sha` equals the branch tips of AC2, with `branch` `openfactory/<id>`.
  - **Run files.** `<repo>/.openfactory/runs/run_0004/` holds both `transcript.json` (the bytes the stand-in printed) and `path_check.txt`, whose lines are exactly `notes/todo.md`. This takes the TASK-047 advisor note.
- [x] **AC4** ("Projection rules": "Rebuilding means emptying the projection tables ..., replaying all events in `seq` order", "A rebuild is identical when, for every projection table, the rows read in primary-key order are equal before and after", "M3 `gate_results`, `commits`"). Applied after flow A and again at the end of flow B:
  - Take a snapshot of the nine tables; each is non-empty.
  - Delete every row of the nine tables on the test's own connection. The emptied snapshot differs from the first, so the comparison is not vacuous.
  - After `SqliteEventRecorder(<db>).rebuild()`, the snapshot equals the first, table by table.
  - `projection_state` is (`1`, highest `seq`), and `events` is unchanged.
- [x] **AC5** ("Restart" step 1: "A task in `gating` that has a `CommitRecorded` moves to `passed`, and its worktree is removed"; step 3; "The events of the repair have no `causation_id`"; "the history never holds two commits for one task"; "Phase 1 is done when": "Killing the process mid-run and restarting resumes from the event log without duplicate commits"). Flow B:
  - The killed child exits by signal 9.
  - Its last stored event is `AUTH-001`'s `CommitRecorded`, and `AUTH-001` is `gating`.
  - The second `run` prints exactly `AUTH-002  passed`, `AUTH-003  escalated` and exits 1.
  - Its first two events are `AUTH-001` `gating`→`passed` and `AUTH-002` `pending`→`ready`, both with null `causation_id`.
  - `AUTH-001`'s worktree is gone.
  - Across both invocations the stand-in implementer started exactly once for `AUTH-001`.
  - Across all `openfactory/*` branches, exactly one commit has trailer `Task: AUTH-001`, and it is `openfactory/AUTH-002`'s parent.
  - `commits` has exactly one row per passed task.
- [x] **AC6** ("Execution" › "`run`": "`--task ID` runs that task only. After the repair it refuses with `unknown task <ID>`"; "Events of one task": "`run` writes the warning `worktree of <task id> not removed: <first line of the error>` to standard error and goes on"; "Restart"; audit F-4). Flow B step 1, then `git worktree lock .openfactory/worktrees/AUTH-001`, then `run --task ZZZ-999`:
  - Standard error is exactly two lines: one starting `worktree of AUTH-001 not removed: ` with a non-empty rest, then `unknown task ZZZ-999`.
  - Standard output is empty and the exit code is 1.
  - The repair's two events (as in AC5) are recorded, and the stand-in was not started.
  - After `git worktree unlock`, a plain `run` prints `AUTH-002  passed`, `AUTH-003  escalated`.
  - Exactly one `Task: AUTH-001` commit still exists.

## Architecture rules that apply
- No module under `src/` changes. The test imports `openfactory.cli.app` and `SqliteEventRecorder` (for `rebuild()`, which is not on the port, ADR-010). The child script patches `SqliteEventRecorder.record` in its own process only.
- "Never write projections directly" is a rule for production code. The `DELETE` in AC4 is test-side damage to disposable tables (decisions row of 2026-10-10). The test never writes `events`.
- All LLM calls go through `claude -p`. A stand-in named `claude` is first on `PATH`, `ClaudeCodeLLM()` and `ClaudeCodeExecutor` stay as wired, no test starts the real `claude`, and `ANTHROPIC_API_KEY` is removed, not read.
- The suite already needs the real `git`.
- Fixed tests are not edited. No `req` markers.

## Plan
1. Create branch `task/TASK-057-m3-close-integration-test` from an up-to-date main.
2. Get the human's answers to the Open questions and record them here and in `docs/decisions.md`. As part of that, confirm on the local git (2.54.0) that `git worktree remove --force` (one `--force`) fails on a locked worktree, and note its first error line.
3. Write `tests/integration/test_m3_close.py`:
   - spec texts, the plan reply and the per-task stand-in table;
   - the stand-in `claude` script and its start log;
   - a `setup` helper (repo, commit, identity config, `init`, `approve spec`, `plan`, `approve plan`);
   - a `killed_run` helper (child process, environment with the stand-in on `PATH`);
   - `query`, `snapshot`, `empty_projections` and `rebuild` over nine tables;
   - git read helpers (`rev-parse`, `rev-list`, `log --format`).
   - One test or more per criterion, each on its own `tmp_path`.
4. Run the file. It is expected to pass with no `src/` change. AC4's emptied-snapshot bullet is the check that the comparison can fail. For AC5, check once by hand that removing the kill (letting the first `run` finish) makes the "last stored event is `CommitRecorded`" assertion fail, and say so in the Outcome. If an assertion that traces to spec text fails, stop and report.
5. Manual step (Open question 3): one real `openfactory run` against the real `claude` on a scratch repo with a one-task approved plan; record the task line, exit code, the run events and `claude --version` in the Outcome.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
7. Update the living docs and the Outcome. Commit `test(cli): add the M3 close integration test` with trailers `Task: TASK-057` and `Milestone: M3`.

## Files expected to change
- `tests/integration/test_m3_close.py` (new, about 520 lines; see Open question 1)
- `docs/progress.md`: Current, Done, the M3 outline becomes empty, the M3 box per Open questions 3 and 6, and the Later lines below
- `docs/decisions.md`: rows for the answers (interrupt mechanism, locked-worktree technique, tick rule)
- `docs/tasks/TASK-057-m3-close-integration-test.md` (this record; Outcome at close)

Not expected to change: everything under `src/`, every existing test file, both fixtures, `pyproject.toml`, `docs/adr/`, `docs/spec/`, `docs/architecture.md` (no component or data flow change), `CHANGELOG.md` and `README.md`.

## Living docs to update
- `docs/progress.md`, `docs/decisions.md` as above.
- `docs/architecture.md`, `CHANGELOG.md`, `README.md`: no change expected.

## New dependencies
None.

## Spec gaps
Spec impact is "wording". No item blocks.

1. **"Execution" › "`run`"** (audit F-4). This is the note the audit asks for in this task's record.
   - Unclear: "It refuses with one line on standard error and exits 1, before any event" does not fit the `--task` refusals, which come "After the repair", after its events and any removal warning.
   - Does not block. It is read, as at TASK-055 and TASK-056, as covering the first three refusals only. AC6 pins the end-to-end result: the warning line, then the refusal line, with the repair's events kept.
2. **"Execution" › "Restart"** (audit F-1): "that warning" has no antecedent. It is read as the removal warning of "Events of one task" (TASK-054). Left for a `/spec-change`.

Readings, not gaps:
- "Killing the process mid-run" is done with a real `SIGKILL` of the `run` process, sent at a chosen point from inside the child. The point chosen is the only one where "Restart" step 1 applies and where a duplicate commit could arise in M3.
- "M3 ... is tested end to end on one task": the flows take three tasks, and each one is end to end.
- The restarted `run` does not print `AUTH-001`, because the repair is not a task it "took".
- A sample repo needs a commit (`repository has no commit` refusal) and a local git identity ("under the repo's configured git identity").

## Later lines in `docs/progress.md`: taken or left
Taken:
- `.openfactory/runs` literal in two places; "the M3 close test should assert that the transcript and a gate file land in one directory" (TASK-047, advisor): AC3. Remove at close.
- Audit F-4, "goes into the task record of outline item 1": Spec gap 1 and AC6. Reword the F-1/F-4 line at close to drop F-4.
- "The command lines of the `GitWorktree` removals ... look again when the run use case depends on them" (TASK-045, reviewer): partly. AC2 and AC5 show removal with the branch kept on real git, and AC6 relies on single `--force` failing on a locked worktree. Reword, do not remove.
- "The instructions of the context pack were not tried on a real implementer run" (TASK-050): the manual step, if Open question 3 is answered as proposed.

Left:
- TASK-056 "a long `run` prints nothing until it ends": not changed by a test.
- TASK-053 "no further git call after a `GitError`": unit level.
- TASK-049 "no real error envelope captured": stays unless the manual run fails.
- TASK-051 "summary with `---` or `Key: value` lines" (before M5): AC2 checks a plain summary only.
- TASK-044 hooks, signing, environment identity: the test sets `commit.gpgsign false` and removes the variables.
- The spec wording lines (TASK-053 to TASK-056) and all others.

## Open questions
None is a spec decision. Each has a proposal and an alternative.

1. **Size.** About 520 lines, against the ~300 aim; TASK-038 was 527.
   - Proposed: one task, since the flows share setup, stand-in and snapshot helpers.
   - Alternative: split into TASK-057 (AC1 to AC4, flow A, about 330 lines) and TASK-058 (AC5, AC6 and AC4 on flow B, about 200 lines, reusing the same helpers by copy).
2. **How the run is interrupted.**
   - Proposed: a child process whose script wraps `SqliteEventRecorder.record` to `os.kill(os.getpid(), SIGKILL)` before recording `AUTH-001` `gating`→`passed`. The kill is real, and the point is the one where step 1 and the no-second-commit property matter.
   - Alternative (a): a stand-in `git` on the child's `PATH` that kills its parent on `git worktree remove`, after `passed`. This patches nothing in Python, but it tests only step 3 and a leftover worktree (F-7), not step 1.
   - Alternative (b): the stand-in `claude` kills its parent during the agent call. This tests step 2, but no commit is at stake in M3.
3. **A real `run` before ticking M3.** Nothing has run the implementer against the real `claude`. The context pack instructions, the tool flags and the agent envelope are unobserved.
   - Proposed, as TASK-038 answer 1: the human (or the session, if the human says so) runs `openfactory run` once on a scratch repo with a one-task approved plan. M3 is ticked only on `<task>  passed` with an `AgentRunFinished` of `exit: ok`; any other outcome is recorded, and the human decides.
   - Alternative: tick on the green suite alone.
4. **AC6 through a locked worktree.**
   - Proposed: make the real removal fail with `git worktree lock`, which `remove --force` with one `--force` does not override (to confirm in Plan step 2).
   - Alternative: drop AC6. F-4 is then only the note in Spec gap 1, and the order stays covered by `test_cli_run.py` AC3 with a stand-in `run_plan`.
5. **Tests field and "confirm it fails".**
   - Proposed: `integration-only`, the session writes the file. "Confirm it fails" is replaced by AC4's emptied-snapshot bullet and the hand check in Plan step 4. Mechanical errors in its own test may be fixed; a spec-traced failure stops the session.
   - Alternative: `acceptance` with the test-writer, where nothing can fail first.
6. **What closing M3 changes in the docs.**
   - Proposed, as for M1 and M2: tick `[x] M3 Executor` (subject to question 3), leave "Milestone: M3" under Current, and leave the `0.3.0` changelog section to the human. If the real run is pending at commit time, commit with the box unticked and a Blockers line.
   - Alternative: also move Current to M4. The "Spec gap (before M4 is planned)" Later line (F-4 `resolve`, F-16, F-33, F-39) would then need a `/spec-change` round first.

## Answers (human, 2026-10-14)
All six proposals approved as written, with the advisor's refinement of question 5:
1. One task.
2. The in-process wrap of `SqliteEventRecorder.record` with `SIGKILL` before `AUTH-001` `gating` to `passed`.
3. The human runs one real `openfactory run`; M3 is ticked only on `<task>  passed` with `exit: ok`; if it is pending at commit time, the box stays unticked with a Blockers line.
4. Keep AC6 through `git worktree lock`; its first run is the confirmation that one `--force` fails on a locked worktree.
5. `integration-only`, written by the session; the hand check moves the kill to just before `CommitRecorded` and watches AC5 fail.
6. Tick M3 (subject to 3), Current stays at M3, `0.3.0` is the human's.

## Outcome
- New `tests/integration/test_m3_close.py` (548 lines, six tests, AC1 to AC6). All six passed at their first run with no change under `src/` and no existing test edited. Full suite: 1295 passed; ruff, pyright and check_docs clean.
- The stand-in `claude` gets its log path baked into the script, not from an environment variable as Scope said; same effect, the test's choice.
- AC6 passing confirms on the local git that `git worktree remove --force` given once fails on a locked worktree (Plan step 2, answer 4).
- Hand check (answer 5), file restored after each: with the kill moved to just before `AUTH-001`'s `CommitRecorded`, AC5 fails at "last stored event is `CommitRecorded`" (`GateEvaluated` found). With those two kill-point assertions also skipped, AC5 fails on the restarted `run`'s lines (`['AUTH-003  escalated']`): `AUTH-001` is `failed` with reason `interrupted` and `AUTH-002` is never promoted. So the restart assertions catch it too.
- Reviewer: approve, no blocking issues. Of its non-blocking notes, applied at the human's word: Status set to done and the boxes ticked, and AC2's citation notes that `--no-verify` is not exercised. The `task_commits` parsing note went to Later.
- Manual real run (answer 3): pending, for the human. M3 stays unticked, with a Blockers line, until it is done.
