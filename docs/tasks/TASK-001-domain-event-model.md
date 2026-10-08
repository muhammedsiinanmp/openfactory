# TASK-001: Domain event model (envelope and event types)

- Milestone: M1
- Status: done
- Spec sections: "Domain model and storage" (spec v1.2, including "Event envelope rules"); "Tech stack and repo layout"

## Objective
Add the pure domain model for an event (`Event` for new events, `StoredEvent` for events read back from the store) and the closed set of 11 Phase 1 event type names, so later M1 tasks (event store, projections, replay) have a validated type to build on.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and the human decided that OpenFactory's own tests carry no `req` markers. Acceptance criteria trace to spec headings instead.

## Scope
In:
- `EventType`: the 11 event type names listed in the spec.
- `Event`: a Pydantic v2 model for a new event, with no `seq`, and the `Event.new(...)` constructor that generates `event_id` and `created_at`.
- `StoredEvent(Event)`: the same envelope plus a required `seq`.
- Unit tests for all three.

Out (follow-up M1 tasks, not this one):
- `EventStore` port (Protocol) in `ports/`.
- SQLite adapter: `events` table DDL, WAL mode, idempotent append keyed on `event_id`, read by stream.
- Per-event-type payload models (payload shapes are not defined in the spec).
- Projection tables and replay.
- Spec YAML models, loader, validation rules, hashing, `spec_version`.
- CLI commands `init`, `validate`, `approve spec`, `events`.
- `domain/states.py` task state machine (not needed until tasks exist).

## Acceptance criteria
Each criterion cites the spec heading it traces to. "Envelope rules" means the "Event envelope rules" list under "Domain model and storage".

