# TASK-034: `plan` command

- Milestone: M2
- Status: done
- Tests: acceptance
- ADR: none. ADR-013 (accepted) covers the two use-case calls with the warning printed between them; ADR-011 (accepted) covers `cli.py` as the composition root and `require_init()`; ADR-010 covers the recorder creating the tables when it opens; ADR-012 covers `Plans`, `Runs` and `GitProvider`; ADR-005 covers the `claude -p` call. No new port, adapter, dependency (structlog is already one), event type, payload or storage change. The logging convention (structlog, JSON lines, standard error) is the spec's own, and the TASK-029 decisions row of 2026-10-11 gave its configuration to this item with "No ADR". Where the configuration is called and which fields a log line has are rows in `docs/decisions.md` (Open questions 2 and 3).
- Spec impact: none. Spec v1.11 settles the task lines, the status line, the rejection lines, the five refusal texts and their order, the source of `<error>`, the warning's text, stream and time, the exit codes, and that log lines are JSON lines on standard error (see "Spec gaps": readings only).
- Spec sections (spec v1.11): "CLI commands" (the command table; "Other commands"; "Output": the three `plan` bullets, "A command that fails exits 1", and the bullet that starts "Command results"); "Task contract" › "Planning" (the first two bullets and the tracked-files bullet) and "Plan checks" (the last paragraph); "Tech stack and repo layout" (the "Logging" row; "log a warning if it was present"; "the command exits 1"); "Domain model and storage" › "Streams and actors" (the paragraph that starts "`plan` records `AgentRunStarted`"); "Milestones and definition of done" (milestone 2)

## Outline item
M2 outline item 10, whole. Items 11 (`approve plan`), 12 (`deleted-requirement`) and 13 (M2 close test) are left.

## Objective
Add the `openfactory plan` command to `src/openfactory/cli.py`: it wires the SQLite, filesystem, git and Claude Code adapters to `prepare_plan` and `create_plan`, prints the task lines and `created plan_NN` or the second reply's rejection lines on standard output, writes the refusals and the `spec files differ` warning on standard error, sets the exit code, and configures structlog to write JSON lines on standard error.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings.

## Scope
In, all in `src/openfactory/cli.py`:
- A `plan` command with no arguments.
  - It calls `require_init()`.
  - It opens `SqliteEventRecorder` first, then `SqliteSpecVersions`, `SqlitePlans` and `SqliteRuns` on the same path.
  - It builds `FilesystemSpecFiles(Path("specs"))`, `GitCli(Path("."))` and `ClaudeCodeLLM()`.
  - It calls `prepare_plan`, prints the refusal or the warning, calls `create_plan` with the `PlanInputs` unchanged, and closes every adapter.
- The three entry refusals on standard error, from `PlanRefused.reason`:
  - `no approved spec version`
  - `policy is invalid; run openfactory validate`
  - `<plan_id> is already approved; use replan`
- `spec files differ from approved <spec_version>` on standard error when `PlanInputs.spec_files_differ`, written before `create_plan` is called.
- From `PlannerResult.outcome`:
  - `created`: one `task_id  objective` line per task, then `created <plan_id>`, exit 0.
  - `rejected`: `rejection_lines(result.rejections)` on standard output, exit 1.
  - `git_failed`: `git ls-files failed: <first line of error>` on standard error, exit 1.
  - `failed`: `planner call failed: <first line of error>` on standard error, exit 1.
- A private helper that configures structlog: JSON renderer, one line per entry, written to standard error (Open questions 2 and 3).
- Tests that run the real app through `typer.testing.CliRunner` in a repo under `tmp_path`, with the real `git` and a stand-in `claude` first on `PATH` (Open question 1).

Out (not this task):
- `approve plan`, the `deleted-requirement` rule, the M2 close test with the rebuild (items 11 to 13).
- Any change under `domain/`, `ports/`, `adapters/` or `app/`, and to the behaviour of `init`, `validate`, `approve spec` or `events`.
- Skipping a `warning:` first line of a `GitError` (Later, TASK-030): `<error>` is the first line, as the spec says.
- A tracked name that is not UTF-8 (`UnicodeDecodeError`), and `GIT_DIR` in the caller's environment (Later, TASK-030).
- What `plan` prints when the recorder's catch-up fails (Later, F-1): the exception propagates.
- Whether a plan with no tasks is created (Later, TASK-032): a `created` result with no tasks prints only the status line; no criterion.
- A started run with no finish (Later, TASK-032).
- Retried-then-accepted output: covered by `run_planner`'s unit tests and due in the M2 close test.
- Hardening: an objective or an error text with odd characters, a `specs` path that is a file, an unreadable database.

