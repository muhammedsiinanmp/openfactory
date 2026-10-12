# TASK-036: `approve plan` command

- Milestone: M2
- Status: done
- Tests: acceptance
- ADR: none. ADR-011 (accepted) covers `cli.py` as the composition root, `require_init()` and "a command with a domain rule or an event calls a use case"; ADR-010 covers the recorder creating the tables when it opens, so it is opened first; ADR-012 covers `Plans`; ADR-001 covers `EventRecorder` and `SpecVersions`. No new port, adapter, dependency, event type, payload or storage change. The shared wiring helper is private to `cli.py` and binds no other module: a row in `docs/decisions.md` (Open question 1). The test fixture is a row too (Open question 2).
- Spec impact: none. Spec v1.11 settles the task lines, the status line, the two refusal texts, their streams, the exit codes, the events and which tasks become `ready` (see "Spec gaps": readings only).
- Spec sections (spec v1.11): "CLI commands" (the command table row for `openfactory approve plan`; "Other commands"; "Output": the `approve plan` bullet, "A command that fails exits 1", and the bullet that starts "Command results"); "Task contract" › "Planning" ("`openfactory approve plan` fails if the draft's spec version is not the latest approved version"); "Domain model and storage" › "Streams and actors" (the rows for `PlanApproved` and `TaskStateChanged`; the sentence that starts "`approve plan` records `PlanApproved`"); "Task state machine" ("When its plan is approved, a task with no dependencies moves to `ready`. A task with dependencies stays `pending`"); "Milestones and definition of done" (milestone 2)

## Outline item
M2 outline item 11, second and last piece: the command. The use case is TASK-035. Items 12 (`deleted-requirement`) and 13 (M2 close test) are left.

## Objective
Add the `openfactory approve plan` command to `src/openfactory/cli.py`: it wires the SQLite adapters to `approve_plan`, prints the `task_id  ready` lines and `approved plan_NN` on standard output or one refusal line on standard error, and sets the exit code.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings.

## Scope
In, all in `src/openfactory/cli.py`:
- A `plan` command in the `approve` group (`approve_app`), with no arguments. The name `plan` is already taken at module level by the top-level command, so the function gets another name and is registered with `@approve_app.command("plan")`.
  - It calls `require_init()`.
  - It opens `SqliteEventRecorder` first, then the read adapters on the same path, calls `approve_plan(versions, plans, recorder)` and closes every adapter before printing.
- From `ApprovePlanResult.outcome`:
  - `approved`: one `<task_id>  ready` line per id in `result.ready`, in the order the result gives them, then `approved <plan_id>`, on standard output, exit 0.
  - `no_draft`: `no draft plan` on standard error, exit 1.
  - `stale_draft`: `<plan_id> was made for <spec_version>; run openfactory plan` on standard error, exit 1.
- The help text of the `approve` group and its callback docstring, which today read "Approve a spec version.", name the plan as well.
- One private helper that opens the recorder and then the read adapters and closes them in reverse order, used by `validate`, `approve spec`, `plan` and `approve plan` (the Later line of TASK-034; Open question 1). The three existing commands keep their behaviour; their existing tests are the check and are not edited.
- Tests that run the real app through `typer.testing.CliRunner` in a repo under `tmp_path`.

Out (not this task):
- Any change under `domain/`, `ports/`, `adapters/` or `app/`. `approve_plan` is used as TASK-035 left it.
- The `deleted-requirement` rule and the `Plans` argument of `validate` and `approve spec` (item 12). The helper makes `Plans` available to them; this task does not pass it.
- The M2 close test: `plan` then `approve plan` with a stand-in `claude`, and the rebuild (item 13).
- Replacing the `approve_plan_01` helper in `tests/integration/test_cli_plan.py`, which records `PlanApproved` directly: that file is a fixed test file and stays as it is.
- A failure between `PlanApproved` and a `TaskStateChanged` (Later, TASK-035, "Spec gap (before M3 is planned)"): the exception propagates.
- What the command prints when the recorder's catch-up fails (Later, F-1): the exception propagates.
- A draft with no tasks (Later, TASK-032): the command prints only `approved plan_NN`; no criterion.
- A shared `conftest.py` fixture for `structlog.reset_defaults()` (Later, TASK-034): left.
- Bare `openfactory approve` printing the help on standard output (Later, TASK-014): left.
- Hardening: an unreadable database, a `.openfactory` path that is a file.

