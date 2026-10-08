# TASK-009: SQLite projector for the spec projections

- Milestone: M1
- Status: done
- Tests: acceptance
- ADR: ADR-009, accepted (the projector is an adapter with no port: its interface, who owns the connection and transaction, the exemption from the port conformance assertion, and what it does with event types that have no projection)
- Spec sections (spec v1.6): "Domain model and storage" ("Projections", "Projection rules", "Event payloads"); "Spec input format" ("Hashing", "Spec versions"); "Tech stack and repo layout"; "Milestones and definition of done" (item 1)

## Objective
Add the SQLite projector that creates the three M1 projection tables (`spec_versions`, `requirements`, `adrs`), applies one stored `SpecImported`, `SpecValidated` or `SpecApproved` event at a time, and rebuilds the tables from the event log identically, so the recorder adapter, the `SpecVersions` adapter and the `validate` and `approve spec` use cases have projections to build on.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- A new adapter module `adapters/sqlite_projector.py` (the module name is the spec's).
- Creating `spec_versions`, `requirements` and `adrs` with the spec's DDL: no foreign key, no `CHECK` constraint.
- Applying one `StoredEvent`:
  - The payload is validated against its model in `PAYLOAD_MODELS` before anything is written.
  - `SpecImported` writes the draft version row and its requirement and ADR rows, replacing the content of an existing draft with the same id. Item hashes are computed with `content_hash`.
  - `SpecApproved` sets `status` to `approved` and `approved_at` from the event's `created_at`.
  - `SpecValidated` is validated and writes nothing, since no projection column holds a validation result.
- Rebuild: drop the three tables, recreate them, and apply every given event in `seq` order.
- Integration tests on a SQLite file under pytest's `tmp_path`, with events appended through the existing `SqliteEventStore` where a log is needed.

Out (follow-up tasks, not this one):
- The `EventRecorder` port and `sqlite_recorder` adapter: append and apply in one transaction, and the repeated `event_id` behaviour (ADR-001).
- The one-row table that records the `seq` of the last applied event, and the catch-up when the database is opened (see Open questions, item 4).
- The `SpecVersions` port and `sqlite_spec_versions` adapter: latest approved version, current draft, next id.
- The `validate` and `approve spec` use cases: hashing the loaded spec set, storing it in canonical order, choosing `sv_NN`, converting `SpecViolation` to `RecordedViolation`, and recording events.
- CLI commands `init`, `validate`, `approve spec`, `events`.
- The M2 tables (`plans`, `tasks`, `task_deps`, `agent_runs`) and their events; `trace_links` (M5).
- Checking a payload's `hash` against its `spec`, or re-sorting `spec` (ADR-007: payload models check shape only; the use case stores canonical order).
- Checking that an event's `stream` matches its payload's `spec_version`.
- Inconsistent event sequences: a `SpecImported` naming an approved version, a `SpecApproved` for an unknown version or with a different hash (see Open questions, item 5).
- Any change to `SqliteEventStore`, the `EventStore` port, `domain/payloads.py`, `domain/spec_hash.py` or the loaders.
- Payload depth limit (stays under Later).

## Acceptance criteria
Each criterion cites the spec v1.6 heading it traces to. "Projection rules", "Projections" and "Event payloads" mean the blocks of those names under "Domain model and storage"; "Spec versions" and "Hashing" are under "Spec input format". In every criterion the projector works on a SQLite database file under `tmp_path`, and rows are read with plain SQL by the test. JSON columns are compared after parsing, not as text. The criteria are written for the proposals under Interpretations; AC5 and AC6 are adjusted in plan step 2 if items 2 or 3 are answered with the alternative.

- [x] AC1 ("Tech stack and repo layout": `adapters/ # sqlite_store, sqlite_projector, ...`; Projections: the DDL under "The tables built in M1 and M2" and "Projection tables have no foreign key and no `CHECK` constraints"; Projection rules: "Each milestone adds the tables for the events it introduces: M1 `spec_versions`, `requirements`, `adrs`"):
  - On an empty database, creating the projection tables gives exactly the tables `spec_versions`, `requirements` and `adrs`, and none of `plans`, `tasks`, `task_deps`.
  - Each table has the spec's column names in the spec's order.
  - The primary keys are `id` for `spec_versions`, and `(spec_version, id)` for `requirements` and `adrs`.
  - No table has a foreign key (`PRAGMA foreign_key_list` is empty) and no table's stored SQL contains `CHECK`.
  - Creating them a second time changes nothing and does not raise.
  - `openfactory.adapters.sqlite_projector` imports nothing from `openfactory.app` (checked by parsing its imports with `ast`).
- [x] AC2 (Event payloads: the `SpecImported` shape and "Item hashes are not in `SpecImported`; the projector computes them from the content"; Projections: the rows of `spec_versions`, `requirements`, `adrs`; Hashing: "A requirement's hash covers the whole requirement", "An ADR's hash covers `id`, `status` and `body`"): applying a stored `SpecImported` for `sv_01`, whose `spec` has components `["auth"]`, the spec's example requirement `REQ-AUTH-001`, a second requirement with `deprecated: true`, and an accepted `ADR-001` with a body, gives:
  - one `spec_versions` row with `id` `sv_01`, `hash` equal to the payload's `hash`, `status` `draft`, `components` parsing to `["auth"]`, and `approved_at` `NULL`;
  - one `requirements` row per requirement with `spec_version` `sv_01`, the `title`, `statement` and `priority` of the payload, `deprecated` `0` or `1`, `components`, `constrained_by` and `acceptance_criteria` parsing to the payload's lists (criteria as `{id, text}` objects), and `hash` equal to `content_hash` of that requirement;
  - one `adrs` row with `spec_version` `sv_01`, the ADR's `status` and `body`, and `hash` equal to `content_hash` of that ADR.
- [x] AC3 (Spec versions: "An existing draft keeps its id and its content is replaced"; "At most one draft exists at a time"): after AC2's event, a second `SpecImported` for `sv_01` is applied, with a different `hash`, different components, one requirement removed, one requirement's statement changed, and the ADR's body changed. Then:
  - `spec_versions` still holds exactly one row, `sv_01`, with the second event's `hash` and components and `status` `draft`;
  - the `requirements` and `adrs` rows for `sv_01` are exactly those of the second event: the removed requirement has no row, and the changed requirement and ADR have their new content and new hashes.
- [x] AC4 (Event payloads: the `SpecApproved` and `SpecValidated` shapes; Projections: "`approved_at TEXT -- ISO 8601 UTC, from SpecApproved.created_at`"; Spec versions: "the version is immutable from then on. Edits after that create a new draft version"):
  - Applying a `SpecApproved` for `sv_01` sets that row's `status` to `approved` and `approved_at` to the event's `created_at` as an ISO 8601 UTC string, and leaves `hash`, `components` and every `requirements` and `adrs` row unchanged.
  - Applying a `SpecImported` for `sv_02` afterwards adds a `draft` row and its items, and leaves every row of `sv_01` in all three tables unchanged.
  - Applying a `SpecValidated` (once with an empty `violations` list, once with one violation) changes no row in any of the three tables.
- [x] AC5 (Event payloads: "the projector validates each payload against its model before applying it and fails on a mismatch"; "the models forbid unknown fields"; Projection rules: "A projection added later is filled by a rebuild"):
  - With `sv_01` already imported, applying each of these raises `pydantic.ValidationError` and changes no row in any of the three tables: a `SpecImported` whose payload has no `hash`; a `SpecImported` whose payload has an extra key; a `SpecApproved` whose `spec_version` is `v1`; a `SpecValidated` whose payload has no `warnings`.
  - Applying a stored event of a type that has no M1 projection (`TaskStateChanged` with any payload) raises nothing and changes no row.
- [x] AC6 (Projection rules: "Rebuilding means dropping the projection tables, recreating them, and applying every event in `seq` order. It is a function covered by tests, not a CLI command"; "A rebuild is identical when, for every projection table, the rows read in primary-key order are equal before and after. The projector therefore uses only data in the event: no clock, no generated ids, no file reads"; "Milestones and definition of done", item 1: "replay rebuilds projections identically"): the log is appended through `SqliteEventStore` and each event applied as it is stored, in this order: import `sv_01`, validated, import `sv_01` again with changed content, validated, approved, a `TaskStateChanged`, import `sv_02`, validated.
  - The rows of each of the three tables, read in primary-key order, are equal before and after a rebuild from `store.read()`.
  - A row inserted directly into `requirements` by the test before the rebuild is gone after it.
  - Rebuilding into a second, empty database file from the same events gives the same rows as the first.

## Interpretations
The spec says what the projector does but leaves these open. All are proposals to be confirmed by the human in plan step 2 and recorded in `docs/decisions.md`, or in the ADR where noted.

1. No port. The spec's port list has no projector port and ADR-001 rejected one, so `sqlite_projector` implements no Protocol and carries no `TYPE_CHECKING` conformance line. The recorder adapter (later task) is the only caller in `src/`. See Open questions, item 1.
2. Interface and transactions. Proposed: a class `SqliteProjector(conn: sqlite3.Connection)` with `create_tables() -> None`, `apply(event: StoredEvent) -> None` and `rebuild(events: Iterable[StoredEvent]) -> None`.
   - It never commits or rolls back; the caller owns the transaction, so the recorder adapter can append and apply in one.
   - `apply` validates the payload before its first write, so a rejected event leaves the tables as they were without a rollback.
   - A mismatch raises `pydantic.ValidationError` unchanged.
   - `rebuild` takes the events from the caller (`EventStore.read()`), so the projector does not read the `events` table itself or duplicate the store's row parsing.
   - Alternative: module-level functions, or `rebuild` reading the `events` table on its own connection.
3. Event types with no projection. Proposed: `apply` does nothing for an event type that has no entry in `PAYLOAD_MODELS` (the eight types of later milestones). The envelope and the store already accept them, and a rebuild must not fail on a log that holds them. `SpecValidated` has a model, is validated, and writes nothing. Alternative: raise on a type with no payload model.
4. Column forms.
   - `priority` and ADR `status` are stored as their string values, and `deprecated` as `0` or `1`.
   - JSON columns are written with `json.dumps`, non-ASCII left as it is, in the order the event holds. The projector does not sort; canonical order is the use case's job (decision of 2026-10-08, TASK-005).
   - `spec_versions.hash` is the payload's `hash`, not recomputed (ADR-007).
   - `approved_at` is `created_at.isoformat()`, the same form `SqliteEventStore` writes.

Kept as already decided: per-type payload models with one mapping, and the projector validates before applying (ADR-007); projection tables are disposable, with no foreign key and no `CHECK` (ADR-002); `seq` is not contiguous and replay orders by `seq` (decision of 2026-10-08, TASK-002).

## Architecture rules that apply
- `src/openfactory/adapters` holds SQLite code. The projector imports from `openfactory.domain` only (`events`, `payloads`, `spec_hash`, `models`) and from the standard library; it imports nothing from `openfactory.app`.
- "Every adapter module ends with a `TYPE_CHECKING` assertion against its port": the projector has no port (Open questions, item 1). No assertion is written unless the human rules otherwise.
- "Never write projections directly": the projector is the one place that writes projection tables, and only by applying a stored event. Tests read with plain SQL; the single direct insert in AC6 is test set-up for the rebuild.
- All state changes go through the events table: the projector appends no events.
- `src/openfactory/domain` and `src/openfactory/ports` are not changed.
- No LLM call is made. Every payload is validated by its Pydantic model before use.

## Plan
1. Create branch `task/TASK-009-sqlite-projector` from an up-to-date main.
2. Get the human's answers to the Open questions and Interpretations 1 to 4; record them here and in `docs/decisions.md`. Draft `docs/adr/ADR-009-sqlite-projector-without-a-port.md` as Status: proposed, unless the human rules that ADR-001, ADR-002 and ADR-006 already cover it. Adjust AC5 and AC6 if items 2 or 3 are answered with the alternative.
3. Write failing tests in `tests/integration/test_sqlite_projector.py`, one or more per criterion AC1 to AC6, with small helpers that build stored spec events through the payload models and read table rows in primary-key order.
4. Add `src/openfactory/adapters/sqlite_projector.py`: the three `CREATE TABLE IF NOT EXISTS` statements from the spec, `create_tables`, `apply` (look up the model in `PAYLOAD_MODELS`, validate, then dispatch by event type), and `rebuild` (drop, recreate, apply in ascending `seq`).
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
6. Update living docs and this record's Outcome; commit with trailers `Task: TASK-009` and `Milestone: M1`.

## Files expected to change
- `src/openfactory/adapters/sqlite_projector.py` (new)
- `tests/integration/test_sqlite_projector.py` (new)
- `docs/adr/ADR-009-sqlite-projector-without-a-port.md` (new, Status: proposed; only if the human confirms an ADR is needed)
- `docs/architecture.md` (Components: add "SQLite projector"; Data flow: replace "the projector validates stored payloads against `PAYLOAD_MODELS`. Nothing does either today" with what now exists, and say nothing calls the projector yet)
- `docs/progress.md` (Current task, then Done; add to Later the last-applied `seq` table and catch-up on open for the recorder task, if item 4 is confirmed)
- `docs/decisions.md` (rows for the confirmed interpretations)
- `docs/tasks/TASK-009-sqlite-projector.md` (this record; Outcome at close)

Not expected to change: everything under `src/openfactory/domain/`, `src/openfactory/ports/` and `src/openfactory/app/`, `src/openfactory/adapters/sqlite_store.py`, `src/openfactory/adapters/filesystem_spec_files.py`, `pyproject.toml`, and every existing test file.

## Living docs to update
- `docs/architecture.md`: Components and Data flow.
- `docs/progress.md`: Current, Done and Later.
- `docs/decisions.md`: the confirmed interpretations.
- `docs/adr/`: the new ADR as proposed, if confirmed.
- `CHANGELOG.md`: no entry expected (no user-visible change).
- `README.md`: no change expected.

## New dependencies
None. `sqlite3` and `json` are in the standard library; Pydantic v2 is already declared.

## Open questions
All answered by the human on 2026-10-09, each with the proposal. Interpretations 1 to 4 are confirmed, and the acceptance criteria stand as written.

- Item 1: exempt. The projector is internal to the recorder adapter per ADR-001, so it has no port and no conformance assertion.
- Item 2: the proposed interface is accepted.
- Item 3: event types with no projection are ignored.
- Item 4: the last-applied `seq` table and the catch-up on open are left to the recorder task.
- Item 5: not checked. Use cases enforce the rules before recording; the projector replays facts.
- ADR-009 is drafted as proposed. The decisions are also rows in `docs/decisions.md`.

The questions as asked:

1. Adapter with no port. CLAUDE.md and ADR-006 say every adapter module ends with `if TYPE_CHECKING: _: type[<Port>] = <Adapter>`. The spec lists `sqlite_projector` under `adapters/` but its port list has no projector port, and ADR-001 rejected one. Is the projector exempt from the assertion (proposed, to be recorded in an ADR), or should a port be added? Adding one would contradict ADR-001's rejected alternative and extend the spec's port list.
2. Interface. The spec gives the projector no signature, does not say who owns the connection and transaction, and does not say what "fails on a mismatch" raises. Is Interpretations, item 2 accepted?
3. Event types with no projection. The decision row of 2026-10-08 (TASK-005) left "what the projector does with a type that has no entry" to this task. Ignore them (proposed) or raise?
4. The last-applied `seq` table. Projection rules say "A one-row table records the `seq` of the last applied event", but the spec gives no table name or DDL, and the table is not in the "Projections" list. Proposed: this task leaves it out, and the recorder task adds it together with the catch-up on open, since both belong to opening the database and to the shared transaction. Alternative: the projector writes it in `apply` and `rebuild` now, which needs a name and DDL from the human (for example `projection_state(id INTEGER PRIMARY KEY, last_seq INTEGER NOT NULL)`) and a seventh criterion, so the task would be split.
5. Inconsistent events. The spec says an approved version "is immutable from then on" but not whether the projector enforces it. A `SpecImported` naming an approved version would replace its content, and a `SpecApproved` for an unknown version would update no row. Proposed: not checked here, because the use cases choose ids from the projections and CLAUDE.md asks for no hardening the spec does not request. Alternative: the projector raises in both cases.

## Outcome
What was built:
- `src/openfactory/adapters/sqlite_projector.py`: `SqliteProjector(conn)` with `create_tables()`, `apply(event)` and `rebuild(events)`. It creates and fills `spec_versions`, `requirements` and `adrs`, validates each payload against `PAYLOAD_MODELS` before writing, ignores event types with no projection, and never commits.
- `tests/integration/test_sqlite_projector.py`: integration tests for AC1 to AC6, written by the test-writer.
- `docs/adr/ADR-009-sqlite-projector-without-a-port.md` (drafted as proposed; marked accepted by the human), four rows in `docs/decisions.md`, and updates to `docs/architecture.md` and `docs/progress.md`.

Deviations from plan:
- None in the implementation.
- The planned ADR was drafted as ADR-009.
- No test edits were made to the test-writer's file. After the review, at the human's request, one test was added to it: `test_ac6_rebuild_applies_events_in_seq_order`, which gives `rebuild` the events in reverse order. The reviewer had noted that the existing AC6 tests would pass without the sort.

Follow-ups (all in `docs/progress.md` under Later):
- Recorder task: add the one-row table holding the `seq` of the last applied event, and the catch-up when the database is opened.
- Recorder task: open an explicit transaction before calling `rebuild`, since `sqlite3` otherwise autocommits the `DROP TABLE` and `CREATE TABLE` statements (reviewer's note, now in ADR-009).
- Before M2 is planned: the spec's "Projection rules" says M2 adds `agent_runs`, but the DDL block has no `CREATE TABLE agent_runs`.
