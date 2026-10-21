# TASK-075: Resolve use case: `TaskResolved`, the refusals and the move out of `escalated`

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-015 (accepted). It already defines `TaskResolved { task_id, decision: "retry" | "abandon" }`: stream `task:<task id>`, actor `human`, "followed by the orchestrator's `TaskStateChanged` pointing at it". It also defines the projector's `retry` reset, done in TASK-065. `ResolveDecision` and `TaskResolvedPayload` exist (TASK-058). This task adds no port, adapter, dependency, event type, payload, schema or convention, so it needs no new ADR and no `decisions.md` row.
- Spec impact: none
- Spec sections (spec v1.16; SC-90):
  - "CLI commands" › "Output": "`resolve TASK-ID` ... records `TaskResolved` with `decision` `retry` or `abandon`, then the orchestrator's `TaskStateChanged` `escalated` to `ready` or `escalated` to `abandoned`, with a null reason ... It does not run the task. It refuses with one line on standard error and exits 1, before any event, checked in this order: `no approved plan`; `unknown task <ID>`, when the approved plan has no such task; `<ID> is <state>, not escalated`. A task escalated on a path violation or a secret can be retried."
  - "Domain model and storage" › "Streams and actors": the table row "`TaskResolved` | `task:<task id>` | `human`", and "`resolve` records `TaskResolved`, with no `causation_id`, then one `TaskStateChanged` pointing at it."
  - "Domain model and storage" › "Projection rules": "A `TaskResolved` whose `decision` is `retry` sets `tasks.attempt` and `tasks.cost_usd` of its task to 0 ... One whose `decision` is `abandon` changes no row; the `TaskStateChanged` that follows it sets the state."
  - "Task state machine": "The `run` and `resolve` use cases check every transition against `TRANSITIONS` before they record it; a transition that is not there is a programming error, and the use case raises before recording anything." The `TRANSITIONS` block has `"escalated": {"ready", "abandoned", "invalidated"}`.

## Outline item
This is the first slice (11a) of M4 outline item 11. The `resolve` command in `cli.py` (11b, TASK-076) comes next: the `--retry`/`--abandon` usage error, the `task_id  <state>` line, the refusal lines and the exit codes.

## Objective
`resolve_task` refuses, before any event, when there is no approved plan, the task is unknown or the task is not `escalated`. Otherwise it records `TaskResolved` (actor `human`, no causation) and then the orchestrator's `TaskStateChanged` `escalated` to `ready` or `abandoned` pointing at it. Each transition is checked against `TRANSITIONS` before anything is recorded.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- New `src/openfactory/app/resolve.py`:
  - `ResolveRefusal(StrEnum)` with `no_approved_plan`, `unknown_task` and `not_escalated`.
  - Frozen `ResolveResult` (`extra="forbid"`) with `refusal: ResolveRefusal | None = None`, `detail: str | None = None` and `state: TaskState | None = None`. `detail` is the task's current state for `not_escalated`. `state` is `ready` or `abandoned` after a resolve, and `None` on a refusal.
  - `resolve_task(task_id: str, decision: ResolveDecision, *, plans: Plans, recorder: EventRecorder) -> ResolveResult`:
    - `plans.approved()`, then `plans.tasks(plan.id)` to find the task and its state.
    - The three refusals in the spec's order.
    - Then the `TRANSITIONS` check, which raises `ValueError` before any record.
    - Then the two events: `TaskResolvedPayload`, then `TaskStateChangedPayload` built from a dict with the key `from`, as `approve_plan` builds it.
  - A module docstring naming the spec sections.
- Tests:
  - New `tests/unit/test_resolve_use_case.py`, with in-memory fakes for `Plans` and the recorder, as in `tests/unit/test_approve_plan_use_case.py`.
  - New `tests/integration/test_resolve_projection.py`, using the real `SqliteEventRecorder` and `SqlitePlans` on a temporary database.

Out:
- `cli.py` and the `resolve` command (11b, TASK-076): the usage error for neither or both flags, the output line, the refusal lines and the exit codes.
- `status` (item 12) and the M4 close test (item 13).
- Any repair of the plan, and any run of the task ("It does not run the task").
- Changes to ports, adapters, domain, payloads, the projector, the schema and `app/run.py`. The private `_Chain` in `run.py` is not reused, because it records every event as `orchestrator`.

## Acceptance criteria
- [x] **AC1** ("CLI commands" › "Output": "It refuses ... before any event, checked in this order: `no approved plan`; `unknown task <ID>` ...; `<ID> is <state>, not escalated`"):
  - With no approved plan, the result is `no_approved_plan`, even for a task id that exists in a draft plan.
  - With an approved plan that has no task of that id, the result is `unknown_task`.
  - For a task in any state other than `escalated` (for example `failed`, `ready`, `passed`, `abandoned`), the result is `not_escalated` with `detail` that state.
  - No refusal records any event.
- [x] **AC2** ("Output": "records `TaskResolved` with `decision` `retry` ..., then the orchestrator's `TaskStateChanged` `escalated` to `ready` ..., with a null reason"; "Streams and actors"):
  - On an `escalated` task with `retry`, exactly two events are recorded, in this order.
  - The first is `TaskResolved` on stream `task:<id>` with actor `human`, `causation_id` `None` and payload `{task_id, decision: "retry"}`.
  - The second is `TaskStateChanged` on stream `task:<id>` with actor `orchestrator`, payload `from` `escalated`, `to` `ready` and `reason` `None`, and `causation_id` the `TaskResolved` event's id.
  - The result's `state` is `ready`.
