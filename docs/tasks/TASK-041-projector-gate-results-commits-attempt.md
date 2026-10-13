# TASK-041: Projector for the gate and commit events (`gate_results`, `commits`) and the `tasks.attempt` rule

- Milestone: M3
- Status: done
- Tests: acceptance
- ADR: ADR-014 (accepted). "Events and tables (SC-57, SC-61)" gives the tables `gate_results` and `commits` "with the DDL of spec v1.12" and the rule "The projector adds 1 to `tasks.attempt` for each `TaskStateChanged` whose `to` is `running`. No stored payload changes". ADR-009 (accepted) covers the projector's interface, validation before the first write, the caller owning the transaction, and "replays facts and does not enforce business rules". ADR-010 (accepted) covers the recorder calling `create_tables` and `rebuild`. ADR-007 (accepted) covers the two payloads read here. No new port, adapter, dependency, event type or payload change, and no storage shape the spec does not give. Column forms and the no-op readings are rows in `docs/decisions.md` (Open question 3).
- Spec impact: none
- Spec sections (spec v1.12, SC-57, SC-61): "Domain model and storage" › "Projections" (the table and the `CREATE TABLE` block), "Projection rules", "Event payloads" (the `GateEvaluated` and `CommitRecorded` entries); "Task state machine"; "Execution" › "Restart" ("An interrupted attempt counts as an attempt"); "Milestones and definition of done" (milestone 3: "the gate result and commit projections")

## Outline item
M3 outline item 1, whole. Items 2 to 11 are left.

## Objective
Make `SqliteProjector` create the `gate_results` and `commits` tables, apply `GateEvaluated` and `CommitRecorded` to them, and add 1 to `tasks.attempt` for each `TaskStateChanged` whose `to` is `running`, so that a rebuild from the event log gives identical rows.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings and to SC-57 and SC-61.

## Scope
In:
- `src/openfactory/adapters/sqlite_projector.py`:
  - DDL for `gate_results` and `commits` as in the spec block, added to `create_tables` and to the tables `rebuild` drops (nine tables).
  - `GateEvaluated`: insert one `gate_results` row (`run_id`, `gate`, `passed` as 0 or 1, `output_path`).
  - `CommitRecorded`: insert one `commits` row (`sha`, `task_id`, `run_id`, `branch`).
  - `TaskStateChanged`: besides setting `state`, add 1 to `attempt` when `to` is `running`.
- A new test file `tests/integration/test_sqlite_projector_m3.py`, which also asserts the nine table names (the skip rule in the conformance test would hide a dropped table).
- `tests/unit/test_spec_conformance.py`: the table parametrisation extended to the M3 tables (Open question 2).
- One approved edit to a fixed test (Open question 1).

Out (not this task):
- The read ports over the new tables: the latest commit of a plan on `Plans`, the unfinished run of a task on `Runs` (outline item 2).
- Every use case and command (items 7 to 10). Nothing records `GateEvaluated`, `CommitRecorded` or a change to `running` yet.
- Any change to `sqlite_recorder.py` (it already calls `create_tables`, `apply` and `rebuild`), to `domain/payloads.py` or to any other module under `src/`.
- `GateEvaluated.task_id`, and `CommitRecorded.spec_version` and `files`: the tables have no column for them, so they are not projected. They stay in the event log; `files` is for M5 (ADR-014).
- Checks of event sequences (ADR-009): a `from` against the stored state or `TRANSITIONS`, a `run_id` or `task_id` with no row, a `CommitRecorded` for a task that is not `gating`, a `branch` against `task_id`.
- A second `GateEvaluated` with a stored `(run_id, gate)` and a second `CommitRecorded` with a stored `sha`: plain `INSERT`, no `OR IGNORE`, no test (Open question 3).
- "A task has attempts left while `attempt < limits.max_attempts`": a rule for the use case (M4 retry); the projector only counts.
- Filling the new tables, or `attempt`, in a database that already holds such events below `last_seq`. The spec says "A projection added later is filled by a rebuild"; no use case records these events yet.
- Every Later line in `docs/progress.md` (see "Later lines" below).
- Hardening against exotic inputs.

