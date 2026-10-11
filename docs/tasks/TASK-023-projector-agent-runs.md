# TASK-023: Projector for the agent run events (`agent_runs`)

- Milestone: M2
- Status: done
- Tests: acceptance
- ADR: ADR-009 (accepted). It covers the projector's interface, validation before the first write, the caller owning the transaction, and "replays facts and does not enforce business rules". ADR-012 (accepted) says "The `agent_runs` table and the types of `AgentRunFinished` are fixed by spec v1.10 (SC-26, SC-27). They follow the rules of ADR-007 and need no decision here". ADR-010 (accepted) covers the recorder calling `create_tables` and `rebuild`. No new port, adapter, dependency, event type or payload change, and no storage shape the spec does not give. Column text forms and the no-op readings are rows in `docs/decisions.md` (Open questions 1 to 3).
- Spec impact: none
- Spec sections (spec v1.10): "Domain model and storage" ("Projections" with its `CREATE TABLE` block, "Projection rules", "Event payloads"); "Metrics" (the "Stored per agent run" bullet); "Milestones and definition of done" (milestone 2: "the plan, task and agent run projections")

## Objective
Make `SqliteProjector` create the `agent_runs` table and apply `AgentRunStarted` and `AgentRunFinished` to it, so that every agent run has one row and a rebuild from the event log gives identical rows.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings.

## Scope
In:
- `src/openfactory/adapters/sqlite_projector.py`:
  - DDL for `agent_runs` as in the spec block, added to `create_tables` and to the tables `rebuild` drops (seven tables).
  - `AgentRunStarted`: insert one row with `id`, `task_id`, `role`, `runtime` and `context_hash` from the payload and `started_at` from the event's `created_at`; the seven other columns are null.
  - `AgentRunFinished`: set `model`, `exit`, `tokens_in`, `tokens_out`, `cost_usd` and `duration_s` from the payload and `ended_at` from the event's `created_at`, on the row whose `id` is the payload's `run_id`.
- A new test file `tests/integration/test_sqlite_projector_runs.py`, which also asserts the `agent_runs` table is present (the skip rule in the conformance test would hide a dropped table).
- The `agent_runs` case of `tests/unit/test_spec_conformance.py` stops skipping, with no edit to that file.

Out (not this task):
- The `Runs` and `Plans` read ports and their adapters, and the stored spec set on `SpecVersions` (outline item 4).
- Every use case and command (items 9 to 12); nothing records the run events yet.
- Any change to `sqlite_recorder.py`: it already calls `create_tables`, `apply` and `rebuild`.
- Any change to `domain/payloads.py`.
- `AgentRunFinished.error`: `agent_runs` has no column for it, so it is not projected. It stays in the event log.
- Checks of event sequences (ADR-009): an `AgentRunFinished` for a run with no row, a second `AgentRunFinished` for one run, a `task_id` that is not in `tasks`, a link between `exit` and `error`.
- Two `AgentRunStarted` with one `run_id`: plain `INSERT`, no `OR IGNORE`, no test. Run ids are chosen by the use case from the `Runs` port ("Ids"), and ADR-012 notes that a retried call reads its id after the first `AgentRunStarted` is committed.
- Filling `agent_runs` in a database that already holds run events below `last_seq`. The spec says "A projection added later is filled by a rebuild"; no use case records these events yet.
- Every Later line in `docs/progress.md`. Checked for this piece: the TASK-015 line (`INSERT OR IGNORE` hiding a `NOT NULL` violation) does not apply, because the insert is a plain `INSERT` and the one nullable field written by it, `task_id`, maps to a nullable column. The `GateEvaluated` line, the two misnamed tests and the payload conformance parametrisation are untouched.

## Acceptance criteria
"DDL block" is the `CREATE TABLE` block under "Projections". A snapshot is every row of `agent_runs` in `id` order. Payloads are built through `AgentRunStartedPayload` and `AgentRunFinishedPayload`; events are stored (`store.append`) before they are applied, with a fixed `created_at`.

- [x] AC1 ("Projections": the DDL block, and "Projection tables have no foreign key and no `CHECK` constraints"; "Projection rules": "Each milestone adds the tables for the events it introduces: ... M2 `plans`, `tasks`, `task_deps`, `agent_runs`"):
  - After `create_tables()`, `agent_runs` exists next to `spec_versions`, `requirements`, `adrs`, `plans`, `tasks` and `task_deps`. The test asserts the seven names and cannot skip.
  - The `agent_runs` case of `test_projection_table_matches_the_spec_create_table` in `tests/unit/test_spec_conformance.py` passes and is not skipped; `uv run pytest -q` reports no skipped test.
  - `agent_runs` has no foreign key, and no table's SQL holds `CHECK`.
  - Calling `create_tables()` again changes no row.
