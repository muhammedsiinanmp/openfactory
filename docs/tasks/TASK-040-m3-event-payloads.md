# TASK-040: Payload models for the gate and commit events

- Milestone: M3
- Status: done
- Tests: acceptance
- ADR: ADR-014 (accepted). "Events and tables (SC-57, SC-61)" gives both payloads field for field, their stream and actor, and why `files` is in the payload now; its Consequences name the edit to `test_ac5_event_type_without_projection_is_ignored` and `build_log`. ADR-007 (accepted, with its 2026-10-11 amendment) covers one model per event type in `domain/payloads.py`, the one mapping, unknown fields forbidden, every field required, shape-only checks and closed sets under the widen-only rule. The task adds no event type, port, adapter, dependency or storage change. Names and types are rows in `docs/decisions.md` (Open question 3).
- Spec impact: wording. One item, which does not stop the task (see "Spec gaps"): `sha: "<40 hex>"` does not say lowercase. No criterion depends on it; it is Open question 4.
- Spec sections (spec v1.12, SC-57): "Domain model and storage" › "Event payloads" (the `GateEvaluated` and `CommitRecorded` entries of the payload block; the closed-sets sentence; "The payload of `ImpactComputed` is defined when its milestone is planned"), "Projection rules" ("An event type whose milestone has not added a payload model is skipped by the projector"), "Streams and actors", "Event envelope rules", "Ids"; "Task contract" (the form of a task id); "Gates and remediation" (the five gate names in the table); "Tech stack and repo layout" (`payloads.py # one payload model per event type`)

## Outline item
M3 outline item 1, whole. Items 2 to 12 are left.

## Objective
Add the pure domain payload models for `GateEvaluated` and `CommitRecorded`, exactly as spec v1.12 gives their shapes, and register them in `PAYLOAD_MODELS`, so the M3 projector and run use case build and check these events through one validated shape.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings.

## Scope
In (names per Open question 3):
- Two frozen models in `src/openfactory/domain/payloads.py`, unknown fields forbidden, every field required:
  - `GateEvaluatedPayload`: `run_id`, `task_id`, `gate`, `passed`, `output_path`.
  - `CommitRecordedPayload`: `sha`, `task_id`, `run_id`, `branch`, `spec_version`, `files`.
- The two types they need, in the same module: the gate name (closed set of five) and the commit sha. `RunId`, `TaskId` and `SpecVersionId` are reused as they are.
- Two new entries in `PAYLOAD_MODELS` (ten in total). `ImpactComputed` still has none.
- Unit tests in a new file, built from Python dicts. No files, no database, no LLM.
- A literal table of stored `GateEvaluated` payloads, one per gate name, so a later rename or narrowing of the set fails a test ("`gate` joins the closed sets").
- The payload field-name conformance test, extended to the two new payloads (Open question 2).
- The edits to existing tests that registration forces, only with the human's approval (Open question 1).

Out (not this task):
- The `gate_results` and `commits` tables, any projector handling of the two events, and the `tasks.attempt` rule (outline item 2). After this task the projector validates the two payloads and writes nothing for them. No file under `src/openfactory/adapters/` changes.
- A test that a valid `GateEvaluated` or `CommitRecorded` "changes no row". Item 2 makes them insert rows, so such a test would be a fixed test the next task has to break.
- Who builds these events, their stream, actor and `causation_id`, and when `output_path` is null (items 9 and 10).
- Sorting `files`. The spec's "sorted as strings" is the use case's job; the model keeps the list as given, as `PlanCreatedPayload` does not reorder `tasks` (ADR-007: "Payload models check shape only").
- Checks across fields or events: `branch` against `task_id`, `output_path` against `passed`, `run_id` against a stored run, an empty `files` list, duplicate paths.
- The payload of `ImpactComputed` (spec: "defined when its milestone is planned").
- Any change to `Event`, `StoredEvent`, `domain/contracts.py`, `domain/states.py`, `domain/events.py`.
- Hardening against exotic inputs: `1` or `"true"` for `passed`, an empty `branch` or `output_path` string, absolute paths, a 64 character object id of a SHA-256 git repo.

## Acceptance criteria
"Event payloads" is the block of that name under "Domain model and storage", with the shapes in its code block. Class and type names follow the proposed answer to Open question 3; if the human answers otherwise, the names change and the assertions do not. `SHA` is any 40 lowercase hex string.

