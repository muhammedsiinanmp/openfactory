# TASK-090: `ImpactComputed` payload model and its registration

- Milestone: M6
- Status: done
- Tests: acceptance
- ADR: ADR-019 (accepted). Its "`ImpactComputed`" bullet defines this payload: `from_version`, `to_version`, `run_id`, `requirements` (`id`, `change`, `kind`, `rationale`, `obsolete_criteria`, `new_work`), `adrs` (`id`, `change`), `tasks`, `downstream`, `files`, `tests`, "changing no projection", with `change` and `kind` closed sets (SC-160). Its Consequences say "`ImpactComputed` gets its payload model, so the projector tests that use it as the type without a model need another (Later, TASK-040)" and "no table changes". ADR-007 governs payloads: they are stable contracts and closed sets are only ever widened. The task adds no port, adapter, event type, table, dependency or convention.
- Spec impact: none
- Spec sections (spec v1.18; SC-160, SC-177):
  - "Domain model and storage" › "Event payloads": "Each event type has one payload model in the domain, and the models forbid unknown fields. Every field of a payload model is required, nullable ones included. … the projector validates each payload against its model before applying it and fails on a mismatch."
  - "Event payloads": the `ImpactComputed` block (`from_version`, `to_version`, `run_id: null | "run_0007"`, `requirements: [ { id, change, kind, rationale, obsolete_criteria, new_work } ]`, `adrs: [ { id, change } ]`, `tasks`, `downstream`, `files`, `tests`).
  - "Event payloads", the paragraph after the block: "In `ImpactComputed`, a requirement's `change` is one of `added`, `removed`, `modified`, `deprecated`, and an ADR's one of `added`, `removed`, `modified`. `kind` is `cosmetic`, `behavioral` or `replacement` when `change` is `modified`, and null otherwise. `rationale` is null, and `obsolete_criteria` and `new_work` are `[]`, unless `change` is `modified` … `ImpactComputed` changes no projection."
  - "Event payloads": "The closed sets a stored payload holds (… an impact's `change` and `kind` …) may be widened but never renamed or narrowed, so every stored event still validates."
  - "Domain model and storage" › "Streams and actors": "`ImpactComputed` | `spec:<to_version>` | `orchestrator`".
  - "Domain model and storage" › "Projections": "A rebuild is identical when, for every projection table, the rows read in primary-key order are equal before and after."

## Outline item
This is M6 outline item 1 in `docs/progress.md`, the whole item. Nothing records `ImpactComputed` yet; the `impact` use case is item 5. Item 2, the structural diff, comes next.

