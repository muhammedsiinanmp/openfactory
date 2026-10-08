# ADR-002: Event sourcing as the core

- Status: accepted
- Date: 2026-10-09

## Context
Phase 1 has to show that the platform's work can be audited and resumed. Two of the
spec's criteria say so directly: "Every state change can be reconstructed from the event
log", and "Killing the process mid-run and restarting resumes from the event log without
duplicate commits". `openfactory events` prints the raw audit log.

The spec's scope keeps storage small: SQLite with append-only events is in Phase 1, and
PostgreSQL, NATS and a durable workflow engine are deferred.

## Decision
The `events` table is the source of truth. Every other table is a projection rebuilt
from it. The spec gives the reason in one sentence: "This gives auditability,
resumability after a crash, and a replayable history in one design choice."

- The log is append-only. The `EventStore` port has no update or delete method.
- `event_id` is the idempotency key. Storing an id again with the same content is a
  no-op, and with different content raises `EventConflictError`.
- Projection tables are written only by applying a stored event. They are disposable:
  they have no foreign key and no `CHECK` constraints, and the payload models are the
  validation.
- Rebuilding means dropping the projection tables, recreating them, and applying every
  event in `seq` order. A rebuild is identical when, for every projection table, the rows
  read in primary-key order are equal before and after.
- The projector uses only data in the event: no clock, no generated ids, no file reads.
  Timestamps in projections come from the events' `created_at`, and ids are chosen by the
  use case when a command runs and are then fixed in the event.
- Each payload carries everything its projections hold, because the spec files and an
  LLM's reply cannot be read again at replay.
- Every task state transition is a `TaskStateChanged` event, approvals are events with
  actor `human`, and `init` records none.

How a use case records an event is decided in
[ADR-001](ADR-001-event-recorder-and-spec-versions-ports.md). What a payload may contain
is decided in [ADR-007](ADR-007-event-payloads-as-stable-contracts.md).

## Alternatives considered
- **Plain state tables updated in place.** Simpler, but there is no history, no rebuild
  after a crash and no audit trail, and the original PRD requires auditability and
  resumable workflows (author's rationale).
- **Events that point at content instead of carrying it.** `SpecImported` would hold
  only the hash and file paths, and the content would be read from git or from a copy
  under `.openfactory/`. The events are smaller, but the event log alone no longer
  reconstructs state, which the spec's success criteria require (gap G11).
- **SQL triggers that enforce append-only.** Rejected as hardening the spec does not ask
  for; the port contract is sufficient (decisions log, TASK-002).
- **An `openfactory rebuild` command.** Useful for the "SQLite file is lost" story, but
  it is a new command. Rebuild is a function covered by tests instead (gap G13).
- **All ten projection tables created in M1, empty.** This fixes their schemas before
  the milestones that use them have been planned. Each milestone adds the tables for the
  events it introduces instead, and a projection added later is filled by a rebuild
  (gap G14).
- **PostgreSQL, NATS or a durable workflow engine.** Deferred to later phases by the
  spec's scope table, under its rule that anything not needed for the demo waits.

## Consequences
Easier:
- One log answers the audit question, and `openfactory events` prints it.
- A restart resumes from the log.
- A projection can be added in a later milestone and filled by a rebuild, so nothing is
  lost by waiting.
- Projection schemas can stay loose, because they are never the record.

Harder:
- Payloads are large. `SpecImported` holds the full spec set, ADR bodies included, and
  `PlanCreated` holds the complete contracts.
- The projector must be deterministic, and "replay rebuilds projections identically" is
  a test every projection has to pass.
- `seq` is strictly increasing but not contiguous. Replay orders by `seq` and must never
  assume it is gapless or equals the row count.
- Stored events must stay readable for as long as the log exists, which constrains the
  payload models (ADR-007).
- A change to the canonical form changes every hash. During Phase 1 development that is
  handled by discarding the development database, not by versioning the hash.
- Appending an event and updating its projections must not come apart (ADR-001).
