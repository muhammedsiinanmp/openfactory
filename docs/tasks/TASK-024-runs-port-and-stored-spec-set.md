# TASK-024: Runs port with `sqlite_runs`, and the stored spec set on `SpecVersions`

- Milestone: M2
- Status: done
- Tests: acceptance
- ADR: ADR-012 (accepted, 2026-10-11). It decides the `Runs` port over `agent_runs` with the adapter `sqlite_runs`, and that "`SpecVersions` gains one method that returns the stored spec set of a version, read from `requirements`, `adrs` and `spec_versions.components`", extending ADR-001 (accepted). It says "Each adapter opens its own connection, as `sqlite_spec_versions` does (ADR-001, ADR-010), and ends with the `TYPE_CHECKING` assertion against its port (ADR-006)" and "Exact signatures are settled in the tasks that build them". That is enough: no new ADR. The signatures and the other answers under Open questions are rows in `docs/decisions.md`.
- Spec impact: none
- Spec sections (spec v1.10): "Domain model and storage" ("Ids", "Projections" with its `CREATE TABLE` block, "Projection rules", "Event payloads", "Streams and actors"); "Task contract" ("Planning": the plan and run id bullet); "Spec input format" ("Hashing", "Spec versions"); "Metrics"; "Tech stack and repo layout"

## Objective
Add the read-only `Runs` port with its SQLite adapter, which gives the next run id from `agent_runs`, and add to `SpecVersions` one method that returns the stored spec set of a version, so the plan use case can choose `run_NNNN` and read the approved requirements, criteria and ADR bodies without touching SQLite.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings.

