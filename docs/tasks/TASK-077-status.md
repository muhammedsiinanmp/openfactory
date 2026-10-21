# TASK-077: `status` use case and command

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-015 (accepted) and ADR-011 (accepted). ADR-015 ("Ports and adapters (SC-84, SC-87, SC-89, SC-92)") adds "the last gate result of a task, for `status`" to `Plans`. TASK-064 built that read as `Plans.last_gate_result`. ADR-015 also puts the `status` use case in `app` "with no I/O of their own". ADR-011 makes `cli.py` the composition root. This task adds no port, adapter, dependency, event type, payload, schema or convention, so no new ADR is needed.
- Spec impact: none
- Spec sections (spec v1.16; SC-92):
  - "CLI commands" table row: "`openfactory status` | Shows tasks, states, attempts and last gate result".
  - "CLI commands" › "Output": "`status` prints one line per task of the approved plan, in ascending task id as strings, as `task_id  state  attempt/max_attempts  gate`, where `gate` is `<gate> passed` or `<gate> failed` for the last gate, in `required_gates` order, evaluated for the task's latest implementer run that has a gate result, or `-` when there is none, and exits 0. It records no events and does not repair the plan. With no approved plan it writes `no approved plan` to standard error and exits 1."
  - "CLI commands" › "Output": "A command that fails exits 1" and "Command results (... status lines; task ... lines ...) go to standard output. Failure messages (... "run `openfactory init` first", the refusals of ... `status` ...) ... go to standard error."
  - "CLI commands" › "Other commands": "run against the current directory and fail with "run `openfactory init` first" if `./.openfactory/` is missing."
  - "Domain model and storage" › "Ids": "They read the plan and task projections through the `Plans` port: ... the tasks of a plan with their dependencies, ... and the last gate result of a task (for `status`)."
  - "Domain model and storage" › "Projection rules": "A task has attempts left while `attempt < limits.max_attempts`." This is the source of the `attempt` and `max_attempts` fields.
  - "Milestones and definition of done", item 4: "**Gates and remediation.** `status`, `resolve`; ..."

## Outline item
This is M4 outline item 12. It depends on item 4 (`Plans.last_gate_result`, TASK-064, done). Only item 13, the M4 close, comes after it.

## Objective
`openfactory status` prints `task_id  state  attempt/max_attempts  gate` for each task of the approved plan and exits 0. With no approved plan it writes `no approved plan` to standard error and exits 1. It records no events and does no repair.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- New `src/openfactory/app/status.py`. It imports only `domain` and `ports`.
  - `plan_status(*, plans: Plans) -> StatusReport`.
  - `StatusReport` is frozen. It holds `refusal` (a one-member `StatusRefusal.no_approved_plan`, or `None`) and `tasks: list[TaskStatus]`.
  - `TaskStatus` is frozen. It holds `task_id`, `state: TaskState`, `attempt: int`, `max_attempts: int` and `gate: GateResultRef | None`.
  - The use case reads `Plans.approved()`, then `Plans.tasks(plan.id)`, sorted by id as strings, then `Plans.last_gate_result(task.id)` per task. `max_attempts` comes from `task.contract.limits.max_attempts`.
  - It has no recorder parameter, so it cannot record an event.
- `src/openfactory/cli.py`:
  - New top-level command `status`, no arguments.
  - It calls `require_init()`, opens `_open_adapters`, calls `plan_status(plans=adapters.plans)` and closes the adapters before printing.
  - A private `_status_line(t: TaskStatus) -> str` builds the line `f"{id}  {state}  {attempt}/{max}  {gate}"`. `gate` is `<gate> passed`, `<gate> failed` or `-`.
  - A refusal writes `no approved plan` to standard error and exits 1.
- New `tests/unit/test_status.py`, using a fake `Plans`.
- New `tests/integration/test_cli_status.py`. It seeds events through `SqliteEventRecorder` and drives the Typer app with `CliRunner`, as `test_cli_resolve.py` does.

Out:
- Any change to `Plans`, `SqlitePlans`, the projector, `domain/` or the other use cases.
- Any repair, worktree, git, gate or LLM adapter for `status`.
- The M4 close test (item 13).
- The cross-plan exposure of `last_gate_result` is already in Later as "Before M6". It is not touched here.

## Acceptance criteria
- [ ] **AC1** ("Output": "`status` prints one line per task of the approved plan, in ascending task id as strings, as `task_id  state  attempt/max_attempts  gate` ... and exits 0"):
  - Seed an approved plan with `AUTH-001`, `AUTH-002` and `AUTH-010` in different states (for example `passed`, `ready`, `pending`).
  - `status` prints exactly one line per task, in ascending string order, with the fields separated by two spaces.
  - Nothing goes to standard error, and the exit code is 0.
- [ ] **AC2** ("Output": "where `gate` is `<gate> passed` or `<gate> failed` for the last gate, in `required_gates` order, evaluated for the task's latest implementer run that has a gate result, or `-` when there is none"):
  - A task whose implementer run recorded `path_check` passed and `ruff` failed shows `ruff failed`.
  - A task whose latest implementer run recorded all five gates passing shows `review passed`.
  - A task with no gate result shows `-`.
