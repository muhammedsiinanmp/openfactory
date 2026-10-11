# TASK-021: Payload models for the plan, task and agent run events

- Milestone: M2
- Status: done
- Tests: acceptance
- ADR: ADR-007 (accepted), with its 2026-10-11 amendment. It covers one payload model per event type in `domain/payloads.py`, the one mapping, unknown fields forbidden, every own field required, shape-only checks, ids fixed in the event, and closed sets held under the widen-only rule (`PlanCreated.tasks` holds `TaskContract`). ADR-012 (accepted) states that the types of `AgentRunFinished` "follow the rules of ADR-007 and need no decision here". The task adds no event type, port, adapter, dependency or storage change, and the shapes are the ones spec v1.10 gives. Names, the spelling of `from` and the id types are rows in `docs/decisions.md` (Open questions 2 and 3).
- Spec impact: none. Spec v1.10 gives every field, its nullability and its closed set for the five payloads, and the forms of the ids.
- Spec sections (spec v1.10): "Domain model and storage" ("Event payloads", "Projection rules", "Ids", "Event types in Phase 1", "Event envelope rules"); "Task contract" (the class block; "Planning": the plan and run id forms); "Task state machine"; "Spec input format" ("Hashing": the form of a hash); "Tech stack and repo layout"

## Objective
Add the pure domain payload models for `PlanCreated`, `PlanApproved`, `TaskStateChanged`, `AgentRunStarted` and `AgentRunFinished`, exactly as spec v1.10 gives their shapes, and register them in `PAYLOAD_MODELS`, so the M2 projector and use-case tasks build and check these events through one validated shape.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- Five frozen models in `src/openfactory/domain/payloads.py`, with unknown fields forbidden and every field required: `PlanCreatedPayload`, `PlanApprovedPayload`, `TaskStateChangedPayload`, `AgentRunStartedPayload`, `AgentRunFinishedPayload` (names per Open question 3).
- The id and closed-set types they need, in the same module: plan id, run id, task id, run role, run exit (Open question 3). `SpecVersionId` and `ContentHash` are reused as they are. `TaskContract` and `TaskState` are imported from `domain/contracts.py` and `domain/states.py`.
- Five new entries in `PAYLOAD_MODELS` (Open question 1).
- Unit tests in a new file, building payloads from Python dicts. No files, no database, no LLM.
- One test with literal stored payloads, one per closed value, so a later rename or narrowing of a closed set fails a test (the fixture that finding F-9 of `docs/spec-audits/2026-10-11-proposal-v1.10.md` left to "the M2 payload task"; Open question 4).
- One conformance test in `tests/unit/test_spec_conformance.py`: the field names of each of the five payloads in the spec's payload block equal the model's (Open question 4).
- The edits to three places in existing tests that registration forces, only if the human approves them (Open question 1).

Out (later outline items, not this task):
- The `plans`, `tasks`, `task_deps` and `agent_runs` tables and any projector handling of the five events (item 3). After this task the projector validates the five payloads and writes nothing for them, as it does for `SpecValidated`. No file under `src/openfactory/adapters/` changes.
- Read ports and adapters (item 4), contract completion and the policy hash (item 5), plan checks (item 6), the LLM and git ports (items 7, 8), every use case and command (items 9 to 12).
- Who builds these events, their streams, actors and `causation_id`, the choice of ids, and the sorting of `PlanCreated.tasks` by `task_id`. The model does not sort or reorder `tasks`, as `SpecImportedPayload` does not reorder `spec` (ADR-007: "Payload models check shape only").
- Checks across fields, events or tasks, other than `reason` (AC3):
  - `from` to `to` against `TRANSITIONS` (TASK-020: `TRANSITIONS` is data; ADR-009: the projector does not check event sequences).
  - Duplicate task ids or an empty list in `PlanCreated.tasks`.
  - `error` against `exit`.
  - `policy_hash` or `context_hash` against any content.
- The payloads of `GateEvaluated`, `CommitRecorded` and `ImpactComputed` (spec: "defined when their milestones are planned"). They get no entry in `PAYLOAD_MODELS`.
- Any change to `Event`, `StoredEvent`, `domain/contracts.py`, `domain/states.py`, `domain/models.py`, `domain/policy.py`.
- Hardening against exotic inputs: negative or non-finite numbers, numeric strings, booleans where a number is expected, an empty `reason`, `error`, `model` or `runtime` string.