## Acceptance criteria
"Output" and "Other commands" are under "CLI commands"; "Planning" and "Plan checks" under "Task contract"; "Streams and actors" under "Domain model and storage".

Fixtures:
- "The repo" is a directory under `tmp_path` made with the real `git init`, with `app/main.py` added by `git add` and `init` run on it. `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` are removed from the environment, as in `tests/integration/test_git_cli.py`.
- "Approved `sv_01`" means valid spec files (`REQ-AUTH-001` with two criteria, component `auth`) approved by running `approve spec` through the app.
- "The stand-in `claude`" is a script in a directory put first on `PATH`.
  - It records each start and the prompt it read from standard input.
  - It prints an envelope built from `tests/fixtures/claude_envelope.json` with a chosen `structured_output`, a different one per start when the test asks, or exits non-zero with chosen standard error.
  - No test starts the real `claude`.
- "A good reply" holds `AUTH-002` (depends on `AUTH-001`) and then `AUTH-001`, in that order, covering the requirement and both criteria.
- "An approved plan" is made by the test recording `PlanApproved` for an existing draft through `SqliteEventRecorder`, because `approve plan` is not built (Open question 5).
- Every run is `plan` through `CliRunner` with the repo as the current directory.

- [x] AC1 ("Output": "`plan` prints one line per task as `task_id  objective`, in ascending task id as strings, then the status line `created plan_NN`, and exits 0" and "Command results (...; task and rejection lines; ...) go to standard output"; "Planning": "`openfactory plan` uses the latest approved spec version" and "the list of tracked files from `git ls-files`"; "Streams and actors": "`plan` records `AgentRunStarted` before each planner call and `AgentRunFinished` after it; ...; then `PlanCreated`"). With approved `sv_01` and a good reply:
  - Standard output is exactly `AUTH-001  <its objective>`, `AUTH-002  <its objective>`, `created plan_01`, with two spaces between the fields.
  - Standard error is empty and the exit code is 0.
  - The event log gains `AgentRunStarted`, `AgentRunFinished`, `PlanCreated` in that order; `PlanCreated.spec_version` is `sv_01`; the `plans` row `plan_01` has status `draft`.
  - The prompt the stand-in read holds `app/main.py`.
- [x] AC2 ("Output": "`plan` refuses with one line on standard error and exits 1. The refusals, checked in this order: `no approved spec version`; `policy is invalid; run openfactory validate`; `plan_NN is already approved; use replan`" and "a `plan` refused by one of them writes no warning"; "Planning": "It fails if there is none" and "It fails if an approved plan exists"; "Other commands": "fail with "run `openfactory init` first" if `./.openfactory/` is missing"). In each case standard output is empty, the exit code is 1, the stand-in `claude` is not started and no event is added:
  - No approved spec version, with an unknown key in `specs/policies.yaml`: standard error is exactly `no approved spec version`.
  - Approved `sv_01`, an approved `plan_01`, and an unknown key in `specs/policies.yaml`: standard error is exactly `policy is invalid; run openfactory validate`.
  - Approved `sv_01`, an approved `plan_01`, a valid policy, and spec files edited after the approval: standard error is exactly `plan_01 is already approved; use replan`, with no `spec files differ` line.
  - A directory with no `.openfactory/`: standard error contains "run `openfactory init` first".
- [x] AC3 ("Output": "When the spec files differ from the latest approved version, or cannot be loaded, `plan` writes the warning `spec files differ from approved sv_NN` to standard error and carries on; the warning does not change the exit code. The warning is written after the first three refusals have been checked and before `git ls-files` runs"; "Planning": "warns if the files on disk differ from it"). With approved `sv_01`:
  - A requirement's statement edited after the approval, and a good reply: standard error is exactly `spec files differ from approved sv_01`; standard output ends with `created plan_01`; the exit code is 0.
  - `specs/requirements.yaml` made invalid YAML, and a good reply: the same warning, the same status line, exit 0.
  - The edited statement and a `git` that fails: standard error is the warning line, then a line starting `git ls-files failed: `; the exit code is 1.
