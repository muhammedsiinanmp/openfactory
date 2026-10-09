# TASK-013: Approve spec use case

- Milestone: M1
- Status: done
- Tests: acceptance
- ADR: ADR-001 and ADR-007 (both accepted). ADR-001 covers recording through `EventRecorder` and reading through `SpecVersions`; ADR-007 covers building `SpecApproved` through its payload model. No new port, adapter, dependency, event type, payload change or storage change: `SpecApproved`, `SpecApprovedPayload` and its projection already exist (TASK-001, TASK-005, TASK-009). The function signature and result model are a row in `docs/decisions.md`.
- Spec impact: none. The spec settles every behaviour this task builds. Three items already under Later in `docs/progress.md` bear on it and do not block it (see "Spec gaps").
- Spec sections (spec v1.8): "Spec input format" ("Spec versions", "Policies"); "Domain model and storage" ("Projection rules", "Event types in Phase 1", "Streams and actors", "Event payloads"); "Tech stack and repo layout"

## Objective
Add the approve-spec use case in `src/openfactory/app/`, which runs the validate use case and then either records `SpecApproved` or reports why it did not (unloadable files, violations, or nothing to approve), so the `approve spec` command has it to build on.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- A new module `app/approve_spec.py` with one use case function and its frozen result model (proposed shape under Open questions, item 1). It depends on `openfactory.domain`, `openfactory.ports` and `app/validate.py` only.
- Calling `validate(files, versions, recorder)` for "loads and hashes the files, imports them if they changed, runs the rules" (decision of 2026-10-09, TASK-012: `ValidateResult` carries `hash` and `validated_event_id` for this purpose).
- The four results: spec files that cannot be loaded; files equal to the latest approved version ("nothing to approve"); violations (refused); approved.
- Building `SpecApproved` through `SpecApprovedPayload`, with stream `spec:<spec version id>`, actor `human`, and `causation_id` set to the `event_id` of the `SpecValidated` recorded in the same call.
- Returning the policy problems that `validate` returned, without letting them block the approval.
- Unit tests with in-memory fakes of `SpecFiles`, `SpecVersions` and `EventRecorder`. No database, no files.

Out (follow-up tasks, not this one):
- Typer, the CLI, printing, the sort of printed lines, the count line, the status line `approved sv_NN`, the `nothing to approve` message, standard output against standard error, and exit codes (outline items 1 and 2). The use case returns data and prints nothing.
- `init` and the "run `openfactory init` first" check (outline item 1).
- Wiring `SqliteEventRecorder`, `SqliteSpecVersions` and `FilesystemSpecFiles` to the use case, and the order in which a command opens them (Later, the `SqliteSpecVersions` line).
- A spec set in which two requirements or two ADRs share an id (Later, "Spec gap (before outline item 2)"). No test in this task covers it.
- The deleted-requirement rule (M2).
- Recording `SpecValidated` and `SpecApproved` in one transaction. The port records one event per call; if the recorder raises, the error propagates.
- Any change to `domain/`, `ports/`, `adapters/`, `app/validate.py` or `app/spec_loader.py`, and any change to an existing test file.

## Acceptance criteria
Each criterion cites the spec v1.8 text it traces to. "Spec versions" and "Policies" are blocks under "Spec input format"; "Streams and actors", "Event types in Phase 1", "Event payloads" and "Projection rules" are under "Domain model and storage". In every criterion the use case runs with a fake `SpecFiles` holding file texts, a fake `SpecVersions` whose latest approved version, current draft and next id the test sets, and a fake `EventRecorder` that keeps the events it is given. "The files' hash" is `content_hash` of the `SpecSet` that `load_spec` returns. Unless stated, `policies.yaml` is valid.

- [x] AC1 (Spec versions: "`openfactory approve spec` does not rely on an earlier `validate`. It loads and hashes the files, imports them if they changed, runs the rules ... Otherwise it records `SpecApproved`" and "`approve spec` records `SpecValidated` with the rule results before `SpecApproved`"; Streams and actors: the table row "`SpecApproved` | `spec:<spec version id>` | `human`" and "`causation_id` is the `event_id` of the event recorded just before it in the same command"; Event types in Phase 1: "Approvals are recorded by `SpecApproved` and `PlanApproved` with actor `human`"; Event payloads: "`SpecApproved` `spec_version`, `hash`"; Projection rules: "Use cases record every event through the `EventRecorder` port"): the files hold a valid spec set; there is no draft and no approved version; the next id is `sv_01`.
  - The recorder received exactly three events in this order: `SpecImported`, `SpecValidated`, `SpecApproved`, all on stream `spec:sv_01`.
  - `SpecApproved` has actor `human`; its payload validates as `SpecApprovedPayload` with `spec_version` `sv_01` and `hash` equal to the files' hash; its `causation_id` is the `event_id` of the `SpecValidated`.
  - The `SpecValidated` before it has actor `orchestrator`, the same `hash` and empty `violations`.
  - The result says the spec was approved, names `sv_01`, and has no violations and no policy problems.
  - `openfactory.app.approve_spec` imports nothing from `openfactory.adapters` (checked by parsing its imports with `ast`).
