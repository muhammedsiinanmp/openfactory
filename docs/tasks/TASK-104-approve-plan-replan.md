# TASK-104: `approve plan` after a replan, the use case

- Milestone: M6
- Status: done
- Tests: acceptance
- ADR: ADR-019 (accepted, with its 2026-10-24 amendment).
  - Its Decision, "Invalidation at approval", says: "`approve plan` of a replan draft reads the latest matching `ImpactComputed` recorded before the draft's `PlanCreated`, records `PlanApproved`, invalidates the listed tasks that can be, then readies every `pending` task whose dependencies have passed".
  - Its Consequences say: "`approve_plan.py` gains the impact read, the invalidations and the `pending` readies".
  - Its "Ports" line says "`ImpactComputed` is read through `EventStore`" and "No new port".
  - The task adds one port parameter (`EventStore`, which already exists) to an existing use case. It adds no port, adapter, event type, payload change, table, dependency or convention, so no new ADR is needed. Each answered Design choice becomes a row in `docs/decisions.md`.
- Spec impact: none (see Spec gaps: readings and one case that cannot be reached; none blocks)
- Spec sections (spec v1.19; SC-165, SC-176, SC-192, SC-196; SC-191 for "before"):
  - "Spec diff and impact analysis" › "Approving a replan": "when an approved plan exists, `approve plan` reads, through the `EventStore` port, the latest `ImpactComputed` recorded before the draft's `PlanCreated` whose `from_version` is the approved plan's spec version and whose `to_version` is the draft's. It refuses when a task in its `tasks` or `downstream` is `running` or `gating`. It records `PlanApproved`, and the projector supersedes the earlier plan and moves its tasks into the new one (see Projection rules). It then records `TaskStateChanged` to `invalidated`, with reason `spec change <to_version>`, for each task in `tasks` and `downstream` that is `pending`, `ready`, `failed`, `escalated` or `passed`, in ascending task id as strings; an `abandoned` or `invalidated` one is skipped. Then it moves to `ready` every `pending` task whose dependencies have all passed, none included, in ascending task id as strings. Untouched tasks keep their state and commits."
  - "CLI commands" › "Output", the `approve plan` bullet, its refusals: "checked in this order: `no draft plan`; `plan_NN was made for sv_NN; run openfactory replan` when the draft's spec version is not the latest approved one and an approved plan exists, or `plan_NN was made for sv_NN; run openfactory plan` when none does; `<task id> is <state>; run openfactory run first` when a task it would invalidate is `running` or `gating`, naming the lowest such task id as strings."
  - "Domain model and storage" › "Streams and actors": "`approve plan` records `PlanApproved`, with no `causation_id`, then, after a replan, one `TaskStateChanged` to `invalidated` per task it invalidates (see Approving a replan), then one `TaskStateChanged` to `ready` per `pending` task whose dependencies have all passed (none included), each group in ascending task id as strings, each pointing at `PlanApproved`."
  - "Task state machine": "The `run`, `resolve` and `approve plan` use cases check every transition against `TRANSITIONS` before they record it; a transition that is not there is a programming error, and the use case raises before recording anything." Also: "Approving a replan changes them only when they are impacted or downstream."
  - "Event envelope rules" (SC-191): "Between events, 'latest', 'earlier', 'before' and 'after' compare `seq`."
  - "Task contract" › "Planning": "`openfactory approve plan` fails if the draft's spec version is not the latest approved version."

## Outline item
This is M6 outline item 7, first piece (7a).

Proposed split of item 7:
- **7a (TASK-104):** the use case in `app/approve_plan.py`. It covers the refusal order and the lowest id (SC-192), the stale-draft variant flag (SC-176), the impact read, the invalidations, the `pending` readies (SC-165) and the `TRANSITIONS` check (SC-196). `cli.py` changes only to pass the event store.
- **7b:** the `approve plan` command output. It prints the `task_id  invalidated` lines, then the `ready` lines, then `approved plan_NN`. It writes the `run openfactory replan` / `run openfactory plan` stale lines and the `<task id> is <state>; run openfactory run first` line. It adds an integration test on a real database: a replan draft, the projector's move and the cross-stream `seq` order.
- Item 8 (the M6 close test) follows.