## Acceptance criteria
Each criterion cites the spec v1.10 text it traces to. "Event payloads" is the block of that name under "Domain model and storage", including the payload shapes in its code block. "The example contract" is the YAML block under "Task contract" that starts `task_id: AUTH-002`, as a dict. `HASH` is any 64 lowercase hex string. Class and type names follow the proposed answers to Open questions 2 and 3, and the `PAYLOAD_MODELS` bullets follow Open question 1; if the human answers otherwise, the names change and the assertions do not, except where Open question 1 says a bullet moves.

- [x] AC1 (Event payloads: "Each event type has one payload model in the domain, and the models forbid unknown fields. Every field of a payload model is required, nullable ones included"; "The payloads of `GateEvaluated`, `CommitRecorded` and `ImpactComputed` are defined when their milestones are planned"; "Tech stack and repo layout": "`payloads.py # one payload model per event type`" and "the domain never imports infrastructure"):
  - `PAYLOAD_MODELS` has exactly eight keys: the three M1 entries unchanged, and `PlanCreated`, `PlanApproved`, `TaskStateChanged`, `AgentRunStarted` and `AgentRunFinished` mapped to the five new classes. `GateEvaluated`, `CommitRecorded` and `ImpactComputed` have no entry.
  - For each of the five models, leaving out any one field raises `pydantic.ValidationError`. This includes the nullable ones: `reason`; `task_id` on `AgentRunStarted`; `model`, `tokens_in`, `tokens_out`, `cost_usd` and `error`.
  - For each of the five models, an unknown key raises it.
  - `openfactory.domain.payloads` imports nothing from `openfactory.adapters`, `openfactory.app` or `openfactory.ports` (the existing `ast` test still passes).
  - In `tests/unit/test_spec_conformance.py`, parsed from the spec's payload code block: for each of the five events, the field names listed under it equal the model's field names as they appear in a dumped payload (so `from`, not a Python-side name).
- [x] AC2 (Event payloads: the `PlanCreated` shape, "`tasks: [ TaskContract ] # complete contracts, as the orchestrator stored them ... the lists inside a contract keep their order`", and the `PlanApproved` shape; "Task contract", "Planning": "Plan ids are `plan_NN` and run ids `run_NNNN`, counted from `plan_01` and `run_0001`, wider when needed"; "Hashing": "written as 64 lowercase hex characters"):
  - `PlanCreatedPayload` validates from `{plan_id: "plan_01", spec_version: "sv_01", policy_hash: HASH, run_id: "run_0001", tasks: [...]}` with two contracts in dict form (the example contract and a second one).
  - Each entry of `tasks` is a `TaskContract`, and `model_dump(mode="json")` equals the input, with `tasks` and every list inside a contract in the order given.
  - A `tasks` entry without `required_gates` or without `limits` (a `PlannedTask` shape) raises `pydantic.ValidationError`.
  - `plan_id` accepts `plan_01` and `plan_100` and rejects `plan_1`, `Plan_01` and the empty string.
  - `run_id` accepts `run_0001` and `run_12345` and rejects `run_001` and `run_1`.
  - `policy_hash` rejects a 63 character value and a 64 character value with an uppercase letter.
  - `PlanApprovedPayload` has exactly the field `plan_id` and validates from `{plan_id: "plan_01"}`.
- [x] AC3 (Event payloads: the `TaskStateChanged` shape, "`from: "pending"`", "`to: "ready"`", "`reason: null | "<text>" # required when to = invalidated`"; "Event types in Phase 1": "invalidation is a `TaskStateChanged` to `invalidated` with a reason in its payload"; "Task state machine": the nine states):
  - `TaskStateChangedPayload` validates from the spec's example, `{"task_id": "AUTH-002", "from": "pending", "to": "ready", "reason": null}`.
  - `model_dump(mode="json")`, with no further argument, returns exactly that dict: the key is `from`.
  - With `to: "invalidated"`, a text `reason` validates and a null `reason` raises `pydantic.ValidationError`.
  - A text `reason` with another `to` validates.
  - A `from` or a `to` outside the nine states (for example `done`) raises it.