- [x] AC2 (Spec versions: "does not rely on an earlier `validate`"; "imports them if they changed"; "Because a draft keeps its id until it is approved, approved versions are numbered without gaps"): the latest approved version is `sv_01` with another hash, the current draft is `sv_02` with the files' hash, and the next id is `sv_03`.
  - The recorder received exactly two events, `SpecValidated` then `SpecApproved`, both on stream `spec:sv_02` with `spec_version` `sv_02`; no `SpecImported` was recorded.
  - `SpecValidated` has no `causation_id`; the `causation_id` of `SpecApproved` is the `event_id` of the `SpecValidated`.
  - The result says the spec was approved and names `sv_02`.
- [x] AC3 (Spec versions: "refuses if there is any violation" and "If they load but have violations, it records `SpecImported` (if the files changed) and `SpecValidated` with the violations, then refuses without recording `SpecApproved`"): the files load, and one requirement has no acceptance criteria and is constrained by an ADR that does not exist.
  - With no draft and no approved version: the recorder received exactly `SpecImported` then `SpecValidated`; the `SpecValidated` payload holds one violation per violation `validate_spec` returns for the loaded spec set; no `SpecApproved` was recorded.
  - With a current draft `sv_01` that has the files' hash: the recorder received exactly one event, a `SpecValidated` with those violations; no `SpecImported` and no `SpecApproved`.
  - In both cases the result says the approval was refused, names `sv_01`, and its violations equal what `validate_spec` returns.
- [x] AC4 (Spec versions: "If the files equal the latest approved version, it records no events and exits 1 with `nothing to approve`, also when a draft exists"): the latest approved version is `sv_01` with the files' hash.
  - With no draft, and again with a draft `sv_02` of another hash, the recorder received no event and the result says there is nothing to approve.
- [x] AC5 (Spec versions: "If the spec files cannot be loaded, it prints the violations and any policy problems, records no events, and exits 1, like `validate`"): `requirements.yaml` is not valid YAML and `policies.yaml` has an unknown key.
  - The recorder received no event.
  - The result says the spec files could not be loaded, has no spec version id, holds the loader's `schema` violations as its violations, and holds the policy's `schema` violation (subject `specs/policies.yaml`) as its policy problems.
- [x] AC6 (Policies: "Policy problems are not recorded in `SpecValidated`, do not stop the content rules, and do not block `approve spec`"): the files hold a valid spec set and `policies.yaml` has `max_attempts: 0`; there is no draft and no approved version.
  - The recorder received `SpecImported`, `SpecValidated` and `SpecApproved`, and the result says the spec was approved.
  - The result's policy problems hold the policy's `schema` violation, and its violations are empty.
  - The `SpecValidated` payload has empty `violations`.

## Architecture rules that apply
- `src/openfactory/app` depends on domain and ports only. `app/approve_spec.py` imports `validate` and its result types from `app/validate.py`, the domain modules and the three port Protocols; nothing from `adapters`.
- "All state changes go through the events table. Never write projections directly": the use case's only write is `EventRecorder.record`.
- Events are built through the payload models (ADR-007): `SpecApproved` through `SpecApprovedPayload`.
- No LLM call is made.

## Plan
1. Create branch `task/TASK-013-approve-spec-use-case` from an up-to-date main and commit this record.
2. Get the human's answer to the open question; record it here and in `docs/decisions.md`.
3. Write failing tests in `tests/unit/test_approve_spec_use_case.py`, one or more per criterion AC1 to AC6. The three fakes and the sample file texts are defined in this test file, in the same shape as those in `tests/unit/test_validate_use_case.py`; that file is not edited.
4. Add `src/openfactory/app/approve_spec.py`:
   - call `validate(files, versions, recorder)`;
   - `unloadable`: return the unloadable result with its violations and policy problems;
   - `matches_approved`: return the nothing-to-approve result;
   - `validated` with violations: return the refused result;
   - `validated` with no violations: record `SpecApproved` on stream `spec:<version>` with actor `human`, payload `SpecApprovedPayload(spec_version, hash)` from the validate result, and `causation_id` set to its `validated_event_id`; return the approved result.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
