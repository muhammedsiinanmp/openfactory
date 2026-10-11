# TASK-025: Plans port with `sqlite_plans`

- Milestone: M2
- Status: done
- Tests: acceptance
- ADR: ADR-012 (accepted, 2026-10-11). It decides the `Plans` port "over the `plans`, `tasks` and `task_deps` projections", what it gives ("the current draft plan, the approved plan if there is one, the next plan id, the tasks of a plan with their dependencies, and the live tasks that reference a requirement (a task that is in neither state `abandoned` nor `invalidated`)") and its adapter `sqlite_plans`. It says "Each adapter opens its own connection, as `sqlite_spec_versions` does (ADR-001, ADR-010), and ends with the `TYPE_CHECKING` assertion against its port (ADR-006)" and "Exact signatures are settled in the tasks that build them". That is enough: no new ADR. The signatures and the other answers under Open questions are rows in `docs/decisions.md`.
- Spec impact: none
- Spec sections (spec v1.10): "Domain model and storage" ("Ids", "Projections" with its `CREATE TABLE` block, "Projection rules", "Streams and actors"); "Task contract" ("Planning"); "Task state machine"; "Spec input format" ("Validation rules": the deleted-requirement bullet); "Tech stack and repo layout"

## Objective
Add the read-only `Plans` port with its SQLite adapter, which gives the current draft plan, the approved plan, the next plan id, the tasks of a plan with their dependencies and the live tasks that reference a requirement, so the plan use case, the approve-plan use case and the deleted-requirement rule can read the plan and task projections without touching SQLite.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings.

## Scope
In:
- `src/openfactory/domain/plans.py` (new): two frozen, `extra="forbid"` return types (names and fields per Open questions 1 and 2).
  - `PlanRef`: `id` (`PlanId`) and `spec_version` (`SpecVersionId`).
  - `Task`: `id` (`TaskId`), `plan_id` (`PlanId`), `state` (`TaskState`), `attempt` (`int`), `contract` (`TaskContract`) and `depends_on` (`list[TaskId]`).
  - It imports from `openfactory.domain` only.
- `src/openfactory/ports/plans.py` (new): the Protocol `Plans` with five methods.
  - `current_draft() -> PlanRef | None`
  - `approved() -> PlanRef | None`
  - `next_id() -> str`
  - `tasks(plan_id: str) -> list[Task]`
  - `live_tasks_referencing(requirement_id: str) -> list[str]`
