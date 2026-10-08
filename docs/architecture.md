# Architecture

## Layers
domain → ports ← adapters; app uses domain + ports.

## Components
<!-- one short section per component as it is built -->

### Domain events
`src/openfactory/domain/events.py`. Pure Pydantic v2 models, no I/O.
- `EventType`: the closed set of 11 Phase 1 event type names.
- `Event`: a new event with no `seq`; its fields cannot be reassigned and unknown fields are rejected. Fields mirror the `events` table columns: `event_id` (any UUID; required), `stream` (non-empty), `type`, `payload` (a JSON object; `NaN`, `Infinity`, strings that are not valid Unicode and integers too large to read back are rejected), `actor` (`human`, `orchestrator` or `agent:<role>`), `causation_id` (optional), `created_at` (an aware datetime or ISO 8601 string, normalised to UTC; naive datetimes and numeric timestamps are rejected).
- `Event.new(...)`: builds a new event with a generated UUID4 `event_id` and the current UTC time as `created_at`.
- `StoredEvent`: an `Event` plus the required `seq` assigned by the store, a strict integer of at least 1.

### EventStore port
`src/openfactory/ports/event_store.py`. The append-only event log interface.
- `EventStore` (Protocol): two methods. `append(event: Event) -> StoredEvent` assigns a `seq` and stores the event; if its `event_id` is already stored with identical content, it returns the original row; if content differs, it raises `EventConflictError`. `read(stream: str | None = None) -> list[StoredEvent]` returns stored events in ascending `seq`, optionally filtered by stream.
- `EventConflictError`: raised when an `event_id` is appended with different content than what is already stored.

### SQLite event store
`src/openfactory/adapters/sqlite_store.py`. Implements `EventStore` over SQLite.
- `SqliteEventStore(path)`: opens the database file (creating it if it does not exist), creates the `events` table if missing using the spec's DDL, and sets WAL mode.
- Idempotency enforced by `event_id UNIQUE NOT NULL` constraint and `INSERT ... ON CONFLICT(event_id) DO NOTHING`.
- Rows read back are validated as `StoredEvent` before they are returned; `close()` releases the connection.

## Data flow
<!-- updated when a milestone changes it -->
Events are appended through the `EventStore` port, which assigns `seq` and stores them in SQLite. Stored events are read back in `seq` order for replay by later tasks.