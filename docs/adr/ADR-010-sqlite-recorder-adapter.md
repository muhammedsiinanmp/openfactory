# ADR-010: SQLite recorder adapter

- Status: accepted
- Date: 2026-10-09

## Context
[ADR-001](ADR-001-event-recorder-and-spec-versions-ports.md) added the `EventRecorder`
port and left "exact signatures and adapter module names" to the task that builds the
adapter. [ADR-009](ADR-009-sqlite-projector-without-a-port.md) fixed the projector's
interface and made its caller own the connection and the transaction. Spec v1.7 defines
the `projection_state` table, what one `record` does, the catch-up and the rebuild.

That still leaves open how the adapter is built:

- whether it shares a connection object with `SqliteEventStore` or opens its own;
- how it reuses the `events` table SQL, since `SqliteEventStore.append` commits its own
  transaction and so cannot be called inside the recorder's;
- where rebuild is exposed, since the port has only `record`;
- when the catch-up runs;
- what happens when the catch-up meets a stored payload its model rejects.

Later SQLite adapters (`sqlite_spec_versions`, the M2 read adapters) will follow whatever
is chosen here.

## Decision
- The adapter is a class `SqliteEventRecorder(path: str | Path)` in
  `adapters/sqlite_recorder.py`, with `record(event) -> StoredEvent`, `rebuild() -> None`
  and `close()`. It opens its own `sqlite3` connection. Two adapters on one database file
  share the file, not a connection object.
- On open it sets WAL mode and `PRAGMA busy_timeout = 5000`, and creates what is missing:
  the `events` table, the projection tables (through `SqliteProjector.create_tables`), and
  `projection_state` with its single row `id = 1`, `last_seq = 0`.
- Every write transaction of the recorder starts with `BEGIN IMMEDIATE`. The write lock
  is taken before anything is read, so `busy_timeout` applies to the wait, and a
  transaction never fails half-way because another connection wrote first.
- The SQL and helpers for the `events` table live in a new module
  `adapters/sqlite_events.py`: the DDL, the column list, the insert, the select, the row
  parsing and the content comparison. `sqlite_store` and `sqlite_recorder` both import
  from it, and no SQL for the `events` table is written anywhere else. The module
  implements no port and carries no conformance assertion, like the projector.
- `rebuild()` is a method of the adapter and is not on the `EventRecorder` port. Use
  cases cannot call it; tests and the M1 close task do.
- `SqliteProjector` is unchanged. It still drops and recreates the projection tables in
  `rebuild`; inside the recorder's transaction that clears them, as spec v1.7 asks.
  `projection_state` is updated in place and never dropped.
- The catch-up runs only when a recorder opens a database, in one transaction. It does
  not run before `record` or `rebuild`.
- A stored payload its model rejects during the catch-up raises
  `pydantic.ValidationError` whose title names the event (`stored event seq N (<model>)`).
  The transaction is rolled back, so no event of that catch-up is applied and `last_seq`
  is unchanged. The recorder does not open.
- A stored event that passes its model but that the projector cannot write is treated
  the same way (no M1 event does this since spec v1.9, SC-12, under which the projector
  keeps the first of two items with one id): the
  catch-up raises `sqlite3.IntegrityError` whose message starts with
  `stored event seq N (<model>)`, with the original error as its cause, and nothing is
  applied.

## Alternatives considered
- **Build the recorder from an existing `sqlite3.Connection` shared with the store.**
  One connection means one lock and no `busy_timeout`. But the caller would then own the
  connection's settings and lifetime, every command would have to wire two adapters to
  one object, and `SqliteEventStore(path)` already opens its own.
- **Make the private helpers of `sqlite_store.py` importable.** The smallest diff: a
  rename and one extracted function. But the recorder would import from another adapter,
  and the store module would carry helpers that exist only for its neighbour.
- **Duplicate the SQL in the recorder.** No change to a merged module, but two copies of
  the DDL, the insert and the content comparison that must never drift apart.
- **`rebuild` on the port.** Use cases could then call it. The spec says rebuild is "a
  function covered by tests, not a CLI command", and no use case needs it.
- **Catch up before every `record`.** An event appended through `EventStore.append`
  while a recorder is open would then be applied by the next `record`. It costs a query
  on every call, for a case that normal operation does not produce: use cases write only
  through the recorder (ADR-001).
- **On a bad stored payload, open anyway and skip or report the event.** The command
  could continue, but the projections would silently miss an event, and `last_seq` could
  no longer mean "everything up to here is applied".

## Consequences
Easier:
- A command builds a recorder from a path, as it builds the store.
- The `events` table SQL has one home, and a change to it reaches both adapters.
- `SqliteEventStore` keeps its behaviour and its tests.
- A rebuild that fails leaves the projections and `last_seq` as they were.
- A database with a bad stored payload fails loudly at open and is left untouched.

Harder:
- Two connections can now contend for the write lock. A writer waits up to five seconds
  and then fails with `sqlite3.OperationalError`; nothing retries.
- An event appended through `EventStore.append` while a recorder is open is not applied
  by that recorder. The next `record` moves `last_seq` past it, so a later catch-up does
  not apply it either; only `rebuild()` does. This is safe only while use cases write
  through the recorder alone, which ADR-001 requires and a later task may enforce by
  narrowing `EventStore` to reading.
- One bad stored payload stops every command that opens a recorder until the log is
  repaired by hand. No repair tool exists.
- `rebuild()` cannot be reached through the port, so a fake recorder in a use-case test
  has no rebuild, and code that needs one depends on the adapter class.
- The error for a bad stored payload is a new exception built from the original error
  list; the original is kept only as its cause.
- `sqlite_events` is a second adapter module with no port, so the conformance-assertion
  rule has two exemptions.