## Scope
In:
- `src/openfactory/ports/runs.py` (new): the Protocol `Runs` with one method, `next_id() -> str`. It imports nothing from `adapters` or `app`.
- `src/openfactory/adapters/sqlite_runs.py` (new; the module name is the spec's):
  - `SqliteRuns(path: str | Path)` with `next_id()` and `close()`.
  - Own connection, `PRAGMA busy_timeout = 5000`, `SELECT` only on `agent_runs`, no table created, nothing cached.
  - Ends with `if TYPE_CHECKING: _: type[Runs] = SqliteRuns`.
- `src/openfactory/ports/spec_versions.py`: a fourth method, `spec_set(version_id: str) -> SpecSet | None`.
- `src/openfactory/adapters/sqlite_spec_versions.py`: `spec_set`, built from `spec_versions.components` and the `requirements` and `adrs` rows of that version, validated through the domain models.
- One approved edit to a fixed test (Open question 4).

Out (not this task):
- The `Plans` port and `sqlite_plans`: the rest of outline item 4, next task. It needs its own domain return types.
- `GitProvider` and `git_cli` (item 8), `LLMProvider` (item 7), every use case and command (items 9 to 12), and any wiring in `cli.py`.
- Any change to `SqliteProjector`, `SqliteEventRecorder`, `domain/models.py`, `domain/payloads.py` and `app/`.
- A database without the `agent_runs` or `spec_versions` table: the `sqlite3.OperationalError` is left as it is (TASK-011 decision).
- Inconsistent projections the use cases cannot produce: a run id that does not match `run_NNNN`, a requirement row whose JSON columns the models reject. Not checked (TASK-009 and TASK-011 decisions).
- Version metadata beyond the spec set (`status`, `approved_at`): `SpecVersionRef` is unchanged.
- The fakes of `SpecVersions` in `tests/unit/test_validate_use_case.py` and `tests/unit/test_approve_spec_use_case.py`. They need no edit: the port is structural, `validate` does not call `spec_set`, and pyright checks `src` only.
- Every Later line in `docs/progress.md`. Checked: the repeated `depends_on` entry concerns `task_deps`, which this task does not read.

## Acceptance criteria
"Ids", "Projections", "Projection rules" and "Event payloads" are under "Domain model and storage"; "Planning" is under "Task contract". In AC2 to AC6 the database is a SQLite file under `tmp_path` opened first by `SqliteEventRecorder`, and every row is produced by recording events built through the payload models. The criteria are written for the proposals under Open questions.

- [x] AC1 ("Tech stack and repo layout": "`ports/ # interfaces: EventStore, EventRecorder, SpecVersions, Plans, Runs, ...`" and "`adapters/ # ..., sqlite_spec_versions, sqlite_plans, sqlite_runs, ...`"; "Ids": "The `Runs` port gives the next run id. Both are read-only"):
  - `openfactory.ports.runs` defines a Protocol `Runs` whose only public method is `next_id`, and imports nothing from `openfactory.adapters` or `openfactory.app` (checked by parsing its imports with `ast`).
  - `openfactory.adapters.sqlite_runs` imports nothing from `openfactory.app`.
- [x] AC2 ("Planning": "Plan ids are `plan_NN` and run ids `run_NNNN`, counted from `plan_01` and `run_0001`, wider when needed; the next id is one more than the highest in use"; "Metrics": "A planner or classifier call is recorded as an agent run with its role and no task"):
  - With no recorded event, `next_id()` returns `run_0001`.
  - After an `AgentRunStarted` for `run_0001` (planner, no task), it returns `run_0002`, whether or not that run's `AgentRunFinished` is recorded.
  - With `run_0001` and `run_0007` started, it returns `run_0008`.
  - With `run_9999` started, it returns `run_10000`.
- [x] AC3 ("Streams and actors": "`plan` records `AgentRunStarted` before each planner call and `AgentRunFinished` after it; a retried call is a second pair"; "Ids": "run ids (`run_NNNN`) are chosen by the use case from the projections when a command runs"): a `SqliteRuns` opened while the recorder is open and the log is empty returns `run_0001`; after the recorder records started and finished for `run_0001`, the same adapter object returns `run_0002`.
- [x] AC4 ("Ids": "the `SpecVersions` port, a read-only port that gives the latest approved version, the current draft, the next spec version id and the stored spec set of a version"; "Event payloads": "`spec: { components, requirements, adrs }` # the full spec set, ADR bodies included, stored in canonical order"; "Projections": the `requirements`, `adrs` and `spec_versions` rows; "Hashing": "The spec set's hash covers the components, the requirements and the ADRs"):
  - The Protocol `SpecVersions` has exactly the public methods `latest_approved`, `current_draft`, `next_id` and `spec_set`.
  - After a `SpecImported` for `sv_01` whose `spec` is in canonical order and holds two components, two requirements and two ADRs, `spec_set("sv_01")` returns a `SpecSet` equal to the payload's `spec`. One requirement is deprecated with `constrained_by`, components and two acceptance criteria; one ADR has a multi-line non-ASCII body.
  - `content_hash` of the result equals the `hash` of `current_draft()` when the payload's hash is the spec's `content_hash`.
  - The result is the same after `SpecApproved` for `sv_01`.
- [x] AC5 ("Spec versions": "an existing draft keeps its id and its content is replaced"; "the version is immutable from then on. Edits after that create a new draft version"; "Ids": "the stored spec set of a version"):
  - With `sv_01` approved and a `SpecImported` for `sv_02` that drops one requirement and changes another, `spec_set("sv_01")` still returns the first set and `spec_set("sv_02")` the second.
  - After a second `SpecImported` for `sv_02`, `spec_set("sv_02")` returns the replaced content.
  - A version imported with only components returns a `SpecSet` with those components and empty `requirements` and `adrs`.
  - `spec_set("sv_09")`, a version with no row, returns `None`.
- [x] AC6 ("Ids": "Both are read-only" and "a read-only port"; "Projection rules": "Projection tables are never written in any other way"): with spec and run events recorded, opening `SqliteRuns` and `SqliteSpecVersions`, calling `next_id()` and `spec_set()` and closing them changes no row. The rows of `events`, `spec_versions`, `requirements`, `adrs`, `agent_runs` and `projection_state`, read by the test on its own connection, are equal before and after.

## Architecture rules that apply
- Ports hold Protocols only and import from `openfactory.domain` only. `ports/spec_versions.py` gains an import of `SpecSet` from `domain/models.py`.
- Each adapter that implements a port ends with its `TYPE_CHECKING` assertion; the existing assertion in `sqlite_spec_versions.py` now also checks `spec_set`.
- "All state changes go through the events table. Never write projections directly": both adapters only read, and tests fill the tables by recording events through `SqliteEventRecorder`.
- Rows read back are validated by the domain models (`Requirement`, `Adr`, `SpecSet`) before they are returned.
- Tests from the test-writer are fixed. The edit under Open question 4 is not mechanical and needs approval first.

## Plan
1. Create branch `task/TASK-024-runs-port-and-stored-spec-set` from an up-to-date main and commit this record.
2. Get the human's answers to Open questions 1 to 5; record them here and as rows in `docs/decisions.md`.
3. Write failing tests:
   - `tests/unit/test_runs_port.py` for AC1, in the style of `tests/unit/test_spec_versions_port.py`.
   - `tests/integration/test_sqlite_runs.py` for AC2, AC3 and the `Runs` half of AC6.
   - `tests/integration/test_sqlite_spec_set.py` for AC4 to AC6, with helpers that build `SpecImported` and `SpecApproved` through the payload models.
4. Make the approved edit to `tests/unit/test_spec_versions_port.py` and nothing else in that file.
5. Add `ports/runs.py` and `adapters/sqlite_runs.py`: one query, `SELECT MAX(CAST(substr(id, 5) AS INTEGER)) FROM agent_runs`, formatted as `run_{n:04d}`.
6. Add `spec_set` to the port and to `SqliteSpecVersions`:
   - Read `components` from the `spec_versions` row; no row gives `None`.
   - Read the `requirements` and `adrs` rows of the version in `id` order, decode the JSON columns and build the models.
7. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until green.
8. Update the living docs and the Outcome. Commit `feat(adapters): add the Runs read port and the stored spec set of a version` with trailers `Task: TASK-024` and `Milestone: M2`.

## Files expected to change
- `src/openfactory/ports/runs.py` (new, about 20 lines)
- `src/openfactory/adapters/sqlite_runs.py` (new, about 35 lines)
- `src/openfactory/ports/spec_versions.py` (about 10 lines added)
- `src/openfactory/adapters/sqlite_spec_versions.py` (about 45 lines added)
- `tests/unit/test_runs_port.py` (new, about 40 lines)
- `tests/integration/test_sqlite_runs.py` (new, about 90 lines)
- `tests/integration/test_sqlite_spec_set.py` (new, about 130 lines)
- `tests/unit/test_spec_versions_port.py` (one assertion, per Open question 4)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-024-runs-port-and-stored-spec-set.md`

About 110 lines of source and 260 of tests: over the 300-line aim, within six criteria (see Open question 5).

Not expected to change: `sqlite_projector.py`, `sqlite_recorder.py`, `cli.py`, everything under `domain/` and `app/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, and every other test file. `tests/integration/test_sqlite_spec_versions.py` calls only the three existing methods.

## Living docs to update
- `docs/architecture.md`:
  - "SpecVersions port": four methods.
  - "SQLite spec versions": it now reads `requirements` and `adrs` too.
  - New sections "Runs port" and "SQLite runs".
  - "Data flow": the two reads exist and no use case calls them yet.
- `docs/progress.md`: Current, then Done; rewrite outline item 4 as the remaining piece ("`Plans` read port with `sqlite_plans` (ADR-012) · depends on TASK-023").
- `docs/decisions.md`: rows for the answered questions.
- `CHANGELOG.md`, `README.md`: no change (no command or output is added).

## New dependencies
None.

## Spec gaps
None.

Readings, not gaps:
- "The stored spec set" is what the projections hold (ADR-012: "read from `requirements`, `adrs` and `spec_versions.components`"), not the `SpecImported` payload. For a version imported with a duplicated id the projector kept the first item ("Projection rules"), so the returned set is smaller than the payload's and its hash differs from `spec_versions.hash`. Such a version "can never be approved", and the M2 callers read approved versions only. No criterion covers it.
- Item hashes in `requirements.hash` and `adrs.hash` are not part of `SpecSet` and are not returned.
- "The highest in use" for a run id is the highest number in any `agent_runs` row, finished or not.

## Open questions
1. **Signature and name of the spec set method.** Proposed: `spec_set(version_id: str) -> SpecSet | None`, for a draft or an approved version alike. Alternative: take a `SpecVersionRef`, or offer only `approved_spec_set()`.
2. **A version with no row.** Proposed: return `None`, as `latest_approved()` does when there is nothing. A version imported with an empty spec set returns an empty `SpecSet`, so the two cases stay apart. Alternative: raise `LookupError`.
3. **Order of the returned lists.** Proposed:
   - `requirements` and `adrs` in ascending `id`, compared as strings by SQLite (`ORDER BY id`).
   - `components`, `constrained_by` and `acceptance_criteria` as the stored JSON arrays hold them.
   - For a payload in canonical order with unique ids this equals the payload's `spec`, which AC4 asserts.
4. **Edit to a fixed test.** `tests/unit/test_spec_versions_port.py::test_ac1_spec_versions_is_a_protocol_with_the_three_methods` asserts `public == {"latest_approved", "current_draft", "next_id"}` and fails once the port has a fourth method. Proposed: add `"spec_set"` to that set and change nothing else; the test name keeps "three" (a Later line, as for the two misnamed tests already there). Alternative: change it to `<=` and assert the exact four only in the new file.
5. **Size and split of outline item 4.** Proposed: this task takes the two single-method reads (about 370 lines with tests), and TASK-025 takes `Plans` with `sqlite_plans`. Alternative: `Runs` alone here (about 185 lines) and the spec set as its own task, which makes item 4 three tasks.

### Answers (human, 2026-10-11)
All five proposed answers approved as written: (1) `spec_set(version_id: str) -> SpecSet | None`, for a draft or an approved version alike; (2) a version with no row returns `None`, and a version imported with an empty spec set returns an empty `SpecSet`; (3) `requirements` and `adrs` by `ORDER BY id`, the inner lists as the stored JSON arrays hold them; (4) the one assertion in `test_ac1_spec_versions_is_a_protocol_with_the_three_methods` gains `"spec_set"`, nothing else in that file, and the name is a Later line; (5) this task takes `Runs` and the spec set, and TASK-025 takes `Plans` with `sqlite_plans`.

## Outcome
- Built: `ports/runs.py` (Protocol `Runs`, `next_id() -> str`) and `adapters/sqlite_runs.py` (`SqliteRuns`: own connection, `busy_timeout` 5000, one `SELECT MAX(CAST(substr(id, 5) AS INTEGER)) FROM agent_runs`, `run_{n:04d}`, `close()`, `TYPE_CHECKING` assertion). `SpecVersions` gained `spec_set(version_id) -> SpecSet | None`; `SqliteSpecVersions.spec_set` reads `spec_versions.components` and the version's `requirements` and `adrs` rows (`ORDER BY id`) and validates with `SpecSet.model_validate`, returning `None` when the version has no row. New tests: `tests/unit/test_runs_port.py`, `tests/integration/test_sqlite_runs.py`, `tests/integration/test_sqlite_spec_set.py`.
- Deviations from plan: none. No mechanical fixes to the test-writer's tests.
- Approved test edit: `"spec_set"` added to the asserted set in `tests/unit/test_spec_versions_port.py::test_ac1_spec_versions_is_a_protocol_with_the_three_methods`; the name keeps "three" (a Later line in `docs/progress.md`).
- Follow-up: TASK-025 takes the `Plans` port with `sqlite_plans`.
