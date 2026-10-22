# TASK-083: `Traces` trace read, requirement to tasks, commits, files and tests

- Milestone: M5
- Status: done
- Tests: acceptance
- ADR: ADR-018 (accepted). Its "Ports" bullet ("A read-only `Traces` port (adapter `sqlite_traces`) serves the queries") covers adding a read to the existing port and adapter. ADR-006 covers the `TYPE_CHECKING` assertion (already in place) and ADR-010 the adapter's own connection. The task adds no port, adapter, event type, payload, storage schema or dependency. Its design choices go in `docs/decisions.md`.
- Spec impact: wording (F-6, already in progress.md "Later"; see Spec gaps)
- Spec sections (spec v1.17; SC-131, SC-133):
  - "Domain model and storage" › "Ids", M5 paragraph: "The `Traces` port, read-only, whose adapter is `sqlite_traces`, gives the queries of `trace`, `why` and `coverage` over `trace_links` and the task and requirement projections."
  - "Traceability" › "Queries": "`openfactory trace REQ-AUTH-001`: requirement → tasks → commits → files and tests, both the tests tagged with the requirement and the tests in those files."
  - "Traceability", link table: requirement → task (`contract`), task → agent run and agent run → commit (`trailer`), commit → file (`diff`), test → requirement and test → file (`test_tag`); "A link is stored in `trace_links` in the direction shown".
  - "CLI commands" › "Output": "`trace REQ-ID` prints `task  <task id>  <state>` for each task linked to the requirement; then `commit  <sha>  <task id>` for each commit of those tasks, by task id, then sha; then `file  <path>` for each file of those commits, once; then `test  <node id>  tagged` for each test tagged with the requirement and `test  <node id>  file` for each other test whose file is one of those files, by node id. … It refuses with `unknown requirement <ID>` and exits 1 when no approved spec version has the requirement."
  - "CLI commands" › "Output": "groups come in the order given, and each group is sorted as strings."

## Outline item
This is M5 outline item 1 in `docs/progress.md`, cut down: the read only. The `trace` use case and command follow as TASK-084, which depends on this task.

## Objective
`Traces` and `SqliteTraces` gain one read. Given a requirement id, it returns that requirement's tasks with their states, those tasks' commits, those commits' files and the related tests, each group in the spec's order. It returns `None` when no approved spec version has the requirement.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- New `src/openfactory/domain/traces.py`. It is pure and imports only `pydantic`, the standard library and `openfactory.domain`. All models are frozen with `extra="forbid"`:
  - `TracedTask(task_id: str, state: TaskState)`
  - `TracedCommit(sha: str, task_id: str)`
  - `TracedTest(node_id: str, tagged: bool)`
  - `RequirementTrace(tasks: list[TracedTask], commits: list[TracedCommit], files: list[str], tests: list[TracedTest])`

  `TracedCommit` and `TracedTask` are meant for reuse by the `why` read (item 2).
- `src/openfactory/ports/traces.py`: `Traces` gains `requirement_trace(requirement_id: str) -> RequirementTrace | None`. The docstring states that `None` means no approved spec version has the requirement, and states the order of each group.
- `src/openfactory/adapters/sqlite_traces.py`: `requirement_trace` runs `SELECT`s only:
  1. **Known check.** Is there a `requirements` row with this id whose `spec_version` has `status = 'approved'` in `spec_versions`? If not, return `None`. Deprecated rows count.
  2. **Tasks.** `trace_links` `('requirement', <id>, 'task', T, 'contract')` joined to `tasks` for `state`, `ORDER BY` task id.
  3. **Commits.** For those tasks, `('task', T, 'run', R, 'trailer')` joined to `('run', R, 'commit', S, 'trailer')`, `ORDER BY` task id, then sha.
  4. **Files.** `DISTINCT` `to_id` of `('commit', S, 'file', P, 'diff')` for those shas, `ORDER BY` path.
  5. **Tests.**
     - Tagged: `('test', N, 'requirement', <id>, 'test_tag')`.
     - File: `('test', N, 'file', P, 'test_tag')` with P among the files and N not tagged.
     - Both kinds come back in one list, `ORDER BY` node id.
- Tests:
  - `tests/unit/test_traces_port.py`: the method is present. It does not assert an exact method set (decision of TASK-081).
  - `tests/integration/test_sqlite_traces.py`: new tests. The projections are built by recording `SpecImported`, `SpecApproved`, `PlanCreated`, `PlanApproved`, `TaskStateChanged`, `CommitRecorded` and `TestsCollected` through `SqliteEventRecorder`, as the existing tests in that file do.