## Acceptance criteria
"Output" and "Other commands" are under "CLI commands"; "Planning" under "Task contract"; "Streams and actors" under "Domain model and storage".

Fixtures:
- "The repo" is a directory under `tmp_path` with a `.git` directory and `init` run on it, as in `tests/integration/test_cli_approve_spec.py`. No `git` and no `claude` process is started.
- "Approved `sv_01`" means valid spec files (`REQ-AUTH-001` with two criteria, component `auth`) approved by running `approve spec` through the app.
- "The draft `plan_01`" is made by the test recording one `PlanCreated` through `SqliteEventRecorder` (Open question 2): plan `plan_01`, spec version `sv_01`, with four complete contracts: `AUTH-001` (no dependencies), `AUTH-002` (depends on `AUTH-001`), `AUTH-010` (no dependencies), `DB-001` (no dependencies).
- Every run is `approve plan` through `CliRunner` with the repo as the current directory.

- [x] AC1 ("Output": "`approve plan` prints one line per task made ready as `task_id  ready`, in ascending task id as strings, then the status line `approved plan_NN`, and exits 0" and "Command results (...; task and rejection lines; ...) go to standard output"). With approved `sv_01` and the draft `plan_01`:
  - Standard output is exactly `AUTH-001  ready`, `AUTH-010  ready`, `DB-001  ready`, `approved plan_01`, with two spaces between the fields. There is no line for `AUTH-002`.
  - Standard error is empty and the exit code is 0.
- [x] AC2 (the command table: "Marks the latest draft plan approved; tasks with no dependencies become `ready`"; "Streams and actors": "`approve plan` records `PlanApproved`, with no `causation_id`, then one `TaskStateChanged` per task with no dependencies, in ascending task id as strings, each pointing at `PlanApproved`" and the rows "`PlanApproved` | `plan:<plan id>` | `human`" and "`TaskStateChanged` | `task:<task id>` | `orchestrator`"; "Task state machine": "When its plan is approved, a task with no dependencies moves to `ready`. A task with dependencies stays `pending`"). After the AC1 run:
  - The event log gains exactly four events: `PlanApproved` on stream `plan:plan_01` with actor `human` and no `causation_id`, then `TaskStateChanged` on `task:AUTH-001`, `task:AUTH-010`, `task:DB-001`, in that order, each with actor `orchestrator` and `causation_id` equal to the `PlanApproved` event id.
  - The `plans` row `plan_01` has status `approved`.
  - In `tasks`, `AUTH-001`, `AUTH-010` and `DB-001` have state `ready` and `AUTH-002` has state `pending`.
- [x] AC3 ("Output": "It refuses with one line on standard error and exits 1: `no draft plan`" and "Failure messages (..., the refusals of `plan` and `approve plan`, ...) ... go to standard error"). In each case standard output is empty, standard error is exactly `no draft plan`, the exit code is 1 and no event is added:
  - Approved `sv_01` and no plan.
  - Approved `sv_01` and the draft `plan_01`, after one `approve plan` that succeeded: the second run.
- [x] AC4 ("Planning": "`openfactory approve plan` fails if the draft's spec version is not the latest approved version"; "Output": "`plan_NN was made for sv_NN; run openfactory plan` when the draft's spec version is not the latest approved one"). With approved `sv_01`, the draft `plan_01`, then a requirement's statement edited and `approve spec` run again so that `sv_02` is the latest approved version:
  - Standard error is exactly `plan_01 was made for sv_01; run openfactory plan`.
  - Standard output is empty and the exit code is 1.
  - No event is added; the `plans` row `plan_01` still has status `draft` and every task is still `pending`.
- [x] AC5 ("Other commands": "fail with "run `openfactory init` first" if `./.openfactory/` is missing"; "Output": "A command that fails exits 1"). In a directory with no `.openfactory/`:
  - Standard error contains "run `openfactory init` first".
  - Standard output is empty and the exit code is 1.
  - No `.openfactory/` directory is created.

## Architecture rules that apply
- The change is inside `src/openfactory/cli.py`, the composition root (ADR-011): it wires, prints and sets the exit code, and holds no rule.
  - It maps `ApprovePlanOutcome` to lines, a stream and an exit code.
  - It does not read the draft, the tasks or the spec versions itself, and does not sort: the ids come from `ApprovePlanResult.ready` in the order the use case gives them.