## Objective
When an approved plan exists, `approve_plan` refuses as the spec orders. Otherwise it reads the matching `ImpactComputed` through `EventStore`. It then records `PlanApproved`, the `invalidated` changes and the `pending` to `ready` changes, each transition checked against `TRANSITIONS` before anything is recorded. A first plan is approved exactly as today.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/app/approve_plan.py`:
  - **Signature.** `approve_plan(versions, plans, recorder, *, events: EventStore) -> ApprovePlanResult` (Design choice 2).
  - **New outcome.** `ApprovePlanOutcome` gains `task_busy`.
  - **New result fields.** `ApprovePlanResult` gains these fields, all with defaults (Design choice 3):
    - `approved_plan_exists: bool = False`, set on `stale_draft`;
    - `task_id: str | None` and `state: TaskState | None`, set on `task_busy`;
    - `invalidated: list[str] = []`.
  - **Private `_latest_impact_before(events, draft, approved)`.** It reads the draft's `PlanCreated` `seq` from `events.read(f"plan:{draft.id}")`. From `events.read(f"spec:{draft.spec_version}")` it keeps the `ImpactComputed` events with a lower `seq` whose payload's `from_version` is the approved plan's spec version, and returns the last one.
  - **One step that computes everything before any event is recorded** (Design choice 1):
    1. Read the tasks of the approved plan and of the draft.
    2. Work out the invalidations.
    3. Apply them in memory.
    4. Work out the readies over the union of both plans' tasks.
    5. Check every transition against `TRANSITIONS`, raising `ValueError` on one that is not there.
    6. Only then record.
  - **Payload helper.** A new payload helper builds the `invalidated` change from a dict with the key `from`, as `_made_ready` does.
- `src/openfactory/cli.py`: `approve_plan_command` opens `closing(SqliteEventStore(database))` next to `_open_adapters`, as `run` and `replan` do, and passes `events=store`. Its printing does not change (7b).
- New `tests/unit/test_approve_plan_replan.py`. It uses in-memory fakes:
  - a `Plans` with an approved `plan_01` (`sv_01`) and a draft `plan_02` (`sv_02`);
  - an `EventStore` whose `read(stream)` returns scripted `StoredEvent`s with explicit `seq`;
  - the existing fakes' pattern for the recorder.
- `tests/unit/test_approve_plan_use_case.py`: two edits, which need human approval (Open question 2):
  - `_run` passes `events=` a fake that fails the test if it is read when no approved plan exists;
  - `test_ac5_takes_exactly_the_three_ports` expects `["versions", "plans", "recorder", "events"]`. Its name no longer matches, so this becomes a Later line.

Out:
- All new output lines and refusal texts in `cli.py`, and the CLI integration test (7b).
- The M6 close test (item 8).
- Any change to `domain/`, `ports/`, `adapters/`, `app/replan.py` or `app/impact.py`.
- Open Later items stay open, including:
  - the TASK-094 traversal "another plan" test;
  - the second-replan invalidated-ids gap;
  - the deletion-only task gap;
  - F-16.

## Acceptance criteria
- [ ] **AC1** ("Output", `approve plan`: the refusals "checked in this order: `no draft plan`; `plan_NN was made for sv_NN; run openfactory replan` when … an approved plan exists, or `… run openfactory plan` when none does"; "Planning": "fails if the draft's spec version is not the latest approved version"):
  - No draft gives `no_draft`.
  - A draft whose spec version is not the latest approved gives `stale_draft` with the draft's `plan_id` and `spec_version`. `approved_plan_exists` is true when `Plans.approved()` is not `None` and false when it is.
  - The stale check comes before the `running`/`gating` check: a stale draft with a busy impacted task gives `stale_draft`.
  - Each refusal records no event.
- [ ] **AC2** ("Approving a replan": "It refuses when a task in its `tasks` or `downstream` is `running` or `gating`"; "Output": "naming the lowest such task id as strings"):
  - With an approved plan and a matching impact, a task in `tasks` or in `downstream` that is `running` or `gating` gives `task_busy`, with `task_id` the lowest such id as strings and `state` its state.
  - Example: with `AUTH-010` gating and `AUTH-002` running, the result names `AUTH-002`, which sorts first as a string.
  - A `running` untouched task does not refuse.
  - The refusal records no event.
- [ ] **AC3** ("Approving a replan": "the latest `ImpactComputed` recorded before the draft's `PlanCreated` whose `from_version` is the approved plan's spec version and whose `to_version` is the draft's"; "Event envelope rules": "'latest' … 'before' … compare `seq`"):
  - The impact is read only through `EventStore.read` of the streams `plan:<draft id>` and `spec:<draft spec version>`. `append` is never called.
  - Of several `ImpactComputed` on `spec:sv_02`, the one used is the one with the highest `seq` below the draft's `PlanCreated` `seq` and `from_version` `sv_01`. An event with a higher `seq` than `PlanCreated`, or with another `from_version`, is ignored even when it lists other tasks.
  - With no approved plan, `EventStore.read` is never called.
- [ ] **AC4** ("Approving a replan": invalidation; "Streams and actors": "`approve plan` records `PlanApproved`, with no `causation_id`, then … one `TaskStateChanged` to `invalidated` per task it invalidates … each pointing at `PlanApproved`"):
  - The first event is `PlanApproved` on `plan:<draft id>`, actor `human`, no `causation_id`.
  - Next comes one `TaskStateChanged` to `invalidated` on `task:<id>`, actor `orchestrator`, `causation_id` the `PlanApproved` event id, reason `spec change sv_02`. There is one for each task in `tasks` ∪ `downstream` that is `pending`, `ready`, `failed`, `escalated` or `passed`, with `from` its state, in ascending id as strings.
  - An `abandoned` or `invalidated` listed task gets no event.
  - Untouched tasks get no event.
  - `ApprovePlanResult.invalidated` lists the invalidated ids in that order.
- [ ] **AC5** ("Approving a replan": "Then it moves to `ready` every `pending` task whose dependencies have all passed, none included, in ascending task id as strings"; "Task state machine": "Approving a replan changes them only when they are impacted or downstream"):
  - After the invalidations, one `pending` to `ready` change (reason null, pointing at `PlanApproved`) is recorded for each `pending` task of the draft or the approved plan whose dependencies are all `passed`. They come in ascending id, after every invalidation, and `ready` lists them.
  - These become `ready`:
    - a new task with no dependencies;
    - a new task depending only on an untouched `passed` task.
  - These stay `pending`:
    - a new task depending on another new task;
    - an untouched `pending` task whose dependency is `escalated` or `abandoned`;
    - an invalidated downstream task, which gets no `ready` event.
  - With no approved plan, the events and result are exactly those of today. The existing tests in `test_approve_plan_use_case.py` pass with only the two approved edits.
- [ ] **AC6** ("Task state machine": "check every transition against `TRANSITIONS` before they record it; … the use case raises before recording anything"):
  - With `openfactory.app.approve_plan.TRANSITIONS` monkeypatched to drop `passed` → `invalidated` (as `test_resolve_use_case.py` does), approving a replan draft that would invalidate a `passed` task raises `ValueError` and records no event, not even `PlanApproved`.
  - The same holds with `pending` → `ready` dropped for a draft with a task to ready.

## Architecture rules that apply
- `app` depends on `domain` and `ports` only. `approve_plan.py` imports nothing from `adapters`, `cli` or other `app` modules. The existing AST test keeps checking this.
- `EventStore` is used for reading only. All state changes go through `EventRecorder.record`.
- The use case returns data and prints nothing. `cli.py` builds the lines in 7b.

## Plan
1. Create branch `task/TASK-104-approve-plan-replan` from an up-to-date main.
2. Record the human's answers to the Design choices and Open questions in this record.
3. Test-writer: write failing `test_task104_ac<N>_…` tests in the new `tests/unit/test_approve_plan_replan.py`, and apply the two approved edits to `test_approve_plan_use_case.py`. Fixture:
   - approved `plan_01` on `sv_01`:
     - AUTH-001 passed, untouched;
     - AUTH-002 passed, impacted;
     - AUTH-003 pending, downstream;
     - AUTH-004 abandoned, impacted;
     - AUTH-005 pending, untouched, depends on an escalated AUTH-006;
   - draft `plan_02` on `sv_02`:
     - AUTH-007 depends on AUTH-001;
     - AUTH-008 depends on AUTH-007;
     - AUTH-009 has no dependencies;
   - `ImpactComputed` events at `seq` below and above the draft's `PlanCreated`, and one with another `from_version`.
4. Implement `_latest_impact_before`, the precomputation and check, the recording, the result fields, and the `cli.py` pass-through.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md` "Approve plan use case": the new port, refusals, impact read, invalidations, readies and the `TRANSITIONS` check.
   - `docs/progress.md`: Current, a Done line, item 7 split into 7a and 7b with 7a done, and a Later line for the renamed-assertion test.
   - `docs/decisions.md`: one row per Design choice.
   - This record's Outcome.
