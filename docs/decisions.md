# Decisions log

Small decisions not worth a full ADR. Newest first.

| Date | Decision | Why | Task |
| --- | --- | --- | --- |
| 2026-10-08 | `event_id` has no default; new events are built with `Event.new`, which generates a UUID4. | `event_id` is the idempotency key: a caller that rebuilds an event on retry must reuse the same id, so ids are never defaulted silently. | TASK-001 |
| 2026-10-08 | OpenFactory's own tests carry no `req` markers. | The spec defines no REQ ids for the platform itself; `req` markers are for the target repo's requirements. | TASK-001 |
| 2026-10-08 | Task ids follow `TASK-NNN`. | No id scheme was defined for this repo's own tasks; decided by the human. | TASK-001 |