## Acceptance criteria
"DDL block" is the `CREATE TABLE` block under "Projections". A snapshot is every row of `tasks` (by `id`), `gate_results` (by `run_id, gate`) and `commits` (by `sha`). Payloads are built through the payload models; events are stored (`store.append`) before they are applied. `SHA` is any 40 lowercase hex string. The plan used is `plan_01` with tasks `AUTH-001` and `AUTH-002`.

- [x] AC1 ("Projections": the DDL block, and "Projection tables have no foreign key and no `CHECK` constraints"; "Projection rules": "Each milestone adds the tables for the events it introduces: ... M3 `gate_results`, `commits`"):
  - After `create_tables()`, `gate_results` and `commits` exist next to the seven earlier tables. The test asserts the nine names and cannot skip.
  - In `tests/unit/test_spec_conformance.py`, `PRAGMA table_info` of each of the two tables equals that of the spec's DDL (names, types, `NOT NULL`, primary keys), and neither case is skipped; `uv run pytest -q` reports no skipped test.
  - Neither table has a foreign key, and no table's SQL holds `CHECK`.
  - Calling `create_tables()` again changes no row.
- [x] AC2 ("Projection rules": "`GateEvaluated` inserts one `gate_results` row"; "Projections": "`gate_results` | run_id, gate, passed, output_path" and the DDL comments "0 | 1" and "relative to the repo; null when the gate wrote no file"):
  - Applying a `GateEvaluated` for `run_0002`, task `AUTH-002`, gate `path_check`, `passed` true, `output_path` null leaves exactly one `gate_results` row: `("run_0002", "path_check", 1, None)`.
  - A `GateEvaluated` for `run_0003`, gate `path_check`, `passed` false, `output_path` `.openfactory/runs/run_0003/path_check.txt` adds the row `("run_0003", "path_check", 0, ".openfactory/runs/run_0003/path_check.txt")` and leaves the first unchanged.
  - Neither event changes a row of `tasks` or `commits`.
