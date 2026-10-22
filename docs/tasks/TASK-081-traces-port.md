# TASK-081: `Traces` read port and `sqlite_traces` adapter, the `coverage` read

- Milestone: M5
- Status: done
- Tests: acceptance
- ADR: ADR-018 (accepted). Its "Ports" bullet says "A read-only `Traces` port (adapter `sqlite_traces`) serves the queries", so it covers the new port and adapter. ADR-006 covers the `TYPE_CHECKING` assertion, and ADR-010 covers the adapter having its own connection. The task adds no event type, payload, storage schema or dependency.
- Spec impact: none
- Spec sections (spec v1.17; SC-130, SC-133):
  - "Domain model and storage" › "Ids", the M5 paragraph: "M5 adds what the links need. The `Traces` port, read-only, whose adapter is `sqlite_traces`, gives the queries of `trace`, `why` and `coverage` over `trace_links` and the task and requirement projections."
  - "Traceability" › "Queries": "`openfactory coverage`: requirements with no passing tagged test. A test in `trace_links` passed: a collection is recorded only for an attempt whose gates all passed."
  - "CLI commands" › "Output": "`coverage` prints, as its id, each requirement of the latest approved spec version that is not deprecated and has no `test_tag` link from a test …"; and "Their lines separate fields by exactly two spaces; groups come in the order given, and each group is sorted as strings."
  - "Domain model and storage" › "Projection rules", the `TestsCollected` sub-bullet (where the test → requirement `test_tag` rows come from).

## Outline item
This is M5 outline item 1 in `docs/progress.md`, made smaller (see Design choice 1). The port and adapter are created with the one read that `coverage` needs. The reads for `trace` and `why` are added to `Traces` and `SqliteTraces` by the tasks for items 3 and 4.

## Objective
Add a read-only `Traces` port and its `SqliteTraces` adapter. The port's first method gives the ids of a spec version's requirements that are not deprecated and have no `test_tag` link from a test, sorted as strings.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- New `src/openfactory/ports/traces.py`: Protocol `Traces` with `untested_requirements(spec_version: str) -> list[str]`. Its docstring names the spec's M5 paragraph, ADR-018 and ADR-012.
- New `src/openfactory/adapters/sqlite_traces.py`:
  - `SqliteTraces(path)` opens its own connection with `PRAGMA busy_timeout = 5000` and has `close()`, the same pattern as `SqlitePlans`.
  - `untested_requirements` runs one `SELECT` on `requirements` with `spec_version = ?` and `deprecated = 0`. It leaves out ids that appear as `to_id` in a `trace_links` row with `from_kind = 'test'`, `to_kind = 'requirement'` and `source = 'test_tag'`. Rows are returned `ORDER BY id`.
  - It creates no table and writes nothing.
  - The module ends with `if TYPE_CHECKING: _: type[Traces] = SqliteTraces`.
- Tests:
  - New `tests/unit/test_traces_port.py`.
  - New `tests/integration/test_sqlite_traces.py`. It builds the projections by recording `SpecImported`, `SpecApproved` and `TestsCollected` (and `PlanCreated`/`PlanApproved` for the `contract` case) through `SqliteEventRecorder`, the same way as `test_sqlite_plans_last_gate.py`.

Out:
- The reads for `trace` and `why`, including the `unknown requirement <ID>` check (outline items 3 and 4).
- The `coverage` use case and command, the `no approved spec version` refusal and any `cli.py` wiring (outline item 2).
- The `GitProvider` commit listing and the rebuild from git (outline item 5).
- Any change to the projector, payloads, `SpecVersions` or `Plans`.
- A `NodeKind`/`LinkSource` type in `domain/`. The literals stay where TASK-080 put them.

## Acceptance criteria
- [ ] **AC1** ("Ids", M5 paragraph: "The `Traces` port, read-only, whose adapter is `sqlite_traces`"): `Traces` in `ports/traces.py` is a `typing.Protocol` with a method `untested_requirements`. The port module imports nothing from `openfactory.adapters` or `openfactory.app`. `adapters/sqlite_traces.py` imports nothing from `openfactory.app` and ends with the `TYPE_CHECKING` assertion against `Traces`.
- [ ] **AC2** ("Output", `coverage`: "each requirement of the latest approved spec version that is not deprecated and has no `test_tag` link from a test"):
  - Setup: one version with three requirements, plus a `TestsCollected` where one test is tagged with the first requirement and an untagged test is in the same file.
  - `untested_requirements(<version>)` returns the other two ids.
  - Once every requirement is tagged it returns `[]`.
- [ ] **AC3** (same sentence, "not deprecated"): a deprecated requirement with no tagged test is never returned. A deprecated requirement that is tagged is not returned either.
- [ ] **AC4** (same sentence, "has no `test_tag` link from a test"; "Projection rules", `TestsCollected` "deletes every row with source `test_tag`"):
  - Only a test → requirement `test_tag` row counts. A requirement → task `contract` row for the requirement (from an approved plan) does not count.
  - After a second `TestsCollected` that no longer tags a requirement, that requirement is returned again.
- [ ] **AC5** ("Ids": "the latest approved spec version", read per version; "Output": "each group is sorted as strings"):
  - Only the given version's requirements are returned. With `sv_01` and `sv_02` holding different requirement sets, each call returns ids from its own version only.
  - A version with no rows gives `[]`.
  - The ids come back sorted as Python sorts strings. The test data must include ids whose numeric order differs from their string order (for example `REQ-A-10` before `REQ-A-2`).
- [ ] **AC6** ("Ids", M5 paragraph: "read-only"): after calls to `untested_requirements`, every projection table and `projection_state` hold the same rows as before, and no table was created. A database opened by `SqliteTraces` alone, with no recorder, raises `sqlite3.OperationalError`, which is not handled. This is the same documented behaviour as `SqlitePlans`.

