# TASK-085: `Traces` why read, file to commits, tasks, requirements and ADRs

- Milestone: M5
- Status: done
- Tests: acceptance
- ADR: ADR-018 (accepted). Its "Ports" bullet ("A read-only `Traces` port (adapter `sqlite_traces`) serves the queries") covers adding a read to the existing port and adapter, as it did for TASK-083. ADR-006 covers the `TYPE_CHECKING` assertion (already in place) and ADR-010 the adapter's own connection. The task adds no port, adapter, event type, payload, storage schema, convention or dependency. Design choices go in `docs/decisions.md`.
- Spec impact: wording (F-6 of `docs/spec-audits/2026-10-22-proposal-v1.17.md`, already in progress.md "Later"; see Spec gaps)
- Spec sections (spec v1.17; SC-131, SC-133):
  - "Domain model and storage" › "Ids", M5 paragraph: "The `Traces` port, read-only, whose adapter is `sqlite_traces`, gives the queries of `trace`, `why` and `coverage` over `trace_links` and the task and requirement projections."
  - "Traceability" › "Queries": "`openfactory why app/auth/login.py`: file → commits → tasks → requirements and ADRs; the ADRs are those of the latest approved spec version."
  - "Traceability", link table: requirement → ADR (`spec`), requirement → task (`contract`), task → agent run and agent run → commit (`trailer`), commit → file (`diff`); "A link is stored in `trace_links` in the direction shown".
  - "Domain model and storage" › "Projection rules": "`SpecApproved` deletes every row with source `spec` and inserts requirement → ADR for each `constrained_by` entry of that version's requirements, so the `spec` rows are those of the latest approved version."
  - "CLI commands" › "Output": "`why PATH` compares PATH as a string with the files of `trace_links` (relative to the repo root, `/` separators, no normalisation). It prints `commit  <sha>  <task id>` for each commit that changed the file, by task id, then sha; then `task  <task id>  <state>` for each of their tasks; then `requirement  <id>` for each requirement linked to those tasks; then `adr  <id>` for each ADR those requirements are constrained by in the latest approved spec version; and exits 0. It refuses with `no commit changed <PATH>` and exits 1."
  - "CLI commands" › "Output": "`trace`, `why` and `coverage` record no events and do not repair the plan. … groups come in the order given, and each group is sorted as strings."

## Outline item
M5 outline item 1 in `docs/progress.md`, cut down to the read only, as TASK-083 was for `trace`. The `why` use case and command follow as TASK-086, which depends on this task. The task also does the "Later" line from the TASK-083 review: share the run → commit `trailer` join and the files subquery in `SqliteTraces`.

## Objective
`Traces` and `SqliteTraces` gain one read. Given a file path, it returns:
- the commits that changed the file, with their tasks;
- those tasks with their states;
- the requirements linked to those tasks;
- the ADRs those requirements are constrained by in the latest approved spec version.

Each group comes in the spec's order. The read returns `None` when no commit changed the path.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/domain/traces.py` gains a frozen `FileTrace(commits: list[TracedCommit], tasks: list[TracedTask], requirements: list[str], adrs: list[str])` with `extra="forbid"`. It reuses `TracedCommit` and `TracedTask` from TASK-083. The module stays pure.
- `src/openfactory/ports/traces.py`: `Traces` gains `file_trace(path: str) -> FileTrace | None`. The docstring says that `None` means no commit changed the path, that the path is compared as an exact string, and the order of each group.
- `src/openfactory/adapters/sqlite_traces.py`: `file_trace` runs only `SELECT`s.
  1. **Commits.** Find `('commit', S, 'file', <path>, 'diff')`, joined through `('run', R, 'commit', S, 'trailer')` to `('task', T, 'run', R, 'trailer')`. Order by task id, then sha. When there are no rows, return `None`.
  2. **Tasks.** `DISTINCT` the T of those commits, joined to `tasks` for `state`, `ORDER BY` task id.
  3. **Requirements.** `DISTINCT` `from_id` of `('requirement', Q, 'task', T, 'contract')` for those tasks, `ORDER BY` id.
  4. **ADRs.** `DISTINCT` `to_id` of `('requirement', Q, 'adr', A, 'spec')` for those requirements, `ORDER BY` id.
  5. **Shared fragments.** Share the run → commit `trailer` join and the commit → file `diff` subquery between `requirement_trace` and `file_trace` (the "Later" line from the TASK-083 review). `requirement_trace` must behave exactly as before.
