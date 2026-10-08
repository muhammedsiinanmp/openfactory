# TASK-002: EventStore port and SQLite event store (append and read)

- Milestone: M1
- Status: done
- Tests: acceptance
- Spec sections: "Domain model and storage" (the `CREATE TABLE events` DDL and "Event envelope rules"); "Tech stack and repo layout"; "CLI commands" (`openfactory events [--stream S]`); "Purpose and demo scenario" (Success criteria)

## Objective
Add the `EventStore` port and a SQLite adapter that appends new events to the `events` table and reads them back in `seq` order, so later M1 tasks (projections, replay, spec approval, CLI) have a durable event log to build on.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- `EventStore`: a `Protocol` in `ports/` with two methods, `append(event: Event) -> StoredEvent` and `read(stream: str | None = None) -> list[StoredEvent]`.
- `EventConflictError`: an exception defined in the port module, raised when an `event_id` is appended again with different content.
- `SqliteEventStore`: an adapter in `adapters/` that implements the port with the standard `sqlite3` module. On opening a file it creates the `events` table if missing, using the spec's DDL, and sets WAL mode.
- Tests for the port and the adapter.

Out (follow-up M1 tasks, not this one):
- Projection tables and replay.
- Per-event-type payload models.
- Spec YAML models, loader, validation rules, hashing, `spec_version`.
- CLI commands `init`, `validate`, `approve spec`, `events`, and creating `.openfactory/`.
- `domain/states.py` task state machine.
- Concurrent writers, multi-process locking, and SQL triggers that block `UPDATE` or `DELETE`. Phase 1 is single-user and sequential.
- Reading by `seq` range, by type, or by `causation_id`.

## Acceptance criteria
Each criterion cites the spec heading it traces to. "Envelope rules" means the "Event envelope rules" list under "Domain model and storage".

- [x] AC1 ("Tech stack and repo layout": `ports/ # interfaces: EventStore, ...` and "the domain never imports infrastructure"): `openfactory.ports.event_store.EventStore` is a `typing.Protocol` that declares `append` and `read`. The module imports nothing from `openfactory.adapters` or `openfactory.app` and does not import `sqlite3` (checked by parsing its imports with `ast`). `SqliteEventStore` lives in `openfactory.adapters.sqlite_store` and provides both methods.
- [x] AC2 ("Tech stack and repo layout": "SQLite via the standard `sqlite3` module, WAL mode"; "Domain model and storage": `CREATE TABLE events`): opening `SqliteEventStore` on a path with no file creates the database with an `events` table whose columns are exactly `seq`, `event_id`, `stream`, `type`, `payload`, `actor`, `causation_id`, `created_at`, and `PRAGMA journal_mode` on that file reports `wal`.
- [x] AC3 (envelope rules: "`seq` is assigned by the store. New events have no `seq`; stored events always do"): `append(event)` returns a `StoredEvent` whose seven envelope fields equal the given event's and whose `seq` was assigned by the store. The first append on a new database returns `seq` 1, and each later append of a new event returns a larger `seq`.
- [x] AC4 (`event_id TEXT UNIQUE NOT NULL -- uuid; idempotency key`): appending an event whose `event_id` is already stored with the same content (all envelope fields except `seq`) writes no row and returns the stored event with its original `seq`. Appending an event whose `event_id` is already stored with different content raises `openfactory.ports.event_store.EventConflictError` and leaves the stored row unchanged. In both cases the table still holds one row for that `event_id`.
- [x] AC5 (envelope rules: "only stored events are replayed"; "CLI commands": `openfactory events [--stream S]`): `read()` returns every stored event as a `StoredEvent`, in ascending `seq`. `read(stream="task:AUTH-002")` returns only the events of that stream, in ascending `seq`. A stream with no events, and a new database, give an empty list.
- [x] AC6 ("Purpose and demo scenario", Success criteria: "Every state change can be reconstructed from the event log"; envelope rules: "`created_at`: timezone-aware UTC, stored as ISO 8601" and "`payload`: a JSON object"): after the store is closed and a new `SqliteEventStore` is opened on the same file, `read()` returns events equal to those `append` returned, including a nested payload, a non-null `causation_id` and the same `created_at` instant. In the raw row, `created_at` is ISO 8601 text with a UTC designator and `payload` is JSON text that parses to the original object.

## Interpretations
The spec leaves these open. All five were confirmed by the human on 2026-10-08; item 2 was changed from the planner's proposal (which did not compare content).

