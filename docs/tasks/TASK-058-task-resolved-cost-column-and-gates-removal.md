# TASK-058: TaskResolved event type, tasks.cost_usd column, and removal of gates/

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-015 (proposed). Its section "Events and tables (SC-90, SC-91)" covers both triggers this task hits: the new event type `TaskResolved` and the storage change `tasks.cost_usd`. ADR-007 (accepted) covers one frozen payload model per event type, unknown fields forbidden, and closed sets that are only ever widened. ADR-014 (accepted) covers deleting `gates/`. ADR-015 has to be accepted by the human; see Open question 3.
- Spec impact: none
- Spec sections (spec v1.14, from `docs/spec-proposals/phase1-spec-v1.14.md`; decisions SC-90, SC-91, SC-96):
  - "Domain model and storage" › "Event types in Phase 1"
  - "Event payloads": the `TaskResolved` entry, and the closed-sets sentence ("a resolve's `decision`")
  - "Streams and actors": the `TaskResolved` row
  - "Projection rules": "the projector validates each payload against its model before applying it and fails on a mismatch", "One whose `decision` is `abandon` changes no row", and "Each milestone adds the tables ... M4 the column `tasks.cost_usd`"
  - "The tables built in M1 to M4": `CREATE TABLE tasks`
  - "Tech stack and repo layout": the layout block, which has no `gates/` package, and "The path check is a pure function in the domain"
  - "Milestones and definition of done", item 4

## Objective
Add `EventType.TaskResolved`, its payload model and the `tasks.cost_usd` column, and delete `src/openfactory/gates/`, so that the code meets spec v1.14's event list, payload block, `tasks` DDL and layout. After this, `./scripts/apply_spec.sh 1.14` passes CI.

## Scope
In:
- `EventType.TaskResolved` in `src/openfactory/domain/events.py`, placed after `CommitRecorded` and before `ImpactComputed`, in the spec's order.
- In `src/openfactory/domain/payloads.py`:
  - a frozen `TaskResolvedPayload` with `task_id: TaskId` and `decision` (`Literal["retry", "abandon"]`), `extra="forbid"`, every field required;
  - an entry for it in `PAYLOAD_MODELS`, making eleven entries. `ImpactComputed` still has none.
- `cost_usd REAL NOT NULL DEFAULT 0` as the last column of `CREATE TABLE IF NOT EXISTS tasks` in `src/openfactory/adapters/sqlite_projector.py`. No rule writes the column.
- Deleting the `src/openfactory/gates/` directory: `__init__.py` and the untracked `__pycache__/`.
- New tests, and the three fixed-test edits listed in Open question 1.

Out:
- The projector rule where `TaskResolved` `retry` resets `attempt` and `cost_usd` to 0 (the `resolve` task).
- The projector rule where `AgentRunFinished` adds `cost_usd` to its task (the cost-limit task).
- The `resolve` command and use case, and any code that records `TaskResolved`.
- Adding the column to a database that already exists. `CREATE TABLE IF NOT EXISTS` leaves an old `tasks` table as it is. This goes to Later for the cost-limit task.
- Any change to `app/`, `ports/` or `cli.py`. Any edit to `docs/spec/`.

## Acceptance criteria
- [x] AC1 ("Event types in Phase 1"):
  - `EventType` has exactly twelve values, the eleven it has now plus `TaskResolved`. A new test asserts the exact set.
  - With the v1.14 spec in place, `test_event_types_match_the_spec_list` passes.
- [x] AC2 ("Event payloads", the `TaskResolved` entry: `task_id: "AUTH-002"`, `decision: "retry" | "abandon"`; "the models forbid unknown fields. Every field of a payload model is required"):
  - `TaskResolvedPayload` validates `{task_id: "AUTH-002", decision: "retry"}` and the same dict with `"abandon"`. `model_dump(mode="json")` returns each dict exactly.
  - Leaving out either field raises `ValidationError`. So does an unknown key, `decision: "skip"`, or `task_id: "auth-2"`.
  - The model is frozen.
  - `PAYLOAD_MODELS` has exactly eleven keys, and `PAYLOAD_MODELS[TaskResolved] is TaskResolvedPayload`. `ImpactComputed` has no entry.
  - With v1.14 in place, `test_payload_fields_match_the_spec_block[TaskResolved]` passes and is not skipped.