- [x] AC4 (Event payloads: the `AgentRunStarted` and `AgentRunFinished` shapes; "`task_id: null | "AUTH-002" # null for a planner or classifier run`"; "`AgentRunStarted.role` is one of `planner`, `implementer`, `reviewer`, `classifier`"; "`exit: "ok" | "error" | "timeout"`"; "`tokens_in: <int> | null # null when the runtime reported none`"; "`duration_s: <float>`"; "`error: null | "<text>"`"):
  - `AgentRunStartedPayload` validates from `{run_id: "run_0001", task_id: null, role: "planner", runtime: "claude-code", context_hash: HASH}`, and with `task_id: "AUTH-002"`.
  - A `role` outside the four (for example `coder`) raises `pydantic.ValidationError`, as does a `context_hash` that is not 64 lowercase hex.
  - `AgentRunFinishedPayload` validates with every reported value set: `exit: "ok"`, a model name, integer `tokens_in` and `tokens_out`, float `cost_usd` and `duration_s`, `error: null`.
  - It also validates as a failed process records it: `exit: "timeout"`; `model`, `tokens_in`, `tokens_out` and `cost_usd` all null; `duration_s` a float; `error` a text.
  - `duration_s: null` raises it, and so does an `exit` outside the three (for example `failed`).
- [x] AC5 (Event payloads: "The closed sets a stored payload holds (a requirement's `priority`, an ADR's `status`, a task's `role` and `required_gates`, a run's `role` and `exit`, and the task states) may be widened but never renamed or narrowed, so every stored event still validates"): a table of stored payloads written in the test as literal dicts and strings, not built from the code's enums or `Literal`s, each validating against `PAYLOAD_MODELS[<type>]`:
  - one `TaskStateChanged` per task state, as `to` (nine) and as `from` (nine);
  - one `AgentRunStarted` per run role (four);
  - one `AgentRunFinished` per `exit` (three);
  - one `PlanCreated` whose contract has `role: implementer` and all five gate names.
- [x] AC6 (Event payloads: "Use cases build events through these models. The envelope itself accepts any JSON object; the projector validates each payload against its model before applying it and fails on a mismatch"; "Event envelope rules": "`payload`: a JSON object"; "Projection rules": "An event type whose milestone has not added a payload model is skipped by the projector"):
  - For each of the five models, `payload.model_dump(mode="json")` is accepted as the `payload` of `Event.new(...)` with the matching `EventType`.
  - After that event goes through `model_dump_json()` and `Event.model_validate_json()`, `PAYLOAD_MODELS[event.type].model_validate(event.payload)` equals the original. This holds for `PlanCreatedPayload` with two contracts, for `TaskStateChangedPayload`, and for `AgentRunFinishedPayload` with its nullable fields null.
  - In `tests/integration/test_sqlite_projector.py` (tests added): `SqliteProjector.apply` on a stored `TaskStateChanged` with a valid payload changes no row of the M1 tables.
  - In the same file: `apply` on a stored `TaskStateChanged` whose payload the model rejects (for example without `reason`) raises `pydantic.ValidationError` and writes nothing.

## Architecture rules that apply
- `src/openfactory/domain` stays pure: `payloads.py` imports only from `openfactory.domain` (`events`, `models`, `contracts`, `states`) and Pydantic.
- A payload model is a contract with the stored log (ADR-007). Shape only; every own field required with no default; unknown fields forbidden. `TaskContract` inside `PlanCreated` keeps its own defaults (ADR-007 amendment, SC-40); the use case writes every field explicitly, in a later task.
- Closed sets in these payloads (`role`, `required_gates`, run `role`, `exit`, task states) are widened only from the first stored event (ADR-007 amendment, SC-35). AC5 is the test that holds this.
- "All state changes go through the events table": no event is recorded and no projection is written here.
- Tests from the test-writer are fixed. The three edits listed in Open question 1 are not mechanical fixes and need the human's approval before the session makes them; each is reported in the Outcome.

## Plan
1. Create branch `task/TASK-021-m2-event-payloads` from an up-to-date main.
2. Get the human's answers to Open questions 1 to 4. Record them here and as rows in `docs/decisions.md`.
3. Write failing tests:
   - `tests/unit/test_m2_payloads.py` for AC1 to AC6, in the style of `tests/unit/test_payloads.py` (a `kwargs_for(name, **overrides)` helper, parametrised over the five model names).
   - Two tests added to `tests/integration/test_sqlite_projector.py` for AC6's last two bullets.
   - One parametrised test added to `tests/unit/test_spec_conformance.py` for AC1's last bullet. Use `code_block("PlanCreated\n  plan_id")` or a similar marker that matches exactly one block; by that file's convention the test skips until the code exists.