- [x] AC2 ("Projections": "`agent_runs` | id, task_id (null for a run that belongs to no task), role, runtime, model, started_at, ended_at, exit, tokens_in, tokens_out, cost_usd, duration_s, context_hash", and the DDL comments "null until AgentRunFinished" and "ISO 8601 UTC, from AgentRunStarted.created_at"; "Metrics": "A planner or classifier call is recorded as an agent run with its role and no task"):
  - Applying an `AgentRunStarted` for `run_0001` with `task_id` null, role `planner`, runtime `claude-code` and a context hash leaves exactly one row: `id` `run_0001`, `task_id` null, `role` `planner`, `runtime` `claude-code`, `started_at` equal to the event's `created_at` in ISO 8601 with the offset `+00:00`, `context_hash` as given, and `model`, `ended_at`, `exit`, `tokens_in`, `tokens_out`, `cost_usd` and `duration_s` all null.
  - An `AgentRunStarted` for `run_0002` with `task_id` `AUTH-002` and role `implementer` adds a second row holding that `task_id` and role, and leaves the first row unchanged.
- [x] AC3 ("Event payloads": the `AgentRunFinished` block; "Projections": the DDL comments "null until AgentRunFinished, or when the runtime reported none" and "null until AgentRunFinished; from its created_at"; "Projection rules": "`approved_at`, `started_at` and `ended_at` come from the events' `created_at`"): with `run_0001` and `run_0002` started,
  - an `AgentRunFinished` for `run_0001` with `exit` `ok`, a model name, `tokens_in`, `tokens_out`, `cost_usd` and `duration_s` sets those six columns to the payload's values and `ended_at` to that event's `created_at`; `id`, `task_id`, `role`, `runtime`, `started_at` and `context_hash` are unchanged, and the `run_0002` row is unchanged.
  - an `AgentRunFinished` for `run_0002` with `exit` `error`, an `error` text, and `model`, `tokens_in`, `tokens_out` and `cost_usd` null sets `exit` to `error`, `duration_s` and `ended_at`, and leaves the four nullable columns null.
- [x] AC4 ("Event payloads": "the projector validates each payload against its model before applying it and fails on a mismatch"): with `run_0001` started,
  - an `AgentRunStarted` for `run_0002` whose payload the model rejects (role `tester`) raises `pydantic.ValidationError` and the snapshot is unchanged.
  - an `AgentRunFinished` for `run_0001` whose payload the model rejects (no `error` key) raises `pydantic.ValidationError` and the snapshot is unchanged: the row's `exit` and `ended_at` are still null.
- [x] AC5 ("Projection rules": "Rebuilding means emptying the projection tables (dropping and recreating them counts), replaying all events in `seq` order" and "A rebuild is identical when, for every projection table, the rows read in primary-key order are equal before and after"; "Metrics": "A retried call is a second run, so a rejected call keeps its cost"): for a log holding started and finished for `run_0001` (planner, `exit` `error`, with a cost), started and finished for `run_0002` (planner, `exit` `ok`) and started only for `run_0003` (implementer, `AUTH-002`):
  - `agent_runs` holds three rows; `run_0001` keeps its `cost_usd` and `exit`, and `run_0003` has `ended_at` and `exit` null.
  - `SqliteProjector.rebuild(store.read())` leaves the snapshot equal to the one before.
  - A row planted in `agent_runs` that no event produced is gone after the rebuild.
- [x] AC6 ("Projection rules": "Use cases record every event through the `EventRecorder` port ... Its adapter appends the event and applies it to the projections in one transaction"; "A projection added later is filled by a rebuild"): the same five events recorded through `SqliteEventRecorder.record` give the same snapshot on a second connection, and `SqliteEventRecorder.rebuild()` leaves it equal.

## Architecture rules that apply
- The projector imports only from `openfactory.domain` and the standard library, has no port and no `TYPE_CHECKING` assertion, and never commits (ADR-009).
- Validate before the first write (AC4).
- Only data in the event: no clock, no generated ids. `started_at` and `ended_at` are the event's `created_at`, never the time of the apply.
- "Never write projections directly" binds production code; the planted row in AC5 is test-side damage to a temporary database (TASK-019 and TASK-022 precedent).
- Tests from the test-writer are fixed. This task expects no edit to an existing test.

## Plan
1. Create branch `task/TASK-023-projector-agent-runs` from an up-to-date main.
2. Get the human's answers to Open questions 1 to 4; record them here and as rows in `docs/decisions.md`.
3. Write failing tests in `tests/integration/test_sqlite_projector_runs.py` for AC1 to AC6, in the style of `tests/integration/test_sqlite_projector_m2.py` (`conn`, `projector` and `store` fixtures, a `snapshot` helper, event builders that go through the payload models and take a `created_at`). Confirm the `agent_runs` conformance case still skips at this point.
4. Extend `src/openfactory/adapters/sqlite_projector.py`: one DDL statement, `agent_runs` added to `_TABLES`, two branches in `apply` (an `INSERT` and an `UPDATE ... WHERE id = ?`), the two payload imports, and the module docstring naming `agent_runs`.
5. Run `uv run pytest -q` (expect no skipped test), `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until green.
6. Update the living docs and the Outcome. Commit `feat(adapters): project the agent run events into agent_runs` with trailers `Task: TASK-023` and `Milestone: M2`.

## Files expected to change
- `src/openfactory/adapters/sqlite_projector.py` (about 50 lines added)
- `tests/integration/test_sqlite_projector_runs.py` (new, about 200 lines)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-023-projector-agent-runs.md`