Out:
- The `trace` use case, the command, the refusal text and the line formatting (TASK-084).
- The `why` read and command (outline item 2), the `GitProvider` commit listing and the rebuild (item 3), and the M5 close test (item 4).
- Any change to the projector, payloads, `SpecVersions`, `Plans`, `cli.py` or `app/`.
- A `NodeKind`/`LinkSource` type. The literals stay as TASK-080 left them.

## Acceptance criteria
- [ ] **AC1** ("Ids", M5 paragraph: "The `Traces` port, read-only, whose adapter is `sqlite_traces`, gives the queries of `trace` …"):
  - `Traces` has `requirement_trace`.
  - `domain/traces.py` imports nothing from `ports`, `adapters` or `app`, and its four models are frozen.
  - `ports/traces.py` still imports nothing from `openfactory.adapters` or `openfactory.app`.
  - `sqlite_traces.py` still ends with the `TYPE_CHECKING` assertion and imports nothing from `openfactory.app`.
- [ ] **AC2** ("Output", `trace`: "when no approved spec version has the requirement"):
  - `requirement_trace` returns `None` in two cases: an id in no version, and an id only in an imported, unapproved draft version.
  - It returns a `RequirementTrace` in two cases: an id only in an older approved version (for example in `sv_01`, removed in the approved `sv_02`), and a deprecated requirement of an approved version.
  - An approved requirement with no links gives four empty lists.
- [ ] **AC3** ("Output": "`task  <task id>  <state>` for each task linked to the requirement"; "each group is sorted as strings"):
  - `tasks` holds every task with a requirement → task `contract` link from the id, with its current `tasks.state` (for example `passed` and `ready` after state changes). It is ordered by task id as strings, with test data where numeric and string order differ (`AUTH-10` before `AUTH-2`).
  - Excluded: a task linked only to another requirement, and a task reached only through a task → task dependency link.
- [ ] **AC4** ("Output": "`commit  <sha>  <task id>` for each commit of those tasks, by task id, then sha; then `file  <path>` for each file of those commits, once"):
  - `commits` holds each commit reached through those tasks' task → run → commit `trailer` links, ordered by task id, then sha. The data has a task with two commits, and sha order that differs from task-id order across tasks.
  - A commit of a task not linked to the requirement is not included.
  - `files` holds the `diff` files of those commits, a file changed by two commits only once, sorted as strings.
- [ ] **AC5** ("Output": "`test  <node id>  tagged` for each test tagged with the requirement and `test  <node id>  file` for each other test whose file is one of those files, by node id"):
  - `tests` holds each test with a `test_tag` link to the requirement (`tagged` true) and each other test whose `test_tag` file is in `files` (`tagged` false), in one list ordered by node id. The data interleaves the two kinds.
  - A test that is tagged and also in one of the files appears once, as tagged.
  - Excluded: an untagged test in a file outside `files`, and a test tagged only with another requirement in a file outside `files`.
- [ ] **AC6** ("Ids", M5 paragraph: "read-only"; "CLI commands" › "Output": "`trace`, `why` and `coverage` record no events"):
  - After calls to `requirement_trace`, every projection table, `projection_state` and `events` hold the same rows as before, and no table was created.
  - `untested_requirements` behaves as before (the existing tests pass unchanged).

## Architecture rules that apply
- `domain/traces.py` is pure, with no I/O. The port imports only from `openfactory.domain` and `typing`. The adapter implements the port on its own connection (ADR-010), only reads, and keeps its `TYPE_CHECKING` assertion (CLAUDE.md, ADR-006).
- The queries go over `trace_links` and the `tasks`, `requirements` and `spec_versions` projections (see Spec gaps, reading 2).