- Tests:
  - `tests/unit/test_traces_port.py`: the method is present. No exact method-set test (TASK-081 decision).
  - `tests/unit/test_traces_models.py`: `FileTrace` is frozen and forbids extra fields.
  - `tests/integration/test_sqlite_traces.py`: new `test_task085_` tests, projections built by recording `SpecImported`, `SpecApproved`, `PlanCreated`, `PlanApproved`, `TaskStateChanged`, `CommitRecorded` and `TestsCollected` through `SqliteEventRecorder`, reusing the file's helpers.

Out:
- The `why` use case, the command, the `no commit changed <PATH>` text and the line formatting (TASK-086).
- The `GitProvider` commit listing and the rebuild (outline item 2) and the M5 close test (item 3).
- Any change to the projector, payloads, `SpecVersions`, `Plans`, `cli.py` or `app/`.
- Normalising or validating PATH. The spec says "no normalisation".

## Acceptance criteria
- [ ] **AC1** ("Ids", M5 paragraph): `Traces` has `file_trace`; `FileTrace` is frozen and forbids extra fields; `domain/traces.py` imports nothing from `ports`, `adapters` or `app`; `ports/traces.py` imports nothing from `openfactory.adapters` or `openfactory.app`; `sqlite_traces.py` still ends with the `TYPE_CHECKING` assertion and imports nothing from `openfactory.app`.
- [ ] **AC2** (`why` compares PATH as a string, no normalisation; refusal): `file_trace` returns `None` for a path no commit changed; for `./<path>` and a different-case spelling of a changed path; for a directory prefix of a changed path (`app/`, `app`); for a path that is only a test's file (a `test_tag` test → file link with no `diff` link). It returns a `FileTrace` for the exact changed path.
- [ ] **AC3** (commits by task id, then sha): `commits` holds every commit with a `diff` link to the path, each with its task from the `trailer` links; ordered by task id then sha, with one task having two commits on the file and sha order differing from task-id order across tasks; a commit that changed only other files is excluded, also when its task has another commit on the path.
- [ ] **AC4** (tasks): `tasks` holds each task of those commits once, with its current `tasks.state` (incl. a later state set by `TaskStateChanged`), ordered by task id; a task linked to the same requirement but with no commit on the path is excluded.
- [ ] **AC5** (requirements and ADRs): `requirements` holds each requirement with a `contract` link to one of those tasks, once, sorted as strings (one requirement linked to two of the tasks, one task with two requirements); a requirement reached only via a task → task dependency link, or linked only to other tasks, is excluded. `adrs` holds each ADR those requirements are constrained by in the latest approved version, once, sorted; with `sv_01` then `sv_02` approved, an ADR only in `sv_01`'s `constrained_by` is excluded and one added in `sv_02` included; a requirement with no `constrained_by` adds no ADR.
- [ ] **AC6** (read-only, no events): after calls to `file_trace`, every projection table, `projection_state` and `events` hold the same rows and no table was created; `requirement_trace` and `untested_requirements` behave as before after the shared-fragment change — every existing test in `test_sqlite_traces.py` passes unchanged.

## Architecture rules that apply
- `domain/traces.py` is pure, with no I/O.
- The port imports only from `openfactory.domain` and `typing`.
- The adapter implements the port on its own connection (ADR-010), only reads, and keeps its `TYPE_CHECKING` assertion (CLAUDE.md, ADR-006).
- The queries go over `trace_links` and the `tasks` projection only.

