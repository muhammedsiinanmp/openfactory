# TASK-027: Plan checks: the rule names and the eight content rules

- Milestone: M2
- Status: done
- Tests: acceptance
- ADR: none. No new port, adapter, dependency, event type, payload or storage change. The cycle check without a graph library is already decided (SC-41, `docs/decisions.md`, spec v1.10 "Tech stack and repo layout"). Module, type and function names are rows in `docs/decisions.md` (Open questions 1 to 3).
- Spec impact: none. The spec settles everything the eight content rules need. Two open spec items touch outline item 6 and are left out of this task; neither blocks it (see "Spec gaps").
- Spec sections (spec v1.10): "Task contract" ("Plan checks": the table and the paragraph after it; "Planning": the reply shape); "Spec input format" ("Spec field rules": `deprecated`, `components`); "CLI commands" ("Output": the `plan` rejection line); "Tech stack and repo layout" (the "Graph queries" row; "the domain never imports infrastructure")

## Objective
Add the pure domain function that checks a list of `PlannedTask` against a `SpecSet` and returns every rejection under the eight content rules of "Plan checks" (`duplicate-task-id`, `unknown-dependency`, `cycle`, `unknown-requirement`, `deprecated-requirement`, `unknown-criterion`, `undeclared-component`, `uncovered`), with the plan's own set of nine rule names, so the plan use case can reject a reply and print its rejection lines.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings.

## Scope
In:
- `src/openfactory/domain/plan_checks.py` (new; names per Open questions 1 to 3):
  - `PlanRule(StrEnum)` with the nine names of the spec's table, `schema` included. It is separate from `Rule` in `domain/spec_validation.py`.
  - `PlanRejection`: frozen, `extra="forbid"`, with `rule` (`PlanRule`), `subject` (`str`) and `message` (`str`).
  - `check_plan(tasks: Sequence[PlannedTask], spec: SpecSet) -> list[PlanRejection]`: runs the eight content rules and returns every rejection in one run. It never returns `schema`.
  - The cycle check in plain Python: a task lies on a cycle when it can reach itself through `depends_on`.
- Unit tests that build `PlannedTask` and `SpecSet` from Python values. No files, no database, no LLM.
- One conformance test added to `tests/unit/test_spec_conformance.py`: the rule names in the first column of the "Plan checks" table equal the values of `PlanRule`.

Out (not this task):
- The `schema` rule: validating the raw reply `{"tasks": [...]}`, turning `pydantic.ValidationError` into `schema` rejections, their subject, their count, and a reply with no structured result. The spec does not settle it (see "Spec gaps"). `check_plan` takes tasks that already validated, so "when there is one the other checks are not run" is the caller's sequencing.
- A repeated entry in `depends_on` that names a task in the plan (Later, TASK-022). No rule is added for it and no criterion asserts what it gives.
- Sorting rejections for output, the `rule  subject  message` line, `AgentRunFinished.error`, the retry, and every caller (outline items 9 and 10). The order `check_plan` returns is not part of the criteria.
- Task-id uniqueness against the `tasks` projection (Later, before M6; F-7 of `docs/spec-audits/2026-10-10-M2.md`). `check_plan` reads no projection.
- `LLMProvider`, `GitProvider` and their adapters (items 7, 8); the `deleted-requirement` validation rule (item 12).
- Any change to `domain/contracts.py`, `domain/models.py`, `domain/spec_validation.py`, `domain/payloads.py`, `domain/plans.py`, everything under `app/`, `ports/`, `adapters/`, and `cli.py`.
- What the other seven rules report for a plan in which two tasks share an id, beyond one rejection per subject and offending id. Such a reply is rejected by `duplicate-task-id` in any case.
- Exact message wording. The spec asks only that "the message names the offending id".
- Hardening against exotic inputs: a `depends_on` entry that is not of task-id form, empty strings in a list, a spec set with duplicated ids (it can never be approved).

## Acceptance criteria
"Plan checks" and "Planning" are under "Task contract"; "Spec field rules" is under "Spec input format"; "Output" is under "CLI commands". Names follow the proposals under Open questions; if the human answers otherwise, the names change and the assertions do not.

"The spec set" has components `[auth]` and three requirements: `REQ-AUTH-001` (criteria `AC-AUTH-001-1`, `AC-AUTH-001-2`), `REQ-AUTH-002` (criterion `AC-AUTH-002-1`) and the deprecated `REQ-AUTH-003` (criterion `AC-AUTH-003-1`). "The valid plan" has two tasks: `AUTH-001` (requirements `[REQ-AUTH-001]`, both its criteria, components `[auth]`, no dependencies) and `AUTH-002` (requirements `[REQ-AUTH-002]`, criterion `AC-AUTH-002-1`, components `[auth]`, `depends_on` `[AUTH-001]`). Each case changes the valid plan in one way. "The rejections under rule X are" means the returned rejections whose `rule` is X, compared without regard to order. "Names Y" means the string Y is in `message`.

