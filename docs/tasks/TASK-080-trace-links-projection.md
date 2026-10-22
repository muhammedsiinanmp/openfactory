# TASK-080: `trace_links` table and its projector rules

- Milestone: M5
- Status: done
- Tests: acceptance
- ADR: ADR-018 (accepted). Its "Storage" and "Writing events" bullets define the table, the seven kinds, one stored direction per link, the four writing events, and that the projector reads `requirements`, `tasks` and `task_deps`. Its "Versions (G14)" bullet says node ids carry no version, `spec` rows are those of the latest approved version, and no row is removed on invalidation or abandon. The task adds no port, adapter, event type, payload change or dependency. The `trace_links` DDL is the spec's own, and ADR-018 covers it.
- Spec impact: none
- Spec sections (spec v1.17; SC-126, SC-127, SC-129):
  - "Domain model and storage" › "Projections": the `trace_links` row of the table, and the `CREATE TABLE trace_links` block under "The tables built in M1 to M5"; "Projection tables have no foreign key and no `CHECK` constraints".
  - "Domain model and storage" › "Projection rules": the `trace_links` bullet and its five sub-bullets (`SpecApproved`, `PlanApproved`, `CommitRecorded`, `TestsCollected`, "No row is removed when a task is invalidated or abandoned"); "Rebuilding means emptying the projection tables ..."; "A rebuild is identical when ..."; "Each milestone adds the tables for the events it introduces: ... M5 `trace_links`".
  - "Traceability": the link table (from → to, `source`, "Written by") and "A link is stored in `trace_links` in the direction shown, with that `source`".

## Outline item
This is M5 outline item 1 in `docs/progress.md` (TASK-079 has already removed the old item 1). The next item is the `Traces` read port and the `sqlite_traces` adapter (SC-133).

## Objective
`SqliteProjector` creates `trace_links` with the spec's DDL. `SpecApproved`, `PlanApproved`, `CommitRecorded` and `TestsCollected` write the links that "Traceability" assigns to them, each link stored once, and a rebuild is identical.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `adapters/sqlite_projector.py`:
  - The `trace_links` DDL is added to `_CREATE_TABLES` and `"trace_links"` to `_TABLES`, so `rebuild` drops it.
  - `SpecApproved`, after its existing `UPDATE`:
    - `DELETE FROM trace_links WHERE source = 'spec'`.
    - Then for each `requirements` row of `payload.spec_version`, one `('requirement', <req id>, 'adr', <adr id>, 'spec')` row per entry of its `constrained_by` JSON.
  - `PlanApproved`, after its existing `UPDATE`, for each `tasks` row of the plan:
    - `('requirement', <req id>, 'task', <task id>, 'contract')` for each id in the stored contract's `requirements`.
    - `('task', <task id>, 'task', <depends_on>, 'contract')` for each of its `task_deps` rows.
  - `CommitRecorded`, after its existing `commits` insert:
    - `('task', task_id, 'run', run_id, 'trailer')` and `('run', run_id, 'commit', sha, 'trailer')`.
    - `('commit', sha, 'file', <path>, 'diff')` for each path in `files`.
  - `TestsCollected` (today validated and nothing written):
    - `DELETE FROM trace_links WHERE source = 'test_tag'`.
    - Then for each test, `('test', node_id, 'file', file, 'test_tag')`, and `('test', node_id, 'requirement', <id>, 'test_tag')` for each id in `req`.
  - Every `trace_links` insert is `INSERT OR IGNORE`, so a link already stored is not inserted again.
  - The module docstring names `trace_links`.
- `tests/unit/test_spec_conformance.py`:
  - `M5_TABLES = ("trace_links",)` is added to the `test_projection_table_matches_the_spec_create_table` parametrisation. This is how TASK-041 added the M3 tables, and it is an addition, not a change to an assertion.
- Tests: new tests for AC1 to AC6, and the edit approved under Open question 1.

Out:
- The `Traces` port, `sqlite_traces`, the `coverage`, `trace` and `why` commands, the `GitProvider` commit listing and the rebuild from git (later outline items).
- Any change to payload models, use cases, `cli.py`, or the events `run`, `approve spec` or `approve plan` record.
- Any handling of a database made before M5: the spec says it is discarded, so `CREATE TABLE IF NOT EXISTS` is enough.
- Checks of event sequences, for example a `PlanApproved` for an unknown plan or a `SpecApproved` for a version with no rows. Such an event writes no links, like today's rules.

## Acceptance criteria
- [ ] **AC1** ("Projections": the `CREATE TABLE trace_links` block; "Projection tables have no foreign key and no `CHECK` constraints"; "Each milestone adds the tables ...: M5 `trace_links`"):
  - `create_tables()` creates `trace_links` exactly as the spec's DDL: the five columns, all `TEXT NOT NULL`, and every column in the primary key.
  - The conformance test runs for `trace_links` and does not skip.
  - The table has no foreign key and no `CHECK`.
  - Calling `create_tables()` twice changes no row.