## Plan
1. Create branch `task/TASK-085-traces-why-read` from an up-to-date main.
2. Record the human's answers to Design choices 1 to 5 here.
3. Test-writer: failing tests for AC1 to AC6, named `test_task085_...`, with a `why` world fixture next to TASK-083's `world`.
4. Implement `FileTrace`, the port method, the adapter method and the shared SQL fragments.
5. Run tests, ruff, pyright and check_docs until all pass.
6. Update `docs/architecture.md`, `docs/progress.md` (split outline item 1; remove the shared-subqueries "Later" line), `docs/decisions.md` (one row per Design choice), and the Outcome.
7. Commit `feat(adapters): add the Traces why read` with trailers `Task: TASK-085`, `Milestone: M5`.

## Files expected to change
- `src/openfactory/domain/traces.py` (~+12), `src/openfactory/ports/traces.py` (~+12), `src/openfactory/adapters/sqlite_traces.py` (~+55)
- `tests/unit/test_traces_port.py` (~+8), `tests/unit/test_traces_models.py` (~+15), `tests/integration/test_sqlite_traces.py` (~+190)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, this record

Expected size: about 300 lines, about 80 in `src/`.

## Design choices to confirm at planning
1. **Shape of the read.** Proposed: `file_trace(path) -> FileTrace | None`, `None` = no commit changed the path (mirrors TASK-083 choice 1). Alternative: always return `FileTrace`, use case refuses on empty `commits`.
2. **Result type.** Proposed: `FileTrace` reusing `TracedCommit`/`TracedTask`, `requirements` and `adrs` as `list[str]`. Alternative: `TracedRequirement`/`TracedAdr` models.
3. **Where the ADRs come from.** Proposed: the `spec` requirement → ADR rows of `trace_links` (latest approved by the Projection rules). Alternative: `requirements.constrained_by` JSON of the latest approved version.
4. **Where the order is decided.** Proposed: in the adapter, `ORDER BY` with BINARY collation (TASK-081 d3, TASK-083 d3); TASK-086 does not re-sort.
5. **Shared SQL fragments.** Proposed: do the TASK-083 "Later" refactor here, guarded by existing `requirement_trace` tests passing unchanged. Alternative: duplicate the joins and keep the "Later" line.

## Human answers (2026-10-22)
Design choices 1 to 5 accepted as proposed; the split of outline item 1 (read here, `why` use case and command in TASK-086) accepted. Advisor: 6 AGREE. For choice 5, keep the advisor's caveat: if sharing makes the SQL harder to read than duplication, keep the duplication and the "Later" line.

## Open questions
None beyond the Design choices.

## Spec gaps
- **"Output", "each group is sorted as strings" against `why`'s "by task id, then sha"** (wording, F-6, already in "Later"). Literal reading would sort the commit group by sha; the line names its own key. TASK-083 read `trace` the same way with the human's answer of 2026-10-22.
- Readings, not gaps:
  1. "The files of `trace_links`" are the commit → file `diff` targets; a test-only file path gets the refusal (AC2).
  2. "Requirement linked to those tasks" means requirement → task `contract` links, unfiltered by version or `deprecated`; task → task links bring no requirement.
  3. "Constrained by in the latest approved spec version" is met by the `spec` rows.
  4. Invalidated or abandoned tasks keep their links and are listed with their state, as in TASK-083.

## Outcome
`FileTrace` added to `domain/traces.py`, `Traces.file_trace` to the port, and its `SELECT`-only implementation to `SqliteTraces`. `requirement_trace` and `file_trace` share the SQL fragments `_COMMIT_TASKS`, `_DIFF`, `_REQUIREMENT_TASKS`, `_COMMITS`, `_FILE_COMMITS` and `_FILE_REQUIREMENTS`, so the "Later" line from the TASK-083 review is done.

- AC1 to AC6 met. Tests, ruff, pyright and check_docs are green; 1706 passed.
- No test was edited after the test-writer; the existing `requirement_trace` and `untested_requirements` tests pass unchanged.
- Design choices 1 to 5 and the split are recorded in `docs/decisions.md`. No ADR needed (ADR-018 covers it).
- The `why` use case and command follow as TASK-086.
