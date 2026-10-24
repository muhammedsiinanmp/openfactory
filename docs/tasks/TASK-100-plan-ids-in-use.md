# TASK-100: Plan wiring — the task ids in use reach the plan checks

- Milestone: M6
- Status: done
- Tests: acceptance
- ADR: ADR-019 (accepted). Its "Plan checks" bullet makes `task-id-in-use` "a new rule for every plan", and its "Ports" bullet says "No new port". ADR-012 covers the `Plans` read port. ADR-013 covers `plan` as two use-case calls, with `create_plan` the call that reads before `run_planner`. The task adds one method to an existing port and its adapter, as TASK-042 and TASK-064 did. It adds no port, adapter, event type, payload field, table, column, dependency or convention, so no new ADR is needed. Design choice 1 adds one row to `docs/decisions.md`.
- Spec impact: none
- Spec sections (spec v1.19):
  - "Task contract" › "Plan checks" table, `task-id-in-use`: "a `task_id` is already in the `tasks` projection, outside the draft being replaced" | subject "the task id" (SC-163)
  - "Task contract" › "Planning": "A task id is unique among all tasks in the `tasks` projection; the `task-id-in-use` check enforces it."
  - "Task contract" › "Planning": "Running `plan` again while a draft plan exists records a new `PlanCreated`. The projector marks the earlier draft `superseded` and removes its tasks from `tasks` and `task_deps` … The new draft may reuse their ids."
  - "Task contract" › "Plan checks": "A reply rejected by Pydantic or by the plan checks … is retried once with the same prompt and the rejection lines added to it … a rejected reply has `exit: ok` and `error` set to its rejection lines … If the second reply is also rejected, `plan` exits 1 and no `PlanCreated` is recorded."
  - "Domain model and storage" › "Projection rules": "A `PlanApproved` applied while another plan is `approved` … moves every one of its tasks, whatever its state, to the newly approved plan … after a replan it holds the untouched, the invalidated and the new tasks."

## Outline item
M6 outline item 5, second half (5b). 5a (TASK-099) gave `check_plan` the keyword-only `ids_in_use` and `untouched`, and nothing passes them yet. This task passes `ids_in_use` for `plan`. Item 6 (`replan`) passes `untouched` and reuses the same read.

