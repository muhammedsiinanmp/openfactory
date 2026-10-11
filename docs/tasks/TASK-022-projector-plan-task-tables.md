# TASK-022: Projector for the plan and task events (`plans`, `tasks`, `task_deps`)

- Milestone: M2
- Status: done
- Tests: acceptance
- ADR: ADR-009 (accepted). It covers the projector's interface, validation before the first write, the caller owning the transaction, and "replays facts and does not enforce business rules". ADR-010 (accepted) covers the recorder calling `create_tables` and `rebuild`. ADR-007 (accepted, with its amendment) covers the payloads read here. The three tables are the spec v1.10 DDL, which ADR-012 relies on ("every read is of a projection that the M2 projector already fills"). No new port, adapter, dependency, event type or payload change, and no storage shape the spec does not give. Column text forms are rows in `docs/decisions.md` (Open question 4).
- Spec impact: wording (one non-blocking item, see Spec gaps; it is a missing decision rather than a text fix, but nothing this task builds or tests depends on it)
- Spec sections (spec v1.10): "Domain model and storage" ("Projections" with its `CREATE TABLE` block, "Projection rules", "Event payloads"); "Task contract" ("Planning": the supersession bullet; "The completed contract is what `PlanCreated` and `tasks.contract` hold"); "Task state machine"; "CLI commands" (the `approve plan` row); "Milestones and definition of done" (milestone 2)

## Objective
Make `SqliteProjector` create the `plans`, `tasks` and `task_deps` tables and apply `PlanCreated`, `PlanApproved` and `TaskStateChanged` to them, including a new draft superseding the earlier one, so that a rebuild from the event log gives identical rows.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings.

## Scope
In:
- `src/openfactory/adapters/sqlite_projector.py`:
  - DDL for `plans`, `tasks` and `task_deps` as in the spec block, added to `create_tables` and to the tables `rebuild` drops.
  - `PlanCreated`: mark every `draft` row of `plans` `superseded`, delete those plans' rows from `task_deps` and `tasks`, insert the new plan as `draft`, insert one `tasks` row per contract (`state` `pending`, `attempt` 0) and one `task_deps` row per `depends_on` entry.
  - `PlanApproved`: set that plan's `status` to `approved`.
  - `TaskStateChanged`: set that task's `state` to `to`.
- A new test file `tests/integration/test_sqlite_projector_m2.py`.
- `tests/unit/test_spec_conformance.py`: the table parametrisation extended to the M2 tables (Open question 3).
- One approved edit to a fixed test (Open question 2).

Out (not this task):
- `agent_runs`, `AgentRunStarted`, `AgentRunFinished` (TASK-023). They stay validated and write nothing.
- Read ports and adapters (item 4), every use case and command (items 9 to 12).
- Any change to `sqlite_recorder.py`: it already calls `create_tables`, `apply` and `rebuild`.
- Checks of event sequences (ADR-009): `from` against the stored state or `TRANSITIONS`, a `PlanApproved` for an unknown or non-draft plan, a `PlanCreated` while an approved plan exists. A `TaskStateChanged` for a task not in `tasks` updates no row and raises nothing; the fixed recorder tests record exactly that (`task_event()` in `tests/integration/test_sqlite_recorder.py`).
- `tasks.attempt` beyond its initial 0 (Later, F-10, before M3). `reason`, `policy_hash` and `run_id` have no column and are not projected.
- Two tasks with one id in a `PlanCreated`, and a repeated `depends_on` entry: plain `INSERT`, no `OR IGNORE`, no test (see Spec gaps).
- Filling the new tables in a database that already holds M2 events below `last_seq`. The spec says "A projection added later is filled by a rebuild"; no use case records these events yet.
- The Later lines on `from_` and pyright (the projector reads `to` and `task_id` only), on narrowing `EventStore`, and on a repair path.

## Acceptance criteria
"DDL block" is the `CREATE TABLE` block under "Projections". A snapshot is every row of `plans` (by `id`), `tasks` (by `id`) and `task_deps` (by `task_id, depends_on`). Contracts are the spec's YAML example and variations of it.

- [x] AC1 ("Projections": the DDL block, and "Projection tables have no foreign key and no `CHECK` constraints"; "Projection rules": "Each milestone adds the tables for the events it introduces: ... M2 `plans`, `tasks`, `task_deps`, `agent_runs`"):
  - After `create_tables()`, `plans`, `tasks` and `task_deps` exist next to the three M1 tables.
  - In `tests/unit/test_spec_conformance.py`, `PRAGMA table_info` of each of the three equals that of the spec's DDL (names, types, `NOT NULL`, the default 0 of `attempt`, primary keys).
  - None of the three has a foreign key, and no table's SQL holds `CHECK`.
  - Calling `create_tables()` again changes no row.
