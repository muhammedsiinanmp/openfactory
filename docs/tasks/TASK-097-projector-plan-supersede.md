# TASK-097: Projector supersedes the approved plan on a replan's `PlanApproved`

- Milestone: M6
- Status: done
- Tests: acceptance
- ADR: ADR-019 (accepted). Its "One approved plan" bullet decides this rule: "A `PlanApproved` applied while another plan is `approved` marks that plan `superseded` and moves every one of its tasks, whatever its state, into the new plan (`tasks.plan_id`), before it inserts the new `contract` links. The rule reads only the projections". Its Consequences say "the projector's `PlanApproved` branch gains the move." The task adds no port, adapter, event type, payload field, table, column, dependency or convention, so no new ADR is needed. The decisions.md row for SC-158 (2026-10-24) already records the decision. Design choices 1 and 2 add one row each.
- Spec impact: none (see Spec gaps: one reading, nothing missing)
- Spec sections (spec v1.18; SC-158):
  - "Domain model and storage" › "Projection rules": "A `PlanApproved` applied while another plan is `approved` (a replan, see Spec diff and impact analysis) marks that plan `superseded` and moves every one of its tasks, whatever its state, to the newly approved plan by setting `tasks.plan_id`, before it inserts the `contract` links of the new plan. So at most one plan is `approved`, and after a replan it holds the untouched, the invalidated and the new tasks."
  - "Domain model and storage" › "Projection rules", `trace_links`: "`PlanApproved` inserts, for each task of the plan, requirement → task for each id in its contract's `requirements`, and task → task from the task to each task it depends on, both with source `contract`. A plan that was never approved has no rows." Also: "No row is removed when a task is invalidated or abandoned."
  - "Domain model and storage" › "Projection rules", rebuild: "A rebuild is identical when, for every projection table, the rows read in primary-key order are equal before and after. The projector therefore uses only the data in the event and the projections built by earlier events".
  - "Domain model and storage" › "Projections": `plans` "status (draft, approved, superseded)".
  - "Spec diff and impact analysis" › "Approving a replan": "It records `PlanApproved`, and the projector supersedes the earlier plan and moves its tasks into the new one (see Projection rules)."

## Outline item
M6 outline item 4 in `docs/progress.md`. It depends on nothing new. Item 7 (`approve plan` after a replan) relies on it: that item records the `PlanApproved`, then the invalidations and readies, which read the moved tasks through `Plans.tasks(<new plan>)`.

## Objective
When `SqliteProjector` applies a `PlanApproved` while another plan is `approved`, it marks that plan `superseded` and moves all of its tasks into the newly approved plan by setting `tasks.plan_id`. It does this before inserting the new plan's `contract` links.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/adapters/sqlite_projector.py`, the `PlanApproved` branch (a private `_apply_plan_approved` if that reads better). The order is:
  1. `UPDATE tasks SET plan_id = <new> WHERE plan_id IN (SELECT id FROM plans WHERE status = 'approved' AND id != <new>)`
  2. `UPDATE plans SET status = 'superseded' WHERE status = 'approved' AND id != <new>`
  3. the existing `UPDATE plans SET status = 'approved' WHERE id = <new>`
  4. the existing `_link_plan(<new>)`

  All four read only projections and the event, as ADR-018 and ADR-019 allow.
- New tests in `tests/integration/test_sqlite_projector_m6.py` (`test_task097_ac<N>_...`). Events are recorded through `SqliteEventRecorder`, as the TASK-090 tests in that module do.
- `SqlitePlans` reads are used as an outside check.

Out:
- Any change to `app/approve_plan.py`: the impact read, the refusal, the invalidations and the `pending` readies are item 7.
- `replan`, plan checks and `task-id-in-use` (items 5 and 6).
- Any change to `SqlitePlans`, `SqliteTraces`, `run`, `status`, `resolve` or the `<base>` rule. ADR-019 Consequences: "need no change".
- Checking event order, for example a `PlanApproved` for an unknown or non-draft plan. architecture.md says the projector does not check event sequences.
- Per-plan cost (M7, F-16 in Later).

## Acceptance criteria
- [x] **AC1** ("Projection rules": "marks that plan `superseded` … So at most one plan is `approved`"):
  - Setup: `plan_01` is approved, then a draft `plan_02` is created and approved.
  - The `plans` rows are `("plan_01", "sv_01", "superseded")` and `("plan_02", "sv_02", "approved")`.
  - Exactly one `plans` row has status `approved`.
  - `SqlitePlans.approved()` is `plan_02`.