1. Port surface: `append(event: Event) -> StoredEvent` and `read(stream: str | None = None) -> list[StoredEvent]`. The spec names `EventStore` but gives no signature.
2. Duplicate `event_id` (AC4): if the stored event has the same content (all envelope fields except `seq`), the second append is a no-op that returns the stored event with its original `seq`. If the content differs, it raises `EventConflictError`, defined in the port module. The spec calls `event_id` the "idempotency key" without saying what a repeat does.
3. Schema creation (AC2): the adapter creates the `events` table and sets WAL mode when it opens a file. The spec assigns creating the SQLite file to `openfactory init`, which is a later task and will open the store.
4. Append-only: enforced by the port having no update or delete method. No SQL triggers.
5. Column text: `event_id` and `causation_id` are stored as the canonical hyphenated UUID string, `type` as the event type name.

## Plan
1. Create branch `task/TASK-002-event-store-sqlite` from an up-to-date main.
2. Write failing tests: `tests/unit/test_event_store_port.py` for AC1, and `tests/integration/test_sqlite_event_store.py` for AC2 to AC6, using a database file under pytest's `tmp_path`.
3. Add `src/openfactory/ports/event_store.py`: the `EventStore` protocol and `EventConflictError`, importing only `Event` and `StoredEvent` from the domain.
4. Add `src/openfactory/adapters/sqlite_store.py`: `SqliteEventStore(path)` opens the file with `sqlite3`, sets `PRAGMA journal_mode=WAL`, and runs the spec's `CREATE TABLE` with `IF NOT EXISTS`. `append` inserts with `ON CONFLICT(event_id) DO NOTHING`, then selects the row by `event_id` as a `StoredEvent`; if its envelope fields differ from the given event's it raises `EventConflictError`, otherwise it returns the stored event. `read` selects ordered by `seq`, with an optional `stream` filter. Rows are turned into `StoredEvent` through Pydantic validation. A `close()` method releases the connection.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, and `uv run python scripts/check_docs.py` until all are green.
6. Update living docs and this record's Outcome; commit with trailers `Task: TASK-002` and `Milestone: M1`.

## Files expected to change
- `src/openfactory/ports/event_store.py` (new)
- `src/openfactory/adapters/sqlite_store.py` (new)
- `tests/unit/test_event_store_port.py` (new)
- `tests/integration/test_sqlite_event_store.py` (new; first file in `tests/integration/`)
- `docs/architecture.md` (Components: add "EventStore port" and "SQLite event store"; Data flow: events are appended through the port)
- `docs/progress.md` (Current task, then Done)
- `docs/decisions.md` (rows for the confirmed interpretations: duplicate `event_id` behaviour, schema created by the adapter)
- `docs/tasks/TASK-002-event-store-sqlite.md` (this record; Outcome at close)

## Living docs to update
- `docs/architecture.md`: Components and Data flow.
- `docs/progress.md`: Current and Done.
- `docs/decisions.md`: the confirmed interpretations.
- `CHANGELOG.md`: no entry expected (no user-visible change).
- `README.md`: no change expected.

## New dependencies
None. `sqlite3` is in the standard library.

## Outcome

**Built:**
- `openfactory.ports.event_store.EventStore`: a `Protocol` declaring `append(event: Event) -> StoredEvent` and `read(stream: str | None = None) -> list[StoredEvent]`. The module imports only from domain, not from adapters or app.
- `openfactory.ports.event_store.EventConflictError`: raised when an `event_id` is appended with different content than what is already stored.
- `openfactory.adapters.sqlite_store.SqliteEventStore`: opens an SQLite database file with the `events` table (DDL from spec) created if missing, WAL mode enabled. `append` inserts with `ON CONFLICT(event_id) DO NOTHING`, fetches the row, and compares the canonical JSON (sorted keys) of the envelope fields to detect conflicts, so `1`, `1.0` and `true` are different content. `read` selects by `seq` with optional stream filter. `close` releases the connection.
- 19 tests (unit and integration) written by test-writer in `tests/unit/test_event_store_port.py` and `tests/integration/test_sqlite_event_store.py`.

**Deviations from plan:** None in code. The interpretation change (interpretation 2: duplicate event_id with different content raises `EventConflictError`) was approved by the human at plan and is now implemented.

**After review (decided by the human):** the conflict comparison was changed from Python equality to canonical JSON, with a test; the AC4 conflict tests were extended to non-payload fields; and `docs/decisions.md` records that `seq` is strictly increasing but not contiguous, because a no-op re-append still advances the `AUTOINCREMENT` counter.

**Follow-ups:** The out-of-scope items from the plan: projection tables and replay; per-event-type payload models; spec YAML models and validation; CLI commands (`init`, `validate`, `approve spec`, `events`, `.openfactory/` directory); domain `states.py` task state machine; concurrent writer handling and multi-process locking; reading by `seq` range, type, or `causation_id`.