- The recorder is opened before the read adapters, because only the recorder creates the tables (ADR-010). The helper keeps that order for all four commands.
- In `plan`, all four adapters stay open across `prepare_plan` and `create_plan`, and the warning is still written between the two calls (ADR-013).
- No filesystem work is added to `cli.py`; the `init` exception is not copied (ADR-011).
- All state changes go through the events table: the command's only write path is `EventRecorder.record` inside `approve_plan`.
- No module under `domain/`, `ports/`, `adapters/` or `app/` imports `openfactory.cli`; none of them is changed.
- Tests from the test-writer are fixed. No existing test file is changed; the tests of `validate`, `approve spec`, `plan` and the M1 close must pass as they are after the helper is introduced.
- No hardening beyond the spec's rules.

## Plan
1. Create branch `task/TASK-036-cli-approve-plan` from an up-to-date main.
2. Get the human's answers to the Open questions; record them here and as rows in `docs/decisions.md`.
3. Write failing tests in `tests/integration/test_cli_approve_plan.py` (new) for AC1 to AC5.
   - Helpers are defined in the file (the repo has no shared test helpers): repo setup as in `test_cli_approve_spec.py`, a `PlanCreated` builder as in `tests/integration/test_sqlite_plans.py` (`TaskContract`, `PlanCreatedPayload`, `Event.new`, recorded through `SqliteEventRecorder`), and readers for `events`, `plans` and `tasks`.
4. In `cli.py`, add the wiring helper (Open question 1): a context manager that opens `SqliteEventRecorder`, then `SqliteSpecVersions`, `SqlitePlans` and `SqliteRuns` on the database path through an `ExitStack` with `closing`, and yields them as one small frozen object.
5. Move `validate`, `approve spec` and `_prepare_and_create_plan` onto the helper, with the result still printed after the adapters are closed (for `plan`, the warning still inside). Run the existing tests; they must pass unchanged.
6. Add the `approve plan` command.
   - `require_init()`; inside the helper, call `approve_plan(versions, plans, recorder)`.
   - `no_draft`: `typer.echo("no draft plan", err=True)`, `typer.Exit(1)`.
   - `stale_draft`: `typer.echo(f"{result.plan_id} was made for {result.spec_version}; run openfactory plan", err=True)`, `typer.Exit(1)`.
   - `approved`: one `f"{task_id}  ready"` per id in `result.ready`, then `f"approved {result.plan_id}"`.
   - Update the `approve` group's help and callback docstring.
7. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until green.
8. Update the living docs and the Outcome. Commit `feat(cli): add the approve plan command` with trailers `Task: TASK-036` and `Milestone: M2`.

## Files expected to change
- `src/openfactory/cli.py` (about 50 lines added, about 25 removed)
- `tests/integration/test_cli_approve_plan.py` (new, about 220 lines)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, `CHANGELOG.md`, `README.md`
- `docs/tasks/TASK-036-cli-approve-plan.md`

