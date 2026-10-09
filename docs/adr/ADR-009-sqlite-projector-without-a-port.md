# ADR-009: SQLite projector without a port

- Status: accepted
- Date: 2026-10-09

## Context
The spec lists `sqlite_projector` under `adapters/` but its port list has no projector
port, and [ADR-001](ADR-001-event-recorder-and-spec-versions-ports.md) rejected one: the
recorder's adapter owns both the append and the projector.
[ADR-006](ADR-006-ports-and-adapters-with-type-checked-conformance.md) and CLAUDE.md
require every adapter module to end with a `TYPE_CHECKING` assertion against its port,
which a module with no port cannot carry.

The spec also gives the projector no signature, does not say who owns the connection
and the transaction, and does not say what it does with an event type that has no
projection yet. The recorder adapter is written against these answers, so they must be
fixed before it is.

## Decision
- The projector implements no port. It is internal to the recorder adapter, which is its
  only caller in `src/`. `adapters/sqlite_projector.py` is exempt from the port
  conformance assertion.
- Its interface is a class `SqliteProjector(conn: sqlite3.Connection)` with
  `create_tables() -> None`, `apply(event: StoredEvent) -> None` and
  `rebuild(events: Iterable[StoredEvent]) -> None`.
- The projector never commits or rolls back. The caller owns the connection and the
  transaction, so the recorder adapter can append and apply in one.
- `apply` validates the payload against its model before its first write, and a mismatch
  raises `pydantic.ValidationError` unchanged.
- `rebuild` takes its events from the caller (`EventStore.read()`). The projector does
  not read the `events` table.
- `apply` does nothing for an event type that has no entry in `PAYLOAD_MODELS`. An event
  type that has a model but no projection column, such as `SpecValidated`, is validated
  and writes nothing.
- The projector replays facts and does not enforce business rules. It does not reject a
  `SpecImported` that names an approved version or a `SpecApproved` for an unknown
  version; the use cases enforce those rules before an event is recorded.
- When a `SpecImported` holds two requirements, or two ADRs, with the same id, the
  projector keeps the first in the payload's order and skips the others (spec v1.9,
  SC-12). The `id-unique` rule, not the projector, reports the duplicate.

## Alternatives considered
- **Add a `Projector` port.** The assertion rule would then hold without an exemption,
  but ADR-001 rejected the port and the spec's port list has none. No use case calls the
  projector, so the port would have no caller in `app/`.
- **Module-level functions instead of a class.** Equivalent, but every call would pass
  the connection, and the recorder adapter would have nothing to hold.
- **`rebuild` reads the `events` table on its own connection.** The projector would
  duplicate the store's row parsing, and the rebuild would run outside the caller's
  transaction.
- **Raise on an event type with no payload model.** Stricter, but the envelope and the
  store already accept the eight types of later milestones, and a rebuild must not fail
  on a log that holds them.
- **The projector rejects inconsistent event sequences.** That is hardening the spec
  does not ask for, and it would put the same rule in the use case and in the projector.

## Consequences
Easier:
- Append and apply share one transaction, so a rejected payload leaves nothing stored.
- A log that holds events of later milestones can be rebuilt today.
- The projector can be tested alone, on a plain SQLite connection.

Harder:
- The adapter assertion rule now has one exemption, which a reader must know.
- Nothing in the type checker ties the recorder adapter to the projector's interface.
- A caller that forgets to commit loses the projection writes.
- The caller must open an explicit transaction before `rebuild`: `sqlite3` otherwise
  autocommits the `DROP TABLE` and `CREATE TABLE` statements, so a rebuild that fails
  part-way cannot be rolled back.
- An event of an unknown type is skipped without notice until its milestone adds a
  model and a projection.
- A wrong event sequence written by code that bypasses the use cases is projected as it
  is.