## Objective
`domain/payloads.py` gets a frozen `ImpactComputedPayload` with its two item models and closed sets, registered in `PAYLOAD_MODELS`, so that every event type has a payload model. The projector validates an `ImpactComputed` event and changes no projection row.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/domain/payloads.py`:
  - New closed sets next to `ResolveDecision`: `RequirementChange = Literal["added", "removed", "modified", "deprecated"]`, `AdrChange = Literal["added", "removed", "modified"]` and `ChangeKind = Literal["cosmetic", "behavioral", "replacement"]`.
  - New frozen `RequirementImpact` (`id: str`, `change: RequirementChange`, `kind: ChangeKind | None`, `rationale: str | None`, `obsolete_criteria: list[str]`, `new_work: list[str]`) and `AdrImpact` (`id: str`, `change: AdrChange`). Both use `extra="forbid"` and every field is required. These are separate from the classifier's `ChangeClass` of item 3 (ADR-007, the `CollectedTest` precedent).
  - `RequirementImpact` gets a model validator for the paragraph's rule (Design choice 2).
  - New frozen `ImpactComputedPayload` (`from_version: SpecVersionId`, `to_version: SpecVersionId`, `run_id: RunId | None`, `requirements: list[RequirementImpact]`, `adrs: list[AdrImpact]`, `tasks: list[TaskId]`, `downstream: list[TaskId]`, `files: list[str]`, `tests: list[str]`), in the spec's field order. The model checks no order; sorting is the use case's job, as for `CommitRecordedPayload.files` and `TestsCollectedPayload.tests`.
  - Registered as `PAYLOAD_MODELS[EventType.ImpactComputed]`, giving thirteen entries, one per `EventType`.
- `src/openfactory/adapters/sqlite_projector.py`: the `if/elif` chain gets no branch for the new payload, so it validates and writes nothing. Design choice 3 covers the now-unreachable "no model" path.
- Tests: new tests for AC1 to AC5, and the approved edits to fixed tests (Open question 1).

Out:
- The structural diff, the classifier (`ChangeClass`, its reply model and checks), the traversal, and the `impact` use case and command (items 2 to 5).
- Any check across the payload's top-level fields, for example `run_id` null when no requirement is `modified`, or `to_version` matching the stream.
- Any table or projection change.
- Reading `ImpactComputed` back through `EventStore` (items 8 and 9).

## Acceptance criteria
- [x] **AC1** ("Event payloads": the `ImpactComputed` block; "Each event type has one payload model in the domain, and the models forbid unknown fields. Every field of a payload model is required, nullable ones included"):
  - `ImpactComputedPayload` has exactly the spec's ten fields in the block's order. Each `requirements` item has exactly `id`, `change`, `kind`, `rationale`, `obsolete_criteria`, `new_work`, and each `adrs` item exactly `id`, `change`.
  - A payload shaped like the spec's example round-trips through `model_validate` and `model_dump(mode="json")`. One example has a `modified` requirement and `run_id` set; another has only `added` and `deprecated` entries and `run_id` null.
  - Removing any field, nullable ones included, at the top level or in an item, is rejected. So is an unknown key at either level.
  - The payload and its items are frozen.
  - `tests/unit/test_spec_conformance.py::test_payload_fields_match_the_spec_block[ImpactComputed]` runs and passes, and no longer skips.
- [x] **AC2** ("Event payloads": "a requirement's `change` is one of `added`, `removed`, `modified`, `deprecated`, and an ADR's one of `added`, `removed`, `modified`. `kind` is `cosmetic`, `behavioral` or `replacement`"; "may be widened but never renamed or narrowed"):
  - Each of the four requirement changes, the three ADR changes and the three kinds validates.
  - An ADR `change` of `deprecated`, a requirement `change` of `unchanged` and a `kind` of `minor` are each rejected.
  - A list of literal stored payloads, one per closed-set value, still validates, as in TASK-058 AC3, so renaming or narrowing a set fails a test.
  - `run_id` and the ids in `tasks` and `downstream` use the existing `RunId` and `TaskId` forms: `run_7` and `auth-2` are rejected.
- [x] **AC3** ("Event payloads": "`kind` is … when `change` is `modified`, and null otherwise. `rationale` is null, and `obsolete_criteria` and `new_work` are `[]`, unless `change` is `modified`; then they are the classifier's"). This AC depends on Design choice 2.
  - A `modified` requirement with a null `kind` or a null `rationale` is rejected.
  - A requirement that is `added`, `removed` or `deprecated` is rejected when it has a non-null `kind`, a non-null `rationale`, or a non-empty `obsolete_criteria` or `new_work`.
  - A `modified` entry with empty lists validates.
- [x] **AC4** ("Event payloads": "Each event type has one payload model in the domain"):
  - `PAYLOAD_MODELS[EventType.ImpactComputed] is ImpactComputedPayload`.
  - The key set of `PAYLOAD_MODELS` equals `set(EventType)` exactly (thirteen entries). This is the exact-key-set test the Later line asks to keep (TASK-040, reviewer), now the one test that would catch a model dropped from the map.
- [x] **AC5** ("Event payloads": "`ImpactComputed` changes no projection"; "the projector validates each payload against its model before applying it and fails on a mismatch"; "Streams and actors"; "A rebuild is identical …"):
  - A valid `ImpactComputed` recorded through `SqliteEventRecorder` on stream `spec:sv_02` with actor `orchestrator`, after spec and plan events, leaves every projection table's rows unchanged. The bookkeeping tables `projection_state` and `sqlite_sequence` are left out, as in `test_sqlite_projector_m5.py`.
  - An `ImpactComputed` payload the model rejects raises `ValidationError` and writes nothing.
  - A rebuild of a log that holds an `ImpactComputed` gives identical rows.

## Architecture rules that apply
- `domain/payloads.py` stays pure and imports only `domain` and pydantic.
- The projector stays the only writer of projections. It has no new rule and no new table.
- "All state changes go through the events table": nothing new writes a projection.

## Plan
1. Create branch `task/TASK-090-impact-computed-payload` from an up-to-date main.
2. Record the human's answers to Open question 1 and Design choices 1 to 3 here.
3. Test-writer: write failing tests (`test_task090_...`):
   - AC1 to AC4 in a new `tests/unit/test_m6_payloads.py`;
   - AC5 in a new `tests/integration/test_sqlite_projector_m6.py`, through `SqliteEventRecorder` as the M5 file does;
   - make the approved edits to fixed tests (Open question 1).
4. Implement the three Literals, `RequirementImpact`, `AdrImpact`, `ImpactComputedPayload` and the `PAYLOAD_MODELS` entry, then the Design choice 3 change in `sqlite_projector.py`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`:
     - payload bullets: add `RequirementImpact`, `AdrImpact`, `ImpactComputedPayload`, the three Literals and the validator;
     - the `PAYLOAD_MODELS` line becomes thirteen entries, one per `EventType`, and loses "Only `ImpactComputed` has no entry yet";
     - the projector `apply` bullet: "`ImpactComputed` is validated and writes nothing". Replace "Event types with no entry in `PAYLOAD_MODELS` are ignored" according to Design choice 3.
   - `docs/progress.md`:
     - Current, and a Done line;
     - item 1 removed from the M6 outline;
     - remove the Later line "`ImpactComputed` is the last event type without a payload model …" (TASK-040) and the "Keep one exact-key-set test alive …" line (now met by AC4);
     - add Later lines for any test whose name no longer matches its assertion after the edits;
     - add the ADR-007 Consequences line (`ImpactComputed` "still to be" defined) to the existing ADR-007 Later line; amending an accepted ADR is the human's job.
   - `docs/decisions.md`: one row for the fixed-test edits (as the TASK-040 and TASK-058 rows) and one row per Design choice.
   - Fill in the Outcome, listing every test edit.
