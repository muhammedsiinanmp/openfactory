# TASK-001: Domain event model (envelope and event types)

- Milestone: M1
- Status: planned
- Spec sections: "Domain model and storage"; "Tech stack and repo layout"

## Objective
Add the pure domain model for an event (the envelope matching the `events` table columns) and the closed set of 13 Phase 1 event type names, so later M1 tasks (event store, projections, replay) have a validated type to build on.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself; the only REQ id in the spec (`REQ-AUTH-001`) belongs to the demo target repo. Acceptance criteria below trace to spec headings instead, and tests for this task carry no `req` marker unless the human assigns ids (see Open questions).

## Scope
In:
- `EventType`: the 13 event type names listed in the spec.
- `Event`: a Pydantic v2 model whose fields mirror the `events` table columns.
- Unit tests for both.

Out (follow-up M1 tasks, not this one):
- `EventStore` port (Protocol) in `ports/`.
- SQLite adapter: `events` table DDL, WAL mode, idempotent append keyed on `event_id`, read by stream.
- Per-event-type payload models (payload shapes are not defined in the spec).
- Projection tables and replay.
- Spec YAML models, loader, validation rules, hashing, `spec_version`.
- CLI commands `init`, `validate`, `approve spec`, `events`.
- `domain/states.py` task state machine (not needed until tasks exist).

## Acceptance criteria
Each criterion cites the spec heading it traces to.

- [ ] AC1 ("Domain model and storage", "Event types in Phase 1"): `EventType` contains exactly these 13 values and no others: `SpecImported`, `SpecValidated`, `SpecApproved`, `PlanCreated`, `PlanApproved`, `TaskStateChanged`, `AgentRunStarted`, `AgentRunFinished`, `GateEvaluated`, `CommitRecorded`, `ImpactComputed`, `TaskInvalidated`, `ApprovalGiven`.
- [ ] AC2 ("Domain model and storage", `CREATE TABLE events`): `Event` exposes exactly the fields `seq`, `event_id`, `stream`, `type`, `payload`, `actor`, `causation_id`, `created_at`, named as the table columns are.
- [ ] AC3 ("Domain model and storage", `NOT NULL` columns): constructing an `Event` without any one of `event_id`, `stream`, `type`, `payload`, `actor`, `created_at` raises `pydantic.ValidationError`.
- [ ] AC4 ("Domain model and storage", `causation_id TEXT` is nullable; `seq` is `AUTOINCREMENT`): `causation_id` and `seq` may be omitted and are then `None`.
- [ ] AC5 ("Domain model and storage", `event_id ... -- uuid; idempotency key`): a valid UUID string is accepted as `event_id`; a non-UUID string such as `"not-a-uuid"` raises `ValidationError`.
- [ ] AC6 ("Domain model and storage", "Event types in Phase 1"): `type` accepts each of the 13 names; an unknown name such as `"TaskExploded"` raises `ValidationError`.
- [ ] AC7 ("Domain model and storage", `payload ... -- JSON, validated by Pydantic`): a payload of nested JSON values (strings, numbers, booleans, null, lists, objects) is accepted; a payload containing a non-JSON value (for example a `set` or an arbitrary object) raises `ValidationError`.
- [ ] AC8 ("Domain model and storage", `payload ... -- JSON`): an `Event` survives `model_dump_json()` followed by `Event.model_validate_json()` and compares equal to the original.
- [ ] AC9 ("Domain model and storage", `actor ... -- 'human' | 'orchestrator' | 'agent:implementer'`): each of `human`, `orchestrator`, `agent:implementer` is accepted as `actor`.
- [ ] AC10 ("Tech stack and repo layout": "the domain never imports infrastructure" and "domain/ # pure models, state machine, rules; no I/O"): `openfactory/domain/events.py` imports nothing from `openfactory.adapters`, `openfactory.app` or `openfactory.ports`, and does not import `sqlite3`, `subprocess` or `socket` (checked by parsing the module's imports with `ast`).

Test fixtures use the `created_at` value `"2026-10-08T12:00:00Z"` and only the three actor values above, so the criteria hold whichever way Open questions 3 and 4 are answered.

## Plan
1. Create branch `task/TASK-001-domain-event-model` from an up-to-date main.
2. Write failing tests in `tests/unit/test_domain_events.py`, one or more per criterion AC1 to AC10.
3. Implement `src/openfactory/domain/events.py`: `EventType` as a `StrEnum`; `Event` as a frozen Pydantic v2 `BaseModel` with `event_id: UUID`, `payload: dict[str, JsonValue]`, `causation_id` and `seq` optional and defaulting to `None`.
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
- `docs/decisions.md`: one row if the human answers the open questions with a small decision.

## New dependencies
None. Pydantic v2 is already declared in `pyproject.toml`.

## Open questions
1. The spec has no REQ ids for OpenFactory itself. Should tests carry `req` markers, and if so which ids?
2. No task ID scheme is defined for this repo's own tasks. Is `TASK-NNN` acceptable?
3. `actor`: is it a closed set (`human`, `orchestrator`, `agent:<role>` for planner, implementer, reviewer) with everything else rejected, or free text? The spec gives three example values only.
4. `created_at`: the column is `TEXT` with no format stated. Is it an ISO 8601 UTC timestamp, and should the model hold it as a timezone-aware datetime or a string?
5. `payload`: must the top level be a JSON object, or is any JSON value allowed? Payload fields per event type are not defined in the spec; should those models be specified by the human or proposed in a later task?
6. `seq`: the column is assigned by SQLite. Is one `Event` model with `seq` as `None` before persistence acceptable, or should unsaved and stored events be separate types?
7. `event_id`: any UUID version, or a specific one?

## Outcome
<!-- filled at close: what was built, deviations from plan, follow-ups -->