- [x] AC4 ("Output": "When the second reply is rejected it prints that reply's rejections as `rule  subject  message`, sorted as violation lines are, on standard output, and exits 1"; "Plan checks": "If the second reply is also rejected, `plan` exits 1 and no `PlanCreated` is recorded" and "one `plan` makes at most two planner calls"). With approved `sv_01`, a first reply the checks reject and a second reply that fails two or more checks of its own:
  - Standard output is exactly `rejection_lines` of the second reply's rejections, and holds no line of the first reply's that the second does not share, and no `created` line.
  - The exit code is 1.
  - The stand-in was started exactly twice; the event log gains four run events and no `PlanCreated`; `plans` has no row.
- [x] AC5 ("Output": "`git ls-files failed: <error>`; `planner call failed: <error>`. `<error>` is the first line of the failure's text; for a planner call that text is `AgentRunFinished.error`" and "A command that fails exits 1"; "Tech stack and repo layout": "it is not retried, the run is recorded with `exit: error` or `timeout` and `error` set, and the command exits 1"). With approved `sv_01`:
  - A `git` that exits non-zero with two lines on standard error:
    - Standard error is exactly `git ls-files failed: <the first of the two lines>`.
    - Standard output is empty and the exit code is 1.
    - The stand-in `claude` is not started and no event is added.
  - A stand-in `claude` that exits non-zero with two lines on standard error:
    - Standard error is exactly `planner call failed: <first line>`, where `<first line>` is the first line of the stored `AgentRunFinished.error`, and that stored text has both lines.
    - Standard output is empty and the exit code is 1.
    - The stand-in was started once, and the log gains `AgentRunStarted` and `AgentRunFinished` (`exit` `error`) with no `PlanCreated`.
- [x] AC6 ("Tech stack and repo layout": the row "Logging | structlog, JSON lines" and "the adapters start `claude` with that variable removed from its environment, without reading its value, and log a warning if it was present"; "Output": "Failure messages (...), warnings and log lines go to standard error"). With approved `sv_01`, a good reply and `ANTHROPIC_API_KEY` set to a value the test chooses:
  - Standard output is exactly the two task lines and `created plan_01`; the exit code is 0.
  - Standard error is exactly one line that parses as a JSON object, whose `event` is `anthropic_api_key_removed` and whose `level` is `warning`.
  - The chosen value appears in neither stream.

## Architecture rules that apply
- The change is inside `src/openfactory/cli.py`, the composition root (ADR-011): it wires, prints and sets the exit code, and holds no rule.
  - It maps `PlanRefusal` and `PlannerOutcome` to a line, a stream and an exit code.
  - It does not inspect the spec set, the policy, tasks or rejections to decide anything.
- ADR-013: `cli.py` calls `prepare_plan`, prints, then calls `create_plan` with the `PlanInputs` unchanged. The warning is written before `create_plan` is called, not from the result afterwards.
- The rejection lines come from `rejection_lines` in `domain/plan_checks.py`; no second sort is written in `cli.py`.
- The recorder is opened before the three read adapters, because only the recorder creates the tables (ADR-010). All four stay open across both calls, so both calls see one database (ADR-013, Consequences).
- No filesystem work is added to `cli.py`; the `init` exception is not copied (ADR-011).
- All LLM calls go through `claude -p`: the command wires `ClaudeCodeLLM` and nothing else. No Anthropic SDK; `ANTHROPIC_API_KEY` is not read.
- All state changes go through the events table: the command's only write path is `EventRecorder.record` inside `run_planner`.
- No module under `domain/`, `ports/`, `adapters/` or `app/` imports `openfactory.cli`; none of them is changed.
- Tests from the test-writer are fixed. No existing test file is changed.
- No hardening beyond the spec's rules.

