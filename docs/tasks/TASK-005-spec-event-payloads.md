# TASK-005: Payload models for the spec events

- Milestone: M1
- Status: done
- Tests: acceptance
- Spec sections (spec v1.4): "Domain model and storage" ("Event payloads", "Event envelope rules", "Ids"); "Spec input format" ("Hashing", "Spec versions"); "Tech stack and repo layout"

## Objective
Add the pure domain payload models for the three M1 spec events (`SpecImported`, `SpecValidated`, `SpecApproved`) and one mapping from event type to payload model, so later M1 tasks (projector and rebuild, `validate`, `approve spec`) build and check event payloads through one validated shape.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- A new pure module `domain/payloads.py` with:
  - `SpecImportedPayload`: `spec_version`, `hash`, `spec` (a `SpecSet`).
  - `SpecValidatedPayload`: `spec_version`, `hash`, `violations`, `warnings`.
  - `RecordedViolation`: `rule` (a plain string), `subject`, `message` (the entry type of `violations`).
  - `SpecApprovedPayload`: `spec_version`, `hash`.
  - `SpecWarning`: `check`, `subject`, `message` (the entry type of `warnings`).
  - `PAYLOAD_MODELS`: a mapping from `EventType` to its payload model, holding the three M1 entries.
- Unit tests, building payloads from Python dicts and from existing domain models (no files, no YAML, no database).

Out (follow-up tasks, not this one):
- Payload models for `PlanCreated`, `PlanApproved`, `TaskStateChanged`, `AgentRunStarted` and `AgentRunFinished`. They are M2 and are added to `PAYLOAD_MODELS` there. The payloads of `GateEvaluated`, `CommitRecorded` and `ImpactComputed` are "defined when their milestones are planned".
- The projector, the projection tables `spec_versions`, `requirements` and `adrs`, the last-applied `seq` table and rebuild. The projector is what validates a stored payload against its model and fails on a mismatch; this task only provides the models and the mapping.
- Any change to `Event` or `StoredEvent`. `Event` stays generic (decision of 2026-10-08, gap G10), and the tests in `tests/unit/test_domain_events.py` stay unchanged.
- Choosing the next `sv_NN` id, the draft and approved logic, streams, actors and `causation_id` for these events, and the `validate` and `approve spec` use cases.
- The YAML loader, the PyYAML dependency, the `schema` rule and the conversion of `pydantic.ValidationError` into `SpecViolation` (stays in `docs/progress.md` under Later).
- The `policies.yaml` model and its hash.
- CLI commands `init`, `validate`, `approve spec`, `events`.
- Checking that `hash` equals the hash of `spec` (see Interpretations, item 3).
- Payload depth limit (stays under Later).

## Acceptance criteria
Each criterion cites the spec v1.4 heading it traces to. "Event payloads" means the block of that name under "Domain model and storage", including the payload shapes listed in it. "Example spec set" means the spec's `requirements.yaml` example plus an ADR with id `ADR-001`, status `accepted` and a body.