- [x] **AC2** ("Projection rules": "moves every one of its tasks, whatever its state, to the newly approved plan by setting `tasks.plan_id` … after a replan it holds the untouched, the invalidated and the new tasks"):
  - Before the replan's `PlanApproved`, `plan_01` holds tasks in at least the states `passed`, `ready`, `pending`, `escalated`, `abandoned` and `invalidated`. One of them has a nonzero `attempt` and `cost_usd`.
  - After it, every one of those tasks has `plan_id` `plan_02`. Its `state`, `objective`, `contract`, `attempt` and `cost_usd` are unchanged.
  - The `task_deps`, `commits`, `agent_runs` and `gate_results` tables are unchanged by that event.
  - `SqlitePlans.tasks("plan_02")` lists the moved tasks and the draft's new tasks, sorted by id. `SqlitePlans.tasks("plan_01")` is empty.
- [x] **AC3** ("Projection rules": "before it inserts the `contract` links of the new plan"; `trace_links`: "`PlanApproved` inserts, for each task of the plan …"; "No row is removed when a task is invalidated or abandoned"):
  - `plan_02` has a new task linked to a requirement and depending on a moved `passed` task of `plan_01`.
  - After the replan's `PlanApproved`, the `trace_links` rows from before it are all still present.
  - The added rows are exactly the new tasks' requirement → task and task → task `contract` links, the dependency on the moved task included. Each is stored once.
- [x] **AC4** ("Projection rules": "A `PlanApproved` applied while another plan is `approved`"; "Planning": "The projector marks the earlier draft `superseded`"):
  - A `PlanApproved` applied when no plan is `approved` moves no task and marks no plan `superseded`.
  - This holds with an earlier draft superseded by `PlanCreated` present: its row stays `superseded` with no tasks, and the approved plan holds only its own tasks.
  - The existing projector tests (`test_sqlite_projector_m2.py`, `test_sqlite_projector_m5.py`, `test_sqlite_plans.py`) pass without edits.
- [x] **AC5** ("Projection rules", rebuild: "A rebuild is identical when, for every projection table, the rows read in primary-key order are equal before and after"):
  - The log covers spec `sv_01` approved, `plan_01` approved, task state changes, a run with a commit, `sv_02` approved, then `plan_02` created and approved.
  - Rebuilt with `SqliteProjector.rebuild` over that log, every projection table has the same rows as before the rebuild.
- [x] **AC6** (CLAUDE.md "All state changes go through the events table"; ADR-019 Consequences "the projector's `PlanApproved` branch gains the move"):
  - The only file changed under `src/` is `src/openfactory/adapters/sqlite_projector.py`.
  - No table, column, event type or payload model changes.
  - The full suite passes with no existing test edited.

## Architecture rules that apply
- The projector is an internal adapter helper with no port (ADR-009). It uses only the event's data and earlier projections: no clock and no generated ids.
- The rule writes projections only while an event is applied through the recorder.

## Plan
1. Create branch `task/TASK-097-projector-plan-supersede` from an up-to-date main.
2. Record the human's answers to the Design choices and Open questions in this record.
3. Test-writer: write failing tests `test_task097_ac<N>_...` in `tests/integration/test_sqlite_projector_m6.py`.
   - Fixture: `sv_01` and `sv_02` imported and approved; `plan_01` with tasks AUTH-001 to AUTH-006 approved; `TaskStateChanged` events putting them in the AC2 states; one `AgentRunStarted`/`AgentRunFinished` with cost and one `CommitRecorded` for the `passed` task; then `plan_02` for `sv_02` with a new task AUTH-010 depending on the passed task, created and approved.