- [x] AC3 (the closed-sets sentence: "a resolve's `decision` ... may be widened but never renamed or narrowed"): a table of two stored payloads, written as literal dicts in the test (one `retry`, one `abandon`), validates against `PAYLOAD_MODELS[EventType.TaskResolved]`.
- [x] AC4 ("Streams and actors", the `TaskResolved` row; "Projection rules": validates and "fails on a mismatch", and "One whose `decision` is `abandon` changes no row"):
  - The dumped payload is accepted by `Event.new` with stream `task:AUTH-002` and actor `human`.
  - It round-trips through `model_dump_json()` and `model_validate_json()`, and then validates to the original payload.
  - `SqliteProjector.apply` raises `ValidationError` on a stored `TaskResolved` whose payload the model rejects, and writes nothing.
  - An `abandon` applied after a `PlanCreated` leaves every projection table unchanged.
  - No test of `retry`: the `resolve` task adds that rule.
- [x] AC5 ("The tables built in M1 to M4", `CREATE TABLE tasks`; "Each milestone adds ... M4 the column `tasks.cost_usd`"):
  - After `create_tables`, the last column of `tasks` is `cost_usd`, `REAL`, `NOT NULL`, default `0`.
  - The rows a `PlanCreated` inserts have `cost_usd` 0.
  - The existing rebuild-identity tests still pass.
  - With v1.14 in place, `test_projection_table_matches_the_spec_create_table[tasks]` passes.
- [x] AC6 ("Tech stack and repo layout": the layout has no `gates/` package; ADR-014: "The package `gates/` is removed from the layout"; SC-96):
  - `src/openfactory/gates/` does not exist, and `importlib.util.find_spec("openfactory.gates")` is `None`.
  - `test_smoke.py` no longer lists `gates` (Open question 1c).

## Plan
1. Stay on `spec/v1.14`. This is the branch-rule exception for this task only (Open question 5).
2. Write the human's answers to Open questions 1 to 5 here and as rows in `docs/decisions.md`. One of those rows records the branch exception and the temporary red conformance tests.
3. Write the failing tests:
   - new `tests/unit/test_m4_payloads.py` for AC1 to AC4 and the exact sets of `EventType` and `PAYLOAD_MODELS`;
   - new `tests/integration/test_sqlite_projector_m4.py` for the projector parts of AC4 and for AC5;
   - one test for AC6 in `tests/unit/test_smoke.py`.
4. Make the approved fixed-test edits (Open question 1) and nothing else in those files.
5. Code changes: the `EventType` member; `TaskResolvedPayload` and its `PAYLOAD_MODELS` entry; the DDL column; then delete `src/openfactory/gates/`.
6. Verify (Open question 2):
   - (a) In the repo, with v1.13 still in `docs/spec/`, run `uv run pytest -q`. Exactly two tests should fail: `test_event_types_match_the_spec_list` and `test_projection_table_matches_the_spec_create_table[tasks]`. Write both names in the Outcome. Ruff, pyright and `check_docs` must be clean.
   - (b) In a throwaway copy of the tree under the scratchpad, outside the repo, put the proposal over that copy's `docs/spec/phase1-spec.md` and run `uv run pytest -q`. Everything should pass, the three conformance tests included. Then delete the copy. The repo's `docs/spec/` is never touched.
   - (c) The authoritative check is the human's `./scripts/apply_spec.sh 1.14`, which runs `ci_local.sh` with the spec in place.
