# TASK-056: `run` command

- Milestone: M3
- Status: done
- Tests: acceptance
- ADR: none. ADR-011 (accepted) covers `cli.py` as the composition root. ADR-014 (accepted) covers the run use case and its ports. This task adds no port, adapter, dependency, event type, payload or storage change. Answers to the open questions become rows in `docs/decisions.md`.
- Spec impact: wording. Nothing stops the plan (see "Spec gaps").
- Spec sections (spec v1.13):
  - "CLI commands": the table row `openfactory run [--task ID]`; "Other commands" (the "run `openfactory init` first" check); "Output" (the `run` bullet, the "A command that fails exits 1" bullet, and the bullet on standard output and standard error);
  - "Execution" › "`run`" (the refusal bullet and the `--task ID` bullet);
  - "Execution" › "Events of one task" (the removal-warning bullet: "`run` writes the warning `worktree of <task id> not removed: <first line of the error>` to standard error and goes on. The warning does not change the exit code").

## Outline item
M3 outline item 1, "`run` command: task lines, exit codes and refusals". Outline item 2 (M3 close) is unchanged.

## Objective
Add the `run [--task ID]` command to `cli.py`. It wires `run_plan` to the real adapters, prints one `task_id  <final state>` line per task taken, writes the refusals and warnings to standard error, and exits 0 only when every task it took passed.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:

**`src/openfactory/cli.py`:** a new command `run`, with option `--task` (`str | None`, default `None`).
- It calls `require_init()`, then `_open_adapters(...)`.
- It calls `run_plan(task_id=..., git=GitCli(Path(".")), workspace=GitWorktree(Path(".")), executor=ClaudeCodeExecutor(Path(".")), run_files=FilesystemRunFiles(Path(".")), runs=..., plans=..., versions=..., recorder=...)`.

