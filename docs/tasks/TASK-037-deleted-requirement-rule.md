# TASK-037: The `deleted-requirement` rule in `validate` and `approve spec`

- Milestone: M2
- Status: done
- Tests: acceptance
- ADR: ADR-012. It is accepted and says "`validate` and `approve_spec` gain a `Plans` argument for the deleted-requirement rule. The task that adds it must keep the M1 tests' assertions as they are." No new port, adapter, dependency, event type, payload shape or storage change: `Plans.live_tasks_referencing` and `SpecVersions.spec_set` exist (TASK-024, TASK-025), and `RecordedViolation.rule` is a plain string, so a new rule name changes no payload. The function names, the message text and where the rule lives are rows in `docs/decisions.md` (Open questions 2 to 4).
- Spec impact: none. Spec v1.11 settles when a requirement is deleted, when a task still references it, the count of violations, the subject, what the message lists, when the rules run, and the output lines (see "Spec gaps": readings only).
- Spec sections (spec v1.11): "Spec input format" › "Validation rules" (the fifth bullet, "No requirement is deleted while tasks still reference it ..."; the paragraph "When there is any `schema` violation in the spec files, the rules above are not run"), "Spec field rules" ("The rule names are ..."; "`deleted-requirement` (from M2; its subject is the requirement id)"), "Spec versions" (the four `validate` cases; the two `approve spec` paragraphs); "Domain model and storage" › "Ids" ("They read the plan and task projections through the `Plans` port: ... the live tasks that reference a requirement"; "the stored spec set of a version"); "CLI commands" › "Output" (the `validate` and `approve spec` bullets); "Milestones and definition of done" (milestone 2: "the deleted-requirement rule")

## Outline item
M2 outline item 12, whole. Item 13 (M2 close test) is left.

## Objective
Make `validate` and `approve spec` report one `deleted-requirement` violation for each requirement that is in the latest approved spec version, absent from the spec files, and still referenced by a live task, by giving both use cases a `Plans` argument.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings.

## Scope
In (names per Open questions 2 to 4):
- `src/openfactory/domain/spec_validation.py`:
  - `Rule.deleted_requirement = "deleted-requirement"`.
  - A pure function that gives the ids of the requirements in the approved spec set that are absent from the loaded one, ascending.
  - A pure function that builds the `SpecViolation` for one deleted requirement from its id and the referencing task ids.
  - `validate_spec(spec)` keeps its signature and never returns the new rule.
- `src/openfactory/app/validate.py`: `validate(files, versions, plans, recorder)`.
  - In the `validated` case, after `validate_spec`: when there is a latest approved version, read `versions.spec_set(approved.id)`, and for each deleted requirement id call `plans.live_tasks_referencing(id)`; a non-empty answer gives one violation.
  - The new violations follow those of `validate_spec` in `ValidateResult.violations` and in `SpecValidated.violations`.
- `src/openfactory/app/approve_spec.py`: `approve_spec(files, versions, plans, recorder)` passes `plans` to `validate`. Nothing else changes.
- `src/openfactory/cli.py`: `validate` and `approve spec` pass `adapters.plans`. No output code changes: `_result_lines` already prints and sorts any rule.
- Mechanical edits to four existing test files so they call the new signatures (Open question 1).

Out (not this task):
- The M2 close test (item 13).
- Any change to the ports, the adapters, the projector or the payload models. `live_tasks_referencing` is used as TASK-025 left it; which task states are live, and that a draft plan's tasks count, are its tested behaviour.
- `plan`, `approve plan`, `replan`, and invalidating tasks on a spec change (M6).
- A hint in the output on how to fix the violation beyond the message text.
- An approved version whose stored spec set cannot be read (`spec_set` gives `None`): unreachable; an `assert` and no criterion (Open question 5).
- What a command prints when the recorder's catch-up fails (Later, F-1).
- Hardening against exotic inputs.

## Acceptance criteria
"Validation rules", "Spec field rules" and "Spec versions" are under "Spec input format"; "Ids" under "Domain model and storage"; "Output" under "CLI commands".