- [x] AC1 ("Event payloads": "Each event type has one payload model in the domain, and the models forbid unknown fields. Every field of a payload model is required, nullable ones included"; "The payload of `ImpactComputed` is defined when its milestone is planned"; "Tech stack and repo layout": "`payloads.py # one payload model per event type`"):
  - `PAYLOAD_MODELS` has exactly ten keys: the eight existing entries unchanged, and `GateEvaluated` and `CommitRecorded` mapped to the two new classes. `ImpactComputed` has no entry.
  - For each of the two models, leaving out any one field raises `pydantic.ValidationError`, the nullable `output_path` included.
  - For each of the two models, an unknown key raises it.
  - `openfactory.domain.payloads` imports nothing from `openfactory.adapters`, `openfactory.app` or `openfactory.ports` (the existing `ast` test still passes).
  - In `tests/unit/test_spec_conformance.py`, parsed from the spec's payload code block: the field names listed under `GateEvaluated` and under `CommitRecorded` equal the model's field names in a dumped payload, in the same order (the form of the test per Open question 2).
- [x] AC2 ("Event payloads": the `GateEvaluated` shape, "`gate: "path_check" # one of the five gate names`", "`passed: true | false`", "`output_path: null | "<path>" # relative to the repo; null when the gate wrote no file`"; "Gates and remediation": the gate table):
  - `GateEvaluatedPayload` validates from `{run_id: "run_0002", task_id: "AUTH-002", gate: "path_check", passed: true, output_path: null}`, and `model_dump(mode="json")` returns exactly that dict.
  - It validates with `passed: false` and `output_path: ".openfactory/runs/run_0002/path_check.txt"`.
  - A `gate` outside the five (for example `semgrep`) raises `pydantic.ValidationError`.
  - `run_id: "run_002"` and `task_id: "auth-2"` each raise it.
- [x] AC3 ("Event payloads": the `CommitRecorded` shape, "`sha: "<40 hex>"`", "`branch: "openfactory/AUTH-002"`", "`spec_version: "sv_01" # the plan's spec version`", "`files: [ "<path>" ] # the paths the commit changed, relative to the repo, sorted as strings`"):
  - `CommitRecordedPayload` validates from `{sha: SHA, task_id: "AUTH-002", run_id: "run_0002", branch: "openfactory/AUTH-002", spec_version: "sv_01", files: ["app/auth/login.py", "tests/auth/test_login.py"]}`, and `model_dump(mode="json")` returns exactly that dict, `files` in the order given.
  - `sha` rejects a 39 character value and a 40 character value that holds a `g`.
  - `spec_version: "v1"`, `run_id: "run_1"` and `task_id: "auth-2"` each raise `pydantic.ValidationError`.
  - `files: "app/auth/login.py"` (a string, not a list) raises it.
- [x] AC4 ("Event payloads": "The closed sets a stored payload holds (... a run's `role` and `exit`, a gate result's `gate`, and the task states) may be widened but never renamed or narrowed, so every stored event still validates"): a table of five stored `GateEvaluated` payloads written in the test as literal dicts, one per gate name (`path_check`, `ruff`, `pytest`, `gitleaks`, `review`), not built from the code's `Literal`; each validates against `PAYLOAD_MODELS[EventType.GateEvaluated]`.
- [x] AC5 ("Event payloads": "Use cases build events through these models. The envelope itself accepts any JSON object; the projector validates each payload against its model before applying it and fails on a mismatch"; "Streams and actors": the `GateEvaluated`, `CommitRecorded` row; "Projection rules": "An event type whose milestone has not added a payload model is skipped by the projector"):
  - For each of the two models, `payload.model_dump(mode="json")` is accepted as the `payload` of `Event.new(...)` with the matching `EventType`, stream `task:AUTH-002` and actor `orchestrator`.
  - After that event goes through `model_dump_json()` and `Event.model_validate_json()`, `PAYLOAD_MODELS[event.type].model_validate(event.payload)` equals the original. This holds for `GateEvaluatedPayload` with `output_path` null and for `CommitRecordedPayload` with two files.
  - In `tests/integration/test_sqlite_projector.py` (test added): `SqliteProjector.apply` on a stored `GateEvaluated` whose payload the model rejects (for example without `output_path`) raises `pydantic.ValidationError` and writes nothing.
  - In the same file, with the approved edit of Open question 1: an event of a type with no model (`ImpactComputed`, any payload) is still ignored, and the four rebuild tests that use `build_log` still pass.