- `src/openfactory/adapters/sqlite_plans.py` (new; the module name is the spec's):
  - `SqlitePlans(path: str | Path)` with the five methods and `close()`.
  - Own connection, `PRAGMA busy_timeout = 5000`, `SELECT` only on `plans`, `tasks` and `task_deps`, no table created, nothing cached.
  - Ends with `if TYPE_CHECKING: _: type[Plans] = SqlitePlans`.

Out (not this task):
- Every caller: the plan use case (item 9), the approve-plan use case (item 11), the `Plans` argument of `validate` and `approve_spec` and the `deleted-requirement` rule itself (item 12), and any wiring in `cli.py`.
- Contract completion and the policy hash (item 5), the plan checks (item 6), `LLMProvider` (item 7), `GitProvider` and `git_cli` (item 8).
- Any change to `SqliteProjector`, `SqliteEventRecorder`, `domain/contracts.py`, `domain/states.py`, `domain/payloads.py` and `app/`.
- Enforcing `TRANSITIONS`: the adapter returns the state the projection holds.
- A database without the `plans`, `tasks` or `task_deps` table: the `sqlite3.OperationalError` is left as it is (TASK-011 decision).
- Inconsistent projections the use cases cannot produce: two draft plans, a plan id that does not match `plan_NN`, a `tasks.contract` the model rejects, a `task_deps` row that disagrees with the contract's `depends_on`. Not checked (TASK-009, TASK-011 and TASK-024 decisions).
- More than one approved plan: it cannot exist before `replan` (M6), because `plan` "fails if an approved plan exists, for any spec version". No criterion covers it (Open question 3).
- Every Later line in `docs/progress.md`. Checked: the repeated `depends_on` entry makes the projector's insert fail, so no such row can be read here; it stays a Later line to settle before the plan use case. The `TaskStateChangedPayload(from_=...)` line concerns typed code in `src/`; this task builds that payload in tests only.

## Acceptance criteria
"Ids", "Projections", "Projection rules" and "Streams and actors" are under "Domain model and storage"; "Planning" is under "Task contract"; "Validation rules" is under "Spec input format". In AC2 to AC6 the database is a SQLite file under `tmp_path` opened first by `SqliteEventRecorder`, and every row is produced by recording events built through the payload models. The criteria are written for the proposals under Open questions.

- [x] AC1 ("Tech stack and repo layout": "`ports/ # interfaces: EventStore, EventRecorder, SpecVersions, Plans, Runs, ...`" and "`adapters/ # ..., sqlite_spec_versions, sqlite_plans, sqlite_runs, ...`"; "Ids": "They read the plan and task projections through the `Plans` port: the current draft plan, the approved plan if there is one, the next plan id, the tasks of a plan with their dependencies, and the live tasks that reference a requirement"):
  - `openfactory.ports.plans` defines a Protocol `Plans` whose public methods are exactly `current_draft`, `approved`, `next_id`, `tasks` and `live_tasks_referencing`, and imports nothing from `openfactory.adapters` or `openfactory.app` (checked by parsing its imports with `ast`).
  - `openfactory.domain.plans` imports nothing from `openfactory.ports`, `openfactory.adapters` or `openfactory.app`; `openfactory.adapters.sqlite_plans` imports nothing from `openfactory.app`.
- [x] AC2 ("Planning": "Plan ids are `plan_NN` and run ids `run_NNNN`, counted from `plan_01` and `run_0001`, wider when needed; the next id is one more than the highest in use, superseded plans included"):
  - With no recorded event, `next_id()` returns `plan_01`.
  - After `PlanCreated` for `plan_01`, it returns `plan_02`.
  - After a second `PlanCreated` for `plan_02`, which supersedes `plan_01`, it returns `plan_03`; it still does after `PlanApproved` for `plan_02`.
  - With `plan_99` created, it returns `plan_100`.
- [x] AC3 ("Ids": "the current draft plan, the approved plan if there is one"; "Planning": "Running `plan` again while a draft plan exists records a new `PlanCreated`. The projector marks the earlier draft `superseded`"; "Projections": "`plans` | id, spec_version, status (draft, approved, superseded)"):
  - With no recorded event, `current_draft()` and `approved()` both return `None`.
  - After `PlanCreated` for `plan_01` made for `sv_01`, `current_draft()` returns `PlanRef(id="plan_01", spec_version="sv_01")` and `approved()` returns `None`.
  - After a second `PlanCreated` for `plan_02`, `current_draft()` returns `plan_02`; the superseded `plan_01` is returned by neither method.
  - After `PlanApproved` for `plan_02`, `current_draft()` returns `None` and `approved()` returns `PlanRef(id="plan_02", spec_version="sv_01")`.
- [x] AC4 ("Ids": "the tasks of a plan with their dependencies"; "Projections": "`tasks` | id, plan_id, state, objective, contract JSON, attempt" and "`task_deps` | task_id, depends_on"; "Task state machine": "A task is created `pending` by `PlanCreated`" and "When its plan is approved, a task with no dependencies moves to `ready`"):
  - After `PlanCreated` for `plan_01` with three contracts (`AUTH-001` with no dependencies, `AUTH-002` depending on `AUTH-001`, `AUTH-003` depending on both), `tasks("plan_01")` returns three `Task` objects in ascending task id.
  - Each has `plan_id` `plan_01`, `state` `pending`, `attempt` 0, and a `contract` equal to the payload's `TaskContract`.
  - Their `depends_on` are `[]`, `["AUTH-001"]` and `["AUTH-001", "AUTH-002"]`.
  - After `PlanApproved` and a `TaskStateChanged` of `AUTH-001` from `pending` to `ready`, `AUTH-001` has `state` `ready` and the other two are still `pending`.
  - `tasks` of a superseded plan and of a plan id with no row both return `[]`.
- [x] AC5 ("Validation rules": "A task still references it when the task is in the `tasks` projection, lists it in its contract, and is in neither state `abandoned` nor `invalidated`", "its message lists the ids of the tasks that reference it, in ascending order as strings" and "Tasks of a draft plan count"):
  - With a draft plan whose `AUTH-002` and `AUTH-001` list `REQ-AUTH-001` and whose `AUTH-003` lists only `REQ-AUTH-002`, `live_tasks_referencing("REQ-AUTH-001")` returns `["AUTH-001", "AUTH-002"]`.
  - After the plan is approved the result is the same.
  - After a `TaskStateChanged` of `AUTH-001` to `invalidated` (with a reason), it returns `["AUTH-002"]`; after one of `AUTH-002` to `abandoned`, it returns `[]`.
  - A requirement id no task lists returns `[]`.
  - The tasks of a superseded draft do not count: after a second `PlanCreated` whose tasks do not list `REQ-AUTH-001`, it returns `[]`.
- [x] AC6 ("Ids": "Both are read-only", said of `Plans` and `Runs`; "Projection rules": "Projection tables are never written in any other way"; "Ids": "plan ids (`plan_NN`) ... are chosen by the use case from the projections when a command runs"):
  - With plan and task events recorded, opening `SqlitePlans`, calling all five methods and closing it changes no row: the rows of `events`, `plans`, `tasks`, `task_deps` and `projection_state`, read by the test on its own connection, are equal before and after.
  - A `SqlitePlans` opened while the recorder is open and the log is empty returns `plan_01` and no draft; after the recorder records `PlanCreated` for `plan_01`, the same adapter object returns `plan_02` and the draft `plan_01`.

## Architecture rules that apply
- Ports hold Protocols only and import from `openfactory.domain` only.
- `domain/plans.py` is pure: no I/O, no import from `ports`, `adapters` or `app`.
- The adapter ends with its `TYPE_CHECKING` assertion against `Plans` (ADR-006, ADR-012) and opens its own connection (ADR-010).
- "All state changes go through the events table. Never write projections directly": the adapter only reads, and tests fill the tables by recording events through `SqliteEventRecorder`.
- Rows read back are validated by the domain models (`PlanRef`, `Task`, `TaskContract`) before they are returned.
- Tests from the test-writer are fixed.

## Plan
1. Create branch `task/TASK-025-plans-port-sqlite` from an up-to-date main and commit this record.
2. Get the human's answers to Open questions 1 to 6; record them here and as rows in `docs/decisions.md`.
3. Write failing tests:
   - `tests/unit/test_plans_port.py` for AC1, in the style of `tests/unit/test_runs_port.py`.
   - `tests/integration/test_sqlite_plans.py` for AC2 to AC6, with helpers that build `PlanCreated`, `PlanApproved` and `TaskStateChanged` through the payload models (stream and actor per "Streams and actors").
4. Add `domain/plans.py` with `PlanRef` and `Task`.
5. Add `ports/plans.py`.
6. Add `adapters/sqlite_plans.py`:
   - `next_id`: `SELECT MAX(CAST(substr(id, 6) AS INTEGER)) FROM plans`, formatted as `plan_{n:02d}`.
   - `current_draft` and `approved`: one helper over `status`, the row with the highest id number, as `_latest` in `sqlite_spec_versions.py`.
   - `tasks`: the `tasks` rows of the plan with `ORDER BY id`, and the `task_deps` rows of those tasks with `ORDER BY depends_on`; the contract is decoded with `TaskContract.model_validate_json`.
   - `live_tasks_referencing`: the `id` and `contract` of rows whose `state` is neither `abandoned` nor `invalidated`, `ORDER BY id`, filtered in Python on the decoded contract's `requirements`.
   - `fetchall` on every query, so no read transaction stays open between calls.
7. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until green.
8. Update the living docs and the Outcome. Commit `feat(adapters): add the Plans read port over the plan and task projections` with trailers `Task: TASK-025` and `Milestone: M2`.

## Files expected to change
- `src/openfactory/domain/plans.py` (new, about 35 lines)
- `src/openfactory/ports/plans.py` (new, about 45 lines)
- `src/openfactory/adapters/sqlite_plans.py` (new, about 90 lines)
- `tests/unit/test_plans_port.py` (new, about 50 lines)
- `tests/integration/test_sqlite_plans.py` (new, about 230 lines)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-025-plans-port-sqlite.md`

About 170 lines of source and 280 of tests: over the 300-line aim, within six criteria (see Open question 6).

Not expected to change: `sqlite_projector.py`, `sqlite_recorder.py`, `sqlite_runs.py`, `sqlite_spec_versions.py`, `cli.py`, everything under `app/`, the other modules under `domain/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, and every existing test file. No fixed test needs an edit.

## Living docs to update
- `docs/architecture.md`:
  - New sections "Plan and task references" (`domain/plans.py`), "Plans port" and "SQLite plans".
  - "Data flow": the five reads exist and no use case calls them yet.
- `docs/progress.md`: Current, then Done; remove outline item 4.
- `docs/decisions.md`: rows for the answered questions.
- `CHANGELOG.md`, `README.md`: no change (no command or output is added).

## New dependencies
None.

## Spec gaps
None.

Readings, not gaps:
- "The current draft plan" is unique: the projector marks every earlier draft `superseded` on `PlanCreated` ("Planning").
- "The approved plan if there is one" is unique in M2: `plan` "fails if an approved plan exists, for any spec version", and `replan` is M6.
- "The highest in use, superseded plans included" is the highest number in any `plans` row, whatever its status.
- "Live" is ADR-012's word for the spec's "in neither state `abandoned` nor `invalidated`".
- A superseded draft's tasks are gone from `tasks` and `task_deps` ("Planning"), so they are neither tasks of that plan nor live tasks; nothing in the adapter filters on plan status.

## Open questions
1. **Return type of the two plan reads.** Proposed: `PlanRef` in a new `domain/plans.py`, with `id` and `spec_version` and no `status`, since each method fixes the status. `approve plan` needs the draft's spec version for its refusal line, and `plan` needs the approved plan's id for its own. Alternative: return the plan id as a string and add a third read for the spec version.
2. **Return type of `tasks(plan_id)` and where its dependencies come from.** Proposed: a domain model `Task` with `id`, `plan_id`, `state`, `attempt`, `contract` and `depends_on`, where `depends_on` is read from `task_deps` (`ORDER BY depends_on`), because ADR-012 puts the port over `task_deps`. `objective` is not a separate field: it is `contract.objective`. Alternative: no `depends_on` field and no read of `task_deps`; callers use `contract.depends_on`, which holds the same ids in the planner's order. The proposal carries the same ids twice in one object; the alternative leaves `task_deps` unread by any port until M5.
3. **More than one row of a status.** Proposed: `current_draft()` and `approved()` return the row with the highest id number, as `SqliteSpecVersions._latest` does, with no criterion and no test for two approved plans. Alternative: raise when two rows have the status.
4. **`tasks` of a plan with no row.** Proposed: `[]`, the same as a plan with no tasks; callers always take the id from `current_draft()` or `approved()`. Alternative: `None` for a plan with no row, as `spec_set` does.
5. **Shape of `live_tasks_referencing`.** Proposed: `live_tasks_referencing(requirement_id: str) -> list[str]`, the task ids in ascending order as strings, which is what the `deleted-requirement` message lists. Alternative: return `list[Task]`, or take several requirement ids and return a mapping.
6. **Size.** Proposed: one task of about 450 lines with tests and six criteria; the five reads share one adapter, one test helper and one set of fixtures. Alternative: TASK-025 takes the plan-level reads (`current_draft`, `approved`, `next_id`, AC1 to AC3) and TASK-026 the task-level reads (`tasks`, `live_tasks_referencing`, AC4 and AC5), each about 230 lines.

### Answers (human, 2026-10-11)
All six proposed answers approved as written: (1) `current_draft()` and `approved()` return `PlanRef | None`, with `id` and `spec_version` and no `status`; (2) `tasks(plan_id)` returns `Task` objects with `id`, `plan_id`, `state`, `attempt`, `contract` and `depends_on`, where `depends_on` is read from `task_deps` (`ORDER BY depends_on`); the advisor recommended the alternative (no `depends_on` field, callers use `contract.depends_on`) and the proposal was kept; (3) the row with the highest id number, with no criterion and no test for two approved plans; (4) `tasks` of a plan id with no row returns `[]`; (5) `live_tasks_referencing(requirement_id: str) -> list[str]`, ascending task ids; (6) one task.

## Outcome
- Built:
  - `domain/plans.py`: frozen `PlanRef` and `Task`.
  - `ports/plans.py`: Protocol `Plans` with the five reads.
  - `adapters/sqlite_plans.py`: read-only `SqlitePlans` on its own connection, ending with the `TYPE_CHECKING` assertion.
  - Tests: `tests/unit/test_plans_port.py` (AC1) and `tests/integration/test_sqlite_plans.py` (AC2 to AC6), written by the test-writer.
  - Living docs: `docs/architecture.md`, `docs/progress.md` and `docs/decisions.md` (six rows).
- Deviations from the plan: none.
- Test edits: none; no existing test file changed.
- Results: 812 tests pass; ruff, pyright and check_docs clean.
- Follow-ups: none new. No use case calls the port yet. The repeated `depends_on` Later line in `docs/progress.md` still stands and is to be settled before the plan use case.
