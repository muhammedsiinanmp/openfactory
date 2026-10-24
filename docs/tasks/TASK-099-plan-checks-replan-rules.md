# TASK-099: Plan checks — `task-id-in-use` and the replan rules of `unknown-dependency` and `uncovered`

- Milestone: M6
- Status: done
- Tests: acceptance
- ADR: ADR-019 (accepted, with its amendment for SC-189). Its "Plan checks" bullet covers the replan rules and `task-id-in-use`. The task adds no port, adapter, event type, payload field, table, dependency or convention.
- Spec impact: none
- Spec sections (spec v1.19):
  - "Task contract" › "Plan checks" table:
    - `unknown-dependency`: "`depends_on` names a task that is not in the plan; in a replan, also not an untouched task that is neither `abandoned` nor `invalidated`" (SC-163, SC-189)
    - `uncovered`: "a requirement that is not deprecated, or one of its acceptance criteria, appears in no task; in a replan, in no new task and no untouched task that is not `invalidated`" (SC-163)
    - `task-id-in-use`: "a `task_id` is already in the `tasks` projection, outside the draft being replaced" (SC-163)
  - "Task contract" › "Plan checks": "There is one rejection per subject and offending id, and the message names the offending id"
  - "Task contract" › "Plan checks": "A reply with no tasks is accepted only when `uncovered` accepts it; for a first plan, that is when the spec set has no requirement that is not deprecated" (SC-188)
  - "Task contract" › "Planning": "A task id is unique among all tasks in the `tasks` projection; the `task-id-in-use` check enforces it."
  - "Spec diff and impact analysis" › "Step 3": "The untouched tasks are the other tasks of the approved plan."

## Outline item
M6 outline item 5, first half (5a): the pure checks. 5b gives `plan` the ids in use: a `Plans` read of the task ids outside the draft being replaced, its `SqlitePlans` version, and `run_planner` passing them. Item 6 (`replan`) passes the untouched tasks.

## Objective
`check_plan` gains `task-id-in-use` and the replan forms of `unknown-dependency` and `uncovered`. These come through two keyword-only arguments: the task ids in use, and the untouched tasks. With neither argument given, the result is the same as today.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/domain/plan_checks.py`:
  - `check_plan(tasks, spec, *, ids_in_use: Collection[str] = frozenset(), untouched: Sequence[Task] = ())`, where `Task` comes from `domain/plans.py`.
  - New `_task_id_in_use`, run last, in the spec table's order.
  - `_unknown_dependency` also accepts the ids of untouched tasks that are neither `abandoned` nor `invalidated`.
  - `_uncovered` also counts the requirements and criteria in the contracts of untouched tasks that are not `invalidated`.
  - Module docstring updated.
- New `test_task099_ac<N>_...` tests in `tests/unit/test_plan_checks.py`.

Out:
- `app/plan.py`, `ports/plans.py`, `adapters/sqlite_plans.py`, `cli.py` (that wiring is 5b).
- `replan` and its prompt (item 6).
- Any change to `cycle`, `unknown-requirement`, `deprecated-requirement`, `unknown-criterion` or `undeclared-component`. These rules read only the reply's tasks.

## Acceptance criteria
- [ ] **AC1** (Plan checks, `task-id-in-use`; "one rejection per subject and offending id"):
  - A reply task whose `task_id` is in `ids_in_use` gets exactly one `task-id-in-use` rejection. Its subject is that id and its message names the id.
  - This holds even when the reply lists the id twice; the `duplicate-task-id` rejection still comes separately.
  - A task whose id is not in use gets no such rejection.
  - With `ids_in_use` not given, no `task-id-in-use` rejection is produced.
- [ ] **AC2** (Plan checks, `unknown-dependency`, "in a replan, also not an untouched task that is neither `abandoned` nor `invalidated`"):
  - A dependency on an untouched task in `pending`, `ready`, `running`, `gating`, `failed`, `escalated` or `passed` gets no rejection.
  - A dependency on an untouched task in `abandoned` or `invalidated`, or on an id that is neither in the reply nor among the untouched tasks, gets one `unknown-dependency` rejection. Its subject is the depending task and its message names the dependency's id.
- [ ] **AC3** (Plan checks, `uncovered`, "in a replan, in no new task and no untouched task that is not `invalidated`"):
  - A requirement that is not deprecated, or one of its criteria, is covered when only an untouched task that is not `invalidated` names it. This includes an `abandoned` one.
  - A requirement or criterion named only by an `invalidated` untouched task gets one `uncovered` rejection per id.
  - Deprecated requirements are still skipped.
- [ ] **AC4** (Plan checks, "A reply with no tasks is accepted only when `uncovered` accepts it"):
  - `check_plan([], spec, untouched=...)` returns no rejections when untouched tasks that are not `invalidated` cover every requirement that is not deprecated, and each of its criteria. Otherwise it returns only `uncovered` rejections.
  - For a first plan (no `untouched`), an empty reply is accepted only when the spec set has no requirement that is not deprecated.
- [ ] **AC5** (Plan checks table; the replan rules change only these two rules):
  - A dependency on an untouched task is never followed by `cycle`.
  - What an untouched task's own contract names cannot cause a `unknown-requirement`, `deprecated-requirement`, `unknown-criterion` or `undeclared-component` rejection.
  - The order of rejections is still the spec table's rule order.
- [ ] **AC6** (CLAUDE.md, tests are fixed; architecture rules):
  - `domain/plan_checks.py` is the only `src/` file changed, and it still imports only `openfactory.domain`, `pydantic` and the standard library.
  - `app/plan.py` is unchanged, and the full suite passes with no existing test edited.

## Architecture rules that apply
- `domain/plan_checks.py` stays pure: no I/O, and no imports from `adapters`, `app` or `ports`.

## Plan
1. Create branch `task/TASK-099-plan-checks-replan-rules` from an up-to-date main.
2. Record the human's answers to the Design choices below.
3. Test-writer: write the failing `test_task099_` tests for AC1 to AC5 in `tests/unit/test_plan_checks.py`. Build `Task` objects with completed contracts for the untouched tasks.
4. Implement:
   - the two keyword-only arguments;
   - `_task_id_in_use` (each id once, in reply order);
   - the widened `_unknown_dependency` and `_uncovered`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md` "Plan checks" (lines 265 to 271): ten rule names; the new `check_plan` signature and what each argument means; the two rules' replan forms.
   - `docs/progress.md`: Current, a Done line, and item 5 split into 5a (done) and 5b. The TASK-042 Later line stays until 5b.
   - This record's Outcome.