Fixtures:
- Unit tests use in-memory fakes of `SpecFiles`, `SpecVersions`, `Plans` and the recorder, defined in the new test file. The fake `SpecVersions` returns a chosen `latest_approved()`, `current_draft()` and `spec_set(version_id)`. The fake `Plans` holds a dict from requirement id to task ids, returns the list as given (not sorted), and keeps the requirement ids it was asked for.
- "The approved set" is `sv_01` with `REQ-AUTH-001` to `REQ-AUTH-005`, each with one criterion and valid.

- [x] AC1 ("Spec field rules": "The rule names are `id-format`, `id-unique`, `missing-acceptance-criteria`, `constrained-by`, `undeclared-component`, `deleted-requirement` (from M2; its subject is the requirement id) and `schema`"; "Validation rules": "A requirement is deleted when it is in the latest approved spec version and absent from the files being validated" and "unless the new version marks it `deprecated`"):
  - The values of `Rule` are exactly the seven names in that sentence, read from the spec file by a conformance test in `tests/unit/test_spec_conformance.py`.
  - The domain function, given the approved set and a loaded set that holds `REQ-AUTH-001`, `REQ-AUTH-004` with `deprecated: true` and a new `REQ-AUTH-006`, returns `REQ-AUTH-002`, `REQ-AUTH-003`, `REQ-AUTH-005` in that order.
  - `validate_spec` on that loaded set returns no `deleted-requirement` violation.
- [x] AC2 ("Validation rules": "No requirement is deleted while tasks still reference it" and "its message lists the ids of the tasks that reference it, in ascending order as strings"; "Spec field rules": "its subject is the requirement id"; "Spec versions": "Otherwise it records `SpecImported` ..., then runs the rules and records `SpecValidated`"). With the approved set, files that hold every requirement except `REQ-AUTH-002`, and the fake `Plans` answering `["AUTH-010", "AUTH-002"]` for `REQ-AUTH-002`:
  - `validate` returns outcome `validated` with exactly one violation: rule `deleted-requirement`, subject `REQ-AUTH-002`, and a message that holds `AUTH-002` before `AUTH-010` (the exact text per Open question 3).
  - `SpecImported` and then `SpecValidated` are recorded for `sv_02`, and `SpecValidated.violations` holds that one violation with `rule` `"deleted-requirement"`.
- [x] AC3 ("Validation rules": "There is one violation per deleted requirement" and "A task still references it when ..."; "Spec field rules": "Validation returns every violation in one run"; "Output": "`SpecValidated.violations` is recorded in the order the rules returned it"). With the approved set and files that hold `REQ-AUTH-001` (now with no acceptance criteria) and `REQ-AUTH-004` with `deprecated: true`; the fake `Plans` answers two task ids for `REQ-AUTH-002`, none for `REQ-AUTH-003`, one for `REQ-AUTH-004` and one for `REQ-AUTH-005`:
  - The violations are, in this order: `missing-acceptance-criteria` for `REQ-AUTH-001`, `deleted-requirement` for `REQ-AUTH-002`, `deleted-requirement` for `REQ-AUTH-005`. There is none for `REQ-AUTH-003` or `REQ-AUTH-004`.
  - The recorded `SpecValidated.violations` has the same three in the same order.
  - `Plans.live_tasks_referencing` was asked for `REQ-AUTH-002`, `REQ-AUTH-003` and `REQ-AUTH-005` only.
- [x] AC4 ("Validation rules": "When there is any `schema` violation in the spec files, the rules above are not run"; "Spec versions": "If the hash equals the latest approved version's, it records no events ... The rules are not run"; "Validation rules": "A requirement is deleted when it is in the latest approved spec version"). In each case the result has no `deleted-requirement` violation and `Plans.live_tasks_referencing` is never called:
  - There is no approved version (the first `validate` of a repo).
  - The files cannot be loaded; outcome `unloadable`, no event.
  - The files equal the latest approved version; outcome `matches_approved`, no event.