- [x] **AC3** ("Output": "... or `escalated` to `abandoned`, with a null reason"):
  - With `abandon`, the same two events are recorded, with `decision` `abandon` and `escalated` to `abandoned`.
  - The result's `state` is `abandoned`.
- [x] **AC4** ("Output": "A task escalated on a path violation or a secret can be retried"; "Projection rules": the `retry` reset):
  - With the real `SqliteEventRecorder` and `SqlitePlans`, set up a task escalated with reason `path violation`, with a non-zero `attempt` and `cost_usd`.
  - After `retry`, `Plans.tasks` shows it `ready` with `attempt` 0 and `cost_usd` 0.
  - A task escalated with `secret found` and then abandoned shows `abandoned` with `attempt` and `cost_usd` unchanged.
- [x] **AC5** ("Task state machine": "check every transition against `TRANSITIONS` before they record it ... raises before recording anything"):
  - Remove `ready` from `escalated` in the module's `TRANSITIONS` (monkeypatch `openfactory.app.resolve.TRANSITIONS`).
  - `resolve_task(..., "retry", ...)` on an `escalated` task then raises `ValueError` and records no event, not even `TaskResolved`.
- [x] **AC6** ("Output": "It does not run the task"; ADR-011):
  - `app/resolve.py` imports only from `openfactory.domain`, `openfactory.ports`, Pydantic and the standard library. Nothing comes from `adapters`, `app/run.py` or `cli`.
  - `resolve_task` takes no port other than `Plans` and `EventRecorder`.
  - The suite passes with no existing test edited.

## Architecture rules that apply
- `app` depends on `domain` and `ports` only. Every state change goes through `EventRecorder.record`, and the projector's `retry` reset (TASK-065) does the rest.
- `human` is the actor only for `TaskResolved`. The state change is the orchestrator's ("only the orchestrator moves a task", ADR-015 Alternatives).

## Plan
1. Create branch `task/TASK-075-resolve-use-case` from an up-to-date main.
2. Test-writer: write failing tests.
   - AC1 to AC3, AC5 and AC6 go in `tests/unit/test_resolve_use_case.py`.
   - AC4 goes in `tests/integration/test_resolve_projection.py`. Seed `PlanCreated`, `PlanApproved`, the moves to `escalated`, and an `AgentRunStarted`/`AgentRunFinished` pair with a cost, through the recorder.
3. Implement `app/resolve.py`.
4. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
5. Update the living docs and fill in the Outcome.
6. Commit `feat(app): add the resolve use case` with the trailers `Task: TASK-075` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/app/resolve.py` (new, about +70)
- `tests/unit/test_resolve_use_case.py` (new, about +130)
- `tests/integration/test_resolve_projection.py` (new, about +70)
- `docs/architecture.md`: a new "Resolve use case" section after "Approve plan use case", covering the signature, the refusals, the two events, the `TRANSITIONS` check and the test files.
- `docs/progress.md`:
  - Current becomes TASK-075, with a Done line.
  - Outline item 11 shrinks to 11b, the `resolve` command.
- `docs/tasks/TASK-075-resolve-use-case.md` (this record).

Not expected to change: `cli.py`, `app/run.py`, `ports/`, `adapters/`, `domain/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, `docs/decisions.md`.

Expected size: about 270 lines with tests, about 70 of them in `src/`.

## Design choices to confirm at planning
1. **Split item 11 into use case (11a) and command (11b).** This follows the TASK-035/TASK-036 precedent. Done together it would come to about 310 lines.
2. **The task's state comes from `plans.tasks(approved.id)`.** No new `Plans` read is needed, and `approved()` gives the plan whose absence is the first refusal.
3. **`decision` is typed `ResolveDecision`** from `domain/payloads.py` (decision row of 2026-10-15, TASK-058). The command (11b) maps `--retry`/`--abandon` onto it.
4. **The `TRANSITIONS` check comes after the refusals and before `TaskResolved`.** "Raises before recording anything" covers both events. The `not_escalated` refusal makes the check unreachable in practice, so AC5 tests it by monkeypatching the module-level name.
5. **No `_Chain` reuse.** It is private to `run.py` and records only as `orchestrator`. The two events are written in `resolve.py`, as `approve_plan.py` writes its own.

## Open questions
None for this slice.

Notes for TASK-076 (the command), not blocking here:
- "Output" says "neither or both is a usage error" (exit 2, standard error). It does not say whether that check comes before the "run `openfactory init` first" check. Typer and click validate options before the command body runs, which puts it first.
- The spec fixes no text for the usage error message.

## Outcome
- Added `src/openfactory/app/resolve.py` (`ResolveRefusal`, `ResolveResult`, `resolve_task`) with `tests/unit/test_resolve_use_case.py` and `tests/integration/test_resolve_projection.py`. AC1 to AC6 are covered.
- No existing code or test changed. No test edits were made and no mechanical fixes.
- No ADR, `decisions.md` row, port, adapter, dependency, event type or schema change.
- Docs: "Resolve use case" section in `docs/architecture.md`; `docs/progress.md` updated (Current, Done line, outline item 11 shrunk to 11b).
- Next: TASK-076, the `resolve` command in `cli.py`.