- [x] AC1 ("Plan checks": the table's "Rule" column and "These names are the plan's own set, separate from the validation rule names"; "Output": "it prints that reply's rejections as `rule  subject  message`"; "Tech stack and repo layout": "the domain never imports infrastructure"):
  - The values of `PlanRule` are exactly `schema`, `duplicate-task-id`, `unknown-dependency`, `cycle`, `unknown-requirement`, `deprecated-requirement`, `unknown-criterion`, `undeclared-component` and `uncovered`, and equal the rule names parsed from the spec's table (conformance test).
  - `PlanRule` is not `Rule`, and `PlanRejection` has exactly the fields `rule`, `subject` and `message`.
  - `check_plan` of the valid plan and the spec set returns `[]`.
  - `openfactory.domain.plan_checks` imports nothing from `openfactory.adapters`, `openfactory.app` or `openfactory.ports` (checked by parsing imports with `ast`).
- [x] AC2 ("Plan checks": "`duplicate-task-id` | two tasks share a `task_id` | the task id", "`unknown-dependency` | `depends_on` names a task that is not in the plan | the task id", and "There is one rejection per subject and offending id, and the message names the offending id: one `duplicate-task-id` per duplicated id"):
  - With a second task whose `task_id` is `AUTH-001`, the rejections under `duplicate-task-id` are one, with subject `AUTH-001`. With three tasks sharing `AUTH-001` it is still one.
  - With `AUTH-001` and `AUTH-002` each used twice, there are two, one per id.
  - With `AUTH-002` depending on `[AUTH-001, AUTH-009]`, the rejections under `unknown-dependency` are one, with subject `AUTH-002`, and its message names `AUTH-009`.
  - With `AUTH-002` depending on `[AUTH-009, AUTH-009]` there is one; on `[AUTH-008, AUTH-009]` there are two, both with subject `AUTH-002`.
- [x] AC3 ("Plan checks": "`cycle` | the task lies on a cycle: it can reach itself through `depends_on` | the task id" and "one `cycle` per task that lies on a cycle"; "Tech stack and repo layout": "the plan's cycle check is plain Python, with no graph library"):
  - With `AUTH-001` depending on `[AUTH-002]` and `AUTH-002` on `[AUTH-001]`, the rejections under `cycle` are two, with subjects `AUTH-001` and `AUTH-002`; each message names its task id.
  - With a ring of three tasks there are three.
  - With `AUTH-001` depending on `[AUTH-001]`, there is one `cycle` rejection with subject `AUTH-001` and no `unknown-dependency` rejection.
  - With a third task that depends on a task of a two-task cycle and that no task depends on, there are two `cycle` rejections and none has the third task as subject.
  - A diamond (`A`; `B` and `C` depend on `A`; `D` depends on `B` and `C`) has no `cycle` rejection.
  - The module imports neither `networkx` nor `graphlib` (checked by parsing imports with `ast`).
- [x] AC4 ("Plan checks": "`unknown-requirement` | a task names a requirement that is not in the spec version | the task id", "`deprecated-requirement` | a task names a deprecated requirement | the task id", "`undeclared-component` | a component is not declared in the spec | the task id"):
  - With `AUTH-001` naming `[REQ-AUTH-001, REQ-AUTH-009]`, the rejections under `unknown-requirement` are one, with subject `AUTH-001`, naming `REQ-AUTH-009`. Naming it twice in the list still gives one.
  - With both tasks naming `REQ-AUTH-009`, there are two, one per task.
  - With `AUTH-002` naming `[REQ-AUTH-002, REQ-AUTH-003]`, the rejections under `deprecated-requirement` are one, with subject `AUTH-002`, naming `REQ-AUTH-003`; there is no `unknown-requirement` rejection.
  - With `AUTH-001` naming components `[auth, billing]`, the rejections under `undeclared-component` are one, with subject `AUTH-001`, naming `billing`.
- [x] AC5 ("Plan checks": "`unknown-criterion` | an acceptance criterion is unknown, or does not belong to one of the task's requirements | the task id"):
  - With `AUTH-001` also listing `AC-AUTH-009-1`, which is not in the spec set, the rejections under `unknown-criterion` are one, with subject `AUTH-001`, naming `AC-AUTH-009-1`.
  - With `AUTH-001` (requirements `[REQ-AUTH-001]`) also listing `AC-AUTH-002-1`, which belongs to `REQ-AUTH-002`, there is one, with subject `AUTH-001`, naming `AC-AUTH-002-1`.
  - With `AUTH-001` naming both `REQ-AUTH-001` and `REQ-AUTH-002` and listing the criteria of both, there is none.
- [x] AC6 ("Plan checks": "`uncovered` | a requirement that is not deprecated, or one of its acceptance criteria, appears in no task | the requirement id or the acceptance criterion id" and "one `uncovered` per id that appears in no task"; "Spec field rules": "the planner creates no tasks for it"):
  - With `AUTH-002` removed from the valid plan, the rejections under `uncovered` are two, with subjects `REQ-AUTH-002` and `AC-AUTH-002-1`; each message names its subject.
  - With `AUTH-001` listing only `AC-AUTH-001-1`, there is one, with subject `AC-AUTH-001-2`, and none with subject `REQ-AUTH-001`.
  - The valid plan has no `uncovered` rejection for `REQ-AUTH-003` or `AC-AUTH-003-1`.
  - A plan that breaks two rules at once (`AUTH-001` names `REQ-AUTH-009`, and `AUTH-002` is removed) returns the rejections of both rules in one call.

## Architecture rules that apply
- `src/openfactory/domain` stays pure: the function takes and returns domain models, with no I/O and no import from `adapters`, `app` or `ports`.
- No runtime dependency is added; the cycle check uses no graph library (spec v1.10, SC-41).
- No event is recorded, no projection is read or written, no LLM call is made.
- Tests from the test-writer are fixed.
- No hardening beyond the spec's rules.

## Plan
1. Create branch `task/TASK-027-plan-content-checks` from an up-to-date main and commit this record.
2. Get the human's answers to the Open questions; record them here and as rows in `docs/decisions.md`.
3. Write failing tests:
   - `tests/unit/test_plan_checks.py` for AC1 to AC6, with one helper that builds the spec set and the valid plan.
   - One test added to `tests/unit/test_spec_conformance.py`: the backticked names in the first column of the table under "**Plan checks:**" equal `{rule.value for rule in PlanRule}`. By that file's convention it skips until the code exists.
   - No existing test is changed.
4. In `domain/plan_checks.py`, add `PlanRule` and `PlanRejection`.
5. Add one private function per rule, each returning one rejection per `(subject, offending id)`:
   - `duplicate-task-id`: ids that occur more than once.
   - `unknown-dependency`: `depends_on` entries not among the plan's task ids.
   - `cycle`: build the mapping from task id to the dependencies that are in the plan; a task is on a cycle when a walk from its dependencies reaches it.
   - `unknown-requirement`, `deprecated-requirement`, `undeclared-component`: look up each named id in the spec set.
   - `unknown-criterion`: a criterion not among the criteria of the task's requirements that are in the spec set.
   - `uncovered`: each requirement that is not deprecated and each of its criteria that no task lists.
6. Add `check_plan`, which concatenates the eight results.
7. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until green.
8. Update the living docs and the Outcome. Commit `feat(domain): add the plan checks for a planner reply` with trailers `Task: TASK-027` and `Milestone: M2`.

## Files expected to change
- `src/openfactory/domain/plan_checks.py` (new, about 110 lines)
- `tests/unit/test_plan_checks.py` (new, about 240 lines)
- `tests/unit/test_spec_conformance.py` (one test added; nothing existing changed)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-027-plan-content-checks.md`

About 110 lines of source and 255 of tests. That is over the 300-line aim; Open question 4 offers a split.

Not expected to change: every other file under `src/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, and every other existing test file.

## Living docs to update
- `docs/architecture.md`: a new "Plan checks" component section (`PlanRule`, `PlanRejection`, `check_plan`, what each rule reports, that `schema` is never returned by it); one sentence in "Data flow" that no use case calls it yet.
- `docs/progress.md`: Current, then Done; reword outline item 6 to what is left (the `schema` rule) or remove it, as the human decides; keep the TASK-022 Later line.
- `docs/decisions.md`: rows for the answered questions.
- `CHANGELOG.md`, `README.md`: no change (no command or output is added).

## New dependencies
None.

## Spec gaps
None for this task.

Open spec items that touch outline item 6, left out of this task and not blocking it:
- "Task contract" ("Plan checks") against "Domain model and storage" (DDL of `task_deps`): a repeated entry in one task's `depends_on` that names a task in the plan passes every plan check, and the projector's `task_deps` insert then fails on its primary key. Spec v1.10 does not settle it. It does not block this task: the eight rules are defined without it, and if the answer is a tenth plan check it is one more name and one more function. It blocks the plan use case (item 9).
- "Task contract" ("Plan checks": the `schema` row and "A `schema` rejection has the field path in its message") with "Tech stack and repo layout" ("An envelope that parses but whose structured result is missing or fails Pydantic validation is a rejected reply"): three things are missing.
  - How many `schema` rejections one reply gets.
  - What "when it can be read" means for a `task_id` that is a string but fails the pattern.
  - The rule, subject and message for a reply with no structured result.
  This is finding F-3 of `docs/spec-audits/2026-10-11-proposal-v1.10.md`, with a proposed fix, and no decisions row answers it. It does not block this task, which leaves the `schema` rule out. It blocks the task that builds that rule.

Readings, not gaps:
- A requirement "appears in" a task when it is in the task's `requirements`; a criterion when it is in a task's `acceptance_criteria`.
- "One `uncovered` per id that appears in no task": a requirement no task names gives one rejection for itself and one for each of its criteria that no task lists.
- A task that depends on itself names a task that is in the plan, so it is not an `unknown-dependency`; it can reach itself, so it is a `cycle`.
- A dependency on a task that is not in the plan is not followed by the cycle check: nothing can be reached through it.
- "One rejection per subject and offending id": the same id named twice in one list of one task gives one rejection.
- The rules run on a spec set that is an approved version, so ids in it are unique.

## Open questions
None is a spec decision; each has a proposal.

Answered 2026-10-11: the human approved every proposal as written (the advisor agreed with all six).
- 1 to 5: as proposed below.
- 6 (outline item 6 afterwards): reword it to "The `schema` plan rule: the reply model and its rejections · after /spec-change settles F-3", kept as its own item before item 9; `/spec-change` for F-3 and the repeated `depends_on` entry runs before that item is planned.
- Advisor notes on 5, taken into the implementation: the docstring says the `uncovered` rejections come in spec-set order, and the "once per offending id" dedupe keeps first-seen order (no iteration over a `set`).

1. **Module and names.** Proposed: a new `domain/plan_checks.py` with `PlanRule`, `PlanRejection` and `check_plan`, as `domain/spec_validation.py` holds `Rule`, `SpecViolation` and `validate_spec`. Alternative: put them in `domain/plans.py` beside `PlanRef` and `Task`.
2. **`PlanRule.schema` now.** Proposed: the enum holds all nine names in this task, so the conformance test compares the whole table, and `check_plan` never returns `schema` (as `validate_spec` never returns `Rule.schema`). Alternative: eight names now, `schema` added with the task that builds it.
3. **Input type.** Proposed: `check_plan(tasks: Sequence[PlannedTask], spec: SpecSet)`. The reply model for `{"tasks": [...]}` comes with the `schema` rule. Alternative: define the reply model here and pass it.
4. **Size.** Proposed: one task (about 365 lines with tests), since the eight rules share one fixture and one module. Alternative: split into the graph rules (`duplicate-task-id`, `unknown-dependency`, `cycle`) and the reference rules (the other five).
5. **Return order.** Proposed: rule order of the spec's table, then the order of the reply, with no test on it; the sort "as violation lines are" is done where the lines are made (items 9 and 10). Alternative: `check_plan` returns them sorted.

## Outcome
Built:
- `domain/plan_checks.py`: `PlanRule(StrEnum)` with the nine names of the spec's table, frozen `PlanRejection` (`rule`, `subject`, `message`, `extra="forbid"`) and `check_plan(tasks, spec) -> list[PlanRejection]`, which runs the eight content rules, one rejection per subject and offending id, in the table's rule order then reply order (`uncovered` in spec-set order). It never returns `schema`. The cycle check is a plain Python walk over `depends_on` that does not follow dependencies outside the plan.
- Tests: `tests/unit/test_plan_checks.py` (AC1 to AC6) and `test_plan_rules_match_the_spec_table` in `tests/unit/test_spec_conformance.py`.
- No use case calls `check_plan` yet. No new dependency, no ADR.

Deviations from plan: size only. The plan estimated about 365 lines with tests (110 source, 255 tests); the result is 527 (209 in `plan_checks.py`, 310 in `test_plan_checks.py`, 8 in the conformance test). Scope and behaviour are as planned.

Test edits: no test-writer test was edited. No existing test changed.

Follow-ups:
- Needs `/spec-change`: F-3 of `docs/spec-audits/2026-10-11-proposal-v1.10.md` (the `schema` plan rule), before outline item 6 is planned.
- Needs `/spec-change`: a repeated `depends_on` entry (Later, TASK-022), before the plan use case (item 9) is planned.
- `docs/adr/ADR-004-python-over-go.md` Consequences still says networkx is a new dependency; spec v1.10 and SC-41 say it is not. Amending an accepted ADR is the human's.