7. Commit `feat(app): invalidate and ready tasks when approving a replan` with the trailers `Task: TASK-104` and `Milestone: M6`. Do not push.

## Files expected to change
- `src/openfactory/app/approve_plan.py` (about +90)
- `src/openfactory/cli.py` (about +3)
- `tests/unit/test_approve_plan_replan.py` (new, about +300)
- `tests/unit/test_approve_plan_use_case.py` (two approved edits, about 4 lines)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, this record

Not expected to change: `domain/`, `ports/`, `adapters/`, other `app/` modules, `docs/spec/`, `docs/adr/`, `pyproject.toml`.

Expected size: about 400 lines, about 95 of them in `src/`. That is over the ~300 target, almost all of it unit test.

## Design choices to confirm at planning
1. **When the transitions are checked.**
   - Proposed: compute the invalidations and readies before recording `PlanApproved`, from the approved plan's and the draft's tasks as they stand. The projector's move changes only `tasks.plan_id`, not states, so the result is the same. Check every transition, then record. This follows "raises before recording anything" literally, as `resolve` checks before both of its events.
   - Alternative: record `PlanApproved`, re-read `Plans.tasks(draft)` after the move, and check each event as it is recorded, like `run`'s `_Chain`. An illegal transition would then leave `PlanApproved` recorded.