## Architecture rules that apply
- The port imports only from `openfactory.domain` and `typing` (ADR-006, ADR-012 pattern). The adapter implements the port, has its own connection (ADR-010) and ends with the `TYPE_CHECKING` assertion (CLAUDE.md, ADR-006).
- The adapter only reads. The event recorder creates and writes the projections.

## Plan
1. Create branch `task/TASK-081-traces-port` from an up-to-date main.
2. Get your answers to Design choices 1 to 3 and record them here.
3. Test-writer: write failing tests for AC1 to AC6 in `tests/unit/test_traces_port.py` and `tests/integration/test_sqlite_traces.py`.
4. Implement `ports/traces.py` and `adapters/sqlite_traces.py`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`: add "Traces port" and "SQLite traces" sections, following the "Runs port"/`sqlite_runs.py` sections.
   - `docs/progress.md`:
     - Update Current and add a Done line.
     - Mark the reduced item 1 done.
     - Add the trace and why reads to items 3 and 4.
   - `docs/decisions.md`: one row per Design choice.
   - Fill in Outcome.
7. Commit `feat(adapters): add the Traces port and the sqlite_traces coverage read` with the trailers `Task: TASK-081` and `Milestone: M5`. Do not push.

## Files expected to change
- `src/openfactory/ports/traces.py` (new, about +20)
- `src/openfactory/adapters/sqlite_traces.py` (new, about +45)
- `tests/unit/test_traces_port.py` (new, about +45)
- `tests/integration/test_sqlite_traces.py` (new, about +170)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-081-traces-port.md` (this record)

Not expected to change: `domain/`, `app/`, `cli.py`, `sqlite_projector.py`, other adapters and ports, any existing test, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 280 lines, about 65 of them in `src/`.

## Design choices to confirm at planning
1. **Scope of the port in this task.**
   - Proposed: one method, the `coverage` read. Items 3 (`trace`) and 4 (`why`) each add their own reads to `Traces` and `SqliteTraces`.
   - Alternative: all the reads in this task. That means `requirement_approved` for the `unknown requirement` refusal, the trace graph and the why graph, plus result models in `domain/`. It is about 450–500 lines, over the ~300-line limit. It does fix the port's shape in one go.
   - Consequence of the proposed choice: the port test should check that the method is present, not assert an exact method set. Otherwise each later task edits a fixed test and leaves a misleading name, as happened with `test_plans_port.py` and `test_runs_port.py` (see Later).
2. **Method shape.**
   - Proposed: `untested_requirements(spec_version: str) -> list[str]`. The `coverage` use case gets the latest approved version from `SpecVersions.latest_approved()`, where its `no approved spec version` refusal already lives, and passes the version id.
   - Alternative: a method with no arguments that finds the latest approved version itself and returns `None` when there is none. That duplicates what `SpecVersions` already reads.
   - The name avoids clashing with `domain/tag_rule.uncovered_requirements`.
3. **Where the sort happens.**
   - Proposed: the adapter returns `ORDER BY id`. SQLite's default `BINARY` collation compares UTF-8 bytes, which gives the same order as Python string sorting for valid text. The use case does not sort again.
   - Alternative: the adapter returns any order and the use case sorts with `sorted()`.

## Decisions at planning (approved by the human, 2026-10-22)
1. Port scope: the proposal. One method, `untested_requirements`. The port test checks that the method is present and does not assert an exact method set. This departs from the exact-set rows of 2026-10-11 (TASK-024) and 2026-10-13 (TASK-042, TASK-043) because those ports' methods are listed in full by the spec. The M5 paragraph names only the three queries, so an exact set here would mean guessing the `trace` and `why` methods.
2. Method shape: the proposal. `untested_requirements(spec_version: str) -> list[str]`. The `coverage` use case reads the version from `SpecVersions.latest_approved()` and keeps the `no approved spec version` refusal.
3. Sorting: the proposal. The adapter uses `ORDER BY id` (BINARY collation) and the use case does not sort again.

## Open questions
None beyond the Design choices.

## Spec gaps
None. These are readings, not gaps:
- "has no `test_tag` link from a test" means a `trace_links` row `('test', <node id>, 'requirement', <id>, 'test_tag')`. Only `TestsCollected` writes such a row.
- The F-6 wording item in Later ("each group is sorted as strings" against the keys that `trace` and `why` name) does not touch `coverage`, which has a single group of ids.

## Outcome
Added `Traces` (`ports/traces.py`) with `untested_requirements(spec_version) -> list[str]` and `SqliteTraces` (`adapters/sqlite_traces.py`), which returns a version's non-deprecated requirement ids with no `test_tag` test link, `ORDER BY id`. Only reads; own connection; ends with the `TYPE_CHECKING` assertion. Tests: `tests/unit/test_traces_port.py` and `tests/integration/test_sqlite_traces.py`, covering AC1 to AC6.
- No test edits were made.
- The new integration test imports `TestsCollectedPayload`, which makes pytest emit one `PytestCollectionWarning` (harmless, not fixed).
- Docs: `docs/architecture.md` (Traces port, SQLite traces), `docs/progress.md`, `docs/decisions.md` (3 rows).
- Plan step 6 said to mark outline item 1 done. It was removed from the M5 outline instead and the rest renumbered, as TASK-080 did, because the outline lists only remaining tasks. The `trace` and `why` items are now items 2 and 3.
- Reviewer notes left as they are: AC3's tagged-deprecated case does not test the `deprecated = 0` filter on its own (the untagged case does), and the collection warning above. Both would need a test-writer test edited.