6. Update living docs and this record's Outcome; commit with trailers `Task: TASK-013` and `Milestone: M1`.

## Files expected to change
- `src/openfactory/app/approve_spec.py` (new)
- `tests/unit/test_approve_spec_use_case.py` (new)
- `docs/architecture.md` (Components: add "Approve spec use case"; Data flow: replace the three "the approve-spec use case is a later task" sentences with what now exists)
- `docs/progress.md` (Current task, then Done; remove item 1 from the M1 outline and renumber the references to it, including the "outline item 3" reference in the Later line on duplicate ids)
- `docs/decisions.md` (one row for the signature and result model)
- `docs/tasks/TASK-013-approve-spec-use-case.md` (this record; Outcome at close)

Not expected to change: everything under `src/openfactory/domain/`, `src/openfactory/ports/` and `src/openfactory/adapters/`, `src/openfactory/app/validate.py`, `src/openfactory/app/spec_loader.py`, `pyproject.toml`, and every existing test file.

## Living docs to update
- `docs/architecture.md`: Components and Data flow.
- `docs/progress.md`: Current, M1 outline, Done and Later (renumbering only).
- `docs/decisions.md`: the row above.
- `CHANGELOG.md`: no entry expected (no user-visible change).
- `README.md`: no change expected.

## New dependencies
None.

## Spec gaps
None new, and none blocks. Three items already under Later in `docs/progress.md` bear on this task:

1. **"Spec input format" › Spec versions, against "Domain model and storage" › the M1 DDL — known gap, does not block this task.**
   - A spec set with a duplicated requirement or ADR id is imported and then reported under `id-unique`, but `PRIMARY KEY (spec_version, id)` makes that `SpecImported` unprojectable.
   - `approve spec` inherits this through `validate`: with the real recorder it would fail with `sqlite3.IntegrityError` instead of refusing with an `id-unique` violation.
   - It does not block TASK-013: the fakes have no primary key and no criterion covers the case. It blocks the `validate` and `approve spec` commands (outline item 2) for this input, as Later already records.
2. **"Domain model and storage" › Event payloads (`SpecValidated`) — wording, does not block.** The stored order of `violations` (finding F-4, decisions row SC-10) is inherited from `validate` unchanged; this task asserts no order.
3. **"CLI commands" › Output — wording, does not block.** What `approve spec` prints when there is nothing to approve (finding F-2: whether the policy lines and the count line come before `nothing to approve`) is for the command task. The use case returns the policy problems in every case, so either reading can be printed.

## Open questions
1. **Signature and result model (the spec gives none).** Proposed:
   - `approve_spec(files: SpecFiles, versions: SpecVersions, recorder: EventRecorder) -> ApproveResult` in `app/approve_spec.py`.
   - `ApproveResult` is a frozen model that rejects unknown fields, with:
     - `outcome`: one of `unloadable`, `nothing_to_approve`, `refused`, `approved`;
     - `spec_version: str | None`: the version approved or refused, the latest approved id for `nothing_to_approve`, `None` for `unloadable`;
     - `violations: list[SpecViolation]`: the `schema` violations when unloadable, the rule results when refused, otherwise empty;
     - `policy_problems: list[SpecViolation]`.
   - These are what the `approve spec` command needs for its lines, status line and exit code. The hash and the `SpecApproved` event id are left out because nothing in M1 reads them; adding them is the alternative.
   - **Answer (human, 2026-10-09):** the proposal as it stands, with the outcome enum named `ApproveOutcome` so it does not clash with `Outcome` in `app/validate.py`.

## Outcome
Built:
- `src/openfactory/app/approve_spec.py`: `approve_spec(files, versions, recorder) -> ApproveResult`, the `ApproveOutcome` enum (`unloadable`, `nothing_to_approve`, `refused`, `approved`) and the frozen `ApproveResult` (`outcome`, `spec_version`, `violations`, `policy_problems`). It calls `validate`, then records `SpecApproved` (stream `spec:<version>`, actor `human`, payload through `SpecApprovedPayload`, `causation_id` the `SpecValidated` event id) only when the files loaded, differ from the latest approved version and have no violations. Policy problems are returned and never block.
- `tests/unit/test_approve_spec_use_case.py`: 8 tests with in-memory fakes, covering AC1 to AC6.
- Living docs: `docs/architecture.md`, `docs/decisions.md` (one row), `docs/progress.md`.

Deviations from the plan: none.

Test edits: none. The test-writer's tests passed unchanged.

Follow-ups: none new. The duplicate-id spec gap stays under Later in `docs/progress.md` and still blocks the `validate` and `approve spec` commands (outline item 2).