- [x] AC3 ("Projection rules": "`GateEvaluated` inserts one `gate_results` row, and `CommitRecorded` one `commits` row"; "Projections": "`commits` | sha, task_id, run_id, branch"; "Event payloads": the `CommitRecorded` entry):
  - Applying a `CommitRecorded` with `sha` `SHA`, task `AUTH-002`, `run_0002`, branch `openfactory/AUTH-002`, `spec_version` `sv_01` and two files leaves exactly one `commits` row: `(SHA, "AUTH-002", "run_0002", "openfactory/AUTH-002")`.
  - The event changes no row of `tasks` (the task's `state` is unchanged; the move to `passed` is its own `TaskStateChanged`) and no row of `gate_results`.
- [x] AC4 ("Projection rules": "The projector adds 1 to `tasks.attempt` for each `TaskStateChanged` whose `to` is `running`"; "Execution" › "Restart": "An interrupted attempt counts as an attempt"; SC-61): with `plan_01` projected,
  - `pending` to `ready` for `AUTH-001` leaves its `attempt` 0.
  - `ready` to `running` sets `state` to `running` and `attempt` to 1, changes no other column of the row, and leaves `AUTH-002` unchanged.
  - `running` to `gating`, `gating` to `failed` and `failed` to `ready` each leave `attempt` 1; a second `ready` to `running` makes it 2.
  - With the approved edit of Open question 1, `test_ac4_task_state_changed_sets_state_and_nothing_else` in `tests/integration/test_sqlite_projector_m2.py` passes.
- [x] AC5 ("Event payloads": "the projector validates each payload against its model before applying it and fails on a mismatch"): with `plan_01` projected and `AUTH-001` `ready`, each of these raises `pydantic.ValidationError` and leaves the snapshot unchanged:
  - a `GateEvaluated` whose `gate` is `semgrep`;
  - a `CommitRecorded` whose `sha` has 39 characters;
  - a `TaskStateChanged` `ready` to `running` for `AUTH-001` without the `reason` key (`attempt` is still 0 and `state` still `ready`).
- [x] AC6 ("Projection rules": "Rebuilding means emptying the projection tables (dropping and recreating them counts), replaying all events in `seq` order", "A rebuild is identical when, for every projection table, the rows read in primary-key order are equal before and after. The projector therefore uses only data in the event", and "Use cases record every event through the `EventRecorder` port ... appends the event and applies it to the projections in one transaction"): for a log holding `PlanCreated` and `PlanApproved` for `plan_01`, the state changes of `AUTH-001` through two changes to `running` and on to `gating`, one failed and one passed `GateEvaluated`, and one `CommitRecorded`:
  - `SqliteProjector.rebuild(store.read())` leaves the snapshot equal to the one before; it is not empty, and `AUTH-001` has `attempt` 2 before and after.
  - A row planted in `gate_results` and a row planted in `commits` that no event produced are gone after the rebuild.
  - The same events recorded through `SqliteEventRecorder.record` give the same snapshot on a second connection, and `SqliteEventRecorder.rebuild()` leaves it equal.

## Architecture rules that apply
- The projector imports only from `openfactory.domain` and the standard library, has no port and no `TYPE_CHECKING` assertion, and never commits (ADR-009).
- Validate before the first write, so a rejected `TaskStateChanged` raises no `attempt` (AC5).
- Only data in the event: no clock, no generated ids, no file reads. `attempt` is counted from the events, never read from a clock or a file. This piece reads no `created_at`.
- "All state changes go through the events table. Never write projections directly" binds production code; the planted rows in AC6 are test-side damage to a temporary database (TASK-019, TASK-022 and TASK-023 precedent).
- Tests from the test-writer are fixed. The edits under Open questions 1 and 2 are not mechanical and need the human's approval before the session makes them; each is reported in the Outcome.
- OpenFactory's own tests carry no `req` markers.

## Plan
1. Create branch `task/TASK-041-projector-gate-results-commits-attempt` from an up-to-date main.
2. Get the human's answers to Open questions 1 to 4. Record them here and as rows in `docs/decisions.md`.
3. Write failing tests:
   - `tests/integration/test_sqlite_projector_m3.py` (new) for AC1 to AC6, in the style of `tests/integration/test_sqlite_projector_m2.py` and `test_sqlite_projector_runs.py` (`conn`, `projector` and `store` fixtures, a `snapshot` helper, event builders that go through the payload models).
   - The parametrisation in `tests/unit/test_spec_conformance.py` (Open question 2). Confirm the two new cases skip at this point.
4. Make the approved edit to `tests/integration/test_sqlite_projector_m2.py` (Open question 1) and nothing else in that file.
5. Extend `src/openfactory/adapters/sqlite_projector.py`: two DDL statements, `_TABLES` extended to nine, two branches in `apply` (two plain `INSERT`s), the `attempt` increment in the `TaskStateChanged` branch, the two payload imports, and the module docstring naming the M3 tables.
6. Run `uv run pytest -q` (expect no skipped test), `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
7. Update the living docs and the Outcome. Commit `feat(adapters): project the gate and commit events and count task attempts` with trailers `Task: TASK-041` and `Milestone: M3`.

## Files expected to change
- `src/openfactory/adapters/sqlite_projector.py` (about 45 lines added)
- `tests/integration/test_sqlite_projector_m3.py` (new, about 230 lines)
- `tests/unit/test_spec_conformance.py` (one tuple and one parametrisation, per Open question 2)
- `tests/integration/test_sqlite_projector_m2.py` (one assertion, per Open question 1)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-041-projector-gate-results-commits-attempt.md` (this record; Outcome at close)

Not expected to change: `sqlite_recorder.py`, `domain/payloads.py` and every other module under `src/`; `pyproject.toml`; `docs/adr/`; `docs/spec/`; every other test file. Checked: `tests/integration/test_sqlite_projector.py`, `test_sqlite_projector_runs.py`, `test_sqlite_recorder.py` and `test_cli_init.py` assert their table sets with `<=` or `>=`; `test_m2_close.py` and `test_sqlite_plans.py` assert `attempt` 0 only for tasks that never moved to `running`; the rebuild tests of `test_sqlite_projector_m2.py` hold a change to `running` in `log_events()` but compare snapshots before and after, so they still pass; `test_task040_ac5_gate_evaluated_the_model_rejects_raises_and_writes_nothing` uses a payload the model rejects.

Expected size: about 300 lines with tests.

## Living docs to update
- `docs/architecture.md`:
  - "SQLite projector": nine tables; `GateEvaluated` and `CommitRecorded` each insert one row, with what is not projected (`task_id` of a gate result, `spec_version` and `files` of a commit); the `attempt` rule; `rebuild` drops nine; the clause "`GateEvaluated` and `CommitRecorded` are validated and write nothing (the M3 tables come with a later task)" goes; the list of what is not checked gains a repeated `(run_id, gate)` and a repeated `sha`.
  - "Data flow": the projection list.
- `docs/progress.md`: Current, then Done; remove outline item 1, renumber and keep the "depends on" references correct; add the Later line for the kept test name if Open question 1 keeps it.
- `docs/decisions.md`: rows for the answered open questions.
- `CHANGELOG.md` and `README.md`: no change (no command or output is added).

## New dependencies
None.

## Spec gaps
None. Spec impact is "none": the DDL of both tables, the two insert rules and the attempt rule are stated in spec v1.12.

Readings, not gaps (each follows from the text as written):
- `gate_results` has no `task_id` column, and `commits` has no `spec_version` or `files` column, so those payload fields are not projected. "Each payload carries everything its projections hold" allows a payload to hold more than its projection (the TASK-023 reading for `AgentRunFinished.error`).
- `passed` is stored as 0 or 1, as the DDL comment says, the form `requirements.deprecated` already has.
- "For each `TaskStateChanged` whose `to` is `running`" names no `from`, so the projector looks at `to` only; `TRANSITIONS` allows only `ready` to `running`, and "The `run` use case checks every transition against `TRANSITIONS` before it records it".
- A repeated `(run_id, gate)` cannot come from a use case: the path check "is evaluated once", and a retry is a new run. A repeated `sha` cannot either: a commit gets one `CommitRecorded`, and "a commit made without its `CommitRecorded` becomes unreachable". So no keep-first rule is needed, unlike `SpecImported`.
- A `PlanCreated` that supersedes a draft removes its tasks, so their `attempt` goes with them; "they never ran".

## Later lines in `docs/progress.md`: taken or left
- "Projector `INSERT OR IGNORE` also skips a row on a `NOT NULL` or `CHECK` violation ... check it when a nullable model field is mapped to a `NOT NULL` projection column (TASK-015)": checked, does not apply. Both new inserts are plain `INSERT`, and the one nullable field written, `output_path`, maps to a nullable column. The line stays.
- "`test_task040_ac5_gate_evaluated_the_model_rejects_raises_and_writes_nothing` builds its `GateEvaluated` event on stream `spec:sv_01` (TASK-040, reviewer)": left; the projector still ignores the stream.
- "`ImpactComputed` is the last event type without a payload model ... (TASK-040)": left; `test_ac5_event_type_without_projection_is_ignored` and `build_log` are not touched.
- "Spec wording: ... `sha: "<40 hex>"` ... does not say lowercase (TASK-040, planner)": left; this task stores what the model accepted.
- The "Spec gap (before the M3 run use case is planned)" line (F-1, F-5, F-7, F-2, F-3) and the three "Spec wording" lines on path patterns and the path check: left; they concern items 7 to 10.
- The two ADR-007 and ADR-004 wording lines, and the misnamed-test lines: left.
- To add at close, if Open question 1 keeps the test's name: "`tests/integration/test_sqlite_projector_m2.py::test_ac4_task_state_changed_sets_state_and_nothing_else` keeps a name its assertion no longer matches: a change to `running` also raises `attempt` (TASK-041)".

## Open questions
Answered 2026-10-13: the human approved the proposed answer to each of the four questions (advisor: 4 AGREE of 4).

None is a spec decision. Questions 1 and 2 are edits to fixed tests and need the human's approval; each has a proposal.

1. **Edit to a fixed test that SC-61 forces.** `tests/integration/test_sqlite_projector_m2.py::test_ac4_task_state_changed_sets_state_and_nothing_else` ends with `assert rows["AUTH-001"][5] == 0` after a `ready` to `running` event (line 221). It was written for TASK-022 AC4 against spec v1.10 ("leaves `state` `running` and `attempt` 0"); under spec v1.12 the value is 1, and the spec wins. ADR-014's Consequences name two fixed-test changes and not this one. Proposed: change that one assertion to `== 1` and nothing else in the file; the test name is kept, with a Later line. Alternative: delete the line and leave the attempt value to the new file.
2. **Conformance parametrisation.** Proposed: add `M3_TABLES = ("gate_results", "commits")` to `tests/unit/test_spec_conformance.py` and extend the parametrisation of `test_projection_table_matches_the_spec_create_table` to `M1_TABLES + M2_TABLES + M3_TABLES`, as the outline words it (TASK-022 Open question 3). The two cases skip by the file's own rule until the projector creates the tables. The assertion that the nine tables are present lives in the new integration file, which cannot skip (TASK-023 decision).
3. **Column forms and no-op readings (decisions rows).** Proposed:
   - `gate_results.passed` is `int(passed)`; `output_path` is the payload's value or null; `commits.branch` is the payload's string as it is.
   - A second `GateEvaluated` with a stored `(run_id, gate)`, or a second `CommitRecorded` with a stored `sha`, is a plain `INSERT` with no `OR IGNORE`, no test and no keep-first rule. It would end in `sqlite3.IntegrityError`, as the TASK-023 decision has it for a repeated run id.
   - A `TaskStateChanged` to `running` for a task not in `tasks` changes no row and raises nothing (TASK-022 decision).
4. **One task or two.** Proposed: one task, about 300 lines with six criteria. Alternative: split the `tasks.attempt` rule (AC4, the fixed-test edit, and the attempt parts of AC5 and AC6) into TASK-042, leaving the two tables here at about 220 lines.

## Outcome
- Built: `SqliteProjector` creates `gate_results` and `commits` (spec v1.12 DDL) and `rebuild` drops nine tables; `GateEvaluated` inserts one `gate_results` row (`passed` as 0 or 1) and `CommitRecorded` one `commits` row, both plain `INSERT`; `TaskStateChanged` sets `state` and adds 1 to `attempt` when `to` is `running`, in one `UPDATE`. Only `src/openfactory/adapters/sqlite_projector.py` changed under `src/`.
- Tests: `tests/integration/test_sqlite_projector_m3.py` (12 tests, AC1 to AC6). The suite is 1102 passed with no skipped test.
- Edits to fixed tests, both approved by the human on 2026-10-13 before they were made (Open questions 1 and 2):
  - `tests/integration/test_sqlite_projector_m2.py::test_ac4_task_state_changed_sets_state_and_nothing_else`: `assert rows["AUTH-001"][5] == 0` became `== 1` (SC-61); the name is kept, with a Later line.
  - `tests/unit/test_spec_conformance.py`: `M3_TABLES` added and the table parametrisation extended to it.
- Deviations from plan: none in scope. Size ran over the estimate: the new test file is 343 lines (planned about 230) and the diff about 417 insertions (planned about 300). No test from the test-writer was changed after it was written.
- Follow-ups: the Later line for the kept test name.
