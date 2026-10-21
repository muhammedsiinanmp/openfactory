# TASK-076: `resolve` command

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-015 (accepted) and ADR-011 (accepted). ADR-015 defines `TaskResolved` and the move out of `escalated`; TASK-075 implemented them in `app/resolve.py`. ADR-011 makes `cli.py` the composition root. This task adds no port, adapter, dependency, event type, payload, schema or convention. No new ADR is needed. The usage-error wording and its order against the init check get one `docs/decisions.md` row once the human answers (see Spec gaps).
- Spec impact: wording
- Spec sections (spec v1.16; SC-90):
  - "CLI commands" table row: "`openfactory resolve TASK-ID --retry | --abandon` | Human action on an escalated task: retry or abandon".
  - "CLI commands" › "Output": "`resolve TASK-ID` takes exactly one of `--retry` and `--abandon`; neither or both is a usage error. It records `TaskResolved` ... prints `task_id  <state>` and exits 0. It does not run the task. It refuses with one line on standard error and exits 1, before any event, checked in this order: `no approved plan`; `unknown task <ID>`, when the approved plan has no such task; `<ID> is <state>, not escalated`. A task escalated on a path violation or a secret can be retried."
  - "Output": "A command that fails exits 1; a usage error exits 2." and "Failure messages (... the refusals of ... `resolve`, usage errors) ... go to standard error."
  - "Other commands": "run against the current directory and fail with "run `openfactory init` first" if `./.openfactory/` is missing."

## Outline item
This is slice 11b of M4 outline item 11. It depends on 11a (TASK-075, done). Next come item 12 (`status`) and item 13 (the M4 close).

## Objective
`openfactory resolve TASK-ID --retry | --abandon` calls `resolve_task`. On success it prints `task_id  <state>` and exits 0. A refusal is one line on standard error with exit 1. Neither flag or both flags is a usage error with exit 2.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/cli.py`:
  - New top-level command `resolve` with a positional `task_id: str` and two bool flags, `--retry` and `--abandon`.
  - First it checks that exactly one flag is given; otherwise it writes the usage message to standard error and raises `typer.Exit(2)`.
  - Then it calls `require_init()`, opens `_open_adapters`, calls `resolve_task(task_id, "retry" | "abandon", plans=adapters.plans, recorder=adapters.recorder)` and closes the adapters before printing.
  - New private `_resolve_refusal_line(refusal, detail, task_id)` maps the refusals to `no approved plan`, `unknown task <ID>` and `<ID> is <detail>, not escalated`, ending in `assert_never`, as `_run_refusal_line` does.
  - On success it prints `<task_id>  <state value>` on standard output.
- New `tests/integration/test_cli_resolve.py`. It seeds an approved plan and an escalated task through `SqliteEventRecorder`, then drives the Typer app with `CliRunner`, as `test_cli_approve_plan.py` does.

Out:
- Any change to `app/resolve.py`, ports, adapters, domain or the projector.
- Running the task after a retry ("It does not run the task").
- `status` (item 12) and the M4 close test (item 13).

## Acceptance criteria
- [x] **AC1** ("Output": "records `TaskResolved` with `decision` `retry` ..., then the orchestrator's `TaskStateChanged` `escalated` to `ready` ..., prints `task_id  <state>` and exits 0. It does not run the task. ... A task escalated on a path violation or a secret can be retried"):
  - Seed `AUTH-001` escalated with reason `path violation`.
  - `resolve AUTH-001 --retry` prints exactly `AUTH-001  ready` on standard output, writes nothing to standard error and exits 0.
  - The log gains exactly two events: `TaskResolved` (actor `human`, `decision` `retry`, null causation), then `TaskStateChanged` `escalated` to `ready` (actor `orchestrator`, null reason) pointing at it. No `AgentRunStarted` follows.
  - The `tasks` row shows `ready` with `attempt` 0.
- [x] **AC2** ("Output": "... or `escalated` to `abandoned`"):
  - `resolve AUTH-001 --abandon` on an escalated task prints `AUTH-001  abandoned` and exits 0.
  - The two events carry `decision` `abandon` and `escalated` to `abandoned`.
- [x] **AC3** ("Output": "It refuses with one line on standard error and exits 1, before any event, checked in this order"):
  - With no approved plan (a draft holding `AUTH-001`), it writes `no approved plan`.
  - With an approved plan, `resolve ZZZ-999 --retry` writes `unknown task ZZZ-999`.
  - For a `pending` task `AUTH-002` it writes `AUTH-002 is pending, not escalated`.
  - Each refusal is exactly that one line on standard error, with nothing on standard output, exit 1, and the event count unchanged.
- [x] **AC4** ("Output": "takes exactly one of `--retry` and `--abandon`; neither or both is a usage error"; "a usage error exits 2"; usage errors go to standard error):
  - Test in an initialised repo with an escalated task.
  - Run `resolve AUTH-001` with neither flag, then `resolve AUTH-001 --retry --abandon`.
  - Each exits 2, writes nothing to standard output and something to standard error, and records no event (the task stays `escalated`).
- [x] **AC5** ("Other commands": "fail with "run `openfactory init` first" if `./.openfactory/` is missing"):
  - In a directory without `.openfactory/`, `resolve AUTH-001 --retry` writes that line to standard error and exits 1.
- [x] **AC6** (ADR-011; "It does not run the task"):
  - `cli.py` calls `resolve_task` with `adapters.plans` and `adapters.recorder` only.
  - No git, worktree, executor, gate or LLM adapter is built for `resolve`.
  - The suite passes with no existing test edited.

## Architecture rules that apply
- `cli.py` wires, prints and sets exit codes. The use case records the events.
- All output is written after the adapters are closed, as in `approve plan`.

## Plan
1. Create branch `task/TASK-076-cli-resolve` from an up-to-date main.
2. Test-writer: write failing tests for AC1 to AC6 in `tests/integration/test_cli_resolve.py`.
   - Seed the state with `PlanCreated`, `PlanApproved` and `TaskStateChanged` moves to `escalated` through `SqliteEventRecorder`.
   - Read events and `tasks` with `sqlite3`.
3. Implement the `resolve` command and `_resolve_refusal_line` in `cli.py`.
4. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
5. Update the docs:
   - `docs/architecture.md` "CLI": add a `resolve` bullet, and add `resolve` to the `require_init()` and `_open_adapters` lists.
   - `docs/architecture.md` "Resolve use case": drop "will".
   - `docs/decisions.md`: one row for the usage-error answers.
   - `docs/progress.md`: Current, a Done line, and item 11 removed from the outline.
   - Fill in the Outcome.
6. Commit `feat(cli): add the resolve command` with the trailers `Task: TASK-076` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/cli.py` (about +40)
- `tests/integration/test_cli_resolve.py` (new, about +180)
- `docs/architecture.md`, `docs/decisions.md`, `docs/progress.md`
- `docs/tasks/TASK-076-cli-resolve.md` (this record)