## Objective
`Plans` gains a read of the task ids in the `tasks` projection outside the draft. `SqlitePlans` implements it, `create_plan` reads it, and `run_planner` passes it to `check_plan` as `ids_in_use` on every attempt.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/ports/plans.py`: a new method `task_ids_in_use() -> list[str]`, the eighth method. It returns the ids, in ascending order, of the tasks in the `tasks` projection whose plan is not `draft`.
- `src/openfactory/adapters/sqlite_plans.py`: one `SELECT id FROM tasks WHERE plan_id NOT IN (SELECT id FROM plans WHERE status = 'draft') ORDER BY id`. It only reads.
- `src/openfactory/app/plan.py`:
  - `run_planner(..., ids_in_use: Collection[str] = frozenset())` passes the ids through `_attempt` to `check_plan(parsed.tasks, spec, ids_in_use=ids_in_use)` on both attempts.
  - `create_plan` calls `plans.task_ids_in_use()` once, after `tracked_files()` succeeds, and passes the result.
  - Module docstring updated.
- New `test_task100_` tests:
  - `tests/unit/test_plan_use_case.py` (run_planner)
  - `tests/unit/test_plan_entry.py` (create_plan)
  - `tests/integration/test_sqlite_plans.py`, or a new `tests/integration/test_sqlite_plans_ids_in_use.py`
  - `tests/unit/test_plans_port.py`

Out:
- `untouched`, the replan prompt and the `replan` use case and command (item 6).
- Any change to `domain/plan_checks.py`, `cli.py` (it already passes `adapters.plans` to `create_plan`), the projector, or any table or event.
- The Later line on a second replan's prompt not listing the ids in use (spec v1.19 advisor). It stays open.

## Acceptance criteria
- [ ] **AC1** ("Plan checks", `task-id-in-use`, "already in the `tasks` projection"; ADR-019 "Ports"):
  - `Plans` has the method `task_ids_in_use() -> list[str]`, and the port's method set is the eight names.
  - `SqlitePlans` ends with its `TYPE_CHECKING` assertion against `Plans` as before.
- [ ] **AC2** ("Plan checks", `task-id-in-use`, "outside the draft being replaced"; "Projection rules", "after a replan it holds the untouched, the invalidated and the new tasks"). On a database built through `SqliteEventRecorder`:
  - `SqlitePlans.task_ids_in_use()` lists every task of the approved plan in ascending id, in any state, `abandoned` and `invalidated` included.
  - It also lists the tasks moved there from a superseded plan.
  - It does not list the tasks of the current draft.
  - With no tasks it is `[]`.
- [ ] **AC3** ("Plan checks", `task-id-in-use` and the retry paragraph). `run_planner(..., ids_in_use={"AUTH-001"})`:
  - A first reply that plans `AUTH-001` is rejected. Its `AgentRunFinished.error` holds the line `task-id-in-use  AUTH-001  task id 'AUTH-001' is already in use`. The retry prompt carries the same rejection lines.
  - An accepted second reply gives `PlanCreated`. A second reply that also reuses the id gives outcome `rejected` and no `PlanCreated`.
  - Without `ids_in_use`, the same reply is accepted as before.
- [ ] **AC4** ("Planning": "A task id is unique among all tasks in the `tasks` projection; the `task-id-in-use` check enforces it"):
  - `create_plan` calls `Plans.task_ids_in_use()` exactly once and passes its result as `ids_in_use`. A fake that returns an id the reply uses gives the `task-id-in-use` rejection.
  - After a `GitError` from `tracked_files`, it is not called.
- [ ] **AC5** ("Planning": "The new draft may reuse their ids"). With the real `SqliteEventRecorder` and `SqlitePlans`:
  - When a draft holding `AUTH-001` exists and no plan is approved, `create_plan` with a reply that plans `AUTH-001` is accepted and records a new `PlanCreated`.
  - `run_planner`, called directly with `ids_in_use=SqlitePlans.task_ids_in_use()` on a database whose approved plan holds `AUTH-001`, rejects the same reply with `task-id-in-use`.
- [ ] **AC6** (CLAUDE.md architecture rules and "Tests from the test-writer are fixed"):
  - Only `ports/plans.py`, `adapters/sqlite_plans.py` and `app/plan.py` change under `src/`. `app/plan.py` still imports only `domain`, `ports` and `app`.
  - `cli.py` and `domain/plan_checks.py` are unchanged.
  - The full suite passes. The only edits to existing tests are the two approved ones under Design choice 4.

## Architecture rules that apply
- The port is a Protocol and imports only `openfactory.domain`.
- `SqlitePlans` runs `SELECT` only and keeps its `TYPE_CHECKING` assertion.
- `app/plan.py` depends on `domain` and `ports` only. It reads through `Plans` and does not decide what counts as "outside the draft". The adapter answers that from `plans.status`.

## Plan
1. Create branch `task/TASK-100-plan-ids-in-use` from an up-to-date main.
2. Record the human's answers to the Design choices and Open questions.
3. Test-writer: write the failing `test_task100_` tests for AC1 to AC5. Make the two approved edits under Design choice 4.
4. Implement the port method, the `SqlitePlans` query, `run_planner`'s `ids_in_use` through `_attempt`, and the read in `create_plan`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`:
     - "Plans port": eight methods, and the new method's sentence.
     - "SQLite plans": the new query.
     - "Plan use case: the planner call": `run_planner`'s `ids_in_use`.
     - The `create_plan` bullet.
     - "Plan checks": "Nothing passes them yet" becomes "`plan` passes `ids_in_use`; `replan` (item 6) passes `untouched`".
     - The wiring paragraphs.
   - `docs/decisions.md`: one row for Design choice 1.
   - `docs/progress.md`:
     - Current, and a Done line.
     - Item 5b marked done.
     - Delete the Later line "Before M6 item 5: … Delete at item 5's close (TASK-042, reviewer; TASK-064)", as TASK-097's answer set.
     - Add the method-set test name drift to the existing TASK-042/TASK-064 Later line.
   - This record's Outcome.
7. Commit `feat(app): pass the task ids in use to the plan checks` with trailers `Task: TASK-100` and `Milestone: M6`. Do not push.

## Files expected to change
- `src/openfactory/ports/plans.py` (about +5)
- `src/openfactory/adapters/sqlite_plans.py` (about +7)
- `src/openfactory/app/plan.py` (about +10)
- `tests/unit/test_plan_use_case.py`, `tests/unit/test_plan_entry.py`, `tests/unit/test_plans_port.py`, `tests/integration/test_sqlite_plans*.py` (about +170 together)
- `docs/architecture.md`, `docs/decisions.md`, `docs/progress.md`, this record

Not expected to change: `cli.py`, `domain/`, other adapters, the projector, `docs/spec/`, `docs/adr/`.

