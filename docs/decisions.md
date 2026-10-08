# Decisions log

Small decisions not worth a full ADR. Newest first.

| Date | Decision | Why | Task |
| --- | --- | --- | --- |
| 2026-10-08 | `seq` is strictly increasing but not contiguous. Replay orders by `seq` and must never assume `seq` is gapless or equals the row count. | A no-op re-append of a stored `event_id` still advances SQLite's `AUTOINCREMENT` counter, so gaps appear; the spec does not require gapless `seq`. Decided by the human. | TASK-002 |
| 2026-10-08 | Duplicate `event_id` with same content is a no-op (returns stored event with original `seq`); different content raises `EventConflictError`. Content is compared as canonical JSON (sorted keys) of the envelope fields, so `1`, `1.0` and `true` differ. | The spec calls `event_id` the idempotency key without defining what happens on repeat. Silent first-write-wins would hide a caller bug reusing an id for a different event. | TASK-002 |
| 2026-10-08 | `SqliteEventStore` creates the `events` table and sets WAL mode when opening a file. | The spec assigns file creation to `openfactory init`, which is a later task; the store must be usable and testable now. | TASK-002 |
| 2026-10-08 | Append-only is enforced by the `EventStore` port having no update or delete method, with no SQL triggers. | Triggers would be hardening the spec does not ask for; the port contract is sufficient. | TASK-002 |
| 2026-10-08 | `event_id` and `causation_id` are stored as hyphenated lowercase UUID strings; `type` as the event type name. | The spec fixes the text form of `created_at` and `payload` but not of these columns; decided by the human. | TASK-002 |
| 2026-10-08 | The `EventStore` port has two methods: `append(event)` returning a `StoredEvent`, and `read(stream)` with an optional stream filter returning a list of `StoredEvent`. | The spec names `EventStore` but gives no signature; this is the minimum that replay and `openfactory events [--stream S]` need. | TASK-002 |
| 2026-10-08 | `event_id` has no default; new events are built with `Event.new`, which generates a UUID4. | `event_id` is the idempotency key: a caller that rebuilds an event on retry must reuse the same id, so ids are never defaulted silently. | TASK-001 |
| 2026-10-08 | OpenFactory's own tests carry no `req` markers. | The spec defines no REQ ids for the platform itself; `req` markers are for the target repo's requirements. | TASK-001 |
| 2026-10-08 | Task ids follow `TASK-NNN`. | No id scheme was defined for this repo's own tasks; decided by the human. | TASK-001 |