Not expected to change: `app/`, `ports/`, `adapters/`, `domain/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 230 lines, about 40 of them in `src/`.

## Design choices to confirm at planning
1. **Usage error raised in the command body with `typer.echo(..., err=True)` and `typer.Exit(2)`.** Typer has no built-in "exactly one of" flags. The other route, raising `click.UsageError`, would import `click` directly. `click` is only a transitive dependency, so that import would need a `decisions.md` dependency row.
2. **Usage-error text (decided 2026-10-21):** answer given: `give exactly one of --retry and --abandon`. Tests check only the exit code, an empty standard output and a non-empty standard error.
3. **Order (decided 2026-10-21):** answer given: the flag check runs before `require_init()`, as click's own parsing errors (a missing `TASK-ID`, an unknown option) already do. AC4 runs in an initialised repo, so the tests do not depend on this answer.
4. **`_open_adapters` is reused** even though only `plans` and `recorder` are needed. Every other command that records events does the same.

## Open questions
None. Both Spec gaps were answered at planning on 2026-10-21 as proposed.

## Spec gaps
1. **"CLI commands" › "Output"**, "neither or both is a usage error": no message text is given for the usage error. Non-blocking: exit 2 and standard error are fixed by the spec, and the tests check only those. The proposed text (Design choice 2) needs the human's yes, recorded in `docs/decisions.md`.
2. **"CLI commands" › "Other commands" vs "Output"**: the spec doesn't say whether the `--retry`/`--abandon` usage error comes before or after the "run `openfactory init` first" check. Non-blocking: no AC depends on the order. The proposal (usage error first, as click's parsing errors) needs the human's yes, recorded in `docs/decisions.md`.

## Outcome
Built the `resolve` command in `src/openfactory/cli.py` and the private `_resolve_refusal_line`. The flag check (exactly one of `--retry`, `--abandon`; otherwise `give exactly one of --retry and --abandon` on standard error, exit 2) runs before `require_init()`. The command then calls `resolve_task` with `adapters.plans` and `adapters.recorder`, closes the adapters, and prints `task_id  <state>` (exit 0) or one refusal line on standard error (exit 1). Added `tests/integration/test_cli_resolve.py`. No change to `app/`, ports, adapters, domain, `pyproject.toml` or ADRs.

Checks: pytest (1578 passed), ruff, pyright and check_docs are all green.

Test edit (non-mechanical, approved by the human): the AC1/AC2 test now expects `attempt` per case, 0 for retry and 1 for abandon, per spec "Projection rules" ("abandon changes no row"; only retry resets `attempt`). The assertion was also split across lines for the line-length limit. No other test was edited.

Docs: `docs/architecture.md` (CLI `resolve` bullet, `require_init()` and `_open_adapters` lists, "Resolve use case"), `docs/decisions.md` (usage-error and test-edit rows), `docs/progress.md`.