- [x] AC1 ("Tech stack and repo layout": `payloads.py # one payload model per event type` and "the domain never imports infrastructure"; Event payloads: "Each event type has one payload model in the domain"): `openfactory.domain.payloads` defines `SpecImportedPayload`, `SpecValidatedPayload` and `SpecApprovedPayload`. `PAYLOAD_MODELS[EventType.SpecImported]`, `PAYLOAD_MODELS[EventType.SpecValidated]` and `PAYLOAD_MODELS[EventType.SpecApproved]` are those three classes, and `PAYLOAD_MODELS` has no other key. The module imports nothing from `openfactory.adapters`, `openfactory.app` or `openfactory.ports` (checked by parsing imports with `ast`).
- [x] AC2 (Event payloads: the `SpecImported` shape, "`spec: { components, requirements, adrs }` # the full canonical spec set, ADR bodies included"): `SpecImportedPayload` validates from a dict with `spec_version` `"sv_01"`, a 64 hex `hash`, and `spec` given as the example spec set in dict form. The result exposes `spec` as a `SpecSet` whose components, requirements (with their acceptance criteria, `constrained_by` and `deprecated`) and ADRs (with `status` and `body`) equal the input. It also validates when `spec` is passed as a `SpecSet` instance. Leaving out any one of `spec_version`, `hash` or `spec` raises `pydantic.ValidationError`.
- [x] AC3 (Event payloads: the `SpecValidated` shape, "`violations: [ { rule, subject, message } ]`" and "`warnings: [ { check, subject, message } ]` # always empty in Phase 1"): `SpecValidatedPayload` validates with `violations` built from the list returned by `validate_spec` on a spec set that breaks at least two rules, each `SpecViolation` converted to a `RecordedViolation(rule, subject, message)` with `rule` as the rule's string value (for example `"id-format"`). It exposes each entry as a `RecordedViolation` whose `rule` is a `str` and whose `rule`, `subject` and `message` equal the source violation's, in the same order. A `rule` string that is not a value of the `Rule` enum (for example `"schema"` or `"some-renamed-rule"`) is accepted. It validates with `violations` and `warnings` both empty. A `warnings` entry with `check`, `subject` and `message` is accepted and exposed as a `SpecWarning`. Leaving out any one of `spec_version`, `hash`, `violations` or `warnings` raises `pydantic.ValidationError`.
- [x] AC4 (Event payloads: the `SpecApproved` shape): `SpecApprovedPayload` has exactly the fields `spec_version` and `hash`. It validates from `{"spec_version": "sv_02", "hash": "<64 hex>"}`, and leaving out either field raises `pydantic.ValidationError`.
- [x] AC5 (Event payloads: "the models forbid unknown fields"; "Spec versions": "an id of the form `sv_NN` (two digits, counted from `sv_01`, wider when needed)"; "Hashing": "written as 64 lowercase hex characters"): each of the three payload models, `RecordedViolation` and `SpecWarning`, raises `pydantic.ValidationError` when given a field that is not in its shape (for example `approved_by` on `SpecApprovedPayload`, or a misspelt `violation` on `SpecValidatedPayload`). On all three models, `spec_version` accepts `sv_01`, `sv_12` and `sv_100` and rejects `sv_1`, `v_01`, `SV_01` and the empty string; `hash` accepts the result of `content_hash` on a spec set and rejects a 63 character value, a 64 character value with an uppercase letter, and a 64 character value with a non-hex letter.
- [x] AC6 (Event payloads: "Use cases build events through these models" and "Each payload carries everything its projections hold, because the spec files and an LLM's reply cannot be read again at replay"; "Event envelope rules": "`payload`: a JSON object"): for each of the three payload models, `payload.model_dump(mode="json")` is accepted as the `payload` of `Event.new(...)` with the matching `EventType`. After that event goes through `model_dump_json()` and `Event.model_validate_json()`, `PAYLOAD_MODELS[event.type].model_validate(event.payload)` returns a model equal to the original. For `SpecImportedPayload` this holds for a spec set with a multi-line ADR body containing non-ASCII text, a requirement with `deprecated` set to `true`, and a requirement with two acceptance criteria; and the hash of the `spec` read back, computed with `content_hash`, equals the hash of the original spec set. For `SpecValidatedPayload` it holds with a non-empty `violations` list.

## Interpretations
The spec leaves these open. All six were confirmed by the human on 2026-10-08, before tests were written. Item 1 was answered with the planner's alternative, item 2 with an addition, items 3 to 6 as proposed.

1. Type of a violation entry. The spec gives `{ rule, subject, message }`. Confirmed: `violations` is `list[RecordedViolation]`, a payload-only model with `rule: str`, `subject: str` and `message: str`, so an old event can always be replayed even if a rule is renamed or removed later. The payload does not reuse `SpecViolation` and its closed `Rule` enum; the use case (later task) converts each `SpecViolation` to a `RecordedViolation`. A `schema` rule therefore needs no change here.
2. "The full canonical spec set". Confirmed: `spec` is a `SpecSet`, and the payload model does not reorder it. The import use case (later task) stores the spec set in canonical order, sorted as for hashing.
3. No cross-check between `hash` and `spec`. Confirmed: the model checks only the form of `hash`; the use case computes it.
4. Required fields. Confirmed: every field of the three payloads is required, including `violations` and `warnings`, so a stored event always states them. The use case passes an empty `warnings` list in Phase 1.
5. Names and the mapping. The spec names the module (`domain/payloads.py`) but not the classes. Confirmed: `SpecImportedPayload`, `SpecValidatedPayload`, `SpecApprovedPayload`, `RecordedViolation`, `SpecWarning`, and `PAYLOAD_MODELS: dict[EventType, type[BaseModel]]` holding only the event types whose models exist. What the projector does with an event type that has no entry is decided in the projector task.
6. Form of `spec_version`. Confirmed pattern: `^sv_\d{2,}$`, from "two digits ... wider when needed". `sv_00` matches the pattern and is not rejected; ids are chosen by the use case, counted from `sv_01`.