7. Update the living docs and the Outcome. Commit `feat(domain): add TaskResolved and tasks.cost_usd for spec v1.14` with the trailers `Task: TASK-058` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/domain/events.py` (1 line)
- `src/openfactory/domain/payloads.py` (about 12 lines)
- `src/openfactory/adapters/sqlite_projector.py` (1 to 2 lines)
- `src/openfactory/gates/__init__.py` (deleted, with its directory)
- `tests/unit/test_m4_payloads.py` (new, about 110 lines)
- `tests/integration/test_sqlite_projector_m4.py` (new, about 70 lines)
- `tests/unit/test_smoke.py`, `tests/unit/test_domain_events.py` and `tests/unit/test_m3_payloads.py` (the approved edits)
- `docs/architecture.md`:
  - "11 Phase 1 event type names" becomes 12;
  - `PAYLOAD_MODELS` has eleven entries, and `TaskResolvedPayload` gets a line;
  - the SQLite projector paragraph gets the `cost_usd` column, with no rule writing it, and `TaskResolved` validated with nothing written.
- `README.md`: delete the layout line `gates/      quality gates` (line 101).
- `docs/progress.md`: Current becomes M4 / TASK-058, the M3 blocker is kept, add the Done line, remove the Later line about `gates/__init__.py`, and add the Later lines below.
- `docs/decisions.md`: rows for the answers.
- this record.

Not expected to change: `app/`, `ports/`, `cli.py`, the other adapters, `tests/unit/test_spec_conformance.py` (it needs no edit), `docs/spec/`, `docs/adr/`, `pyproject.toml`.

Expected size: about 220 lines including tests.

## Later lines to add at close
- The `tasks.cost_usd` column exists, but no rule writes it. The `TaskResolved` `retry` reset and the `AgentRunFinished` cost sum belong to the `resolve` and cost-limit tasks. (TASK-058)
- A database created before TASK-058 has no `tasks.cost_usd`, because `create_tables` uses `IF NOT EXISTS` and the recorder's catch-up does not rebuild. The cost-limit task must handle it, for example with a rebuild. The spec says "A projection added later is filled by a rebuild" but not what triggers one. (TASK-058, planner)
- If the human keeps the names under Open question 1 (a) and (b): `test_ac01_event_type_has_exactly_the_eleven_phase1_values` and `test_ac1_payload_models_has_exactly_the_ten_events_without_impact_computed` keep names their assertions no longer match. (TASK-058)

## Spec gaps
None. Spec impact is "none": v1.14 settles everything this task needs. The existing-database question above is for the cost-limit task, not this one.

## Open questions
1. **Fixed tests this change forces to edit.** TASK-040 is the precedent: an exact-set test becomes a presence check with its name kept, and the new exact set moves to the new task's test file. Proposed edits:
   - (a) `tests/unit/test_domain_events.py::test_ac01_event_type_has_exactly_the_eleven_phase1_values` (lines 84 to 86). It asserts the sorted set equals `EVENT_TYPE_NAMES` and that `len == 11`, so it fails with twelve. Change it to assert that the eleven names are present. The exact twelve go in `test_m4_payloads.py`, and `test_spec_conformance.py` already ties the set to the spec. The name is kept, with a Later line. Alternative: add `"TaskResolved"` to `EVENT_TYPE_NAMES`, change 11 to 12, and rename the test.
   - (b) `tests/unit/test_m3_payloads.py::test_ac1_payload_models_has_exactly_the_ten_events_without_impact_computed` (line 57). It asserts `set(PAYLOAD_MODELS) == {ten}`. Change it to assert those ten are present, keeping the `ImpactComputed not in` assertion and the two identity assertions. The name is kept. The exact eleven go in `test_m4_payloads.py`.
   - (c) `tests/unit/test_smoke.py::test_layer_packages_import` (line 14). Remove `"gates"` from the parameter list, because the package is deleted by decision. AC6 adds the test that it is absent.

   No other test asserts an exact event or payload set, or the columns of `tasks`. Checked: `test_payloads.py` and `test_m2_payloads.py` are already presence checks; the `tasks` queries in the close and projector tests name their columns; `test_m1_close.py`'s `len(objs) == 11` counts events in a log, not event types.
2. **How to verify green.** The code is judged against v1.14, but v1.13 stays in `docs/spec/` during the task. Proposed: steps 6 (a), (b) and (c) of the Plan. Step (b) copies the proposal over the spec file of a throwaway copy outside the repo and never commits it; the human approves this explicitly, since it is a hand copy of a spec file even though it is outside the repo. Alternative: skip (b) and rely only on (a) plus `apply_spec.sh`. Either way, the `spec/v1.14` branch is red on two conformance tests between this commit and the apply. The pre-push hook would fail, which is harmless, since only `apply_spec.sh` pushes, after copying the spec.
3. **ADR-015 is still proposed.** The task writes code for its decision on events and tables, and `apply_spec.sh` warns about proposed ADRs. Proposed: the human accepts ADR-015 before the commit, or at the latest before running `apply_spec.sh`.
4. **Name of the `decision` type.** Proposed: `ResolveDecision = Literal["retry", "abandon"]` in `payloads.py`, next to `RunRole`, `RunExit` and `GateName`. Alternative: keep it inline in the field.
5. **The exception, as a decisions row.** Proposed text: "TASK-058 is committed on `spec/v1.14`, not on a `task/` branch, for this task only. Between that commit and `apply_spec.sh 1.14`, two conformance tests fail against v1.13 by design. `apply_spec.sh` then squash-merges code and spec as one `spec: v1.14` PR." Also: Current in `progress.md` moves to M4 while M3 stays unticked until the human's real `run` (existing blocker).

## Answers (2026-10-15, the human, following the advisor)
1. As proposed: (a) and (b) become presence checks with their names kept, the exact sets go to `tests/unit/test_m4_payloads.py`; (c) `"gates"` leaves the smoke list. A Later line notes that the edited event test duplicates `test_ac01_event_type_contains_value`.
2. As proposed, with the copy made without `.venv` or `.git` (`uv sync --locked`) and the full `./scripts/ci_local.sh` run in it.
3. The human accepts ADR-015 before the commit, or at the latest before `apply_spec.sh`. Its Consequences sentence on the conformance tests was updated to say code and spec land together.
4. `ResolveDecision = Literal["retry", "abandon"]` in `payloads.py`.
5. The decisions row, amended: it supersedes the "Current stays at M3" clause of the 2026-10-14 TASK-057 row (the M3 blocker stays), and the human checks or adds the `Task: TASK-058` / `Milestone: M4` trailers in the squash commit on main.

## Outcome
- Built: `EventType.TaskResolved` (after `CommitRecorded`); `ResolveDecision` and frozen `TaskResolvedPayload` (`task_id`, `decision`) in `domain/payloads.py`, registered in `PAYLOAD_MODELS` (eleven entries, `ImpactComputed` still none); `cost_usd REAL NOT NULL DEFAULT 0` as the last column of the projector's `tasks` table, written by no rule; `src/openfactory/gates/` deleted (`__init__.py` with `git rm`, the untracked `__pycache__/` by hand). No change to the projector's `apply`: it validates `TaskResolved` through `PAYLOAD_MODELS` and writes nothing.
- Tests: 21 new tests from the test-writer (`tests/unit/test_m4_payloads.py`, `tests/integration/test_sqlite_projector_m4.py`, `test_gates_package_is_removed` in `tests/unit/test_smoke.py`) failed first and pass now. The three approved fixed-test edits (Answers 1) are as planned.
- Deviation: two more fixed tests broke on the added column and were fixed as mechanical errors, with the assertion's intent unchanged (CLAUDE.md exception; the reviewer checks them):
  - `tests/integration/test_sqlite_projector_m2.py::test_ac6_rebuild_drops_a_task_row_no_event_produced`: the positional `INSERT INTO tasks VALUES (...)` had six values for seven columns; a seventh value `0` was added.
  - `tests/integration/test_sqlite_projector_m3.py::test_ac4_attempt_counts_each_change_to_running`: the whole-row tuple comparison got `*before["AUTH-001"][6:]` appended, so `cost_usd` must be unchanged as every other column but `state` and `attempt`.
  The planner's check had covered queries that name their columns, not these two.
- Verification (Answers 2): (a) the repo suite under v1.13 gives exactly two failures, `test_event_types_match_the_spec_list` and `test_projection_table_matches_the_spec_create_table[tasks]`, with 1313 passed; ruff, pyright and check_docs clean. (b) In a throwaway copy under the scratchpad (no `.venv`, `uv sync --locked`) with the proposal over its `docs/spec/phase1-spec.md`, the full `./scripts/ci_local.sh` passed; the copy was deleted. (c) The human's `./scripts/apply_spec.sh 1.14` is the authoritative check.
- For the human: accept ADR-015 before `apply_spec.sh`; check or add the `Task: TASK-058` / `Milestone: M4` trailers in the squash commit on main.