Not expected to change: everything under `src/openfactory/domain/`, `ports/`, `adapters/` and `app/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, and every existing test file.

## Living docs to update
- `docs/architecture.md`:
  - "CLI": the `approve plan` command (wiring, lines per outcome, exit codes); the wiring helper; in the `validate`, `approve spec` and `plan` bullets, replace "The adapter wiring is repeated ..., not shared" and the per-command adapter lists with the helper; `require_init` gains a caller; the `approve` group now has two commands.
  - "Approve plan use case": replace "No command calls it yet".
  - "Data flow": the sentences that say no command calls `approve_plan`.
- `docs/progress.md`:
  - Current, then Done; remove outline item 11.
  - Remove the TASK-034 Later line on the repeated wiring (taken here, if Open question 1 is answered as proposed; otherwise reword it to point at item 12).
- `docs/decisions.md`: rows for the answered questions.
- `CHANGELOG.md` and `README.md`: the `approve plan` command.

## New dependencies
None.

## Spec gaps
Spec impact is "none". Nothing is missing for this task.

Readings, not gaps:
- "Marks the latest draft plan approved": there is at most one draft, because the projector marks an earlier draft `superseded` when a new `PlanCreated` is recorded ("Planning", last bullet). `Plans.current_draft()` gives it (TASK-025).
- In `plan_NN was made for sv_NN; run openfactory plan`, `plan_NN` is the draft's id and `sv_NN` the draft's spec version ("was made for"), both from `ApprovePlanResult` (TASK-035 reading).
- `no draft plan` covers every state without a draft: no plan at all, and an already approved plan. The spec names no separate line for a second `approve plan`, so AC3 asserts `no draft plan` for it.
- `approve plan` compares version ids from the projections. It does not load the spec files or the policy, and the spec names no `spec files differ` warning for it, so the command writes none (TASK-035 reading).
- "Output" names no standard-output line for a refusal, so standard output is empty then (AC3, AC4).
- The `ready` in `task_id  ready` is the literal word in the spec's line, the same for every task.

## Later lines in `docs/progress.md`: taken or left
- The repeated recorder-then-read-adapters wiring in `cli.py` (TASK-034, planner): taken (Open question 1).
- `approve_plan` records its events in separate transactions (TASK-035): left; the command lets the exception propagate.
- `structlog.configure` is process-global and only `test_cli_plan.py` resets it (TASK-034): left; `approve plan` emits no log line.
- A `created` plan with no tasks, and a plan with no tasks at all (TASK-032, TASK-034): left; no criterion.
- F-1, the recorder's catch-up failing: left.
- Bare `openfactory approve` help on standard output (TASK-014, TASK-017): left.
- The stand-in `git` timing check for the `plan` warning (TASK-034, reviewer): left to the M2 close test.

## Open questions
None is a spec decision. Each has a proposal, and neither blocks planning.

Answered by the human on 2026-10-12: both as proposed (the advisor agreed on both). The helper is in scope and all four commands use it; the tests record `PlanCreated` through `SqliteEventRecorder`.

1. **The shared wiring helper (the TASK-034 Later line).** `approve plan` would be the fourth copy of "open the recorder, then the read adapters, close in reverse". Proposed: in scope. One private context manager in `cli.py` opens the recorder and then `SqliteSpecVersions`, `SqlitePlans` and `SqliteRuns`, always all three, and all four commands use it. The three read adapters only open a connection and set `busy_timeout`, so opening one a command does not use costs nothing that matters. Item 12 then only passes the `Plans` it already has to `validate` and `approve spec`. The cost is that three working commands are touched in a task about a fourth, with no criterion of their own: their existing tests, unchanged, are the check. Alternative: write `approve plan` with its own `ExitStack` and leave the helper to item 12, which changes the wiring of `validate` and `approve spec` anyway; the Later line is then reworded, and this task shrinks by about 30 changed lines.
2. **How the command tests get a draft plan.** Proposed: the test records one `PlanCreated` through `SqliteEventRecorder`, with contracts built from `TaskContract` as in `tests/integration/test_sqlite_plans.py`. The command under test wires no git and no LLM, so the tests need neither a real `git` nor a stand-in `claude`, and the task ids and dependencies are chosen freely (three ready tasks, out of four). This mirrors the TASK-034 answer 5 in the other direction. Alternative: run the real `plan` with the stand-in `claude` copied from `tests/integration/test_cli_plan.py` (about 100 more lines of helpers, and a process start per test); the chain `plan` then `approve plan` is item 13's.

## Outcome
Built as planned, all in `src/openfactory/cli.py`:
- `_open_adapters(database)`, a private context manager that opens `SqliteEventRecorder`, then `SqliteSpecVersions`, `SqlitePlans` and `SqliteRuns`, yields them as the frozen dataclass `_Adapters` and closes them in reverse order. `validate`, `approve spec`, `plan` (`_prepare_and_create_plan`) and `approve plan` use it.
- `approve plan` (`approve_plan_command`, registered with `@approve_app.command("plan")`): calls `approve_plan` and prints the `task_id  ready` lines and `approved plan_NN` (exit 0), or `no draft plan` or `plan_NN was made for sv_NN; run openfactory plan` on standard error (exit 1).
- The `approve` group's help and callback docstring read "Approve a spec version or a plan."

Tests: `tests/integration/test_cli_approve_plan.py`, six tests for AC1 to AC5, from the test-writer; none was edited. No existing test file was changed.

Deviations from plan: none. The helper's return type is `Generator[_Adapters]`, because pyright reports `Iterator` with `@contextmanager` as deprecated.

Follow-ups: none new. Item 12 passes `adapters.plans` to `validate` and `approve spec`.