2. **How the event store is passed.**
   - Proposed: a required keyword-only `events: EventStore`, which needs the two approved test edits.
   - Alternative: `events: EventStore | None = None`, which avoids the `_run` edit but still breaks the parameter-list test, and makes the replan path depend on an optional argument.
3. **Result shape.**
   - Proposed: one `ApprovePlanResult` with new defaulted fields (`approved_plan_exists`, `task_id`, `state`, `invalidated`) and the new outcome `task_busy`. The existing tests keep reading the old fields.
   - Alternative: a separate `stale_draft_replan` outcome instead of the flag.
4. **No matching `ImpactComputed`.** See Spec gaps 1.
   - Proposed: `assert impact is not None`, as `prepare_replan` asserts its invariants.
   - Alternative: invalidate nothing and carry on.

## Spec gaps
None blocking; Spec impact is none. These are readings and one case that cannot be reached:
1. **"Approving a replan": no matching `ImpactComputed`.** The spec does not say what happens when an approved plan exists but no matching `ImpactComputed` precedes the draft's `PlanCreated`.
   - It cannot be reached through the commands. `plan` refuses while a plan is approved, so such a draft can only come from `replan`. `replan` refuses without a matching impact whose `to_version` is the latest approved one. The stale check ensures that is still the draft's version.
   - It does not block. Design choice 4 asks the human rather than assuming an answer.
2. **"raises before recording anything".** This is read as "before any event of the command" (Design choice 1). Every transition the use case can produce is in `TRANSITIONS`, because `running`/`gating` is refused and `abandoned`/`invalidated` are skipped. So the reading matters only for the AC6 monkeypatch tests.
3. **Ready candidates.** "every `pending` task" is read as the pending tasks of the plan after approval: the draft's tasks plus the moved tasks. For a first plan this gives exactly today's "no dependencies" rule, since every task is `pending`.

## Open questions
1. Do you accept the split of item 7 into 7a (this task, the use case) and 7b (the command output and a real-database integration test)?
2. Do you approve the two edits to `tests/unit/test_approve_plan_use_case.py`, the `_run` helper and the parameter-list test, which become necessary when `events` is added?
3. Size is about 400 lines. Keep it as one task, or split it further:
   - 7a-i: refusals and impact read (AC1 to AC3);
   - 7a-ii: events and the `TRANSITIONS` check (AC4 to AC6).
4. Do you accept Design choices 1 to 4 as proposed? In particular, the up-front transition check (choice 1) and the `assert` on a missing impact (choice 4).

Answers (human, 2026-10-24): 1 yes, split into 7a and 7b; 2 yes, both edits approved; 3 keep one task; 4 Design choices 1 to 4 accepted as proposed. Until 7b lands, the CLI prints `approved plan_NN` for a `task_busy` result and `run openfactory plan` for a stale replan draft; 7b fixes both.

## Outcome
`approve_plan` in `src/openfactory/app/approve_plan.py` now takes a keyword-only `events: EventStore` and handles a replan draft as ADR-019 and the spec describe.
- Refusals: `no_draft`, `stale_draft` (now with `approved_plan_exists`), then the new `task_busy` (lowest id as strings, with its state).
- `_latest_impact_before` reads the draft's `PlanCreated` `seq` and returns the last matching `ImpactComputed` below it; a missing one fails an `assert` (Design choice 4).
- Everything is computed before recording: invalidations, then `pending` readies over both plans' tasks, each transition checked against `TRANSITIONS` (`_check`), then `PlanApproved` and the changes (Design choice 1). The payload helper is now `_change`.
- `ApprovePlanResult` gained `approved_plan_exists`, `task_id`, `state` and `invalidated` (Design choice 3).
- `cli.py` opens `SqliteEventStore` next to `_open_adapters` and passes `events=`; printing is unchanged (7b).
- Tests: new `tests/unit/test_approve_plan_replan.py`. No test edits were made by the implementer beyond the two human-approved edits to `test_approve_plan_use_case.py`, which the test-writer applied.
- ADR: none needed. Decisions rows added for Design choices 1 to 4 and the 7a/7b split.
- Later: the stale name of `test_ac5_takes_exactly_the_three_ports`; the CLI lines for `task_busy` and a stale replan draft until 7b (both in progress.md).
