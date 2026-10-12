# TASK-035: Approve plan use case

- Milestone: M2
- Status: done
- Tests: acceptance
- ADR: none. No new port, adapter, dependency, event type, payload shape or storage change: `PlanApproved` and `TaskStateChanged` have payload models (TASK-021) and projections (TASK-022). ADR-001 covers recording through `EventRecorder` and reading spec versions through `SpecVersions`; ADR-012 covers `Plans` (`current_draft`, `tasks`) and tests with in-memory fakes; ADR-007 covers building events through the payload models. The module, the names, the result type and how the `from` field is written are rows in `docs/decisions.md` (Open questions 1 to 3).
- Spec impact: none. Spec v1.11 settles the two refusals, the events, their order, streams, actors and `causation_id`, the payloads, and which tasks become `ready` (see "Spec gaps": readings only).
- Spec sections (spec v1.11): "Task contract" › "Planning" ("`openfactory approve plan` fails if the draft's spec version is not the latest approved version"); "Domain model and storage" › "Streams and actors" (the table rows for `PlanApproved` and `TaskStateChanged`; "each `TaskStateChanged` written by `approve plan` points at the `PlanApproved` event"; the sentence that starts "`approve plan` records `PlanApproved`"), "Event payloads" (the `PlanApproved` and `TaskStateChanged` blocks), "Event types in Phase 1" ("Approvals are recorded by `SpecApproved` and `PlanApproved` with actor `human`"), "Projection rules" ("Use cases record every event through the `EventRecorder` port") and "Ids" ("They read the plan and task projections through the `Plans` port"); "Task state machine" ("When its plan is approved, a task with no dependencies moves to `ready`. A task with dependencies stays `pending`"); "CLI commands" › "Output" (the `approve plan` bullet, for what the result must carry)

## Outline item
M2 outline item 11, first piece: the use case. The `approve plan` command (`cli.py`, output lines, refusal texts, exit codes, wiring) is left as the second piece. Items 12 and 13 are left.

## Objective
Add the app-layer function that approves the current draft plan: it returns a refusal when there is no draft or the draft was made for a spec version that is not the latest approved one, and otherwise records `PlanApproved` and one `TaskStateChanged` (`pending` to `ready`) per task with no dependencies, returning the plan id and the ids made ready.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings.

## Scope
In (names per Open questions 2 and 3), all in a new `src/openfactory/app/approve_plan.py`:
- `ApprovePlanOutcome(StrEnum)`: `no_draft`, `stale_draft`, `approved`.
- `ApprovePlanResult` (frozen, `extra="forbid"`): `outcome`, `plan_id: str | None` (the draft's id; `None` for `no_draft`), `spec_version: str | None` (the draft's spec version; `None` for `no_draft`), `ready: list[str]` (the ids of the tasks made ready, ascending; empty unless `approved`).
- `approve_plan(versions: SpecVersions, plans: Plans, recorder: EventRecorder) -> ApprovePlanResult`.
- Unit tests with in-memory fakes. No database.

Out (not this task):
- `cli.py`: the `approve plan` command, the lines `task_id  ready` and `approved plan_NN`, the refusal texts `no draft plan` and `plan_NN was made for sv_NN; run openfactory plan`, exit codes, the shared wiring helper (Later, TASK-034). Second piece of item 11.
- Any change to `domain/payloads.py`, the ports, the adapters, the projector, or the other modules under `app/`.
- The second half of the TASK-021 Later line: a stored payload with the key `from_` validates (Open question 1).
- The `deleted-requirement` rule and the M2 close test (items 12 and 13).
- Reading the spec files or the policy: `approve plan` compares the draft's spec version with the latest approved version id and nothing else.
- Checking `pending` to `ready` against `TRANSITIONS`, or a draft task found in a state other than `pending`: a draft's tasks never ran.
- A draft together with an approved plan: `plan` is refused while an approved plan exists, so M2 cannot reach it.
- A draft with no tasks (Later, TASK-032): `PlanApproved` is recorded and `ready` is empty; no criterion.
- A recorder that raises between the events: the error propagates, as in `approve_spec` and `run_planner` (Open question 5).

## Acceptance criteria
"Planning" is under "Task contract"; "Streams and actors", "Event payloads", "Event types in Phase 1", "Projection rules" and "Ids" under "Domain model and storage"; "Output" under "CLI commands".

