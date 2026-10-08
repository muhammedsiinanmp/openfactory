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

### Spec models
`src/openfactory/domain/models.py`. Pure Pydantic v2 models for a spec set, no I/O.
- `AcceptanceCriterion`: `id` and `text`.
- `Requirement`: `id`, `title`, `statement`, `priority`, `constrained_by` (list of ADR ids), `components`, `acceptance_criteria` (list of `AcceptanceCriterion`), and `deprecated` (boolean, optional, defaults to `false`); `constrained_by`, `components` and `acceptance_criteria` default to empty lists.
- `Adr`: `id`, `status` (closed set: `proposed`, `accepted`, `superseded`), and `body` (string, optional, defaults to empty string).
- `Priority`: closed set (`must`, `should`, `could`), enforced by enum.
- `SpecSet`: `components` (list of strings), `requirements` (list of `Requirement`), and `adrs` (list of `Adr`).
- All models are frozen. `AcceptanceCriterion`, `Requirement` and `SpecSet` reject unknown fields; `Adr` ignores them, since ADR front matter normally has more than `id` and `status`.

### Spec validation
`src/openfactory/domain/spec_validation.py`. Pure function that validates a spec set against deterministic rules.
- `Rule` enum: `id-format`, `id-unique`, `missing-acceptance-criteria`, `constrained-by`, `undeclared-component`.
- `SpecViolation`: `rule` (a `Rule`), `subject` (the id the violation concerns), and `message`.
- `validate_spec(spec: SpecSet) -> list[SpecViolation]`: applies the first four deterministic validation rules from the spec (the fifth, on deleted requirements, is enforced from M2 and not implemented) and returns every violation in a fixed rule order, collecting all violations in one run.

### Spec hashing
`src/openfactory/domain/spec_hash.py`. Pure functions that compute canonical JSON and SHA-256 hashes of spec items.
- `canonical_json(item: SpecItem) -> bytes`: the model dumped in JSON mode with sorted keys, separators `,` and `:` with no spaces, non-ASCII characters left as they are, and encoded as UTF-8.
- `content_hash(item: SpecItem) -> str`: the SHA-256 of the canonical JSON, written as 64 lowercase hex characters.
- `SpecItem`: `AcceptanceCriterion`, `Requirement`, `Adr`, or `SpecSet`.
- Before hashing, lists are sorted innermost first; items with an `id` sort by `(id, canonical JSON of the item)`, and every list of strings is sorted by value, including each requirement's `components` and `constrained_by`. Omitted optional fields hash the same as their defaults.

### Event payloads
`src/openfactory/domain/payloads.py`. Pure Pydantic v2 models for the payloads of the three M1 spec events, no I/O. Its only first-party imports are from `openfactory.domain`.
- `SpecImportedPayload`: `spec_version`, `hash` and `spec` (a `SpecSet`).
- `SpecValidatedPayload`: `spec_version`, `hash`, `violations` (list of `RecordedViolation`) and `warnings` (list of `SpecWarning`).
- `SpecApprovedPayload`: `spec_version` and `hash`.
- `RecordedViolation`: `rule`, `subject` and `message`, all strings. `rule` is a plain `str`, not the `Rule` enum, so a stored event stays valid if a rule is later renamed or removed. `SpecWarning`: `check`, `subject` and `message`, all strings.
- `SpecVersionId` is a string matching `^sv_\d{2,}$`; `ContentHash` is a string of 64 lowercase hex characters. Only the form of `hash` is checked; it is not compared with `spec`.
- All fields are required. The models are frozen and reject unknown fields. The `SpecImportedPayload` model does not reorder `spec`.
- `PAYLOAD_MODELS: dict[EventType, type[BaseModel]]` maps `SpecImported`, `SpecValidated` and `SpecApproved` to these models. The other event types have no entry yet.

## Data flow
<!-- updated when a milestone changes it -->
Events are appended through the `EventStore` port, which assigns `seq` and stores them in SQLite. Stored events are read back in `seq` order for replay by later tasks. Specs are validated by the `validate_spec` function, which returns every violation found.

Use cases are meant to build the payload of a spec event through the models in `payloads.py`. No use case exists yet: the import, validate and approve-spec use cases are later tasks. Planned for later tasks: the validate use case converts each `SpecViolation` to a `RecordedViolation`, and the projector validates stored payloads against `PAYLOAD_MODELS`. Nothing does either today.