## Design choices to confirm at planning
1. **What the read takes.** Proposed: `task_ids_in_use()` with no argument, meaning every task whose plan is not `draft`. At most one draft exists, and the next `PlanCreated` of `plan` or `replan` always supersedes it, so "the draft being replaced" is the current draft whenever one exists. Superseded drafts have no tasks (the projector removes them), and a superseded approved plan has none either (TASK-097 moves them). Alternative: `task_ids_outside(plan_id: str | None)`, with the caller passing `current_draft().id`: same rows, one more read and a caller duty.
2. **Who reads, who passes.** Proposed: `create_plan` reads, and `run_planner` takes `ids_in_use: Collection[str] = frozenset()` and passes it to `check_plan` on both attempts. `run_planner` stays a pure call-with-retry that `replan` can reuse; existing `run_planner` tests need no change. Alternative: `run_planner` calls `plans.task_ids_in_use()` itself, closer to the outline wording but forcing an edit to `FakePlans` in `tests/unit/test_plan_use_case.py`.
3. **Read once.** The ids are read once per `plan`, before the first attempt. The retry uses the same set, since nothing between the two attempts changes `tasks`.
4. **Two edits to existing tests (approval needed):**
   - `tests/unit/test_plans_port.py::test_ac1_plans_is_a_protocol_with_exactly_the_five_reads`: the exact method set gains `task_ids_in_use`; the name is kept, as in TASK-042 and TASK-064 (the name drift is already in Later).
   - `tests/unit/test_plan_entry.py` `FakePlans`: gains `task_ids_in_use(self) -> list[str]` returning `[]`. Mechanical: without it the existing AC6 test fails with `AttributeError`. No assertion changes.
5. **Return type.** `list[str]` in ascending id, like `live_tasks_referencing`. `check_plan` accepts any `Collection[str]`.

## Spec gaps
None. A note that is not a gap: in every state the commands can reach, `plan` gets an empty set, so the rule has no visible effect for `plan` today (`plan` refuses when an approved plan exists; superseded drafts lose their tasks; a replan's approval moves the old plan's tasks into the new approved plan). ADR-019 still makes the rule apply to every plan. AC3 to AC5 show the wiring through fakes and a direct `run_planner` call; item 6 (`replan`) is where it matters.

## Open questions
1. Do you accept Design choice 2 (read in `create_plan`, pass through `run_planner`) over the outline's more literal "`run_planner` reads"?
2. Do you approve the two edits to existing tests under Design choice 4?
3. Should the Later line "Before M6 item 5 … Delete at item 5's close" be deleted at this task's close, as TASK-097's answer said?

Answers (human, 2026-10-24): all approved as proposed. 1: `create_plan` reads, `run_planner` takes `ids_in_use`. 2: both test edits approved. 3: delete the Later line at this task's close. Advisor note kept for item 6: its acceptance criteria should check that `replan` passes `ids_in_use`, since the parameter defaults to empty.

## Outcome
What changed:
- `ports/plans.py`: `Plans.task_ids_in_use() -> list[str]`, the eighth method.
- `adapters/sqlite_plans.py`: one `SELECT id FROM tasks WHERE plan_id NOT IN (SELECT id FROM plans WHERE status = 'draft') ORDER BY id`; read only.
- `app/plan.py`: `run_planner(..., ids_in_use=frozenset())` passes the ids through `_attempt` to `check_plan` on both attempts; `create_plan` reads `task_ids_in_use()` once, after `tracked_files()` succeeds; module docstring updated.
- New tests: `tests/integration/test_sqlite_plans_ids_in_use.py`, and `test_task100_` tests in `tests/unit/test_plan_use_case.py`, `tests/unit/test_plan_entry.py` and `tests/integration/test_sqlite_plans.py`; `tests/unit/test_plans_port.py` has no new test, only the approved edit below (it covers AC1).
- `cli.py`, `domain/plan_checks.py`, the projector and the spec are unchanged.

Edits to existing tests (both approved, Design choice 4; no other test edited):
- `tests/unit/test_plans_port.py`: the exact method set gains `task_ids_in_use`; the test name is kept.
- `tests/unit/test_plan_entry.py`: `FakePlans` gains a `task_ids_in_use` stub returning `[]`.

Checks: 1996 passed; ruff, pyright and `scripts/check_docs.py` clean.

Docs: architecture.md (Plans port, SQLite plans, planner call, `create_plan`, Plan checks, wiring), decisions.md (one row for Design choice 1), progress.md (Done, item 5b, the "Before M6 item 5" Later line deleted, the method-set name drift added to the TASK-042/TASK-064 line, a Later line for item 6 to check that `replan` passes `ids_in_use`).