## Architecture rules that apply
- `src/openfactory/domain` stays pure: `payloads.py` imports only from `openfactory.domain` and Pydantic.
- A payload model is a contract with the stored log (ADR-007). Shape only; every field required with no default; unknown fields forbidden; frozen.
- The gate names are a closed set held under the widen-only rule from the first stored event (spec, the closed-sets sentence). AC4 is the test that holds it. The names must stay equal to `REQUIRED_GATES` and the `required_gates` `Literal` in `domain/contracts.py`; a later widening touches both.
- "All state changes go through the events table": no event is recorded and no projection is written here.
- Tests from the test-writer are fixed. The edits in Open questions 1 and 2 are not mechanical fixes and need the human's approval before the session makes them; each is reported in the Outcome.
- OpenFactory's own tests carry no `req` markers.
- No hardening beyond the spec's shapes.

## Plan
1. Create branch `task/TASK-040-m3-event-payloads` from an up-to-date main.
2. Get the human's answers to Open questions 1 to 4. Record them here and as rows in `docs/decisions.md`.
3. Write failing tests:
   - `tests/unit/test_m3_payloads.py` (new) for AC1 to AC5, in the style of `tests/unit/test_m2_payloads.py` (`BASE`, `data_for`, `validate`, parametrised over the two model names).
   - One test added to `tests/integration/test_sqlite_projector.py` for AC5's third bullet.
   - The conformance test in `tests/unit/test_spec_conformance.py` per the answer to Open question 2.
4. Make the approved edits to existing tests (Open question 1) and nothing else in those files.
5. Extend `src/openfactory/domain/payloads.py`: the two types, the two models with `ConfigDict(frozen=True, extra="forbid")`, the two `PAYLOAD_MODELS` entries.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
7. Update the living docs and the Outcome. Commit `feat(domain): add the payload models for the gate and commit events` with trailers `Task: TASK-040` and `Milestone: M3`.