- [x] AC5 ("Spec versions": "If the hash equals the current draft's, it records no `SpecImported`. It runs the rules and records `SpecValidated` for the draft again, because a rule's result can change while the files do not: the deleted-requirement rule depends on the tasks"). With the approved set, a draft `sv_02` whose hash equals the files' (which lack `REQ-AUTH-002`), and the same fakes across two `validate` calls:
  - First call, the fake `Plans` answers `["AUTH-002"]`: one `SpecValidated` with the `deleted-requirement` violation is recorded and no `SpecImported`.
  - Second call, the fake now answers `[]` (the task was abandoned): one more `SpecValidated` for `sv_02` with empty `violations` is recorded, no `SpecImported`, and the result has no violations.
- [x] AC6 ("Output": "`validate` and `approve spec` print one line per violation ... as `rule  subject  message`", "`validate` exits with 1 if there is any violation", "It exits 1 when it refuses because of violations", "A refused `approve spec` prints no status line"; "Spec versions": "If they load but have violations, it records `SpecImported` (if the files changed) and `SpecValidated` with the violations, then refuses without recording `SpecApproved`"; "Validation rules": "The fix is to restore the requirement with `deprecated: true`" and "Tasks of a draft plan count"). Through `CliRunner` in a repo under `tmp_path`, with `sv_01` (two requirements) approved through the app and a draft `plan_01` recorded as one `PlanCreated` through `SqliteEventRecorder`, whose task `AUTH-002` lists `REQ-AUTH-002`; then `REQ-AUTH-002` is removed from `requirements.yaml`:
  - `validate` prints `deleted-requirement  REQ-AUTH-002  <message>` and `1 violations, 0 policy problems` on standard output and exits 1.
  - `approve spec` prints the same two lines and no status line, exits 1, and the event log holds no `SpecApproved` for `sv_02`; its last event is a `SpecValidated` for `sv_02` with the violation.
  - After `REQ-AUTH-002` is restored with `deprecated: true`, `approve spec` prints `0 violations, 0 policy problems` and `approved sv_02` and exits 0.

## Architecture rules that apply
- `domain` stays pure: the two new functions take models and plain lists and call no port. The port calls are in `app/validate.py`.
- `app` depends on `domain` and `ports` only; `validate` reads the projections only through `SpecVersions` and `Plans` (ADR-001, ADR-012).
- All state changes go through the events table: the only writes are `EventRecorder.record` of `SpecImported`, `SpecValidated` and `SpecApproved`, built through the payload models (ADR-007).
- `cli.py` only passes `adapters.plans` (ADR-011); it holds no rule.
- Tests from the test-writer are fixed. The existing tests' assertions stay as they are (ADR-012); only the call sites and fakes listed in Open question 1 change, and each edit is reported in the Outcome.
- No hardening beyond the spec's rules.

## Plan
1. Create branch `task/TASK-037-deleted-requirement-rule` from an up-to-date main.
2. Get the human's answers to the Open questions; record them here and as rows in `docs/decisions.md`.
3. Write failing tests:
   - `tests/unit/test_deleted_requirement_rule.py` (new) for AC1 (domain part) to AC5.
   - `tests/unit/test_spec_conformance.py`: one new test for the rule names (AC1).
   - `tests/integration/test_cli_deleted_requirement.py` (new) for AC6, with repo setup as in `tests/integration/test_cli_approve_spec.py` and the `PlanCreated` builder as in `tests/integration/test_cli_approve_plan.py`.
4. Add the `Rule` member and the two domain functions; update the module docstring.
5. Change `validate` and `approve_spec` to take `plans`; add the rule to the `validated` case.
6. Pass `adapters.plans` in the `validate` and `approve spec` commands.
7. Make the mechanical edits to the four existing test files (Open question 1) and check that no assertion changed.
8. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until green.
9. Update the living docs and the Outcome. Commit `feat(app): add the deleted-requirement rule` with trailers `Task: TASK-037` and `Milestone: M2`.