The output after `run_plan` returns, in this order:
1. Each of `RunReport.warnings` (the repair's) goes to standard error.
2. On a refusal, the refusal line goes to standard error, and the command exits 1:
   - `no_approved_plan` gives `no approved plan`;
   - `no_commit` gives `repository has no commit`;
   - `git_failed` gives `git failed: <detail>`;
   - `unknown_task` gives `unknown task <detail>`;
   - `not_ready` gives `<ID> is <detail>, not ready`.
3. Otherwise, for each result in `tasks`:
   - `f"{task_id}  {state.value}"` goes to standard output;
   - then its `warning`, when set, goes to standard error.
4. Exit 1 when any task's `state` is not `passed`, otherwise 0. With no task taken, nothing goes to standard output and the exit code is 0.

A private helper builds the refusal line, as `_refusal_line` does for `plan`.

**`tests/unit/test_run_plan.py`:** new tests only, for the repair's warnings on a `--task` refusal (Later line, TASK-055 reviewer). No existing test is edited.

**`tests/integration/test_cli_run.py`:** new (see Open question 1).

Out:
- A `run` that passes a task through a stand-in `claude`, interruption and restart, and the rebuild check. These are outline item 2 (M3 close).
- Any change to `app/run.py`, `domain/`, `ports/` or `adapters/`.
- Progress output while a task runs (Open question 2).
- What `run` prints when the catch-up of the recorder fails (Later, SC-42).

## Acceptance criteria
- [x] **AC1** ("Execution" › "`run`": "It refuses with one line on standard error and exits 1, before any event. The refusals, checked in this order: `no approved plan`; `repository has no commit`, when `HEAD` points at no commit; `git failed: <error>`, when a git command fails before the repair"). Real wiring, no stand-ins:
  - an initialised repo with no approved plan gives `no approved plan`;
  - a repo with an approved plan and no commit gives `repository has no commit`;
  - an initialised directory with an approved plan where `git rev-parse` fails (no `.git`) gives `git failed: <first line of git's error>`.
  - Each case writes that one line to standard error, nothing to standard output, records no event and exits 1.
- [x] **AC2** ("CLI commands" › "Output": "`run` prints one line per task it took as `task_id  <final state>`, in the order it took them ... It exits 0 when every task it took passed, otherwise 1; with no `ready` task it prints nothing and exits 0"):
  - task lines appear on standard output in the order of `RunReport.tasks`, with exactly two spaces and the state's value (for example `AUTH-002  escalated`);
  - all `passed` exits 0;
  - any `failed` or `escalated` exits 1;
  - with no task taken, standard output is empty and the exit code is 0.
- [x] **AC3** ("Execution" › "`run`": "`--task ID` runs that task only. After the repair it refuses with `unknown task <ID>` when the approved plan has no such task, or `<ID> is <state>, not ready`"):
  - `--task X` reaches `run_plan` as `task_id="X"`, and without the option `task_id` is `None`;
  - `unknown_task` writes `unknown task X` and `not_ready` writes `X is failed, not ready`, each to standard error with exit 1 and nothing on standard output;
  - the repair's warnings are written before the refusal line (audit F-4);
  - in `tests/unit/test_run_plan.py`, `run_plan` returns the repair's warnings with an `unknown_task` and with a `not_ready` refusal. This closes the TASK-055 reviewer Later line.
- [x] **AC4** ("Execution" › "Events of one task": "`run` writes the warning `worktree of <task id> not removed: <first line of the error>` to standard error and goes on. The warning does not change the exit code"; "CLI commands" › "Output", the bullet on standard output and standard error; F-5 as decided at TASK-053):
  - the repair's warnings go to standard error before the first task line;
  - a task's `warning` goes to standard error after its own task line and before the next task line;
  - a run whose tasks all passed, one of them with a warning, exits 0.
- [x] **AC5** ("CLI commands" › "Other commands": "Other commands run against the current directory and fail with "run `openfactory init` first" if `./.openfactory/` is missing"; ADR-011):
  - `run` in a directory with no `.openfactory/` writes that line to standard error and exits 1;
  - `cli.py` is still the only module that imports both `openfactory.adapters` and `openfactory.app`;
  - every existing test passes unchanged.

## Architecture rules that apply
- `cli.py` is the composition root (ADR-011). It wires the adapters, prints and sets the exit code. `app/run.py` stays unchanged and prints nothing.
- All LLM calls go through `claude -p` (`ClaudeCodeExecutor`). There is no SDK and nothing reads `ANTHROPIC_API_KEY`.
- No new dependency. Fixed tests are not edited.

## Plan
1. Create branch `task/TASK-056-cli-run` from an up-to-date main.
2. Test-writer: write failing tests for AC1 to AC5:
   - `tests/integration/test_cli_run.py` (new);
   - the two new tests in `tests/unit/test_run_plan.py`.
3. Implement the `run` command and its refusal-line helper in `cli.py`.
4. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
5. Update the docs:
   - `docs/architecture.md`: the "CLI" section gains `run`; in "Run use case: the loop" and "Run use case: one task", the lines saying `cli.py` does not wire `run_plan` yet (and the stale "outline items 2 and 3") change; "Data flow" gains the `run` wiring;
   - `docs/decisions.md`: rows for the answers;
   - `docs/progress.md`: Current, Done, remove outline item 1, and the Later lines taken;
   - this record's Outcome.
6. Commit `feat(cli): add the run command` with trailers `Task: TASK-056` and `Milestone: M3`.

## Files expected to change
- `src/openfactory/cli.py` (about +50 lines)
- `tests/integration/test_cli_run.py` (new, about +200 lines)
- `tests/unit/test_run_plan.py` (about +40 lines; new tests only)
- `docs/architecture.md`
- `docs/decisions.md`
- `docs/progress.md`
- `docs/tasks/TASK-056-cli-run.md`

Not expected to change: `app/`, `domain/`, `ports/`, `adapters/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`. Expected size is about 290 lines of code and tests.

## Spec gaps
Spec impact is "wording". No item blocks.

1. **"Execution" › "`run`"**: "It refuses with one line on standard error and exits 1, before any event" (audit F-4).
   - Unclear: the `--task` refusals come "After the repair". So the repair's events are already recorded, and its removal warnings come before the refusal on standard error, giving more than one line.
   - Does not block. The sentence is read as covering the first three refusals only, as at TASK-055. The `--task` refusals are written after the repair's warnings (AC3).
2. **"Execution" › "Events of one task"**, the removal-warning bullet (audit F-5).
   - Unclear: the bullet does not give the warning's order against the `task_id  passed` line.
   - Does not block. The TASK-053 decision applies: the warning comes after its task line (AC4).
3. **"CLI commands" › "Output"**, the `run` bullet.
   - Unclear: it gives the order of the lines but not when they are written, so they could come at the end or as each task finishes.
   - Does not block. See Open question 2.
4. **"CLI commands" › "Output"**: "with no `ready` task it prints nothing and exits 0".
   - Unclear: the repair may still write warnings.
   - Does not block. "Prints nothing" is read as nothing on standard output; warnings still go to standard error, which matches the bullet sending warnings there.

## Later lines in `docs/progress.md`: taken or left
- Taken:
  - "No test asserts the repair's warnings on a `--task` refusal" (TASK-055, reviewer), closed by the new `test_run_plan.py` tests in AC3;
  - audit F-4 (TASK-055, planner), recorded here as Spec gap 1;
  - the TASK-053 F-5 line, applied by AC4.
- Left:
  - the `assert spec is not None` in `run_plan` (no refusal named by the spec);
  - the TASK-053 reviewer line on git calls after a `GitError`;
  - all others.

## Open questions
All five proposed answers approved by the human on 2026-10-14 (advisor: 5 AGREE). For Q1, cross-stream ordering is checked in a child process.

1. **Test approach.**
   - Proposed:
     - AC1 and AC5 run the real wiring with real git and no `claude`; no refusal reaches the executor.
     - AC2 to AC4 replace `openfactory.cli.run_plan` with a monkeypatched stand-in. It records its keyword arguments and returns a given `RunReport`, so lines, exit codes and warnings are checked for every state with no `claude`.
     - The ordering across standard output and standard error is checked on the combined output, or in a child process as in the M2 close test.
   - Alternative: a stand-in `claude` script on `PATH` for every test, as `plan` did (TASK-034 row). It cannot easily cause a worktree removal failure, and it overlaps outline item 2, which runs that end-to-end path.
2. **When lines are written.**
   - Proposed: all output is written after `run_plan` returns, in the order of AC4. No change to `app/run.py`. A Later line records that a long run shows nothing until it ends.
   - Alternative: a per-task callback parameter on `run_plan`, so each line is written as its task finishes. This changes the use case's signature and its tests.
3. **Adapter roots.** Proposed: `Path(".")` for `GitCli`, `GitWorktree`, `ClaudeCodeExecutor` and `FilesystemRunFiles`, as `plan` builds `GitCli(Path("."))`; "Other commands run against the current directory".
4. **State text.**
   - Proposed: `TaskState.value` for the task line's `<final state>`.
   - `RunReport.detail` (already the state's value) is the `<state>` of `<ID> is <state>, not ready`; the `<ID>` is the `--task` value as given.
5. **`--task` refusal output order.** Proposed: the repair's warnings first, then the refusal line, each on standard error (Spec gap 1).

## Outcome
- `src/openfactory/cli.py`: new command `run [--task ID]` and the private `_run_refusal_line`. It calls `require_init()`, `_open_adapters`, then `run_plan` with `GitCli`, `GitWorktree`, `ClaudeCodeExecutor` and `FilesystemRunFiles` on `Path(".")`. After `run_plan` returns it writes the repair's warnings to standard error, then the refusal line (exit 1) or one `task_id  <state>` line per task on standard output with each task's `warning` to standard error after its line; exit 1 when any task did not pass.
- Tests: new `tests/integration/test_cli_run.py` (real wiring for the refusals, a stand-in `run_plan` for lines, exit codes and warnings, a child process for the order across the two streams) and two new tests in `tests/unit/test_run_plan.py` for the repair's warnings on a `--task` refusal.
- After review (non-blocking note 1): `_run_refusal_line(refusal, detail, task_id)` checks `not_ready` explicitly and ends with `assert_never`, so a new `RunRefusal` member is a pyright error, not a wrong line. Notes 2 (a fixed test) and 3 (already a Later line) left.
- No test from the test-writer was edited. No change to `app/`, `domain/`, `ports/` or `adapters/`.
- 1289 tests pass; ruff, pyright and check_docs are clean.
- Docs: `docs/architecture.md`, `docs/decisions.md` (five rows), `docs/progress.md`, `CHANGELOG.md`, `README.md`.
- ADR: none needed.
