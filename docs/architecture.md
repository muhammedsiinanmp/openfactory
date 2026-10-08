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

## Data flow
<!-- updated when a milestone changes it -->