- [x] AC1 ("Event types in Phase 1"): `EventType` contains exactly these 11 values and no others: `SpecImported`, `SpecValidated`, `SpecApproved`, `PlanCreated`, `PlanApproved`, `TaskStateChanged`, `AgentRunStarted`, `AgentRunFinished`, `GateEvaluated`, `CommitRecorded`, `ImpactComputed`.
- [x] AC2 (`CREATE TABLE events`; envelope rules, `seq`): `Event` exposes exactly the fields `event_id`, `stream`, `type`, `payload`, `actor`, `causation_id`, `created_at`, named as the table columns are, and has no `seq` field.
- [x] AC3 (`NOT NULL` columns; revised, decision 8): constructing an `Event` without any one of `event_id`, `stream`, `type`, `payload`, `actor`, `created_at` raises `pydantic.ValidationError`. The same holds for `StoredEvent`.
- [x] AC4 (`causation_id TEXT` is nullable): `causation_id` may be omitted and is then `None`.
- [x] AC5 (envelope rules, `event_id`): any valid UUID is accepted as `event_id`, whatever its version (for example a UUID1 and a UUID4), given as a `UUID` or as a string; a non-UUID string such as `"not-a-uuid"` raises `ValidationError`.
- [x] AC6 (envelope rules, `event_id`: "new events use UUID4"; replaced, decision 8): `event_id` has no default. `Event.new(stream=..., type=..., payload=..., actor=..., causation_id=None)` takes keyword arguments only and returns an `Event` whose `event_id` is a generated UUID of version 4 and whose `created_at` is the current time as a timezone-aware datetime with a zero UTC offset (between the instants just before and just after the call). Two calls give different ids. `causation_id` is `None` unless given. The envelope rules still apply: an invalid `actor`, `type`, `payload` or empty `stream` passed to `Event.new` raises `ValidationError`.
- [x] AC7 ("Event types in Phase 1"): `type` accepts each of the 11 names; an unknown name such as `"TaskExploded"` raises `ValidationError`, and so do the two names removed in spec v1.2, `"ApprovalGiven"` and `"TaskInvalidated"`.
- [x] AC8 (envelope rules, `payload`: "a JSON object"): a payload that is an object of nested JSON values (strings, numbers, booleans, null, lists, objects) is accepted, including the empty object. A top-level value that is not an object (a list, a string, a number, `None`) raises `ValidationError`. A payload containing a non-JSON value (for example a `set` or an arbitrary object) raises `ValidationError`.
- [x] AC9 (envelope rules, `actor`): `actor` must match `^(human|orchestrator|agent:[a-z][a-z-]*)$`. Accepted: `human`, `orchestrator`, `agent:planner`, `agent:implementer`, `agent:reviewer`, `agent:test-writer`. Rejected with `ValidationError`: the empty string, `robot`, `Human`, `agent:`, `agent:Implementer`, `agent:1x`, `agent:-x`, `agent:implementer ` (trailing space), `human\n` (trailing newline).
- [x] AC10 (envelope rules, `created_at`: "timezone-aware UTC"): a timezone-aware UTC datetime is accepted, as a `datetime` or as the ISO 8601 string `"2026-10-08T12:00:00Z"`, and `created_at` is then a timezone-aware `datetime` with a zero UTC offset. A naive datetime raises `ValidationError`, both as a `datetime` object and as the string `"2026-10-08T12:00:00"`. Revised, decision 12: only aware datetimes and ISO 8601 strings are accepted, so a numeric Unix timestamp raises `ValidationError` as an `int` (`1759924800`), as a `float` (`1759924800.5`), as the numeric string `"1759924800"`, and as a bare number in JSON text passed to `model_validate_json`.
- [x] AC11 (envelope rules, `created_at`: "timezone-aware UTC"): a timezone-aware datetime with a non-UTC offset (for example `2026-10-08T17:30:00+05:30`) is converted to UTC, so the stored value is the same instant with a zero offset (approved, decision 9). A value that cannot be represented in UTC, such as `0001-01-01T00:00:00+05:00`, raises `ValidationError`.
- [x] AC12 (envelope rules, `created_at`: "stored as ISO 8601"): in the output of `model_dump_json()`, `created_at` is an ISO 8601 string that carries a UTC designator (`Z` or `+00:00`) and parses back to the same instant.
- [x] AC13 (envelope rules, `seq`: "stored events always do"; revised, decision 11): `StoredEvent` is a subclass of `Event` with one extra field, `seq`, a required strict integer of at least 1. Constructing a `StoredEvent` without `seq` raises `ValidationError`, as does a `seq` that is not an `int` (`"abc"`, `"7"`, `7.0`, `1.5`, `True`, `None`) or is below 1 (`0`, `-1`). `1` and a large value such as `2**40` are accepted. A stored event still survives the JSON round trip (AC14).
- [x] AC14 (`payload ... -- JSON`): an `Event` and a `StoredEvent` each survive `model_dump_json()` followed by `model_validate_json()` on their own class and compare equal to the original.
- [x] AC15 ("Tech stack and repo layout": "the domain never imports infrastructure" and "domain/ # pure models, state machine, rules; no I/O"): `openfactory/domain/events.py` imports nothing from `openfactory.adapters`, `openfactory.app` or `openfactory.ports`, and does not import `sqlite3`, `subprocess` or `socket` (checked by parsing the module's imports with `ast`).
- [x] AC16 (envelope rules, `seq`: "New events have no `seq`"; decision 10): unknown fields are rejected on both models. `Event(..., seq=5)` raises `ValidationError`, as does a misspelt field such as `causation=...` on `Event` or `StoredEvent`, and JSON text with an extra key passed to `model_validate_json`.
- [x] AC17 (`stream TEXT NOT NULL`; decision 13): `stream` must have at least one character; the empty string raises `ValidationError`. No format is imposed: `"task:AUTH-002"`, `"x"` and `"spec"` are accepted.

## Decisions from the human (2026-10-08)
1. No `req` markers on OpenFactory's own tests.
2. Task ids follow `TASK-NNN`.
3. `actor` is a closed set: `human`, `orchestrator`, `agent:<role>`, pattern `^(human|orchestrator|agent:[a-z][a-z-]*)$`.
4. `created_at` is a timezone-aware UTC datetime; naive datetimes are rejected; it serializes as ISO 8601.
5. `payload` is a JSON object: `dict[str, JsonValue]`.
6. Two models: `Event` (no `seq`) and `StoredEvent(Event)` with `seq: int` required.
7. Any valid UUID is accepted as `event_id`; new ids are generated with `uuid4`.

Second round, after the first review:

8. No `uuid4` default: `event_id` is required when constructing `Event` directly. `Event.new(...)` generates a `uuid4` `event_id` and a UTC `created_at`. This also makes `StoredEvent.event_id` required.
9. Converting non-UTC offsets to UTC is approved (AC11).
10. `extra="forbid"` on `Event` and `StoredEvent`.
11. `seq` is a strict `int`, at least 1.
12. `created_at` rejects numeric timestamps; ISO strings and aware datetimes are accepted.
13. `stream` has `min_length=1` and no format pattern.

## Interpretations
Both earlier interpretations are settled: the `uuid4` default on `event_id` was replaced by `Event.new` (decision 8), and converting non-UTC offsets to UTC was approved (decision 9).

One remains, open to correction:

- AC6: `Event.new` is inherited by `StoredEvent` but is meant for new events only; calling `StoredEvent.new(...)` raises `ValidationError` because no `seq` is supplied.

## Plan
1. Create branch `task/TASK-001-domain-event-model` from an up-to-date main.
2. Write failing tests in `tests/unit/test_domain_events.py`, one or more per criterion AC1 to AC17.
3. Implement `src/openfactory/domain/events.py`: `EventType` as a `StrEnum`; `Event` as a frozen Pydantic v2 `BaseModel` with `extra="forbid"`, a required `event_id: UUID`, a non-empty `stream`, `payload: dict[str, JsonValue]`, a pattern-constrained `actor`, a UTC-normalised aware `created_at` that accepts only datetimes and ISO 8601 strings, `causation_id` optional, and an `Event.new` classmethod; `StoredEvent(Event)` adding a strict `seq: int` of at least 1.
4. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, and `uv run python scripts/check_docs.py` until all are green.
5. Update living docs and this record's Outcome; commit with trailers `Task: TASK-001` and `Milestone: M1`.

## Files expected to change
- `src/openfactory/domain/events.py` (new)
- `tests/unit/test_domain_events.py` (new)
- `docs/architecture.md` (Components: add a short "Domain events" section)
- `docs/progress.md` (Current task, then Done)
- `docs/tasks/TASK-001-domain-event-model.md` (this record; Outcome at close)

## Living docs to update
- `docs/architecture.md`: Components section.
- `docs/progress.md`: Current and Done.
- `CHANGELOG.md`: no entry expected (no user-visible change).
- `README.md`: no change expected.
- `docs/decisions.md`: rows for the task id scheme, the no-`req`-marker rule, and the required `event_id` with `Event.new`.

## New dependencies
None. Pydantic v2 is already declared in `pyproject.toml`.

## Outcome
Closed 2026-10-08.

### What was built
- `src/openfactory/domain/events.py`:
  - `EventType`: a `StrEnum` with the 11 Phase 1 event type names.
  - `Event`: a frozen Pydantic v2 model for a new event, with `extra="forbid"` so unknown fields (including `seq`) are rejected. Fields: `event_id` (`UUID` of any version, required, no default), `stream` (at least one character, no format imposed), `type` (`EventType`), `payload` (`dict[str, JsonValue]`, non-finite floats, strings that are not valid Unicode and integers of 4300 or more digits rejected), `actor` (must match `^(human|orchestrator|agent:[a-z][a-z-]*)$`), `causation_id` (`UUID | None`, default `None`), `created_at` (required; an aware datetime or an ISO 8601 string, normalised to UTC; naive datetimes and numeric Unix timestamps are rejected).
  - `Event.new(*, stream, type, payload, actor, causation_id=None)`: a keyword-only classmethod that builds an event with a generated UUID4 `event_id` and `created_at` set to the current UTC time. The envelope rules apply to its arguments.
  - `StoredEvent(Event)`: the same envelope plus a required `seq`, a strict `int` of at least 1. It inherits `new`, which raises `ValidationError` there because no `seq` is supplied.
- `tests/unit/test_domain_events.py`: 230 test cases covering AC1 to AC17. Full suite: 236 passed. ruff clean; `check_docs` passes.

### Deviations from the plan
One in the code: `payload` carries a validator the plan does not mention (see the review finding below). Points the plan and criteria did not fix:
- The tests go beyond the literal criteria: `None` rejected for the NOT NULL fields; extra invalid UUIDs; nested non-JSON values in a payload; a negative UTC offset; `StoredEvent` inheriting the envelope rules; dumped JSON keys equal to the column names; `StoredEvent.new` raising.
- `Event` is frozen, as the plan says, but no criterion or test covers it. Freezing is shallow: fields cannot be reassigned, but the `payload` dict can still be mutated in place, and `model_copy(update=...)` and `model_construct` skip validation as they do on any Pydantic model.
- `causation_id` is typed `UUID | None`. The criteria did not fix its type; it refers to another event's `event_id`.
- The first review found that a payload could hold `NaN` or `Infinity`, which are not JSON and serialised as `null`, breaking AC8 and AC14. Fixed with a validator on `payload` that rejects non-finite floats at any depth, on both the Python and the JSON-text input paths, and seven added test cases.

The task went through a second round. After the first review the human made decisions 8 to 13. The criteria were revised (AC3, AC6, AC10, AC13) and extended (AC16, AC17), the tests were written first and seen failing (38 failed, 154 passed), and the model was then changed to pass them.

The review of that round found that an aware `created_at` too close to the edge of the datetime range to be converted to UTC (for example `0001-01-01T00:00:00+05:00`) raised a raw `OverflowError`. It now raises `ValidationError`; six test cases were added first and seen failing.

The next review found that a payload string holding a lone surrogate (for example text decoded with `errors="surrogateescape"`, such as a file name from git) passed validation on the Python path. As a key it was silently written as replacement characters; as a value it made `model_dump_json()` raise a serialisation error. Both break AC8 and AC14. The payload validator now also rejects any key or string value, at any depth, that cannot be encoded as UTF-8; thirteen test cases were added first, twelve of which were seen failing (the thirteenth checks that ordinary non-ASCII text is still accepted).

The review after that found one more value of the same kind: an integer of about 4300 digits or more passed validation and was written by `model_dump_json()`, but `model_validate_json()` then refused the text ("number out of range"), so a stored event could not be read back (AC14). The payload validator now rejects integers whose absolute value is `10**4299` or more; smaller integers, including ones far beyond 64 bits, are accepted and round-trip. Fifteen test cases were added first, ten of which were seen failing; four more cases pin a bad entry that is not the first in its object.

### Known limits
- Payload depth. The payload validator (non-finite floats, invalid Unicode, oversized integers) recurses in Python, one frame per nesting level, and Pydantic does not convert `RecursionError` into `ValidationError`. Measured by the reviewer and re-measured on the final code: Pydantic itself accepts payload nesting up to 254 levels beneath the payload object on the Python path and 198 on the JSON-text path (256 and 200 containers counting the payload object and the innermost one), and raises `ValidationError` beyond that; but a payload nested 254 deep, validated from a caller already about 750 or more frames deep (default recursion limit 1000), raises a raw `RecursionError`. It needs both a pathologically nested payload and a very deep call stack. Tracked in `docs/progress.md` under Later as "payload depth limit".
- `created_at` string forms. Strings are parsed with `datetime.fromisoformat` (Python 3.12), so the accepted set is CPython's: besides `2026-10-08T12:00:00Z` it takes the basic format, a space separator, week dates, offsets without a colon, a comma as the fraction separator, and offsets with seconds; fractions beyond microseconds are truncated, and text after an embedded NUL is ignored. Output is always the canonical `...Z` form. No test pins the wider set.
- Payload integer size. The bound of `10**4299` is the limit of Pydantic's JSON reader (measured on pydantic 2.13.5), not a design choice; the spec sets no integer range. SQLite and most JSON consumers handle far less (64-bit), so a tighter bound may be wanted.
- Validation bypass. In-place mutation of `event.payload`, `model_copy(update=...)` and `model_construct` bypass validation, as on any Pydantic model.

### Still open
The earlier interpretations and the reviewer's strictness questions are settled by decisions 8 to 13. Four points remain:
- The one item under Interpretations: `StoredEvent.new(...)` raises `ValidationError` because no `seq` is supplied. Open to correction by the human.
- Whether the accepted `created_at` string forms should be narrowed (see Known limits).
- Whether payload integers should be bounded more tightly, for example to signed 64-bit (see Known limits).
- Spec note: the `events` DDL comment gives `'TaskStarted'` as an example `type`, which is not one of the 11 event types. The spec was not edited; the fix is listed in `docs/progress.md` under Later.

### Follow-ups
The M1 items listed under "Out" in Scope, each to get its own task record:
- `EventStore` port (Protocol) in `ports/`.
- SQLite adapter: `events` table DDL, WAL mode, idempotent append keyed on `event_id`, read by stream.
- Per-event-type payload models.
- Projection tables and replay.
- Spec YAML models, loader, validation rules, hashing, `spec_version`.
- CLI commands `init`, `validate`, `approve spec`, `events`.
- `domain/states.py` task state machine.