Fixtures:
- The fake `SpecVersions` returns a chosen `latest_approved()` (`SpecVersionRef`).
- The fake `Plans` returns a chosen `current_draft()` (`PlanRef`) and a chosen list for `tasks(plan_id)`, and keeps the plan ids it was asked for.
- The fake recorder keeps the events it is given, in order, and returns each as a `StoredEvent`.
- "The sample tasks" are four `Task` objects of plan `plan_03`, all in state `pending`: `AUTH-001` (no dependencies), `AUTH-002` (depends on `AUTH-001`), `AUTH-010` (no dependencies), `DB-001` (no dependencies). The fake returns them in an order that is not ascending (Open question 4).

- [x] AC1 ("Output": "It refuses with one line on standard error and exits 1: `no draft plan`"). With `current_draft()` `None` and an approved `sv_01`:
  - The result has `outcome` `no_draft`, `plan_id` `None`, `spec_version` `None` and `ready` empty.
  - No event is recorded.
- [x] AC2 ("Planning": "`openfactory approve plan` fails if the draft's spec version is not the latest approved version"; "Output": "`plan_NN was made for sv_NN; run openfactory plan` when the draft's spec version is not the latest approved one"). With draft `plan_02` made for `sv_01`, latest approved `sv_02`, and the fake holding tasks for `plan_02`:
  - The result has `outcome` `stale_draft`, `plan_id` `plan_02`, `spec_version` `sv_01` and `ready` empty.
  - No event is recorded.
- [x] AC3 ("Streams and actors": the row "`PlanApproved` | `plan:<plan id>` | `human`" and "`approve plan` records `PlanApproved`, with no `causation_id`"; "Event types in Phase 1": "Approvals are recorded by `SpecApproved` and `PlanApproved` with actor `human`"; "Event payloads": the `PlanApproved` block). With draft `plan_03` made for `sv_02`, latest approved `sv_02`, and the sample tasks:
  - The first event recorded is `PlanApproved` on stream `plan:plan_03`, with actor `human` and no `causation_id`.
  - Its payload is exactly `{"plan_id": "plan_03"}`.
  - The result has `outcome` `approved`, `plan_id` `plan_03` and `spec_version` `sv_02`.
- [x] AC4 ("Streams and actors": "then one `TaskStateChanged` per task with no dependencies, in ascending task id as strings, each pointing at `PlanApproved`" and the row "`TaskStateChanged` | `task:<task id>` | `orchestrator`"; "Event payloads": the `TaskStateChanged` block; "Task state machine": "When its plan is approved, a task with no dependencies moves to `ready`. A task with dependencies stays `pending`"; "Output": "one line per task made ready ..., in ascending task id as strings"). With the same inputs as AC3:
  - Exactly four events are recorded: `PlanApproved`, then three `TaskStateChanged` for `AUTH-001`, `AUTH-010`, `DB-001`, in that order. None is for `AUTH-002`.
  - Each `TaskStateChanged` is on stream `task:<its task id>`, with actor `orchestrator` and `causation_id` equal to the `event_id` of `PlanApproved` (not of the event before it).
  - Each payload is exactly `{"task_id": <id>, "from": "pending", "to": "ready", "reason": null}`, with the key `from` and no key `from_`, and validates as `TaskStateChangedPayload`.
  - The result's `ready` is `["AUTH-001", "AUTH-010", "DB-001"]`.
- [x] AC5 ("Ids": "They read the plan and task projections through the `Plans` port"; "Projection rules": "Use cases record every event through the `EventRecorder` port"):
  - `approve_plan` takes exactly the three ports `SpecVersions`, `Plans` and `EventRecorder` (checked with `inspect.signature`): no `SpecFiles`, no `GitProvider`, no LLM.
  - `openfactory.app.approve_plan` imports nothing from `openfactory.adapters` or `openfactory.cli` (checked by parsing its imports with `ast`).
  - In the AC3 run, `Plans.tasks` was asked for `plan_03` only.