7. Commit `feat(domain): add the ImpactComputed payload model` with trailers `Task: TASK-090` and `Milestone: M6`. Do not push.

## Files expected to change
- `src/openfactory/domain/payloads.py` (about +45)
- `src/openfactory/adapters/sqlite_projector.py` (about ±4, Design choice 3)
- `tests/unit/test_m6_payloads.py` (new, about +130)
- `tests/integration/test_sqlite_projector_m6.py` (new, about +50)
- Approved edits only: `tests/unit/test_m3_payloads.py`, `tests/unit/test_m4_payloads.py`, `tests/unit/test_m5_payloads.py`, `tests/integration/test_sqlite_projector.py`
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, this record

Not expected to change: `domain/events.py`, `ports/`, other adapters, `app/`, `cli.py`, `tests/unit/test_spec_conformance.py` (its skip branch stays but no entry reaches it any more), `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 280 lines, about 50 of them in `src/`.

## Design choices to confirm at planning
1. **Names.**
   - Proposed: `ImpactComputedPayload`, `RequirementImpact`, `AdrImpact`, `RequirementChange`, `AdrChange`, `ChangeKind`, all in `domain/payloads.py`. Item 3's `ChangeClass` may reuse `ChangeKind` (domain to domain).
   - Alternative: put `ChangeKind` in a new `domain/impact.py` with the diff types of item 2.
2. **The rule across item fields.**
   - Proposed: a `model_validator(mode="after")` on `RequirementImpact` enforcing AC3. The spec states it as a rule of the payload, and `TaskStateChangedPayload`'s "reason required when to = invalidated" is the precedent.
   - Alternative: no validator, leaving the rule to the `impact` use case (the `GateOutput` and `RunResult` precedent). AC3 would then be dropped.
3. **The projector's no-model path.**
   - Proposed: `apply` uses `PAYLOAD_MODELS[event.type]` and drops `if model is None: return` and its docstring line. Once every type has a model, that path cannot be reached, and a model missing from the map would then fail rather than be skipped quietly ("fails on a mismatch").
   - Alternative: leave `sqlite_projector.py` untouched. The branch stays dead and the architecture line is reworded.

## Open questions
1. **Approval of edits to fixed tests.** Registering `ImpactComputed` makes five existing tests fail, because each one either asserts that `ImpactComputed` has no model or uses it as a type whose payload nothing validates. None of the edits is mechanical, so under CLAUDE.md each needs the human's approval, is listed in the Outcome and is checked by the reviewer. The precedents are the TASK-040 (2026-10-13) and TASK-058 (2026-10-15) rows in `docs/decisions.md`: the older exact tests become presence checks with their names kept, the exact check moves to the new milestone's file, and a Later line records each name that no longer matches.
   - `tests/unit/test_m3_payloads.py::test_ac1_payload_models_has_exactly_the_ten_events_without_impact_computed`: remove line 71, `assert EventType.ImpactComputed not in p.PAYLOAD_MODELS`. The presence check and `is` checks stay. Its name already has a Later line (TASK-058).
   - `tests/unit/test_m4_payloads.py::test_ac2_payload_models_has_exactly_the_eleven_keys`: remove line 81, `not in`. Line 80, `== ELEVEN_MODEL_KEYS`, becomes `>=`, a presence check. The exact set moves to AC4. Its name already has a Later line (TASK-079).
   - `tests/unit/test_m5_payloads.py::test_task079_ac3_payload_models_registers_tests_collected_with_twelve_entries`: remove lines 55 (`len(...) == 12`) and 56 (`not in`), keeping the `is` check. Add a new Later line because "with_twelve_entries" no longer matches.
   - `tests/integration/test_sqlite_projector.py::test_ac5_event_type_without_projection_is_ignored`: its payload `{"to": "ready", "anything": [1, 2]}` would now raise `ValidationError`. It becomes a valid `ImpactComputed` payload, and the test keeps its intent: an event type with no projection rule changes no row. The name is kept and the stream is unchanged, since the projector ignores the stream (as the TASK-040 Later line on `spec:sv_01` notes).
   - `tests/integration/test_sqlite_projector.py::build_log`: the `ImpactComputed` event's payload `{"to": "ready"}` becomes a valid `ImpactComputed` payload, so the rebuild tests still replay an event with no projection.
   - Proposed: approve all as listed.
   - Alternative: keep the exact counts in place, with `test_m4_payloads.py` line 80 becoming `== THIRTEEN` and `test_m5_payloads.py` line 55 becoming `== 13`, and AC4 then only checks the `is` entry. This is fewer edits, but it splits the exact check across old files against the TASK-040 and TASK-058 precedent.

## Decisions at planning
Approved by the human on 2026-10-24, following the advisor (4 AGREE):
- Open question 1: all five fixed-test edits as listed. Add Later lines for `test_ac5_event_type_without_projection_is_ignored` nearly duplicating AC5 (its "ignored" no longer holds after Design choice 3), and for that test and `build_log` keeping `ImpactComputed` on `task:AUTH-002`, not `spec:<to_version>`.
- Design choice 1: the proposed names, in `domain/payloads.py`.
- Design choice 2: the `model_validator` on `RequirementImpact` (AC3 stays).
- Design choice 3: `apply` indexes `PAYLOAD_MODELS[event.type]` and drops the no-model path.

## Spec gaps
None. These are readings, not gaps:
- The item field types come from the spec. `id` is a plain string, as requirement and ADR ids are elsewhere. `obsolete_criteria` and `new_work` are `list[str]`, as in `ChangeClass`. `tasks` and `downstream` hold "<task id>" and use `TaskId`. `files` and `tests` are `list[str]`.
- The "sorted by id" and "sorted as strings" comments are the use case's job; the model checks no order (the TASK-079 Design choice 2 precedent).
- "Then they are the classifier's" means a `modified` entry has a non-null `kind` and `rationale`, because `ChangeClass.kind` and `rationale` are required. Every `modified` requirement is classified, since one classifier call is made "when some requirement is `modified`". AC3 rests on this if Design choice 2 is taken.
- Not a spec gap: `docs/adr/ADR-007-event-payloads-as-stable-contracts.md` line 70 still calls the `ImpactComputed` payload "still to be" defined. Amending an accepted ADR is the human's job, so it goes in Later with the existing ADR-007 line.

## Outcome
Done on branch `task/TASK-090-impact-computed-payload`. All five acceptance criteria are met; the full suite passes (1819 tests).

- `src/openfactory/domain/payloads.py`: the `RequirementChange`, `AdrChange` and `ChangeKind` Literals; frozen `RequirementImpact` with a `model_validator` (AC3), `AdrImpact` and `ImpactComputedPayload`; `PAYLOAD_MODELS[EventType.ImpactComputed]`, thirteen entries, one per `EventType`.
- `src/openfactory/adapters/sqlite_projector.py`: `apply` indexes `PAYLOAD_MODELS[event.type]`; the no-model path and its docstring line are removed. `ImpactComputed` is validated and writes nothing.
- New tests: `tests/unit/test_m6_payloads.py` (AC1 to AC4, 13 tests) and `tests/integration/test_sqlite_projector_m6.py` (AC5, 3 tests). `test_payload_fields_match_the_spec_block[ImpactComputed]` no longer skips.
- Docs: `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`. No ADR drafted: ADR-019 (accepted) covers the payload.

Test edits (all approved by the human 2026-10-24, following the advisor; the reviewer checks each):
1. `tests/unit/test_m3_payloads.py::test_ac1_payload_models_has_exactly_the_ten_events_without_impact_computed`: removed the `assert EventType.ImpactComputed not in p.PAYLOAD_MODELS`.
2. `tests/unit/test_m4_payloads.py::test_ac2_payload_models_has_exactly_the_eleven_keys`: `== ELEVEN_MODEL_KEYS` became `>=`; the `not in` line removed.
3. `tests/unit/test_m5_payloads.py::test_task079_ac3_payload_models_registers_tests_collected_with_twelve_entries`: removed `len(...) == 12` and the `not in`; the `is` check stays.
4. `tests/integration/test_sqlite_projector.py::test_ac5_event_type_without_projection_is_ignored`: uses a new module-level valid `IMPACT_PAYLOAD`.
5. `tests/integration/test_sqlite_projector.py::build_log`: uses `IMPACT_PAYLOAD`.
6. A non-mechanical fix of a test-writer test, approved after the advisor: in `tests/unit/test_m6_payloads.py::test_task090_ac2_stored_payloads_of_every_closed_set_value_still_validate` the first loop no longer builds a `modified` entry from the ADDED template (null `kind` and `rationale`, which AC3 rejects); `modified` is stored once per kind by the next line. Assertion and intent unchanged.

Later lines added in `docs/progress.md`: the `..._with_twelve_entries` name; `test_ac5_event_type_without_projection_is_ignored` no longer tests "ignored" and nearly duplicates AC5; that test and `build_log` keep `ImpactComputed` on `task:AUTH-002`, not `spec:<to_version>`; the ADR-007 Consequences line folded into the existing ADR-007 line. Two Later lines removed: `ImpactComputed` being the last type without a model (TASK-040) and "Keep one exact-key-set test alive" (met by AC4).