## Plan
1. Create branch `task/TASK-034-cli-plan` from an up-to-date main.
2. Get the human's answers to the Open questions; record them here and as rows in `docs/decisions.md`.
3. Write failing tests in `tests/integration/test_cli_plan.py` (new) for AC1 to AC6.
   - Helpers are defined in the file: repo setup with real `git init`, the stand-in `claude` (the shape of the one in `tests/integration/test_claude_code_llm.py`, with a reply per start), a stand-in `git` for the failing cases, and readers for `events` and `plans`.
   - An autouse fixture removes `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE` and `ANTHROPIC_API_KEY`, puts a stand-in `claude` first on `PATH`, and calls `structlog.reset_defaults()` after each test so no logger keeps a closed `CliRunner` stream.
4. In `cli.py`, add the logging helper and call it where Open question 2 decides.
   - Processors: `add_log_level`, `JSONRenderer()`. No timestamp (answer 3).
   - The logger factory writes to the `sys.stderr` of the moment it is configured.
   - `cache_logger_on_first_use` stays off: the adapter's module-level `structlog.get_logger()` must pick up the configuration, and `capture_logs` in the existing adapter tests must keep working.
5. Add the `plan` command.
   - `require_init()`; open the recorder, then `SqliteSpecVersions`, `SqlitePlans`, `SqliteRuns`, closing all in reverse order (`contextlib.ExitStack` with `closing`, or nested `try`/`finally`).
   - Call `prepare_plan(files, versions, plans)`. On `PlanRefused`, write its line with `typer.echo(..., err=True)` and raise `typer.Exit(1)`.
   - When `spec_files_differ`, write the warning to standard error.
   - Call `create_plan(inputs, git=GitCli(Path(".")), llm=ClaudeCodeLLM(), runs=..., plans=..., recorder=...)`.
   - Print by outcome as under Scope. `<error>` is `error.splitlines()[0]`, through one private helper used for both failure lines.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until green.
7. Update the living docs and the Outcome. Commit `feat(cli): add the plan command` with trailers `Task: TASK-034` and `Milestone: M2`.

## Files expected to change
- `src/openfactory/cli.py` (about 80 lines added)
- `tests/integration/test_cli_plan.py` (new, about 350 lines)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, `CHANGELOG.md`, `README.md`
- `docs/tasks/TASK-034-cli-plan.md`

Over the 300-line aim with tests, within six criteria (Open question 4).