## Files expected to change
- `src/openfactory/domain/spec_validation.py` (about 30 lines added)
- `src/openfactory/app/validate.py` (about 20 lines added)
- `src/openfactory/app/approve_spec.py` (about 4 lines)
- `src/openfactory/cli.py` (2 call sites)
- `tests/unit/test_deleted_requirement_rule.py` (new, about 200 lines)
- `tests/integration/test_cli_deleted_requirement.py` (new, about 110 lines)
- `tests/unit/test_spec_conformance.py` (one test added)
- `tests/unit/test_validate_use_case.py`, `tests/unit/test_approve_spec_use_case.py`, `tests/integration/test_duplicate_ids.py`, `tests/integration/test_cli_validate.py` (mechanical edits only, Open question 1)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, `CHANGELOG.md`
- `docs/tasks/TASK-037-deleted-requirement-rule.md`

Not expected to change: everything under `ports/` and `adapters/`, `domain/payloads.py`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, and every other existing test file.

The total is about 380 changed lines, above the 300-line aim (Open question 6).

## Living docs to update
- `docs/architecture.md`:
  - The spec validation section: the `Rule` list, the two new functions, and the sentence that says the fifth rule "is enforced from M2 and not implemented".
  - "Validate use case" and "Approve spec use case": the new signatures and the rule in the `validated` case.
  - "CLI": `validate` and `approve spec` pass `plans`.
  - "Data flow" and the `Plans` section: `live_tasks_referencing` now has a caller.
- `docs/progress.md`: Current, then Done; remove outline item 12.
- `docs/decisions.md`: rows for the answered questions.
- `CHANGELOG.md`: `validate` and `approve spec` report `deleted-requirement`.
- `README.md`: only if it lists the rule names.

## New dependencies
None.

## Spec gaps
Spec impact is "none". Nothing is missing for this task.

Readings, not gaps:
- "In the latest approved spec version" is the stored spec set of `SpecVersions.latest_approved()`, read with `spec_set`. The current draft is not compared.
- "Absent from the files being validated" compares requirement ids. A requirement present with `deprecated: true` is not absent, so the "unless" clause needs no code of its own. A requirement that was already deprecated in the approved version and is then removed is deleted, like any other.
- With no approved version nothing is deleted, so the rule gives nothing and `Plans` is not asked.
- A deleted requirement with no live task gives no violation ("while tasks still reference it").
- When the files equal the approved version the rules are not run; no requirement can be deleted in that case.
- The rule is the fifth in the spec's list, so its violations follow those of the first four; within the rule they are in ascending requirement id. "Output" sorts the printed lines anyway.
- The spec gives the exact message text of no validation rule; it says what this one lists. The text is a decisions row (Open question 3), as for the other five rules.
- Which states are live and that a draft plan's tasks count are in `Plans.live_tasks_referencing` (TASK-025); AC6 shows the second through a draft plan.

## Later lines in `docs/progress.md`: taken or left
- None of the Later lines is about this rule. All are left.
- F-1, what a command prints when the recorder's catch-up fails: left.

## Open questions
None is a spec decision. Each has a proposal. Question 1 needs the human's approval before work starts, because it edits fixed tests.

1. **Edits to three fixed test files.** ADR-012 foresees them ("every caller and fake" changes; the assertions stay). Proposed, with no assertion touched:
   - `tests/unit/test_validate_use_case.py` and `tests/unit/test_approve_spec_use_case.py`: the `run` helper passes a fake `Plans` whose `live_tasks_referencing` returns `[]`, and `FakeVersions` gains `spec_set`. The second is needed because the fakes have no `spec_set` today, and tests such as the ones at lines 193 and 213 of `test_validate_use_case.py` set an approved version whose hash differs from the files', so the new code would call a method the fake lacks.
   - `tests/integration/test_duplicate_ids.py` (lines 311 and 322): open a `SqlitePlans` on the same database and pass it.
   - Alternative: a keyword argument `plans: Plans | None = None` so that no test changes. It lets a caller skip the rule silently, so it is not proposed.
