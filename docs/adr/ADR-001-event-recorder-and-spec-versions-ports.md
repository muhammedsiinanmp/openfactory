# ADR-001: EventRecorder and SpecVersions ports

- Status: accepted
- Date: 2026-10-09

## Context
Spec v1.5 says "Use cases append an event, then apply it" and that spec version ids are
"chosen by the use case from the projections". Use cases live in `app`, which may depend
on the domain and the ports only. The spec's port list (`EventStore`, `SpecFiles`,
`AgentExecutor`, `WorkspaceManager`, `GitProvider`, `LLMProvider`) gives a use case no
way to apply an event to the projections and no way to read `spec_versions`. The
projector is named only as an adapter (`sqlite_projector`).

Appending and applying as two steps also leaves a window: a crash between them stores an
event whose projections are stale. Spec v1.5 closes that window with a catch-up when the
database is opened, which every command then depends on.

The gap blocks the remaining M1 work: the projector, `validate` and `approve spec`.

## Decision
Add two ports.

- `EventRecorder`, with one method `record(event) -> StoredEvent`. Its adapter appends
  the event to the `events` table and applies it to the projections in one SQLite
  transaction. Use cases record every event through it. This replaces "append, then
  apply". Recording an `event_id` that is already stored behaves like
  `EventStore.append`: the same content returns the stored event without applying it
  again, and different content raises `EventConflictError`.
- `SpecVersions`, a read-only port over the spec version projections. It gives the latest
  approved version, the current draft and the next spec version id.

`EventStore` stays as it is. It is the port for reading the log (`openfactory events`,
rebuild), and the recorder's adapter uses the same table.

The catch-up on open is kept, but only as a recovery for a database written before
append and apply shared a transaction. Projection tables are still never written in any
way other than by applying a stored event.

Exact signatures and adapter module names are settled in the tasks that build them.
The spec v1.6 proposal lists the adapters as `sqlite_recorder` and
`sqlite_spec_versions`.

## Alternatives considered
- **A `Projector` port next to `EventStore`.** The use case calls `append`, then
  `apply`, as spec v1.5 words it. This is the smallest change to the spec, but every use
  case must remember the second call, and the two calls are separate transactions unless
  a unit-of-work port is added as well. The crash window and the catch-up stay on the
  normal path.
- **`EventStore.append` applies the projections itself.** No new write port is needed.
  But `SqliteEventStore` and its tests are merged and define `append` as storing an
  event and nothing else, the store would have to know every projection, and a rebuild
  needs to read events without applying them through the same object.
- **Use cases read projections by replaying events through `EventStore.read`.** No read
  port is needed and the app stays free of SQL. But each use case would rebuild in memory
  what the projection tables already hold, which duplicates the projector's logic in the
  app layer and grows with the log.
- **One generic query port** (for example `Projections.query(table, ...)`) instead of
  `SpecVersions`. It would cover M2's plan and run ids too, but it leaks table shapes
  into the app layer and cannot be faked in a test without reimplementing queries.

## Consequences
Easier:
- A use case makes one call per event and cannot store an event without projecting it.
- An event whose payload the projector rejects is not stored, because the transaction
  rolls back.
- Use cases are tested with an in-memory fake recorder and a fake `SpecVersions`, with no
  database.
- The catch-up on open is no longer something normal operation relies on.

Harder:
- The recorder's adapter owns both the append and the projector, so the two SQLite
  adapters must share one connection or one transaction.
- There are two write paths to the `events` table, `EventStore.append` and
  `EventRecorder.record`. Use cases must use only the second; a later task may narrow
  `EventStore` to reading.
- `record` must detect an `event_id` that is already stored before it applies anything,
  so that a repeated event is returned without being applied twice and a conflicting one
  raises `EventConflictError`, as `EventStore.append` does.
- M2 needs the same kind of read access for plan ids, run ids and tasks. This ADR adds
  only `SpecVersions`; the M2 read ports are decided when M2 is planned.