4. If Open question 1 is answered as proposed, make the three approved edits to existing tests and nothing else in those files.
5. Extend `src/openfactory/domain/payloads.py`:
   - the id and closed-set types;
   - the five models with `ConfigDict(frozen=True, extra="forbid")`;
   - on `TaskStateChangedPayload`, the `from` alias with serialisation by alias, and one validator for `reason` when `to` is `invalidated`;
   - the five `PAYLOAD_MODELS` entries;
   - the module docstring no longer says "for the M1 spec events".
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
7. Update the living docs and this record's Outcome. Commit with subject `feat(domain): add the payload models for the plan, task and agent run events` and trailers `Task: TASK-021` and `Milestone: M2`.

## Files expected to change
- `src/openfactory/domain/payloads.py` (about 70 lines added)
- `tests/unit/test_m2_payloads.py` (new, about 200 lines)
- `tests/unit/test_spec_conformance.py` (one parametrised test added; nothing existing changed)
- `tests/integration/test_sqlite_projector.py` (two tests added; two existing places edited per Open question 1)
- `tests/unit/test_payloads.py` (one existing test edited per Open question 1)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-021-m2-event-payloads.md` (this record; Outcome at close)

Not expected to change: every module under `src/openfactory/adapters/`, `app/`, `ports/` and `cli.py`; `domain/contracts.py`, `domain/states.py`, `domain/events.py`; `pyproject.toml`; `docs/adr/`; `docs/spec/`; every other existing test file. `tests/integration/test_sqlite_recorder.py` already uses a valid `TaskStateChanged` payload (`task_event()`), so it needs no edit.

## Living docs to update
- `docs/architecture.md`:
  - "Event payloads": the five models, the new types, the `from` alias, the `reason` rule, and `PAYLOAD_MODELS` now holding eight entries.
  - "SQLite projector": the five M2 events are validated and write nothing yet.
  - "Data flow": the last sentence, which says the contract models and states are used by nothing yet.
- `docs/progress.md`: Current, then Done; remove item 2 from the M2 outline and point the "depends on 2" of item 3 at TASK-021.
- `docs/decisions.md`: rows for the answered open questions.
- `CHANGELOG.md` and `README.md`: no change (nothing a user sees).

## New dependencies
None. `serialize_by_alias` needs Pydantic 2.11 or later; `pyproject.toml` already requires `pydantic>=2.13.5`.

## Spec gaps
None. Three readings to record; none is a gap.
- "`reason` ... required when to = invalidated" is enforced by the payload model. Every payload field is already required, so "required" here can only mean non-null, and the payload model is the only validation a stored payload gets ("the payload models are the validation"). A text `reason` with another `to` is allowed, since the shape is `null | "<text>"`.
- `task_id` in `TaskStateChanged` and `AgentRunStarted` takes the form the spec gives a task id in `PlannedTask` (`^[A-Z]+-\d{3}$`), as the M1 payloads check the form of `sv_NN` (Open question 3).
- The spec states no constraint on the numbers in `AgentRunFinished` and no link between `exit` and `error` in the payload shape, so the model adds none.

## Open questions
1. **Registering the five models in `PAYLOAD_MODELS`, and three edits to fixed tests.** Once the models are registered, the projector validates these events instead of skipping them, and existing tests that feed it a made-up `TaskStateChanged` payload fail. Proposed: register in this task (TASK-005 and TASK-020 both left the `PAYLOAD_MODELS` change to this outline item, and ADR-007 names one mapping) and approve these edits, which keep each test's intent:
   - `tests/unit/test_payloads.py::test_ac1_payload_models_map_from_event_types_with_no_other_keys`: assert the three M1 entries are in `PAYLOAD_MODELS` rather than that they are its only keys. The exact key set moves to AC1 of this task.
   - `tests/integration/test_sqlite_projector.py::test_ac5_event_type_without_projection_is_ignored` (payload `{"to": "ready", "anything": [1, 2]}`): change the event type to `EventType.GateEvaluated`, which still has no model.
   - `build_log` in the same file (payload `{"to": "ready"}`, used by the four AC6 rebuild tests): the same change of type.

   Alternative: define the five models here and leave the `PAYLOAD_MODELS` entries, with these edits, to outline item 3. Then no existing test changes in this task, and three things move to item 3: the first bullet of AC1, the `PAYLOAD_MODELS` lookups in AC5 and AC6 (the tests name the classes directly instead), and the last two bullets of AC6.
2. **Spelling of `from`.** `from` is a Python keyword. Proposed:
   - the field is `from_` with `alias="from"`;
   - the model config has `serialize_by_alias=True`, so the plain `model_dump(mode="json")` every use case already calls writes `from`;
   - the config also has `validate_by_name=True`, so code can pass `from_=`.

   Callers then follow no new convention. The alternative, `model_dump(by_alias=True)` at each call site, would be a convention other code must follow and would need an ADR.
3. **Names and types.** Proposed:
   - classes `PlanCreatedPayload`, `PlanApprovedPayload`, `TaskStateChangedPayload`, `AgentRunStartedPayload`, `AgentRunFinishedPayload`;
   - `PlanId` (`^plan_\d{2,}$`), `RunId` (`^run_\d{4,}$`) and `TaskId` (`^[A-Z]+-\d{3}$`) as annotated strings next to `SpecVersionId`;
   - `RunRole = Literal["planner", "implementer", "reviewer", "classifier"]` and `RunExit = Literal["ok", "error", "timeout"]`;
   - `from` and `to` typed as `TaskState`;
   - `runtime`, `model`, `reason` and `error` as plain strings.

   `TaskId` repeats the pattern that `PlannedTask.task_id` holds inline, because `domain/contracts.py` is not changed here; a plain `str` for `task_id` is the alternative.
4. **The closed-value table and the conformance test.** Proposed:
   - AC5's table is literal dicts in `tests/unit/test_m2_payloads.py`, not committed fixture files;
   - the conformance test covers the five M2 payloads only.

   F-9 of the v1.10 proposal audit said a fixture of one stored event per closed value "can wait for the M2 payload task". A `priority` and an ADR `status` value are already exercised by the M1 payload tests and are not added.

Answers (human, 2026-10-11): all four approved as proposed. The models are registered in this task and the three edits to existing tests under question 1 are approved.

## Outcome
**Built**
- `src/openfactory/domain/payloads.py`: frozen `PlanCreatedPayload`, `PlanApprovedPayload`, `TaskStateChangedPayload`, `AgentRunStartedPayload` and `AgentRunFinishedPayload` (`extra="forbid"`, every field required), the types `PlanId`, `RunId`, `TaskId`, `RunRole` and `RunExit`, and five new `PAYLOAD_MODELS` entries (eight in total). `TaskStateChangedPayload` has the field `from_` with alias `from`, `serialize_by_alias=True` and `validate_by_name=True`, and a validator that rejects a null `reason` when `to` is `invalidated`.
- No file under `adapters/`, `app/`, `ports/` or `cli.py` changed. The projector now validates the five M2 events and writes nothing for them.
- Tests: `tests/unit/test_m2_payloads.py` (AC1 to AC6), one parametrised test in `tests/unit/test_spec_conformance.py`, two tests in `tests/integration/test_sqlite_projector.py`.

**Human-approved edits to existing tests** (Open question 1)
- (a) `tests/unit/test_payloads.py::test_ac1_payload_models_map_from_event_types_with_no_other_keys` now asserts the three M1 entries are present in `PAYLOAD_MODELS`; the name is kept.
- (b) `tests/integration/test_sqlite_projector.py::test_ac5_event_type_without_projection_is_ignored` uses `EventType.GateEvaluated`.
- (c) `build_log` in the same file likewise.

**Deviations from the plan**
- Mechanical fix to a test-writer test: the literal `STATES` table in `tests/unit/test_m2_payloads.py` had `blocked` and `cancelled`, which are not spec states; they are replaced by `escalated` and `abandoned`, so the table holds the spec's nine states. The assertion's intent is unchanged.
- Addition by the test-writer beyond the criteria: `test_ac5_the_table_has_the_expected_number_of_rows`, a guard on the table size (26).

**Follow-ups**
- The test in (a) keeps a name ("with_no_other_keys") that no longer matches its assertion.
- (b) and (c) need the same change again when `GateEvaluated` gets a model.
- pyright rejects `from_=` in typed code (the reviewer probed it); it works at run time only. Settle this when the first `src/` caller is written; the candidates are `validation_alias`/`serialization_alias` or dropping `validate_by_name`, and nothing stored changes. Under Later in `docs/progress.md`, with the two test follow-ups above.
- Parametrising the payload field-name conformance test over every `PAYLOAD_MODELS` key is under Later in `docs/progress.md`.