## Architecture rules that apply
- `src/openfactory/app` depends on `domain` and `ports` only.
- All state changes go through the events table: the function records only through `EventRecorder.record`, with events built by `Event.new` from the payload models (ADR-007). It writes no projection.
- The use case returns data and prints nothing (decisions row of 2026-10-10, TASK-018). The refusal texts and the output lines are written by `cli.py` in the second piece.
- The use case reads the projections only through `SpecVersions` and `Plans` (ADR-001, ADR-012).
- Tests from the test-writer are fixed. No existing test is changed.
- No hardening beyond the spec's rules.

## Plan
1. Create branch `task/TASK-035-approve-plan-use-case` from an up-to-date main.
2. Get the human's answers to the Open questions; record them here and as rows in `docs/decisions.md`.
3. Write failing tests in `tests/unit/test_approve_plan_use_case.py` (new) for AC1 to AC5, with fakes for `SpecVersions`, `Plans` and the recorder defined in the file (the repo has no shared test helpers).
4. Add `src/openfactory/app/approve_plan.py`:
   - `ApprovePlanOutcome` and `ApprovePlanResult`.
   - `approve_plan`:
     - `plans.current_draft()` is `None`: return `no_draft`.
     - `versions.latest_approved()` is `None` or its id is not the draft's `spec_version`: return `stale_draft` with the draft's id and spec version.
     - Record `PlanApproved` (`PlanApprovedPayload`, stream `plan:<id>`, actor `human`, no `causation_id`).
     - Take `plans.tasks(draft.id)`, keep those with an empty `depends_on`, sort by `id` (Open question 4).
     - For each, record `TaskStateChanged` (stream `task:<id>`, actor `orchestrator`, `causation_id` the `PlanApproved` event id, `from` `pending`, `to` `ready`, `reason` null), with the payload built as Open question 1 decides.
     - Return `approved` with the plan id, the spec version and the ids.
   - A module docstring naming the spec sections and ADR-001, ADR-012.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until green.
6. Update the living docs and the Outcome. Commit `feat(app): add the approve plan use case` with trailers `Task: TASK-035` and `Milestone: M2`.

## Files expected to change
- `src/openfactory/app/approve_plan.py` (new, about 75 lines)
- `tests/unit/test_approve_plan_use_case.py` (new, about 230 lines)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-035-approve-plan-use-case.md`

Not expected to change: `cli.py`, the other modules under `app/`, everything under `domain/`, `ports/` and `adapters/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, and every existing test file.

## Living docs to update
- `docs/architecture.md`:
  - New section "Approve plan use case": the two refusals and their order, the events with streams, actors and `causation_id`, which tasks are made ready, the result, and how the `from` field is written.
  - "Data flow": correct "no use case builds `TaskStateChanged` yet" and "no use case calls the other three yet" (`current_draft` and `tasks` now have a caller; `live_tasks_referencing` still has none). No command calls `approve_plan` yet.
- `docs/progress.md`:
  - Current, then Done.
  - Reword outline item 11 to what is left: "The `approve plan` command · depends on TASK-035".
  - Reword the TASK-021 Later line on `from_` to what is left after Open question 1.
- `docs/decisions.md`: rows for the answered questions.
- `CHANGELOG.md`, `README.md`: no change (no command or output is added).

## New dependencies
None.

## Spec gaps
Spec impact is "none". Nothing is missing for this task.

Readings, not gaps:
- "Fails if the draft's spec version is not the latest approved version" compares two version ids from the projections. The spec files on disk are not loaded, no `spec files differ` warning exists for `approve plan`, and the policy is not read.
- In `plan_NN was made for sv_NN; run openfactory plan`, `sv_NN` is the draft's spec version ("was made for"), so the result carries it.
- "No draft plan" is checked first: without a draft there is nothing to compare.
- "A task with no dependencies" is a `Task` whose `depends_on` (from `task_deps`) is empty; it equals the contract's `depends_on` (SC-45).
- "Each pointing at `PlanApproved`": every `TaskStateChanged` has the `PlanApproved` event id as `causation_id`. They are not chained to one another, unlike the events of `plan`.
- `PlanApproved` has actor `human` and the `TaskStateChanged` events `orchestrator`, in one command ("Streams and actors" table).
- `reason` is null: it is required only when `to` is `invalidated`.
- A draft with no tasks breaks no rule here: `PlanApproved` alone is recorded (ties to the TASK-032 Later line on empty plans).