Not expected to change: `sqlite_recorder.py`, `domain/payloads.py` and every other module under `src/`; `pyproject.toml`; `docs/adr/`; `docs/spec/`; every existing test file. `tests/unit/test_spec_conformance.py` already lists `agent_runs` in `M2_TABLES`. `tests/integration/test_sqlite_projector.py`, `test_sqlite_projector_m2.py`, `test_sqlite_recorder.py` and `test_cli_init.py` assert their table sets with `<=` or by name, and none asserts that a run event writes nothing.

## Living docs to update
- `docs/architecture.md`: "SQLite projector" (seven tables, the two run events, `error` not projected, what is not checked, `rebuild` drops seven; the sentence "`agent_runs` is not yet built" and the "until `agent_runs` exists, TASK-023" clause go), and "Data flow" (the projection list).
- `docs/progress.md`: Current, then Done; remove outline item 3.
- `docs/decisions.md`: rows for the answered questions.
- `CHANGELOG.md`, `README.md`: no change (no command or output is added).

## New dependencies
None.

## Spec gaps
None.

Readings, not gaps:
- `AgentRunFinished.error` has no column in the DDL block or the "Projections" row, so it is not projected. "Each payload carries everything its projections hold" allows a payload to hold more than its projection.
- `agent_runs.exit`, `role` and `runtime` are the payload's strings as they are; `duration_s` and `cost_usd` are stored as `REAL`.
- A repeated `run_id` in two `AgentRunStarted` cannot come from a use case: "Ids" has the use case choose the run id from the projections through `Runs`, and ADR-012 covers the retried call. So no keep-first rule is needed, unlike `SpecImported`.

## Open questions
Answered by the human on 2026-10-11: the proposed answer stands for all four (advisor: 4 AGREE). For question 3 the reason is corrected: the recorder names the event's `seq` only during catch-up; `record` and `rebuild` raise the `sqlite3.IntegrityError` unchanged, and `record` stores nothing.

1. **Form of `started_at` and `ended_at`.** The DDL says "ISO 8601 UTC, from AgentRunStarted.created_at". Proposed: `event.created_at.isoformat()`, the form the projector already writes for `approved_at` and the one "CLI commands" ("Output") names ("in ISO 8601 with the offset `+00:00`, the same form as `approved_at`"). A decisions row extending the TASK-009 row.
2. **`AgentRunFinished` for a run with no row.** Proposed: the `UPDATE` changes no row and raises nothing, as a `TaskStateChanged` for an unknown task does (TASK-022 decision; ADR-009, "does not enforce business rules"). No test. Alternative: none the spec supports; raising would be a sequence check ADR-009 rejects.
3. **A second `AgentRunStarted` with a stored `run_id`.** Proposed: plain `INSERT`, no `OR IGNORE`, no test; it would end in `sqlite3.IntegrityError`, which the recorder names with the event's `seq` only during catch-up; `record` and `rebuild` raise it unchanged, and `record` stores nothing (corrected from the planner's wording, which said the recorder already reports the `seq`). See Readings.
4. **Where the presence assertion lives.** The outline asks for "a test [that] asserts the `agent_runs` table is present". Proposed: in the new integration file (AC1), asserting all seven names with `<=`, so `tests/unit/test_spec_conformance.py` needs no edit. Alternative: a non-skipping test in the conformance file that every table of `M1_TABLES + M2_TABLES` exists, which guards all seven against the skip rule in the file that owns the rule, at the price of an edit to that file.

## Outcome
**Built.** `SqliteProjector` in `src/openfactory/adapters/sqlite_projector.py` creates `agent_runs` (spec v1.10 DDL) and `rebuild` drops seven tables. `AgentRunStarted` inserts a row with a plain `INSERT`: `id`, `task_id`, `role`, `runtime` and `context_hash` from the payload, `started_at` the event's `created_at.isoformat()`, the seven other columns null. `AgentRunFinished` sets `model`, `exit`, `tokens_in`, `tokens_out`, `cost_usd`, `duration_s` and `ended_at` (its event's `created_at.isoformat()`) on the row whose `id` is `run_id`; `error` is not projected. No sequence checks (ADR-009). `sqlite_recorder.py` is unchanged. New tests in `tests/integration/test_sqlite_projector_runs.py` (13, AC1 to AC6); the `agent_runs` case of `tests/unit/test_spec_conformance.py` runs with no edit to that file.

**Deviations from the plan.** None. No test from the test-writer was edited, and no existing test file was edited (plan step order aside).

**Checks.** 773 passed, none skipped; ruff, pyright and check_docs pass.

**Living docs.** `docs/architecture.md`, `docs/progress.md` and `docs/decisions.md` updated (four rows for Open questions 1 to 4, with the `error` reading). `CHANGELOG.md` and `README.md` unchanged: the changelog lists user-visible changes only, and this adds no command or output.

**Follow-ups.** None new. Next is outline item 4, the `Plans` and `Runs` read ports.