## Files expected to change
- `src/openfactory/domain/payloads.py` (about 35 lines added)
- `tests/unit/test_m3_payloads.py` (new, about 150 lines)
- `tests/unit/test_spec_conformance.py` (about 20 lines, per Open question 2)
- `tests/integration/test_sqlite_projector.py` (one test added; two existing places edited per Open question 1)
- `tests/unit/test_m2_payloads.py` (one existing test edited per Open question 1)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-040-m3-event-payloads.md` (this record; Outcome at close)

Not expected to change: every module under `src/openfactory/adapters/`, `app/`, `ports/` and `cli.py`; `domain/contracts.py`, `domain/states.py`, `domain/events.py`; `pyproject.toml`; `docs/adr/`; `docs/spec/`; `tests/unit/test_payloads.py`; every other existing test file. No other test builds a `GateEvaluated`, `CommitRecorded` or `ImpactComputed` event (`tests/unit/test_domain_events.py` only lists the names).

Expected size: about 250 lines with tests.

## Living docs to update
- `docs/architecture.md`:
  - "Event payloads": the two models, the two new types, and `PAYLOAD_MODELS` now holding ten entries with only `ImpactComputed` left without one.
  - "SQLite projector": the two M3 events are validated and write nothing yet.
- `docs/progress.md`: Current, then Done; remove outline item 1, renumber and keep the "depends on" references correct; remove the two Later lines this task takes; add the Later lines listed below.
- `docs/decisions.md`: rows for the answered open questions.
- `CHANGELOG.md` and `README.md`: no change (nothing a user sees).

## New dependencies
None.

## Spec gaps
Spec impact is "wording". The one item does not stop the task.

1. "Domain model and storage" › "Event payloads", the line `sha: "<40 hex>"` of `CommitRecorded`. For a content hash the spec says "written as 64 lowercase hex characters" ("Spec input format" › "Hashing"); for the sha it says "40 hex" and no case. The meaning is clear (a git commit id, which git prints in lowercase), but the model has to either accept uppercase letters or reject them. It does not block: no criterion uses an uppercase sha, and the only writer will pass what git prints. It is Open question 4 for the human, not an assumption of the task.

Readings, not gaps (each follows from the text as written):
- "One of the five gate names" is the five rows of the table under "Gates and remediation", the same five as `required_gates` and the comment on `gate_results.gate`.
- `task_id` takes the form the spec gives a task id (`^[A-Z]+-\d{3}$`), as in `TaskStateChanged` and `AgentRunStarted` (TASK-021).
- `spec_version` is in `CommitRecorded` and not in the `commits` table. "Each payload carries everything its projections hold" allows more; the column question belongs to item 2 and M5.
- The spec states no constraint on `branch` or `output_path` beyond being text, and none on the length of `files`, so the model adds none.

## Later lines in `docs/progress.md`: taken or left
- "When `GateEvaluated` gets a payload model (M3, SC-57), `test_ac5_event_type_without_projection_is_ignored` and `build_log` ... need another event type without a model (TASK-021, reviewer)": **taken, in scope.** Registration makes the projector validate their made-up `GateEvaluated` payloads, so five existing tests fail without the edit. ADR-014's Consequences already name this edit "with the human's approval"; the form is Open question 1.
- "Parametrise the payload field-name conformance test over every key of `PAYLOAD_MODELS` ... (TASK-021, advisor)": **taken, in scope, if the human approves** (Open question 2). The task must add conformance coverage for the two new payloads anyway, and the general form costs about the same lines as two more rows. If declined, two rows are added to the existing list and the line stays.
- "`test_ac1_payload_models_map_from_event_types_with_no_other_keys` keeps a name its assertion no longer matches": left. Not touched here.
- "A stored `TaskStateChanged` payload with the key `from_` still validates": left; another payload.
- "Projector `INSERT OR IGNORE` also skips a row on a `NOT NULL` or `CHECK` violation ... check it when a nullable model field is mapped to a `NOT NULL` projection column": left for item 2. `output_path` is nullable in both the model and the DDL.
- The "Spec gap (before the M3 run use case is planned)" line (F-1, F-5, F-7, F-2, F-3) and the three "Spec wording" lines on path patterns: left; they concern items 4 to 11.
- To add at close:
  - "`ImpactComputed` is the last event type without a payload model; when it gets one (M6), `test_ac5_event_type_without_projection_is_ignored` and `build_log` have no type left to use (TASK-040)".
  - "`docs/adr/ADR-007-*.md`: the amendment's list of closed sets lacks a gate result's `gate`, and Consequences still says the `GateEvaluated` and `CommitRecorded` payloads are to be defined; amending an accepted ADR is the human's (TASK-040, planner)".
  - If Open question 1 keeps the test's name: "`test_ac1_payload_models_has_exactly_the_eight_spec_events` keeps a name its assertion no longer matches (TASK-040)".
  - If Open question 4 is not settled by a spec change first: "Spec wording: `sha: "<40 hex>"` does not say lowercase ('Event payloads')", with the answer given.

## Open questions
Question 4 is a spec wording item and is the human's to answer. The others are not spec decisions; each has a proposal.

1. **Three edits to fixed tests that registration forces.** Proposed: approve these, which keep each test's intent.
   - `tests/integration/test_sqlite_projector.py::test_ac5_event_type_without_projection_is_ignored` (line 348): change the event type from `EventType.GateEvaluated` to `EventType.ImpactComputed`, the only type left without a model.
   - `build_log` in the same file (line 397, used by the four AC6 rebuild tests): the same change.
   - `tests/unit/test_m2_payloads.py::test_ac1_payload_models_has_exactly_the_eight_spec_events`: it asserts `PAYLOAD_MODELS` equals exactly eight entries and fails with ten. Change it to assert the eight entries are present; the exact key set moves to AC1 of this task. The name is kept, as TASK-021 did for the M1 test, with a Later line.

   Alternative for the third: rename it too (for example `..._has_the_eight_m1_and_m2_events`).
2. **The form of the field-name conformance test.** `test_m2_payload_fields_match_the_spec_block` is parametrised over five hand-written rows. Proposed: replace it with one test parametrised over every entry of the spec's payload block (the lines that start an entry in the block found by `code_block("PlanCreated\n  plan_id")`), which asserts that `PAYLOAD_MODELS[EventType(<entry>)]` exists and that its dumped field names equal the spec's. It then covers the three M1 payloads, fails for `GateEvaluated` and `CommitRecorded` before the code exists, and covers `ImpactComputed` the day the spec block gains it. Replacing the existing test is an edit to a fixed test and needs approval. Alternative: leave the existing test, and add two rows to its list (or a second test for the two M3 payloads); the Later line then stays.
3. **Names and types.** Proposed:
   - classes `GateEvaluatedPayload` and `CommitRecordedPayload`;
   - `GateName = Literal["path_check", "ruff", "pytest", "gitleaks", "review"]` in `payloads.py`, next to `RunRole` and `RunExit`, repeating the five names that `TaskContract.required_gates` holds inline, so `domain/contracts.py` is not changed;
   - `CommitSha` as an annotated string next to `ContentHash` (pattern per Open question 4);
   - `passed: bool`, `output_path: str | None`, `branch: str`, `files: list[str]`.

   Alternative for the gate names: define `GateName` once in `domain/contracts.py` and use it in `TaskContract` and in the payload; one definition, but `contracts.py` changes.
4. **Can a `sha` hold uppercase hex letters?** (Spec gaps, item 1.) Proposed: no, `^[0-9a-f]{40}$`, as git prints it and as `ContentHash` does; record the answer as a decisions row and leave the spec text to a later `/spec-change`. No test is written for it either way. Alternative: accept both cases.

### Answers (human, 2026-10-13: "do as the advisor says")
1. Approved as proposed: (a) and (b) switch to `EventType.ImpactComputed`; (c) the exact-eight test asserts the eight entries are present, its name kept, with a Later line. The exact ten-key set is asserted in `tests/unit/test_m3_payloads.py`.
2. Replace `test_m2_payload_fields_match_the_spec_block` with one test parametrised over every entry of the spec's payload block, with the advisor's change: an entry whose event type has no key in `PAYLOAD_MODELS` is skipped (`pytest.skip`), not failed, by the file's own rule ("A part whose code does not exist yet is skipped"). So the conformance bullet of AC1 skips before the models exist; the ten-key test is the one that fails first.
3. As proposed: `GateEvaluatedPayload`, `CommitRecordedPayload`, `GateName` in `payloads.py`, `CommitSha` next to `ContentHash`; `domain/contracts.py` unchanged. With the advisor's addition: one assertion that `get_args(GateName)` equals `REQUIRED_GATES`.
4. Lowercase only: `^[0-9a-f]{40}$`. A row in `docs/decisions.md`; the spec text is left to a later `/spec-change`; no test for uppercase.

## Outcome
Built: `GateEvaluatedPayload` and `CommitRecordedPayload`, with `GateName` and `CommitSha`, in `src/openfactory/domain/payloads.py`, and two new entries in `PAYLOAD_MODELS` (ten in total, `ImpactComputed` has none). The projector validates the two events and writes nothing for them. No adapter, port or `contracts.py` change.

Tests: new `tests/unit/test_m3_payloads.py` (36 tests) and one projector test added in `tests/integration/test_sqlite_projector.py`.

Edits to existing fixed tests, four, all approved by the human on 2026-10-13:
- `tests/integration/test_sqlite_projector.py::test_ac5_event_type_without_projection_is_ignored`: event type switched from `GateEvaluated` to `ImpactComputed`.
- `build_log` in the same file: the same switch.
- `tests/unit/test_m2_payloads.py::test_ac1_payload_models_has_exactly_the_eight_spec_events`: now asserts the eight entries are present; name kept.
- `tests/unit/test_spec_conformance.py::test_m2_payload_fields_match_the_spec_block`: replaced by `test_payload_fields_match_the_spec_block`, parametrised over the spec's payload block, entries with no model skipped.

No mechanical test fixes were needed during implementation.

Deviation from the plan: one test added that the plan did not have, `get_args(GateName)` equals `REQUIRED_GATES` (the advisor's addition).

Final suite: 1088 passed, no skips.

Follow-ups: the Later lines in `docs/progress.md` (`ImpactComputed` and the two test helpers, the ADR-007 wording, the kept test name, the lowercase `sha` spec wording).