- [x] AC2 ("Task state machine": "A task is created `pending` by `PlanCreated`; the initial state has no `TaskStateChanged` event"; "Task contract": "The completed contract is what `PlanCreated` and `tasks.contract` hold"; "Projections": the rows for `plans`, `tasks`, `task_deps`): applying a `PlanCreated` for `plan_01` on `sv_01` with two contracts, `AUTH-001` (no dependencies) and `AUTH-002` (`depends_on: [AUTH-001]`):
  - `plans` holds exactly `("plan_01", "sv_01", "draft")`.
  - `tasks` holds one row per contract with `plan_id` `plan_01`, `state` `pending`, `objective` equal to the contract's, `attempt` 0, and `contract` that parses as JSON to the contract as the payload holds it, lists in order.
  - `task_deps` holds exactly `("AUTH-002", "AUTH-001")`.
- [x] AC3 ("Task contract", "Planning": "Running `plan` again while a draft plan exists records a new `PlanCreated`. The projector marks the earlier draft `superseded` and removes its tasks from `tasks` and `task_deps`; they never ran, and they remain in the event log. The new draft may reuse their ids"): after AC2's event, applying a `PlanCreated` for `plan_02` whose tasks are `AUTH-002` (reused id, different objective, no dependencies) and `AUTH-003` (`depends_on: [AUTH-002]`):
  - `plans` holds `plan_01` with status `superseded` and its `spec_version` unchanged, and `plan_02` with status `draft`.
  - `tasks` holds only `AUTH-002` and `AUTH-003`, both with `plan_id` `plan_02`; `AUTH-002` has the new objective and contract; `AUTH-001` is gone.
  - `task_deps` holds exactly `("AUTH-003", "AUTH-002")`.
- [x] AC4 ("CLI commands": "`openfactory approve plan` | Marks the latest draft plan approved; tasks with no dependencies become `ready`"; "Task state machine": "only the orchestrator moves it between them; every transition is a `TaskStateChanged` event"; "Projections": "`plans` | id, spec_version, status (draft, approved, superseded)"):
  - `PlanApproved` for `plan_01` sets its `status` to `approved` and changes no row of `tasks` or `task_deps`; every task is still `pending`.
  - `TaskStateChanged` for `AUTH-001` with `to: ready` sets that row's `state` to `ready` and changes nothing else in it; `AUTH-002` is unchanged.
  - A second `TaskStateChanged` (`ready` to `running`) leaves `state` `running` and `attempt` 0.
- [x] AC5 ("Event payloads": "the projector validates each payload against its model before applying it and fails on a mismatch"): with `plan_01` projected as a draft, applying a `PlanCreated` for `plan_02` whose payload the model rejects (one contract without `limits`) raises `pydantic.ValidationError`, and the snapshot is unchanged: `plan_01` is still `draft` with its tasks. The same holds for a `PlanApproved` with `plan_id: "p1"`.
- [x] AC6 ("Projection rules": "Rebuilding means emptying the projection tables (dropping and recreating them counts), replaying all events in `seq` order" and "A rebuild is identical when, for every projection table, the rows read in primary-key order are equal before and after. The projector therefore uses only data in the event"; "Use cases record every event through the `EventRecorder` port ... appends the event and applies it to the projections in one transaction"): for a log holding `PlanCreated` `plan_01`, `PlanCreated` `plan_02` (reusing a task id), `PlanApproved` `plan_02` and two `TaskStateChanged`:
  - `SqliteProjector.rebuild(store.read())` leaves the snapshot equal to the one before, and it is not empty.
  - A row planted in `tasks` that no event produced is gone after the rebuild.
  - The same events recorded through `SqliteEventRecorder.record` give the same snapshot on a second connection, and `SqliteEventRecorder.rebuild()` leaves it equal.

## Architecture rules that apply
- The projector imports only from `openfactory.domain` and the standard library, has no port and no `TYPE_CHECKING` assertion, and never commits (ADR-009).
- Validate before the first write, so a rejected `PlanCreated` supersedes nothing (AC5).
- Only data in the event: no clock, no generated ids. This piece reads no `created_at`.
- "Never write projections directly" binds production code; the planted row in AC6 is test-side damage to a temporary database (TASK-019 precedent).
- Tests from the test-writer are fixed. The edit under Open question 2 is not mechanical and needs approval first.

