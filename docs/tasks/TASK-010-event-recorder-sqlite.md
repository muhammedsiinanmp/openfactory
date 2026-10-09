# TASK-010: EventRecorder port and SQLite recorder adapter

- Milestone: M1
- Status: done
- Tests: acceptance
- ADR: ADR-010, accepted (the recorder adapter: its own connection and `busy_timeout`, the shared `adapters/sqlite_events.py` module, `rebuild()` outside the port, catch-up only when the recorder opens, and the error for a bad stored payload). The port and the adapter themselves are covered by ADR-001 (accepted); the projector's interface and transaction ownership by ADR-009 (accepted).
- Spec sections (spec v1.7): "Domain model and storage" (the `projection_state` DDL, "Projections", "Projection rules", "Event payloads", "Event envelope rules"); "Tech stack and repo layout"; "Milestones and definition of done" (item 1)

## Objective
Add the `EventRecorder` port and its SQLite adapter, which appends an event, applies it to the projections and sets `projection_state.last_seq` in one transaction, catches up when it opens a database, and rebuilds the projections inside one transaction, so the `validate` and `approve spec` use cases have a single call for recording an event.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- A new port module `ports/event_recorder.py`: the Protocol `EventRecorder` with one method, `record(event: Event) -> StoredEvent`. `EventConflictError` is reused from `ports/event_store.py`.
- A new shared module `adapters/sqlite_events.py` holding everything both SQLite adapters need for the `events` table: the DDL, the column list, the insert, the select, the row parsing and the content comparison. `adapters/sqlite_store.py` imports from it and keeps its behaviour; no SQL for the `events` table is written twice. The module implements no port and carries no conformance assertion, like the projector.
- A new adapter module `adapters/sqlite_recorder.py` (the module name is the spec's): the class `SqliteEventRecorder(path: str | Path)` with `record`, `rebuild() -> None` and `close()`, ending with the `TYPE_CHECKING` assertion against `EventRecorder`.
- The recorder opens its own connection, sets WAL mode and `PRAGMA busy_timeout = 5000`, and creates what is missing: the `events` table, the spec projections, and `projection_state` with its single row `id = 1`, `last_seq = 0`.
- `record`: insert the event into `events`, apply it with `SqliteProjector`, and set `last_seq`, all in one transaction that is committed on success and rolled back on any error.
- A repeated `event_id`: the same content returns the stored event and applies nothing; different content raises `EventConflictError`.
- Catch-up when the recorder opens a database: stored events with `seq > last_seq` are applied in `seq` order and `last_seq` is set, in one transaction. A stored payload its model rejects raises `pydantic.ValidationError` naming the event's `seq`, and a stored event the projector cannot write raises `sqlite3.IntegrityError` naming its `seq` and payload model; in both cases nothing is applied.
- `rebuild()` in one explicit transaction: `SqliteProjector.rebuild` with every stored event, then `last_seq` set to the highest `seq`; rolled back if anything fails.
- Integration tests on a SQLite file under pytest's `tmp_path`, and a unit test for the port module.

Out (follow-up tasks, not this one):
- The `SpecVersions` port and `sqlite_spec_versions` adapter (M1 outline item 2).
- The `validate` and `approve spec` use cases, and any in-memory fake recorder for their tests (outline items 3 and 4).
- CLI commands `init`, `validate`, `approve spec`, `events` (outline items 5 to 7). `init` creating the database file is not this task; the recorder creates what is missing when it opens a file, as `SqliteEventStore` does (decision of 2026-10-08, TASK-002).
- Narrowing `EventStore` to reading, or removing `SqliteEventStore.append` (ADR-001 leaves this to a later task).
- Any change to `SqliteProjector`, to `domain/`, or to the `EventStore` port.
- The M2 tables and events; `trace_links` (M5).
- Recovering from a bad stored payload: the open fails and the database is left as it was. Repairing the log is not this task.
- Catch-up at any time other than when the recorder opens. An event appended through `SqliteEventStore` while a recorder is open is not applied by that recorder (ADR-010).
- Retry on `SQLITE_BUSY`. `busy_timeout` makes a writer wait; nothing retries after it expires (Phase 1 is a single-user, sequential CLI).
- Payload depth limit (stays under Later).

## Acceptance criteria
Each criterion cites the spec v1.7 text it traces to. "Projection rules", "Event payloads" and "Event envelope rules" mean the blocks of those names under "Domain model and storage". In every criterion the recorder is `SqliteEventRecorder` working on a SQLite database file under `tmp_path`; rows are read by the test with plain SQL on a second connection, or through `SqliteEventStore(path).read()`, so that only committed data is seen. "The spec projections" are `spec_versions`, `requirements` and `adrs`. "`last_seq`" is the value in the single row of `projection_state`.

- [x] AC1 ("Tech stack and repo layout": "`ports/ # interfaces: EventStore, EventRecorder, ...`", "`adapters/ # sqlite_store, sqlite_projector, sqlite_recorder, ...`" and "Storage | SQLite via the standard `sqlite3` module, WAL mode"; Projection rules: "Use cases record every event through the `EventRecorder` port, `record(event) -> StoredEvent`"; the DDL "`CREATE TABLE IF NOT EXISTS projection_state (id INTEGER PRIMARY KEY, last_seq INTEGER NOT NULL)`"; Projection rules: "exactly one row: `id = 1` ... The event recorder creates it"):
  - `openfactory.ports.event_recorder` defines a Protocol `EventRecorder` whose only public method is `record`, and imports nothing from `openfactory.adapters` or `openfactory.app` (checked by parsing its imports with `ast`).
  - Opening the recorder on a path that does not exist creates the file with the `events` table, the spec projections and `projection_state`, in WAL journal mode. `projection_state` has the columns `id` and `last_seq` and holds exactly one row, `id = 1`, `last_seq = 0`. Opening the recorder a second time on the same file raises nothing and changes no row.
  - `openfactory.adapters.sqlite_recorder` imports nothing from `openfactory.app`.
  - Not in the spec; from the human's decision on shared SQL (ADR-010): the texts `CREATE TABLE IF NOT EXISTS events` and `INSERT INTO events` each appear in exactly one module under `src/openfactory/adapters/`, and that module is `sqlite_events.py`.
- [x] AC2 (Projection rules: "Its adapter appends the event and applies it to the projections in one transaction, so an event is never stored without its projections being updated"; Event envelope rules: "`seq` is assigned by the store. New events have no `seq`; stored events always do"): a `SpecImported` for `sv_01`, a `SpecValidated` and a `SpecApproved` are recorded in that order.
  - Each `record` returns a `StoredEvent` with the event's own `event_id`, `stream`, `type`, `payload`, `actor` and `created_at`, and a `seq` higher than the one before.
  - After each call, the event is in `SqliteEventStore(path).read()` and its projection is visible on the second connection. After the third, `spec_versions` holds `sv_01` with `status` `approved` and `approved_at` equal to the `SpecApproved` event's `created_at`, and the `requirements` and `adrs` rows are those of the import.
  - Recording a `TaskStateChanged` (a type with no M1 projection) stores it, changes no row in the spec projections, and sets `last_seq` to its `seq`.
- [x] AC3 (Event payloads: "the projector validates each payload against its model before applying it and fails on a mismatch"; Projection rules: "in one transaction, so an event is never stored without its projections being updated"): with `sv_01` already recorded, recording a `SpecImported` whose payload has no `hash` raises `pydantic.ValidationError`. Afterwards:
  - the `events` table has no row with that `event_id`, and the number of stored events is unchanged;
  - every row of the spec projections and `last_seq` are unchanged;
  - a valid event recorded next is stored and projected normally.
- [x] AC4 (Projection rules: "Recording an `event_id` that is already stored behaves like `EventStore.append`: the same content returns the stored event without applying it again, and different content raises `EventConflictError`"): event A imports `sv_01`; event B imports `sv_01` again with different content; both are recorded.
  - Recording A again returns a `StoredEvent` equal to the one first returned for A, with the same `seq`. The number of stored events is unchanged, the spec projections still hold B's content, and `last_seq` is still B's `seq`.
  - Recording an event with A's `event_id` and a different payload raises `EventConflictError`, imported from `openfactory.ports.event_store`, and changes no stored event, no projection row and not `last_seq`.
- [x] AC5 (Projection rules: "Recording an event appends it to the events table, applies it to the projections, and sets `last_seq` in one transaction. When the recorder opens the database, it applies every event with `seq > last_seq`; if `projection_state` is missing, it is created and catch-up starts from the first event. Because append and apply share a transaction, this catch-up is needed only as a recovery for a database written before they did"):
  - After every successful `record`, `projection_state` holds exactly one row, with `id = 1` and `last_seq` equal to the `seq` that call returned.
  - One event (import `sv_01`) is recorded and the recorder closed; a `SpecValidated`, a `SpecApproved` and an import of `sv_02` are then appended through `SqliteEventStore` only. Opening the recorder again leaves the spec projections equal to those of a second database file in which the same four events were all recorded through the recorder, and `last_seq` equal to the highest stored `seq`.
  - A database file that holds only an `events` table filled through `SqliteEventStore` (no projection tables, no `projection_state`) is brought up to date in the same way when the recorder opens it.
  - Closing and opening the recorder once more changes no row.
  - Not in the spec; from the human's decision on a bad stored payload (ADR-010): one event (import `sv_01`) is recorded and the recorder closed; a `SpecValidated` and then a `SpecApproved` whose `spec_version` is `v1` are appended through `SqliteEventStore`. Opening the recorder raises `pydantic.ValidationError`, and `str()` of the error contains `seq N`, where N is the `seq` of the `SpecApproved` event. Afterwards the spec projections and `last_seq` are as they were before the open: nothing was applied, not even the valid `SpecValidated`.
  - Not in the spec; from the human's decision after the review (ADR-010): the same set-up, but the second appended event is a `SpecImported` for `sv_02` whose spec holds the same requirement twice, which its model accepts and the projector cannot write. Opening the recorder raises `sqlite3.IntegrityError`, and `str()` of the error contains `seq N` for that event and the model name `SpecImportedPayload`. Afterwards the spec projections and `last_seq` are as they were before the open.
- [x] AC6 (Projection rules: "Rebuilding means clearing the projection tables, replaying all events in `seq` order, and setting `last_seq` to the highest `seq` in one transaction; any failure rolls the whole rebuild back. `projection_state` is reset on rebuild, not dropped, and a correct rebuild leaves projection_state's value unchanged. It is a function covered by tests, not a CLI command" and "A rebuild is identical when, for every projection table, the rows read in primary-key order are equal before and after"; "Milestones and definition of done", item 1: "replay rebuilds projections identically"): the log is recorded in this order: import `sv_01`, validated, import `sv_01` again with changed content, validated, approved, a `TaskStateChanged`, import `sv_02`, validated.
  - After the recorder's `rebuild()`, the rows of each spec projection, read in primary-key order, are equal to what they were before, and a row the test inserted directly into `requirements` beforehand is gone. `projection_state` still holds exactly one row, `id = 1`, and its `last_seq` is unchanged and equal to the highest stored `seq`.
  - Traces to ADR-009 (accepted), Consequences, "The caller must open an explicit transaction before `rebuild`"; spec v1.7 now says the same in "any failure rolls the whole rebuild back": while the recorder stays open, a `SpecApproved` whose `spec_version` is `v1` is appended through `SqliteEventStore`. `rebuild()` then raises `pydantic.ValidationError`, and the spec projections and `last_seq`, read on the second connection, are as they were before the call.

## Decisions
The human answered the open questions on 2026-10-09. Items 1 and part of 2 are now spec text (spec v1.7, merged as `spec/projection-state`); the rest are recorded in ADR-010 (accepted) and `docs/decisions.md`.

1. `projection_state` is used as spec v1.7 defines it. The recorder adapter creates it and is its only writer; `SqliteProjector` is unchanged and still knows nothing about it.
2. `SqliteEventRecorder(path)` opens its own connection and sets `PRAGMA busy_timeout = 5000`. Every write transaction starts with `BEGIN IMMEDIATE`, so the write lock is taken up front and the time-out applies to it.
3. The shared SQL moves to a new module `adapters/sqlite_events.py`. `sqlite_store.py` imports from it with its behaviour unchanged, and its existing tests pass unchanged. No SQL is duplicated.
4. `rebuild()` is a method of `SqliteEventRecorder` that is not on the `EventRecorder` port. It reads every stored event on its own connection and passes them to `SqliteProjector.rebuild`.
5. A bad stored payload during catch-up raises `pydantic.ValidationError` naming the `seq`, and the catch-up applies nothing. One test covers it (AC5, the `pydantic.ValidationError` bullet).
6. ADR-010 is written as proposed, and was marked accepted by the human after the review. It records that catch-up runs only when the recorder opens.
7. The task stays one task. The AC6 rollback bullet is kept and tagged as tracing to ADR-009.

Implementation notes that follow from these:
- A new event is told from a repeated one by the row count of `INSERT ... ON CONFLICT(event_id) DO NOTHING`: one row inserted means new, so it is applied and `last_seq` is set. None inserted means repeated, so the stored row is compared as `SqliteEventStore.append` does and nothing is applied.
- The error for a bad stored payload is built with `ValidationError.from_exception_data`, with the title `stored event seq N (<payload model name>)` and the original error list, so it is still a `pydantic.ValidationError`.
- `SqliteProjector.rebuild` drops and recreates the three spec projection tables. Inside the recorder's transaction this clears them, which is what spec v1.7 asks for; `projection_state` is updated in place and never dropped.

Kept as already decided: `record` behaves like `append` for a repeated `event_id` (ADR-001); the projector never commits and validates before its first write (ADR-009); event types with no entry in `PAYLOAD_MODELS` are stored and project nothing (ADR-009); `seq` is not contiguous and replay orders by `seq` (decision of 2026-10-08, TASK-002); content is compared as canonical JSON of the envelope (decision of 2026-10-08, TASK-002).

## Architecture rules that apply
- `src/openfactory/ports` holds Protocols only: `ports/event_recorder.py` defines `EventRecorder` and imports from `openfactory.domain` only.
- Adapters implement ports and end with the `TYPE_CHECKING` assertion: `adapters/sqlite_recorder.py` ends with `if TYPE_CHECKING: _: type[EventRecorder] = SqliteEventRecorder`. `sqlite_projector` stays exempt (ADR-009), and `sqlite_events` is an internal helper with no port, exempt in the same way.
- "All state changes go through the events table. Never write projections directly": the recorder writes projection rows only by calling `SqliteProjector.apply` or `rebuild` with stored events. `projection_state` is bookkeeping, not a projection, and is written only next to an apply. Tests read with plain SQL; the single direct insert in AC6 is test set-up.
- `src/openfactory/domain` is not changed. `src/openfactory/app` is not changed; no use case exists yet.
- No LLM call is made. Every payload is validated by its Pydantic model in the projector before use.

## Plan
1. Create branch `task/TASK-010-event-recorder-sqlite` from an up-to-date main and commit this record.
2. Draft ADR-010 as Status: proposed.
3. Write failing tests:
   - `tests/unit/test_event_recorder_port.py` for the port half of AC1, following `tests/unit/test_event_store_port.py`.
   - `tests/integration/test_sqlite_recorder.py`, one or more tests per criterion AC1 to AC6, with helpers that build spec events through the payload models and read table rows in primary-key order on a second connection.
4. Add `src/openfactory/ports/event_recorder.py`.
5. Add `src/openfactory/adapters/sqlite_events.py` and make `src/openfactory/adapters/sqlite_store.py` import from it, with no change in behaviour; run the existing store tests unchanged.
6. Add `src/openfactory/adapters/sqlite_recorder.py`: open and create, catch-up, `record`, `rebuild`, `close`, and the conformance assertion.
7. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
8. Update living docs and this record's Outcome; commit with trailers `Task: TASK-010` and `Milestone: M1`.

## Files expected to change
- `src/openfactory/ports/event_recorder.py` (new)
- `src/openfactory/adapters/sqlite_events.py` (new)
- `src/openfactory/adapters/sqlite_recorder.py` (new)
- `src/openfactory/adapters/sqlite_store.py` (imports the shared SQL; behaviour unchanged)
- `tests/unit/test_event_recorder_port.py` (new)
- `tests/integration/test_sqlite_recorder.py` (new)
- `docs/adr/ADR-010-sqlite-recorder-adapter.md` (new, Status: proposed)
- `docs/architecture.md` (Components: add "EventRecorder port", "SQLite events helpers" and "SQLite recorder"; Data flow: replace "Nothing calls the projector yet ..." with what now exists, and say no use case calls the recorder yet)
- `docs/progress.md` (Current task, then Done; remove item 1 from the M1 outline and renumber the references to it; remove the two "Recorder task" items from Later)
- `docs/decisions.md` (rows for the decisions not carried by the spec or the ADR)
- `docs/tasks/TASK-010-event-recorder-sqlite.md` (this record; Outcome at close)

Not expected to change: everything under `src/openfactory/domain/` and `src/openfactory/app/`, `src/openfactory/ports/event_store.py`, `src/openfactory/ports/spec_files.py`, `src/openfactory/adapters/sqlite_projector.py`, `src/openfactory/adapters/filesystem_spec_files.py`, `pyproject.toml`, and every existing test file.

## Living docs to update
- `docs/architecture.md`: Components and Data flow.
- `docs/progress.md`: Current, M1 outline, Done and Later.
- `docs/decisions.md`: the decisions above that the ADR does not carry.
- `docs/adr/`: ADR-010 as proposed.
- `CHANGELOG.md`: no entry expected (no user-visible change).
- `README.md`: no change expected.

## New dependencies
None. `sqlite3` and `json` are in the standard library; Pydantic v2 is already declared.

## Outcome
What was built:
- `src/openfactory/ports/event_recorder.py`: the Protocol `EventRecorder` with `record(event) -> StoredEvent`.
- `src/openfactory/adapters/sqlite_events.py`: `create_events_table`, `insert_event`, `stored_event` and `select_events`, holding all SQL for the `events` table. `src/openfactory/adapters/sqlite_store.py` now calls them; its behaviour and its tests are unchanged.
- `src/openfactory/adapters/sqlite_recorder.py`: `SqliteEventRecorder(path)` with `record`, `rebuild()` and `close()`. It opens its own connection with WAL mode and `busy_timeout` 5000 ms, creates the missing tables and catches up in one transaction when it opens, and starts every transaction with `BEGIN IMMEDIATE`.
- `tests/unit/test_event_recorder_port.py` and `tests/integration/test_sqlite_recorder.py`: tests for AC1 to AC6, written by the test-writer.
- `docs/adr/ADR-010-sqlite-recorder-adapter.md` (drafted as proposed; marked accepted by the human), six rows in `docs/decisions.md`, and updates to `docs/architecture.md` and `docs/progress.md`.

Deviations from plan:
- The spec was amended first (v1.7, `projection_state`), on its own branch, and this record was rewritten against it before the task branch was created.
- The human's instruction named the branch `task/010-event-recorder-sqlite`; the branch is `task/TASK-010-event-recorder-sqlite`, the form CLAUDE.md and the metrics hook use. Reported to the human.
- Creating the missing tables and the catch-up share one transaction, so a failed open leaves the file untouched (`docs/decisions.md`).
- `busy_timeout` has no test: it cannot be read through the adapter's public interface.
- The living docs were updated in the main session, not by the docs-keeper subagent.
- Test edits after the test-writer staged its files, both at the human's request following the reviewer's notes; no assertion was removed without a stricter one replacing it:
  - `test_ac2_record_returns_stored_events_and_projects_each_one` now compares every row of the three spec projections with the expected content after each of the three `record` calls. The id-only checks it had are covered by that comparison.
  - `test_ac5_stored_event_the_projector_cannot_write_fails_the_open_naming_seq_and_model` was added, with its AC5 bullet. It also asserts that the error's cause is the original `sqlite3.IntegrityError`.
- After the review, the catch-up was extended to name the stored event for a `sqlite3.IntegrityError` as well (ADR-010).

Follow-ups (in `docs/progress.md` under Later):
- An event appended through `EventStore.append` while a recorder is open is never applied by a catch-up; narrowing `EventStore` to reading would close this (ADR-010, ADR-001).
- There is no repair path for a stored event whose payload its model rejects.