## Plan
1. Create branch `task/TASK-083-traces-trace-read` from an up-to-date main.
2. Get the human's answers to Design choices 1 to 3 and record them here.
3. Test-writer: write failing tests for AC1 to AC6 in `tests/unit/test_traces_port.py` and `tests/integration/test_sqlite_traces.py` (plus a small `tests/unit/test_traces_models.py` if AC1's model checks do not fit the port test).
4. Implement `domain/traces.py`, the port method and the adapter method.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`:
     - "Traces port": two methods, and the "added by their own tasks" sentence updated.
     - "SQLite traces": the new read, and `tasks` and `spec_versions` added to the tables it reads.
     - A short entry for `domain/traces.py`.
   - `docs/progress.md`: Current, a Done line, and outline item 1 split into the done read and the remaining "`trace` use case and command (TASK-084)".
   - `docs/decisions.md`: one row per Design choice.
   - Fill in the Outcome.
7. Commit `feat(adapters): add the Traces trace read` with the trailers `Task: TASK-083` and `Milestone: M5`. Do not push.

## Files expected to change
- `src/openfactory/domain/traces.py` (new, about +35)
- `src/openfactory/ports/traces.py` (about +10)
- `src/openfactory/adapters/sqlite_traces.py` (about +60)
- `tests/unit/test_traces_port.py` (about +15)
- `tests/integration/test_sqlite_traces.py` (about +200)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-083-traces-trace-read.md` (this record)

Not expected to change: `app/`, `cli.py`, `sqlite_projector.py`, other ports and adapters, payloads, any existing test assertion, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 320 lines, about 105 of them in `src/`.

## Design choices to confirm at planning
1. **Shape of the read.**
   - Proposed: one method, `requirement_trace(requirement_id) -> RequirementTrace | None`, where `None` means no approved spec version has the id. The TASK-084 use case maps `None` to `unknown requirement <ID>`.
   - Alternative: two methods, `approved_requirement(requirement_id) -> bool` (or the same check on `SpecVersions`) and `requirement_trace(...) -> RequirementTrace`.
   - Trade-off: the proposal is one call and keeps the "any approved version" check next to the query that needs it. The alternative mirrors TASK-081, where the refusal's read lived on `SpecVersions`. But `SpecVersions` has no per-requirement read today, and adding one changes every `SpecVersions` fake.
2. **Where the result types live.**
   - Proposed: a new `domain/traces.py` with the four frozen models, so ports return domain models as `Plans` does (`Task`, `CommitRef`, `GateResultRef` in `domain/plans.py`).
   - Alternative: plain tuples or `list[tuple[str, str]]` on the port, with no domain module.
   - `TracedTest.tagged: bool` against a `kind: Literal["tagged", "file"]` field: the proposal is the bool. The command prints the word.
3. **Where the order is decided.**
   - Proposed: the adapter, through `ORDER BY` with BINARY collation, as TASK-081 decision 3 did. The use case will not sort again.
   - The keys: tasks by task id; commits by task id, then sha; files by path; tests by node id, both kinds in one list.

## Open questions
None beyond the Design choices.

## Answers (human, 2026-10-22)
Approved as proposed: split item 1 (TASK-084 follows with the use case and command); one method returning `RequirementTrace | None`; frozen models in `domain/traces.py` with `tagged: bool`; order decided in the adapter by `ORDER BY` with the keys above, both test kinds in one list by node id.

## Spec gaps
- **"CLI commands" › "Output", line 867 against lines 868 and 869 (wording, F-6 of `docs/spec-audits/2026-10-22-proposal-v1.17.md`, already in progress.md "Later").**
  - What is unclear: "each group is sorted as strings" literally means sorting the whole line. For the `commit  <sha>  <task id>` group that gives sha order, but line 868 says "by task id, then sha". The text also leaves open whether the two kinds of `test` line form one group or two.
  - Why it does not block: the meaning is clear from line 868's own keys. Commits go by task id, then sha. The two `test` kinds together go by node id. The audit and its advisor read it this way, and the proposed fix ("by the key its line names where one is given") only rewords it. The read implements those stated keys and adds no assumption.
- Readings, not gaps:
  1. "No approved spec version has the requirement" means any approved version, not only the latest, and a deprecated requirement counts as having it.
  2. The known check joins `requirements` to `spec_versions.status`. The M5 paragraph names "the task and requirement projections"; `spec_versions` is read only to tell approved rows from draft ones.
  3. "Each task linked to the requirement" means the requirement → task `contract` links. A dependency link alone does not count. Invalidated or abandoned tasks keep their links (Projection rules) and are listed with their state.
  4. "Commit of those tasks" goes through the task → run → commit `trailer` links, not the `commits` table, per the M5 paragraph.

## Outcome
- Added `domain/traces.py` (four frozen models), `Traces.requirement_trace` and `SqliteTraces.requirement_trace`; architecture, progress and decisions updated. AC1 to AC6 covered by `tests/unit/test_traces_models.py`, `tests/unit/test_traces_port.py` and `tests/integration/test_sqlite_traces.py`.
- No test edits: no existing test was changed.
- The test-writer used `AUTH-002` and `AUTH-010` instead of `AUTH-2` and `AUTH-10` (AC3) because `TaskId` requires three digits, so the task-order check cannot tell string order from numeric order. String order is still exercised on commits, files and tests.
- No ADR needed beyond ADR-018; design choices are rows in `docs/decisions.md`.