2. **Where the rule lives.** Proposed: two pure functions in `domain/spec_validation.py`, `deleted_requirements(approved: SpecSet, spec: SpecSet) -> list[str]` and `deleted_requirement_violation(requirement_id: str, task_ids: list[str]) -> SpecViolation`; `app/validate.py` makes the port calls between them. Alternative: one domain function that takes a mapping from requirement id to task ids, which makes `validate` ask `Plans` before it knows which requirements are deleted.
3. **Message text.** Proposed: `requirement 'REQ-AUTH-002' is deleted but tasks still reference it: AUTH-002, AUTH-010`, with the ids joined by `, `. It follows the form of the other rule messages. Alternative: add the fix, `; restore it with deprecated: true`.
4. **Who keeps the ascending order of the task ids.** The port promises ascending ids. Proposed: `deleted_requirement_violation` sorts the ids itself and the fake returns them out of order, so AC2 can fail (as answer 4 of TASK-035). Alternative: rely on the port's order.
5. **`spec_set` gives `None` for the approved version.** It cannot happen: an approved version has a row. Proposed: treat it as no deleted requirement, with no criterion and no test. Alternative: an `assert`.
6. **Size.** About 380 lines with tests. Proposed: keep it as one task, because the signature change forces `cli.py` and the three test files to change in the same commit. Alternative: move AC6 (the command test, about 110 lines) to a TASK-038 marked `integration-only`.

## Answers (the human, 2026-10-12: "do as the advisor says")
1. Approved, with the advisor's two changes: `plans` is a required argument, and the mechanical edits cover four files, not three. The fourth is `tests/integration/test_cli_validate.py` (the `approve(repo)` helper near line 197 calls `approve_spec` directly; it opens a `SqlitePlans` on the same database and passes it). The `spec_set` added to `FakeVersions` in the two unit files returns an empty `SpecSet()`. No assertion is touched; each edit is reported in the Outcome.
2. As proposed: `deleted_requirements` and `deleted_requirement_violation` in `domain/spec_validation.py`, the port calls in `app/validate.py`.
3. As proposed: `requirement 'REQ-AUTH-002' is deleted but tasks still reference it: AUTH-002, AUTH-010`, with no fix hint.
4. As proposed: `deleted_requirement_violation` sorts the task ids itself; the test fake returns them out of order.
5. The advisor's answer, not the proposal: `assert` that the approved version's stored spec set is not `None`, with the one-line comment `prepare_plan` has in `app/plan.py`. No criterion and no test.
6. As proposed: one task.

## Outcome
<!-- filled at close: what was built, deviations from plan, follow-ups -->
Built as planned, with the answers above:
- `domain/spec_validation.py`: `Rule.deleted_requirement`, `deleted_requirements(approved, spec)` and `deleted_requirement_violation(requirement_id, task_ids)`, which sorts the task ids. `validate_spec` is unchanged.
- `app/validate.py`: `validate(files, versions, plans, recorder)`. In the `validated` case, when there is an approved version, it reads the version's stored spec set (asserted not `None`), asks `Plans.live_tasks_referencing` for each deleted id and appends one violation per non-empty answer after those of `validate_spec`.
- `app/approve_spec.py`: `approve_spec(files, versions, plans, recorder)` passes `plans` to `validate`.
- `cli.py`: `validate` and `approve spec` pass `adapters.plans`.

Edits to existing tests (call sites and fakes only, no assertion touched; approved in answer 1):
- `tests/unit/test_validate_use_case.py`: `FakeVersions` gains `spec_set`, which returns an empty `SpecSet()`; new `FakePlans` whose `live_tasks_referencing` returns `[]`; the `run` helper passes `FakePlans()` to `validate`.
- `tests/unit/test_approve_spec_use_case.py`: the same three edits, for `approve_spec`.
- `tests/integration/test_duplicate_ids.py`: imports `SqlitePlans`; `test_ac5_...` opens one on the same database, passes it to `validate` and `approve_spec`, and closes it.
- `tests/integration/test_cli_validate.py`: imports `SqlitePlans`; the `approve(repo)` helper opens one, passes it to `approve_spec`, and closes it.

No edit to the tests the test-writer wrote for this task. Deviations from the plan: none. Checks: 997 tests pass, ruff, pyright and `check_docs` clean.
