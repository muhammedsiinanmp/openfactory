# TASK-094: `Traces` impact traversal read

- Milestone: M6
- Status: done
- Tests: acceptance
- ADR: ADR-019 (accepted). Its "Ports" bullet covers it: "No new port: `Traces` gains the traversal … (SC-168)". The task adds one method to the existing `Traces` port and its `SqliteTraces` adapter, plus one frozen domain result model. It adds no port, adapter, event type, payload change, table, dependency or convention. The method's shape is a row in `docs/decisions.md`.
- Spec impact: none (two literal readings are written into AC2 and AC4; see "Readings to confirm")
- Spec sections (spec v1.18; SC-162, SC-168):
  - "Spec diff and impact analysis" › "Step 3: traversal (deterministic)": "The seeds are the requirements whose change is `removed` or `deprecated`, and the `modified` ones classified `behavioral` or `replacement`. Walking `trace_links` with a recursive CTE: the impacted tasks are the tasks of the approved plan, not `invalidated` or `abandoned`, with a requirement → task `contract` link from a seed; the downstream tasks are the other tasks of the approved plan, not `invalidated` or `abandoned`, that depend on an impacted or downstream task through `depends_on`, transitively; they are invalidated too; the files are the commit → file links of the commits of the impacted and downstream tasks (task → run → commit); the tests are each test tagged with a seed and each other test whose file is one of those files, as for `trace`."
  - "Domain model and storage" › "Ids", M6 paragraph: "`Traces` also gives the traversal of Step 3 (see Spec diff and impact analysis) from a set of seed requirements over the tasks of the approved plan."
  - "Domain model and storage" › "Event payloads", `ImpactComputed`: `tasks` "the impacted tasks, sorted as strings", `downstream` "the downstream tasks, sorted as strings", `files` "sorted as strings", `tests` "sorted as strings".
  - "Traceability": the link table (requirement → task and task → task `contract`; task → run and run → commit `trailer`; commit → file `diff`; test → requirement and test → file `test_tag`).

## Outline item
M6 outline item 2. Item 3 (the `impact` use case and command) is the only caller. It takes the seeds from `SpecDiff` plus the accepted `ChangeClass` entries, and the plan id from `Plans.approved()`.