- [ ] **AC3** ("Output": "`attempt/max_attempts`"; "Projection rules": "A task has attempts left while `attempt < limits.max_attempts`"):
  - The field is the task's projected `attempt` and its contract's `limits.max_attempts`. With a policy of `max_attempts: 2`:
    - a task moved to `running` once shows `1/2`;
    - a task never run shows `0/2`;
    - a task escalated after two attempts and then given `resolve --retry` shows `0/2`.
- [ ] **AC4** ("Output": "It records no events and does not repair the plan"):
  - Seed a task left in `running` with an unfinished implementer run, which is the state a killed `run` leaves.
  - `status` shows it as `running`.
  - The `events` table's row count is unchanged after the command.
  - `cli.py`'s `status` passes only `adapters.plans` to the use case. No git, worktree, executor, gate or LLM adapter is built for it.
- [ ] **AC5** ("Output": "With no approved plan it writes `no approved plan` to standard error and exits 1"; refusals go to standard error):
  - In an initialised repo whose only plan is a draft, `status` writes exactly `no approved plan` on standard error.
  - Standard output is empty, the exit code is 1 and no event is recorded.
- [ ] **AC6** ("Other commands": "fail with "run `openfactory init` first" if `./.openfactory/` is missing"):
  - In a directory without `.openfactory/`, `status` writes that line to standard error and exits 1.

## Architecture rules that apply
- `app/status.py` depends on `domain` and `ports` only, does no I/O and returns data. `cli.py` formats, prints and sets exit codes (ADR-011).
- All output is written after the adapters are closed, as in `approve plan` and `resolve`.

## Plan
1. Create branch `task/TASK-077-status` from an up-to-date main.
2. Test-writer: write failing tests.
   - `tests/unit/test_status.py`: the use case with a fake `Plans`, covering sorting, the fields, `gate` `None`, the refusal, and only reads called.
   - `tests/integration/test_cli_status.py`: AC1 to AC6. Seed the state through `SqliteEventRecorder` with `PlanCreated`, `PlanApproved`, `TaskStateChanged`, `AgentRunStarted` (role `implementer`), `GateEvaluated` and `TaskResolved`. Read the event count with `sqlite3`.
3. Implement `app/status.py`, then the `status` command and `_status_line` in `cli.py`.
4. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
5. Update the docs:
   - `docs/architecture.md`: a new "Status use case" section; a `status` bullet under "CLI"; `status` added to the `require_init()` and `_open_adapters` lists; the "nothing calls it yet" sentence about `Plans.last_gate_result` updated.
   - `docs/progress.md`: Current, a Done line, and item 12 removed from the outline.
   - Fill in the Outcome.
6. Commit `feat(cli): add the status command` with the trailers `Task: TASK-077` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/app/status.py` (new, about +50)
- `src/openfactory/cli.py` (about +30)
- `tests/unit/test_status.py` (new, about +90)
- `tests/integration/test_cli_status.py` (new, about +150)
- `docs/architecture.md`, `docs/progress.md`
- `docs/tasks/TASK-077-status.md` (this record)

Not expected to change: `ports/`, `adapters/`, `domain/`, other `app/` modules, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 300 lines, about 80 of them in `src/`.

## Design choices to confirm at planning
1. **`status` reuses `_open_adapters`, so the recorder opens and runs its catch-up.** Catch-up writes projections and `projection_state`, never an event, so "records no events" holds. The alternative (open only `SqlitePlans`, read-only) could show stale projections and would need the tables to already exist. Recommendation: reuse `_open_adapters`, as every other command that reads projections does.
2. **The use case returns data and `cli.py` formats the line**, following the `run` and `resolve` precedent. `TaskStatus.gate` is the `GateResultRef` itself, not a preformatted string.
3. **Sorting:** the use case sorts by `task.id` in Python even though `SqlitePlans.tasks` already orders by id. This pins "ascending task id as strings" in `app`, not in an adapter's SQL.
4. **Two-space separator:** the spec states the "exactly two spaces" rule for the `validate` lines. The `status` template, and the `run`, `resolve` and `approve plan` lines, use the same two-space form. This record reads the template literally. It is not a gap.

## Open questions
None.

## Spec gaps
None. A gate row outside the contract's `required_gates` is already in Later (TASK-064). It is unreachable, since `complete_contract` sets all five gates, and it does not affect this task.

## Outcome
Added `src/openfactory/app/status.py` (`plan_status`, `StatusReport`, `TaskStatus`, `StatusRefusal`) and the `status` command with `_status_line` in `src/openfactory/cli.py`, with `tests/unit/test_status.py` and `tests/integration/test_cli_status.py`. The use case takes only `Plans`, so it records no events. No port, adapter, dependency, event type, payload or schema changed. Docs: `docs/architecture.md` (Status use case section, `status` CLI bullet, `require_init()` and `_open_adapters` lists, `Plans.last_gate_result` sentence) and `docs/progress.md`.

Mechanical test edits (assertion intent unchanged), made to satisfy ruff:
- `tests/unit/test_status.py`: the two `pytest.raises(Exception)` became `pytest.raises(ValidationError)` (B017; pydantic frozen models raise `ValidationError`), with the import added.
- `ruff format` wrapped one over-long line in each test file.

Results: 1588 tests pass; ruff, pyright and check_docs clean.