## Plan
1. Create branch `task/TASK-022-projector-plan-task-tables` from an up-to-date main.
2. Get the human's answers to Open questions 1 to 5; record them here and as rows in `docs/decisions.md`.
3. Write failing tests:
   - `tests/integration/test_sqlite_projector_m2.py` for AC1 to AC6, in the style of `tests/integration/test_sqlite_projector.py` (`conn`, `projector` and `store` fixtures, a `snapshot` helper, event builders that go through the payload models).
   - The parametrisation in `tests/unit/test_spec_conformance.py`.
4. Make the approved edit to `tests/integration/test_sqlite_projector.py` and nothing else in that file.
5. Extend `src/openfactory/adapters/sqlite_projector.py`: three DDL statements, `_TABLES` extended, three branches in `apply` with a `_apply_plan_created` helper, and the module docstring no longer saying "for the M1 tables".
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until green.
7. Update the living docs and the Outcome. Commit `feat(adapters): project the plan and task events into plans, tasks and task_deps` with trailers `Task: TASK-022` and `Milestone: M2`.

## Files expected to change
- `src/openfactory/adapters/sqlite_projector.py` (about 75 lines added)
- `tests/integration/test_sqlite_projector_m2.py` (new, about 200 lines)
- `tests/unit/test_spec_conformance.py` (the table tuple and one parametrisation)
- `tests/integration/test_sqlite_projector.py` (one assertion, per Open question 2)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-022-projector-plan-task-tables.md`

Not expected to change: `sqlite_recorder.py` and every other module under `src/`; `pyproject.toml`; `docs/adr/`; `docs/spec/`; every other test file. `tests/integration/test_sqlite_recorder.py`, `test_cli_init.py` and `test_sqlite_spec_versions.py` assert their table sets with `<=` or by name and need no edit.

## Living docs to update
- `docs/architecture.md`: "SQLite projector" (six tables, the three events, supersession, what is not checked, `rebuild` drops six), "SQLite recorder" ("the spec projections"), and "Data flow".
- `docs/progress.md`: Current, then Done; rewrite outline item 3 as the remaining piece (`agent_runs` and the two run events, depends on TASK-022); add the Spec gaps item under Later.
- `docs/decisions.md`: rows for the answered questions.
- `CHANGELOG.md`, `README.md`: no change.

## New dependencies
None.

## Spec gaps
1. **"Task contract" ("Plan checks") against "Domain model and storage" (DDL of `task_deps`: `PRIMARY KEY (task_id, depends_on)`).**
   - Missing: what happens when a task's `depends_on` names the same task twice. `PlannedTask.depends_on` is a plain list, and none of the nine plan checks rejects a repeated entry, so such a reply is accepted and recorded in `PlanCreated`. The projector's two inserts then collide on the primary key, and `plan` would end in `sqlite3.IntegrityError`. This is the case SC-12 settled for a duplicated requirement id. The spec picks none of: the projector skips the repeat, a plan check rejects it, or contract completion removes it.
   - Does not block: no use case records `PlanCreated` until outline item 9, no criterion here feeds that input, and this task writes a plain `INSERT` without inventing a rule. It must be decided through `/spec-change` before item 9 is planned, and before item 6 if the answer is a plan check.
   - Proposed Later line: "Spec gap (before the plan use case is planned): a repeated entry in `depends_on` passes every plan check and makes the projector's `task_deps` insert fail on its primary key (TASK-022)".

Readings, not gaps:
- "The earlier draft" is every `plans` row with status `draft` when the event is applied; the use cases allow at most one. An approved plan is not touched.
- Two tasks with one id inside a `PlanCreated` cannot reach the projector, because `duplicate-task-id` rejects the reply first. So no keep-first rule is needed, unlike `SpecImported`.
- The Later line from TASK-015 (`INSERT OR IGNORE` hiding a `NOT NULL` violation) was checked for this piece and does not apply: the new inserts are plain `INSERT`, and no nullable field maps to a `NOT NULL` column.
- `attempt` is 0 for every task in M2; what raises it is F-10, before M3.

## Open questions
1. **Splitting outline item 3.** Proposed: this task covers `plans`, `tasks`, `task_deps` and three events; TASK-023 covers `agent_runs` and the two run events. One task for everything stays within six criteria but is about 430 lines.
2. **Edit to a fixed test.** `tests/integration/test_sqlite_projector.py::test_ac1_creates_exactly_the_m1_tables_with_spec_columns_and_keys` asserts `names == set(TABLES)` and fails once `create_tables` makes more tables. Proposed: change that one assertion to `set(TABLES) <= names`, and have the new file assert the three new tables are present. No test then asserts an exact table set, which means TASK-023 needs no further edit; the test name keeps "exactly". Alternative: assert the exact six in the new file and edit it again in TASK-023.
3. **Conformance parametrisation.** Proposed: extend it to all four M2 tables now, as the outline words it. `agent_runs` then skips by the file's own rule ("the projector does not create the ... table yet") until TASK-023, which needs no edit to the file. Alternative: three tables now, the fourth in TASK-023, with no skipped test in between.
4. **Column forms (decisions rows, extending the TASK-009 row).** Proposed:
   - `tasks.contract` is `json.dumps` of the contract's `model_dump(mode="json")`, non-ASCII left as it is, keys and lists in the order the event holds.
   - `tasks.state` and `plans.status` are plain strings.
   - `tasks.objective` is the contract's `objective`.
   - A `TaskStateChanged` for a task not in `tasks` is a no-op.
5. **The repeated `depends_on` entry (Spec gaps item 1).** Proposed: plain `INSERT`, no test, a Later line for `/spec-change`. Alternative: stop and decide it now, which would add an `INSERT OR IGNORE` and a criterion with no spec text behind it.

### Answers (human, 2026-10-11)
All five proposed answers approved as written: (1) split, `agent_runs` and the run events go to TASK-023; (2) the one assertion in `test_ac1_creates_exactly_the_m1_tables_with_spec_columns_and_keys` becomes `set(TABLES) <= names`, nothing else in that file; (3) the conformance parametrisation covers all four M2 tables, `agent_runs` skipping until TASK-023; (4) the column forms as proposed; (5) plain `INSERT`, no test, the Later line.

## Outcome
**Built.** `SqliteProjector` in `src/openfactory/adapters/sqlite_projector.py` creates `plans`, `tasks` and `task_deps` (spec v1.10 DDL) and `rebuild` drops six tables. `PlanCreated` deletes the `task_deps` and `tasks` rows of every `draft` plan, marks those plans `superseded`, inserts the new plan as `draft`, one `tasks` row per contract (`pending`, `attempt` 0, `contract` as `json.dumps(..., ensure_ascii=False)` of `model_dump(mode="json")`) and one `task_deps` row per `depends_on` entry, with plain `INSERT`. `PlanApproved` sets `status` to `approved`. `TaskStateChanged` sets `state` to `to`; for a task not in `tasks` it changes no row. `AgentRunStarted` and `AgentRunFinished` are validated and write nothing. No sequence checks (ADR-009). `sqlite_recorder.py` is unchanged. New tests in `tests/integration/test_sqlite_projector_m2.py`; `tests/unit/test_spec_conformance.py` is parametrised over the four M2 tables.

**Checks.** 759 passed, 1 skipped (the `agent_runs` conformance case, until TASK-023); ruff, pyright and check_docs pass.

**Test edit (approved, Open question 2).** In `tests/integration/test_sqlite_projector.py`, `names == set(TABLES)` became `set(TABLES) <= names` in `test_ac1_creates_exactly_the_m1_tables_with_spec_columns_and_keys`. No other edit to a test-writer test was made after the tests were written. The test keeps a name its assertion no longer matches (Later line in `docs/progress.md`).

**Reviewer.** Approve, no blocking issues. Its three non-blocking notes were applied at the human's request, which edits test-writer tests in `tests/integration/test_sqlite_projector_m2.py`: (1) new `test_ac3_new_draft_leaves_an_approved_plan_and_its_tasks`, which pins that a `PlanCreated` touches only `draft` plans; (2) the AC1 to AC5 tests now apply stored events (`projector.apply(store.append(...))`, with the `store` fixture) where they passed an unstored `Event`, no assertion changed; (3) outline item 3 in `docs/progress.md` asks TASK-023 for a test that `agent_runs` is present.

**Living docs.** `docs/architecture.md`, `docs/progress.md` and `docs/decisions.md` updated. `CHANGELOG.md` and `README.md` unchanged: the changelog lists user-visible changes only, and this adds no command or output.

**Remains for TASK-023.** The `agent_runs` table, `AgentRunStarted` and `AgentRunFinished` in the projector (adding it to `create_tables` and the tables `rebuild` drops); the `agent_runs` conformance case then stops skipping with no edit to the file. The repeated `depends_on` entry stays a spec gap for `/spec-change` (Later in `docs/progress.md`).