Spec gaps reported with this plan (what `validate` records when the files cannot be loaded; whether `policies.yaml` violations go into `SpecValidated.violations`; no port for reading spec files; the meaning of "canonical" for the stored spec set) do not block this task. The human will resolve them in a spec update before the loader and `validate` tasks.

Kept as already decided: the payload models are frozen and forbid unknown fields like the other domain models; `Adr` inside `spec` still ignores unknown fields (decision of 2026-10-08, TASK-003), so a dumped payload never contains them.

## Plan
1. Create branch `task/TASK-005-spec-event-payloads` from an up-to-date main.
2. Get the human's answers to Interpretations 1 to 6 and record them here and in `docs/decisions.md` (done 2026-10-08; AC3 adjusted for item 1).
3. Write failing tests in `tests/unit/test_payloads.py`, one or more per criterion AC1 to AC6, building payloads from Python dicts and from `SpecSet`, `validate_spec` and `content_hash`.
4. Add `src/openfactory/domain/payloads.py`: two annotated string types (spec version id, 64 lowercase hex hash), `RecordedViolation`, `SpecWarning`, the three payload models as frozen Pydantic v2 models with `extra="forbid"`, and `PAYLOAD_MODELS`. It imports only from `openfactory.domain`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, and `uv run python scripts/check_docs.py` until all are green.
6. Update living docs and this record's Outcome; commit with trailers `Task: TASK-005` and `Milestone: M1`.

## Files expected to change
- `src/openfactory/domain/payloads.py` (new)
- `tests/unit/test_payloads.py` (new)
- `docs/architecture.md` (Components: add "Event payloads"; Data flow: use cases build payloads through the models)
- `docs/progress.md` (Current task, then Done)
- `docs/decisions.md` (rows for the confirmed interpretations)
- `docs/tasks/TASK-005-spec-event-payloads.md` (this record; Outcome at close)

Not expected to change: `src/openfactory/domain/events.py`, `src/openfactory/domain/models.py`, `src/openfactory/domain/spec_validation.py`, `src/openfactory/domain/spec_hash.py`, and every existing test file.

## Living docs to update
- `docs/architecture.md`: Components and Data flow.
- `docs/progress.md`: Current and Done.
- `docs/decisions.md`: the confirmed interpretations.
- `CHANGELOG.md`: no entry expected (no user-visible change).
- `README.md`: no change expected.

## New dependencies
None. Pydantic v2 is already declared in `pyproject.toml`.

## Outcome
Built as planned:
- `domain/payloads.py` with `SpecImportedPayload`, `SpecValidatedPayload`, `SpecApprovedPayload`, the entry models `RecordedViolation` and `SpecWarning`, and `PAYLOAD_MODELS` holding the three M1 entries. All five models are frozen and forbid unknown fields. `spec_version` and `hash` are two annotated string types, `SpecVersionId` (`^sv_\d{2,}$`) and `ContentHash` (`^[0-9a-f]{64}$`).
- 60 tests in `tests/unit/test_payloads.py`.

Deviations from plan: none. `violations` holds the payload-only `RecordedViolation` with `rule: str`, not `SpecViolation`, as the human answered Interpretation 1 before tests were written; AC3, AC5 and the scope were adjusted then.

Test edits: none. The test-writer's tests are unchanged.

Notes on how the tests read the criteria (test-writer's choices, not changed):
- The "example spec set" in AC2 and AC6 is a spec set written for the tests with the stated features, not the spec's literal `requirements.yaml` example.
- In the AC6 fixture, the requirement with `deprecated` set to `true` is also the one with two acceptance criteria.
- AC4's "exactly the fields" is checked through `model_fields`.

Follow-ups:
- Spec gaps reported with the plan, to be resolved in a spec update before the loader and `validate` tasks: what `validate` records when the spec files cannot be loaded; whether `policies.yaml` violations go into `SpecValidated.violations`; no port for reading spec files; the meaning of "canonical" for the stored spec set.
- Later tasks: the use case converts `SpecViolation` to `RecordedViolation`; the import use case stores the spec set in canonical order.