## Objective
Add `Traces.impact_traversal(plan_id, seeds)` and its `SqliteTraces` implementation. It returns the impacted tasks, downstream tasks, files and tests of Step 3, each sorted as strings, for direct use as the `tasks`, `downstream`, `files` and `tests` of `ImpactComputed`.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `domain/traces.py`: a new frozen `ImpactTraversal` (`extra="forbid"`) with `tasks: list[TaskId]`, `downstream: list[TaskId]`, `files: list[str]` and `tests: list[str]`.
- `ports/traces.py`: `impact_traversal(self, plan_id: str, seeds: Collection[str]) -> ImpactTraversal`, with a docstring stating Step 3 and the order.
- `adapters/sqlite_traces.py`: the implementation.
  - `SELECT`s only, over `tasks` and `trace_links`.
  - Downstream tasks come from a `WITH RECURSIVE` CTE over the task → task `contract` links (the spec's "recursive CTE").
  - Order is set by `ORDER BY`, as in TASK-081, TASK-083 and TASK-085.
  - Reuse `_COMMIT_TASKS` and `_DIFF` where they fit.
- Tests added to `tests/unit/test_traces_port.py`, `tests/unit/test_traces_models.py` and `tests/integration/test_sqlite_traces.py`. The integration tests build the projections by recording events through `SqliteEventRecorder`, as the existing tests there do.

Out:
- Computing the seeds from the diff and the classification, the `impact` use case, `ImpactComputed` recording, the command and its output (item 3).
- The projector's supersede-and-move rule (item 4). This read filters on `tasks.plan_id` only, whatever the move does later.
- Any refusal, such as no approved plan. The caller checks that before calling.

## Acceptance criteria
- [ ] **AC1** ("Step 3": "the impacted tasks are the tasks of the approved plan, not `invalidated` or `abandoned`, with a requirement → task `contract` link from a seed"):
  - `tasks` holds every task whose `tasks.plan_id` is the given plan, whose state is neither `invalidated` nor `abandoned`, and which has a requirement → task `contract` link from some seed.
  - A task linked to a seed but in another plan, `invalidated` or `abandoned` is not in `tasks`.
  - A task linked only to a non-seed requirement is not in `tasks`.
- [ ] **AC2** ("Step 3": "the downstream tasks are the other tasks of the approved plan, not `invalidated` or `abandoned`, that depend on an impacted or downstream task through `depends_on`, transitively"):
  - `downstream` holds each live task of the plan that is not impacted and reaches an impacted task through one or more task → task `contract` links. Every task along that path must itself be impacted or downstream.
  - A chain A ← B ← C gives B and C.
  - A task that depends only on an untouched task is not downstream.
  - A task that reaches an impacted task only through an `invalidated` or `abandoned` task is not downstream.
  - An `invalidated` or `abandoned` task that depends on an impacted task is not downstream.
  - No task is in both `tasks` and `downstream`.
- [ ] **AC3** ("Step 3": "the files are the commit → file links of the commits of the impacted and downstream tasks (task → run → commit)"):
  - `files` holds each path with a commit → file `diff` link from a commit reached by task → run → commit `trailer` links from an impacted or downstream task, listed once.
  - Files changed only by commits of untouched tasks are absent.
- [ ] **AC4** ("Step 3": "the tests are each test tagged with a seed and each other test whose file is one of those files, as for `trace`"):
  - `tests` holds the node id of each test with a test → requirement `test_tag` link to a seed, and of each test whose test → file `test_tag` link points at a path in `files`, each node id once.
  - A test tagged with a seed is included even when no task is impacted.
- [ ] **AC5** ("Event payloads", `ImpactComputed`: "sorted as strings"):
  - The four lists are each sorted as strings, with no duplicates.
  - With an empty `seeds` all four are empty.
  - A seed with no links adds nothing.
- [ ] **AC6** ("Domain model and storage", M6 paragraph: "`Traces` also gives the traversal"; ADR-019 "No new port"; CLAUDE.md architecture rules):
  - `Traces` has `impact_traversal` and keeps its existing three methods.
  - `SqliteTraces` still ends with its `TYPE_CHECKING` assertion and runs only `SELECT` statements; a test checks that no projection row changes.
  - `domain/traces.py` imports no outer layer.
  - The existing `Traces` tests pass without edits.

## Architecture rules that apply
- Ports stay read-only Protocols. `domain/traces.py` stays pure.
- The adapter reads projections only and records no events.
- The adapter does not touch `task_deps`. The spec says the traversal walks `trace_links`.

## Plan
1. Create branch `task/TASK-094-traces-impact-traversal` from an up-to-date main.
2. Record the human's answers to the design choices in this record.
3. Test-writer: write failing tests `test_task094_ac<N>_...`.
   - In `tests/integration/test_sqlite_traces.py`, build a fixture plan with:
     - REQ-AUTH-001 linked to AUTH-002 and AUTH-003;
     - AUTH-005 depending on AUTH-003, and AUTH-006 depending on AUTH-005;
     - AUTH-004 untouched, plus one `invalidated` and one `abandoned` task linked to the seed;
     - commits with files for the impacted, downstream and untouched tasks;
     - a `TestsCollected` with tagged, file-matched and unrelated tests;
     - a second plan whose task is linked to the seed.
   - Add the model test to `test_traces_models.py` and the method-presence test to `test_traces_port.py`.
4. Implement `ImpactTraversal`, the port method and `SqliteTraces.impact_traversal`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`: the "Traces port" section gains the method;
   - `docs/progress.md`: Current, a Done line, outline item 2 marked done;
   - `docs/decisions.md`: one row per answered design choice;
   - this record's Outcome.
7. Commit `feat(adapters): add the Traces impact traversal` with trailers `Task: TASK-094` and `Milestone: M6`. Do not push.

## Files expected to change
- `src/openfactory/domain/traces.py` (about +12)
- `src/openfactory/ports/traces.py` (about +15)
- `src/openfactory/adapters/sqlite_traces.py` (about +60)
- `tests/integration/test_sqlite_traces.py` (about +170)
- `tests/unit/test_traces_port.py`, `tests/unit/test_traces_models.py` (about +25)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, this record

Not expected to change: `app/`, `cli.py`, `sqlite_projector.py`, other ports and adapters, `docs/spec/`, `docs/adr/`.

## Design choices to confirm at planning
1. **Signature.**
   - Proposed: `impact_traversal(plan_id: str, seeds: Collection[str]) -> ImpactTraversal`. The caller passes `Plans.approved().id`, as `untested_requirements` takes the version id from its caller (TASK-081 decision). The adapter then has no "no approved plan" case.
   - Alternative: `impact_traversal(seeds)` reads the approved plan itself, and returns `None` or raises when there is none.
2. **Result shape.**
   - Proposed: one frozen `ImpactTraversal` with the four lists, named as the `ImpactComputed` fields.
   - Alternative: a tuple of four lists, or four separate port methods.

## Readings to confirm
These follow the spec text literally. They are written into the ACs, not assumed.
- **AC2, the walk only passes through impacted or downstream tasks.** "depend on an impacted or downstream task … transitively" means a task reached only through an `invalidated` or `abandoned` task is not downstream.
- **AC3/AC4, commits of excluded tasks contribute no files.** Commits of `invalidated` or `abandoned` tasks linked to a seed add nothing to `files`, because those tasks are not impacted. Tests of the files they changed are not in `tests` unless one of those files is also in `files` (changed by an impacted or downstream task's commit) or the test is tagged with a seed.

## Open questions
None beyond the two design choices.

## Answers (human, 2026-10-24)
1. Signature: approved as proposed, `impact_traversal(plan_id: str, seeds: Collection[str]) -> ImpactTraversal`.
2. Result shape: approved as proposed, one frozen `ImpactTraversal`; element types match `ImpactComputedPayload`.
3. AC2 reading: approved, the walk passes only through impacted or downstream tasks.
4. AC3/AC4 reading: approved, with the advisor's rewording above.

## Spec gaps
None found for this task. The existing Later lines on Step 1 and Step 2 (a requirement deprecated in both versions; how the seeds are formed) concern item 3. They do not touch a read that takes its seeds as given.

## Outcome
Added `ImpactTraversal` (`domain/traces.py`), `Traces.impact_traversal(plan_id, seeds)` (`ports/traces.py`) and its `SqliteTraces` implementation. One recursive CTE (`_impact_cte` in `sqlite_traces.py`) gives live, impacted, reached and files; downstream is reached EXCEPT impacted. SELECTs only; `task_deps` is not read. Tests added in `tests/integration/test_sqlite_traces.py`, `tests/unit/test_traces_models.py` and `tests/unit/test_traces_port.py`.

Test edits: the implementer made none. The test-writer added an optional `reason` argument to its own `state` helper before the tests were handed over.

Docs: `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md` (four rows: signature, result shape, the two approved readings). No ADR needed (ADR-019 covers it).