- [ ] **AC2** ("Projection rules": "`SpecApproved` deletes every row with source `spec` and inserts requirement → ADR for each `constrained_by` entry of that version's requirements, so the `spec` rows are those of the latest approved version"):
  - After `SpecImported` and `SpecApproved` for `sv_01`, `trace_links` holds exactly one `(requirement, <id>, adr, <adr>, spec)` row per `constrained_by` entry.
  - After a second version `sv_02` with a different `constrained_by` is imported and approved, only `sv_02`'s `spec` rows remain.
  - Rows with any other source are untouched.
- [ ] **AC3** ("Projection rules": "`PlanApproved` inserts, for each task of the plan, requirement → task for each id in its contract's `requirements`, and task → task from the task to each task it depends on, both with source `contract`. A draft or superseded plan has no rows"):
  - After `PlanCreated` alone, there are no `contract` rows.
  - After a second `PlanCreated` supersedes it and the new plan is approved, `trace_links` holds the `contract` rows of the approved plan's tasks only.
  - Those rows are requirement → task for each contract requirement, and task → task for each dependency, in that direction.
- [ ] **AC4** ("Projection rules": "`CommitRecorded` inserts task → run (`task_id` to `run_id`) and run → commit (`run_id` to `sha`) with source `trailer`, and commit → file for each path in `files` with source `diff`"):
  - One `CommitRecorded` with two files adds exactly these four rows: `(task, AUTH-002, run, run_0002, trailer)`, `(run, run_0002, commit, <sha>, trailer)`, and one `(commit, <sha>, file, <path>, diff)` per file.
  - A second task's `CommitRecorded` adds its own rows and keeps the first task's rows.
- [ ] **AC5** ("Projection rules": "`TestsCollected` deletes every row with source `test_tag` and inserts, for each test, test → file and test → requirement for each id in its `req`, with source `test_tag`"):
  - A `TestsCollected` with a tagged test, an untagged test (`req` `[]`) and a test with two ids gives one test → file row per test and one test → requirement row per id.
  - A second `TestsCollected` replaces every `test_tag` row with its own and leaves `spec`, `contract`, `trailer` and `diff` rows untouched.
- [ ] **AC6** ("Projection rules": "each stored once: a link that is already stored is not inserted again"; "No row is removed when a task is invalidated or abandoned"; "Rebuilding ..."; "A rebuild is identical when ..."):
  - A link written twice is stored once and raises no error. Examples: a contract that repeats a requirement id, a test whose `req` repeats an id, and a link that `CommitRecorded` writes again for a retried task's same run (if that can be built without a second `commits` row; otherwise the contract and `req` cases suffice).
  - A `TaskStateChanged` to `abandoned` or `invalidated`, and a `TaskResolved` `abandon`, remove no `trace_links` row.
  - After a log with all four writing events, `rebuild` drops and refills `trace_links`, and its rows read in primary-key order are identical before and after.
  - The full suite passes, with only the edit approved under Open question 1.

## Architecture rules that apply
- The projector stays in the adapters layer with no port (ADR-009). It imports only `openfactory.domain` and the standard library.
- It uses only the event's data and the projections built by earlier events (`requirements`, `tasks`, `task_deps`): no clock, no generated ids and no file reads (ADR-002 as amended by ADR-018).
- Nothing outside the projector writes `trace_links`.

## Plan
1. Create branch `task/TASK-080-trace-links-projection` from an up-to-date main.
2. Get the human's answers to the Open questions and to Design choices 1 and 2, and record them here.
3. Test-writer: write failing tests.
   - AC1: add `M5_TABLES` to `tests/unit/test_spec_conformance.py`.
   - AC1 to AC6: new tests in `tests/integration/test_sqlite_projector_m5.py`, driving `SqliteProjector` with `SqliteEventStore` the way `test_sqlite_projector_m3.py` does.
   - Make the edit approved under Open question 1.
4. Implement the DDL, the `_TABLES` entry and the four rules in `sqlite_projector.py`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`, "SQLite projector": ten tables; the `trace_links` rules for `SpecApproved`, `PlanApproved`, `CommitRecorded` and `TestsCollected`; `INSERT OR IGNORE`; `create_tables` and `rebuild` now cover ten tables; remove "`TestsCollected` ... writes nothing" if it is stated.
   - `docs/progress.md`:
     - Current and a Done line.
     - Remove item 1 from the M5 outline.
     - Remove the Later line "M5: the `trace_links` table and `M5_TABLES` ...".
   - `docs/decisions.md`: rows for Design choices 1 and 2, and for the approved edit to the fixed TASK-079 test.
   - Fill in the Outcome, listing every test edit.
7. Commit `feat(adapters): project trace_links from the four writing events` with the trailers `Task: TASK-080` and `Milestone: M5`. Do not push.

## Files expected to change
- `src/openfactory/adapters/sqlite_projector.py` (about +70)
- `tests/integration/test_sqlite_projector_m5.py` (new tests, about +200; the edit approved under Open question 1)
- `tests/unit/test_spec_conformance.py` (about +2)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-080-trace-links-projection.md` (this record)