4. Implement the move and supersede in the `PlanApproved` branch, in the order given under Scope.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`, the "SQLite projector" `apply` paragraph: `PlanApproved` first moves the tasks of any other `approved` plan into the new plan and marks that plan `superseded`, then sets its own status, then inserts the links. The `contract` sentence covers all tasks now in the plan, the moved ones being no-ops.
   - `docs/progress.md`: Current, a Done line, item 4 marked done, and the Later lines as answered under Open questions.
   - `docs/decisions.md`: one row per Design choice.
   - This record's Outcome.
7. Commit `feat(adapters): supersede the approved plan when a replan is approved` with trailers `Task: TASK-097` and `Milestone: M6`. Do not push.

## Files expected to change
- `src/openfactory/adapters/sqlite_projector.py` (about +15)
- `tests/integration/test_sqlite_projector_m6.py` (about +180)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, this record

Not expected to change: `app/`, `domain/`, `ports/`, other adapters, `cli.py`, any existing test, `docs/spec/`, `docs/adr/`.

## Design choices to confirm at planning
1. **Link insertion after the move.**
   - Proposed: keep `_link_plan(<new>)` as it is. After the move it selects every task now in the new plan, the moved ones included. Their `contract` links were stored when `plan_01` was approved and no rule removes `contract` rows, so `INSERT OR IGNORE` adds only the new tasks' links. The rows are the same as with the alternative.
   - Alternative: limit the links to the tasks the new plan's `PlanCreated` created. That needs the draft's task ids read before the move, which is more code for the same rows.
2. **"Another plan" in SQL.**
   - Proposed: the move and the supersede exclude the event's own `plan_id` (`id != ?`). A `PlanApproved` for the plan that is already approved then changes nothing.
   - Alternative: run them before the new plan is marked approved, with no exclusion. The result is the same for every sequence the commands can record. The spec does not ask for a repeated approval to be handled, so no test covers that case (CLAUDE.md: no hardening against exotic inputs).

## Open questions
1. **TASK-094 Later line ("the AC1 'another plan' case is not really tested … worth covering in item 4").**
   - With this rule the case can be built from events: after the move, `Traces.impact_traversal("plan_01", seeds)` on the superseded plan must return no tasks even though its old tasks keep their seed links. Removing the `plan_id` filter would make that test fail.
   - Proposed: leave it out of this task. It tests `SqliteTraces`, not the rule's spec text, and the Later line stays as it is.
   - Alternative: add one test to `tests/integration/test_sqlite_traces.py`, with no `src/` change. The human decides.
2. **Later line "Before M6: `SqlitePlans.latest_commit` joins `commits` to `tasks` on the task id … `last_gate_result` … same exposure".**
   - Under spec v1.18 the moved tasks bring their commits into the new plan on purpose: "Approving a replan" says `<base>` stays the chain tip. Reusing a task id is stopped by `task-id-in-use` (item 5).
   - Proposed: at close, mark the line as settled by SC-158, SC-159 and item 5, and do not delete it. The human decides whether to delete it.

## Answers at planning (human, 2026-10-24: "do as the advisor says")
1. Design choice 1: proposed. `_link_plan(<new>)` unchanged.
2. Design choice 2: proposed. `id != ?` in the move and the supersede; no repeated-approval test.
3. Open question 1: proposed, with the advisor's change. No `SqliteTraces` test here; the TASK-094 Later line's "worth covering in item 4" is reworded to point at a later M6 task (item 7).
4. Open question 2: the alternative. At close, the commit-carry part of the Later line is marked settled by SC-158 and SC-159; the id-reuse part stays open until item 5 (`task-id-in-use`) lands, and the line is deleted at item 5's close.

## Spec gaps
None; Spec impact is none. One reading, not a gap:
1. "before it inserts the `contract` links of the new plan" gives the same `trace_links` rows whether "the tasks of the plan" means only the draft's tasks or all tasks in the plan after the move. The moved tasks' links are already stored and `contract` rows are never removed. Design choice 1 picks the shorter code.

Audit findings F-1 and F-2 (`docs/spec-audits/2026-10-24-proposal-v1.18.md`, due with `/spec-change` before item 5) concern `unknown-dependency` and `uncovered` in a replan. They do not touch this rule.

## Outcome
- One src file changed: `src/openfactory/adapters/sqlite_projector.py` (about +13 lines, the move and the supersede in the `PlanApproved` branch, in the order given under Scope).
- 5 new tests in `tests/integration/test_sqlite_projector_m6.py`. AC3 and AC4 passed before the implementation, as regression guards.
- The test-writer fixed a setup helper's reason for `invalidated` while writing, before any implementation.
- No existing test edited.
- 1941 passed; ruff, pyright and check_docs clean.
- Later lines updated as answered at planning (TASK-094 review reworded to item 7; the commit-carry part of the `latest_commit` line settled by SC-158 and SC-159, the id-reuse part open until item 5).
- Review: approve, no blocking issues. Non-blocking note 1 applied: the `docs/architecture.md` "does not check event sequences" sentence no longer says a `PlanApproved` for an unknown or non-draft plan ends in `sqlite3.IntegrityError`; it now says such an event is applied as given. Notes 2 (AC3's "stored once" is also held by the schema) and 3 (AC5's check reads `plan_id` by column position) not applied.