## Later lines in `docs/progress.md`: taken or left
- `TaskStateChangedPayload(from_=...)` and the key `from_` validating (TASK-021, reviewer): the first half is settled here by Open question 1; the second half is left, and the line is reworded.
- The repeated recorder-then-read-adapters wiring in `cli.py` (TASK-034, planner): left to the command piece of item 11.
- A plan with no tasks (TASK-032, TASK-034): left; no criterion.
- F-1, what a command prints when the recorder's catch-up fails: left; this function opens nothing.
- F-7, which states can be invalidated, and `TRANSITIONS` not being enforced: left; `pending` to `ready` is in the block.

## Open questions
None is a spec decision. Each has a proposal.

1. **How the `from` field is written (the TASK-021 Later line).** pyright rejects `TaskStateChangedPayload(from_=...)` in typed code. Proposed: the use case builds the payload with `TaskStateChangedPayload.model_validate({"task_id": ..., "from": TaskState.pending, "to": TaskState.ready, "reason": None})` in one private helper, as the helpers in `tests/integration/test_sqlite_plans.py` and `test_sqlite_projector_m2.py` already do. `domain/payloads.py` and every fixed test stay as they are. That a stored key `from_` validates stays a Later line: no use case writes it. Alternatives, each of which edits a fixed test and so needs the human's approval:
   - `validation_alias`/`serialization_alias` in place of `alias`: `tests/unit/test_spec_conformance.py` reads the field name as `f.alias or key` and would see `from_`.
   - Dropping `validate_by_name`: `test_ac3_task_state_changed_also_validates_by_field_name` builds the model with `from_=`.
   If the human sees "build this payload from a dict" as a convention M3 must follow, the ADR field becomes "needed (how `TaskStateChanged` payloads are built)".
2. **Module and names.** Proposed: `app/approve_plan.py`, `approve_plan(versions, plans, recorder)`, `ApprovePlanOutcome`, `ApprovePlanResult`; it mirrors `app/approve_spec.py`, whose `ApproveOutcome` and `ApproveResult` keep their names. Alternative: add the function to `app/plan.py`.
3. **Result type.** Proposed: one frozen model with an outcome enum and nullable fields, as `ApproveResult` has; `cli.py` needs no second call, so the union of `prepare_plan` buys nothing. Alternative: a union of a refusal model and an approved model.
4. **Who keeps the ascending order.** `Plans.tasks` promises ascending ids. Proposed: `approve_plan` sorts the tasks it makes ready by id itself (one `sorted`, as `run_planner` sorts its contracts), and the fake returns the sample tasks out of order, so AC4 can fail. Alternative: rely on the port's order, with a fake that returns ascending ids; the order assertion then tests the fake.
5. **Several `record` calls, no shared transaction.** A failure after `PlanApproved` and before the last `TaskStateChanged` leaves an approved plan with a `pending` task that has no dependencies, and a second `approve plan` then finds no draft. Proposed: let the error propagate, no criterion, and add a Later line; the spec's restart criterion belongs to M3's `run`. Alternative: a recovery rule, which is the spec's to state.

Answers (human, 2026-10-12): the five proposals are approved as written. The advisor agreed with all five; its suggested amendments were not taken up.

## Outcome
Built `src/openfactory/app/approve_plan.py` with `ApprovePlanOutcome`, `ApprovePlanResult` and `approve_plan(versions, plans, recorder)`: it refuses with `no_draft`, then `stale_draft`; otherwise it records `PlanApproved` and one `TaskStateChanged` per task with no dependencies, sorted by id, each with `causation_id` the `PlanApproved` event id. The payload is built in `_made_ready` with `model_validate` from a dict with the key `from`. Tests are in `tests/unit/test_approve_plan_use_case.py` (AC1 to AC5). Living docs updated: architecture, progress, decisions (five rows for the answered questions).

Deviations from plan: none.

Test edits: no test from the test-writer was edited.

Follow-ups:
- The `approve plan` command (rest of outline item 11).
- The Later line on separate transactions carries the prefix "Spec gap (before M3 is planned):" (advisor and reviewer; added at the human's word before the commit).
- Advisor suggestions not taken up: read `plans.tasks` before recording `PlanApproved`; move `_made_ready` beside the model when a second use case builds `TaskStateChanged`; add a comment in the test that the fake's task order is deliberately not the port's.