Not expected to change: everything under `src/openfactory/domain/`, `ports/`, `adapters/` and `app/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, and every existing test file.

## Living docs to update
- `docs/architecture.md`:
  - "CLI": the `plan` command (wiring order, the two calls, the lines per outcome, the first-line helper) and the logging helper; `require_init` gains a caller.
  - "Claude Code LLM adapter": "structlog is not configured here" gains where it is configured.
  - "Plan use case" sections and "Data flow": replace the sentences that say no command calls `run_planner`, `prepare_plan` or `create_plan` and that `cli.py` wires no M2 adapter.
- `docs/progress.md`:
  - Current, then Done; remove outline item 10.
  - Reword the TASK-030 Later line on the `warning:` first line: the command now prints the first line as the spec says.
- `docs/decisions.md`: rows for the answered questions.
- `CHANGELOG.md` and `README.md`: the `plan` command.

## New dependencies
None. structlog is already a runtime dependency (TASK-029).

## Spec gaps
Spec impact is "none". Nothing is missing for this task.

Readings, not gaps:
- "Output" names no standard-error line for a second rejected reply, so the command writes none there; AC4 asserts standard output and the exit code only. TASK-017 read a refused `approve spec` the same way.
- "The refusals, checked in this order" lists five. The first three are `PlanRefused`; `git ls-files failed` and `planner call failed` are `PlannerResult` outcomes. The order holds because `create_plan` runs after `prepare_plan` and reads git before the planner.
- A first reply rejected and a second call that fails is a failed process: `planner call failed: <error>`, not rejection lines (TASK-032 reading).
- "`<error>` is the first line of the failure's text": taken literally. When git prints `warning:` before `fatal:`, the warning is the line (Later, TASK-030).
- "Logging | structlog, JSON lines" and "log lines go to standard error" fix the form and the stream. The keys of a line are not spec text. AC6 asserts `event` (structlog's own key) and `level` (from "log a warning"), nothing else (Open question 3).
- The warning "does not change the exit code": a warned `plan` exits 0 when created and 1 when it then fails (AC3).

## Later lines in `docs/progress.md`: taken or left
- `warning:` before `fatal:` becomes `<error>` (TASK-030): the line is built here by the spec's rule; the Later line is reworded, not removed.
- A tracked name that is not UTF-8, and `GitCli` passing the caller's environment (TASK-030): left.
- An envelope with `is_error` and exit status 0, and what `claude` prints on a non-zero exit (TASK-029/TASK-031): left to the M2 close, the first real run.
- A plan with no tasks (TASK-032): left; no criterion.
- A started run with no finish (TASK-032): left.
- F-1, the recorder's catch-up failing: left; `plan` opens the recorder like `validate`.
- Bare `openfactory` help on standard output (TASK-014): left.

## Open questions
None is a spec decision. Each has a proposal.

1. **How the command tests supply the LLM.** Proposed: a stand-in `claude` script first on `PATH`, so the tests run the real wiring (`ClaudeCodeLLM()` with its default executable), in line with ADR-011 ("`cli.py` is tested only through `CliRunner` on real directories"). Each planner call costs a process start of about 0.2 to 0.6 s. Alternative: `monkeypatch.setattr` of `ClaudeCodeLLM` in `openfactory.cli` with an in-memory fake, which is faster but leaves the adapter wiring to item 13.
2. **Where structlog is configured.** Proposed: a private helper called from the Typer callback `main()`, so every command writes log lines the same way, though only `plan` can emit one today. Alternative: inside `plan` only, as the outline's wording has it; the next command that calls an adapter would then repeat the call.
3. **Fields of a log line.** Proposed: `event`, `level` and `timestamp` (ISO 8601 UTC). Alternative: `event` and `level` only, with no clock in the output.
4. **Size.** Proposed: one task of about 430 lines with tests and six criteria; every criterion shares one repo fixture and one stand-in. Alternative: TASK-034 takes AC1 to AC5 and a TASK-035 takes the structlog configuration (AC6).
5. **The approved-plan fixture.** `approve plan` is item 11, so a test that needs an approved plan must make one. Proposed: the test runs `plan`, then records `PlanApproved` for `plan_01` through `SqliteEventRecorder`. Alternative: plan item 11 first and write this refusal's test with the real command.

### Answers (human, 2026-10-12, following the advisor on all five)
1. A stand-in `claude` script first on `PATH`; the tests run the real `ClaudeCodeLLM()` wiring.
2. structlog is configured by a private helper called from the Typer callback `main()`. This refines the TASK-029 decisions row of 2026-10-11 ("is the `plan` command's"): the configuration is this task's, for every command.
3. A log line has `event` and `level` only; no `timestamp` (the advisor disagreed with the proposal, and the human took the advisor's answer).
4. One task.
5. The test runs `plan`, then records `PlanApproved` for `plan_01` through `SqliteEventRecorder`.

## Outcome
What was built:
- `plan` command in `src/openfactory/cli.py`: `require_init()`, then `_prepare_and_create_plan(database)` (recorder first, then `SqliteSpecVersions`, `SqlitePlans`, `SqliteRuns`, closed through an `ExitStack`), `prepare_plan`, the `spec files differ from approved <sv>` warning on standard error, then `create_plan` with `GitCli(Path("."))` and `ClaudeCodeLLM()`.
- `_refusal_line` (the three refusal texts) and `_first_line` (`<error>` for `git ls-files failed` and `planner call failed`). `created` prints `task_id  objective` lines then `created plan_NN` (exit 0); `rejected` prints `rejection_lines` on standard output (exit 1).
- `_configure_logging()` (structlog: `add_log_level`, `JSONRenderer`, `PrintLoggerFactory(file=sys.stderr)`, no timestamp), called from the Typer callback `main()` for every command.
- `tests/integration/test_cli_plan.py`: 12 tests for AC1 to AC6 through `CliRunner`, with the real `git` and a stand-in `claude` first on `PATH`.

Deviations from plan: none in scope. The wiring sits in a private helper `_prepare_and_create_plan`, so the adapters are closed before the result is printed.

Test edits: none (the test-writer's file is unchanged).

Checks: 971 tests pass; ruff, pyright and `check_docs` clean.

Follow-ups (Later lines in `docs/progress.md`): the repeated recorder-then-read-adapters wiring; `structlog.configure` being process-global; a `created` plan with no tasks printing only the status line; the `warning:` before `fatal:` line reworded.