Not expected to change: `domain/`, `ports/`, `app/`, `cli.py`, other adapters, `pyproject.toml`, `docs/adr/`, `docs/spec/`, the M1 to M4 projector tests, `test_m3_close.py`, `test_m4_close.py`. The close tests rebuild through `projector.rebuild` and compare their own explicit table lists, which do not include `trace_links`.

Expected size: about 280 lines, about 70 of them in `src/`.

## Design choices to confirm at planning
1. **Where the kind and source strings live.**
   - Proposed: string literals in `sqlite_projector.py` (`'requirement'`, `'adr'`, `'task'`, `'run'`, `'commit'`, `'file'`, `'test'`; `'spec'`, `'contract'`, `'trailer'`, `'diff'`, `'test_tag'`). This matches today's literals such as `'draft'` and `'approved'`.
   - Alternative: a new `domain/traces.py` with `NodeKind` and `LinkSource` `Literal` types now. The `Traces` port task (next item) may want them, but no code in this task would need them.
2. **What `SpecApproved` reads.**
   - Proposed: the `requirements` projection rows of `payload.spec_version`, decoding `constrained_by` from JSON. This includes deprecated requirements, because the spec says "that version's requirements" with no exception.
   - Alternative: skip deprecated requirements. The spec text does not support this, so it is listed only for completeness.

## Open questions
1. **Approval of an edit to a fixed test.**
   - What breaks: `tests/integration/test_sqlite_projector_m5.py::test_task079_ac3_a_tests_collected_event_is_recorded_and_changes_no_projection` (TASK-079) asserts that recording a `TestsCollected` changes no projection row. That was the interim state ("checked against its model and writes nothing", TASK-079 Spec gaps). The spec rule implemented here inserts a test → file row for its one test, so the assertion fails.
   - Option A: `all_rows` also leaves out `trace_links`, so the test still asserts that no other projection changes. AC5 covers what `trace_links` receives. The docstring and test name stay the same.
   - Option B: change the assertion to expect exactly one added `trace_links` row, `('test', 'tests/test_a.py::test_x', 'file', 'tests/test_a.py', 'test_tag')`, with every other table unchanged. This is closer to how TASK-041 updated the fixed M2 test from `== 0` to `== 1`.
   - The test cannot be deleted or skipped (CLAUDE.md).

## Answers (human, 2026-10-22: approved as proposed)
- Design choice 1: string literals in `sqlite_projector.py`.
- Design choice 2: deprecated requirements are included.
- Open question 1: Option B. The fixed TASK-079 test expects exactly one added `trace_links` row, `('test', 'tests/test_a.py::test_x', 'file', 'tests/test_a.py', 'test_tag')`, and every other table unchanged. The test name and module docstring stay as they are; a Later line notes they no longer match. The edit gets a row in `docs/decisions.md` and is listed in Outcome.

## Spec gaps
None. These are readings, not gaps:
- "that version's requirements" includes deprecated ones (Design choice 2).
- A `SpecApproved` or `PlanApproved` whose version or plan has no projected rows writes no links. The projector checks no event sequences today, and the spec asks for none.
- `TestsCollected` writes its links whatever the task's later state. The spec records the event only on the passing path, and ADR-018 Consequences accepts the crash case ("leaves the collection in `trace_links` until the next task passes").
- A database made before M5 gets an empty `trace_links` from `CREATE TABLE IF NOT EXISTS` and is discarded per the spec (SC-129). Nothing is handled here.

## Outcome
Done. `SqliteProjector` creates `trace_links` with the spec's DDL and `rebuild` drops ten tables. `SpecApproved`, `PlanApproved`, `CommitRecorded` and `TestsCollected` write the links "Traceability" assigns to them, every insert `INSERT OR IGNORE`; `SpecApproved` and `TestsCollected` first delete their `spec` and `test_tag` rows. Design choices as approved: string literals in the projector; deprecated requirements included. Final result: 1633 passed, ruff, pyright and check_docs clean.

Test edits:
- (a) `tests/unit/test_spec_conformance.py`: `M5_TABLES = ("trace_links",)` added to the `test_projection_table_matches_the_spec_create_table` parametrisation. No assertion changed.
- (b) Approved Option B edit to the fixed TASK-079 test `test_task079_ac3_a_tests_collected_event_is_recorded_and_changes_no_projection`: it now expects exactly one added `trace_links` row and every other table unchanged. Name and docstring kept; a Later line in `docs/progress.md` notes the mismatch. Row in `docs/decisions.md`.
- (c) Mechanical fix to the test-writer's new `state_changed` helper in `tests/integration/test_sqlite_projector_m5.py`: it passed `reason: None` for a change to `invalidated`, which `TaskStateChangedPayload` rejects ("reason is required when to is invalidated"), so `test_ac6_abandon_and_invalidate_remove_no_link[invalidated]` errored while building its fixture. The helper now passes `"requirement changed"` when `to == "invalidated"`. Assertions unchanged.
- After review, with the human's go-ahead: `docs/architecture.md` now says the `gate_results` and `commits` rows are plain `INSERT` (reviewer note 2) and that `CommitRecorded`'s `files` go to `trace_links`.