7. Commit `feat(domain): add task-id-in-use and the replan plan checks` with trailers `Task: TASK-099` and `Milestone: M6`. Do not push.

## Files expected to change
- `src/openfactory/domain/plan_checks.py` (about +40)
- `tests/unit/test_plan_checks.py` (about +150)
- `docs/architecture.md`, `docs/progress.md`, this record

Not expected to change: `app/`, `ports/`, `adapters/`, `cli.py`, `docs/spec/`, `docs/adr/`.

## Design choices to confirm at planning
1. **How replan data reaches `check_plan`.** Proposed: two keyword-only arguments with empty defaults, `ids_in_use` and `untouched: Sequence[Task]`.
   - An empty `untouched` behaves exactly like a first plan, so no separate replan flag is needed.
   - The caller works out "outside the draft being replaced" and "the other tasks of the approved plan". `check_plan` stays pure and does not decide which tasks are untouched.
   - Alternative: a frozen `ReplanContext` model. That is more types for the same data.
2. **`abandoned` untouched tasks count for `uncovered`.** This is the literal reading of "no untouched task that is not `invalidated`", and it matches the SC-163 decisions row: it keeps "only the impacted subgraph" true when an abandoned task exists. They do not count for `unknown-dependency` (SC-189).
3. **`task-id-in-use` subject and order.** One rejection per reply task id that is in use, in reply order, run after `uncovered` to follow the table. The message names the id.
4. **Splitting item 5.** 5a is this task; 5b is the `Plans` read and the `plan` wiring. Alternative: one task with both, at about 350 lines and with a port change.

Human's answers (2026-10-24): all five proposed answers approved as written (design choices 1 to 4; the Later line stays out of scope). Advisor: 5 AGREE. Caller duty noted for 5b and item 6: the untouched tasks' ids must also be in `ids_in_use`.

## Spec gaps
None; Spec impact is none. The spec's text settles each rule. Design choices 1 and 3 are about how the code is laid out, not what the rules mean, and choice 2 is the literal reading backed by the SC-163 row.

## Open questions
- Is the 5a/5b split acceptable (Design choice 4)?
- The progress.md Later line (spec v1.19 advisor) stays open and out of scope: on a second replan the planner cannot see the ids of earlier-invalidated tasks, so it may reuse one and cost a `task-id-in-use` retry. This task only produces the rejection.

## Outcome
`check_plan` now takes keyword-only `ids_in_use: Collection[str] = frozenset()` and `untouched: Sequence[Task] = ()`; with neither it behaves as before.
- New `_task_id_in_use`: one rejection per distinct reply id in `ids_in_use`, reply order, run last after `uncovered`, message `task id 'X' is already in use`.
- `_unknown_dependency` also accepts untouched task ids not `abandoned` or `invalidated`; `_uncovered` also counts the contracts of untouched tasks not `invalidated`.
- Only `src/openfactory/domain/plan_checks.py` changed in `src/`; 23 new `test_task099_` tests in `tests/unit/test_plan_checks.py`, no existing test edited, no test edits by the implementer. Full suite: 1984 passed.
- Reviewer note 1 applied at the human's direction ("do as u would do"): `check_plan` adds the untouched tasks' ids to `ids_in_use` itself, so 5b and item 6 have no caller duty; one test of my own added for it (`test_task099_untouched_task_id_counts_as_in_use`). Notes 2 (weak AC5 cycle test) and 3 (indirect AC1 "not in use" case) not applied. Nothing passes the new arguments yet.
- Remaining: 5b (the `Plans` read, `SqlitePlans`, `run_planner` wiring); the TASK-042 Later line stays until then.
