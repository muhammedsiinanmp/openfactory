# TASK-003: Spec domain models and deterministic validation rules

- Milestone: M1
- Status: planned
- Tests: acceptance
- Spec sections: "Spec input format" (the `requirements.yaml` example and "Validation rules (deterministic, run by `openfactory validate`)"); "Tech stack and repo layout"

## Objective
Add the pure domain models for a spec set (requirements, acceptance criteria, ADRs, declared components) and a pure function that applies the four M1 deterministic validation rules and returns every violation found, so later M1 tasks (YAML loader, `openfactory validate`, hashing and `approve spec`) have a validated spec to build on.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- `AcceptanceCriterion`, `Requirement`, `Adr` and `SpecSet`: Pydantic v2 models in `domain/models.py`, with the field names used in the spec's `requirements.yaml` example.
- `SpecViolation` and `validate_spec(spec: SpecSet) -> list[SpecViolation]` in `domain/spec_validation.py`: the first four deterministic validation rules.
- Unit tests for the models and the rules.

Out (follow-up M1 tasks, not this one):
- Reading `specs/requirements.yaml`, ADR markdown front matter and `policies.yaml` from disk, and the YAML parser dependency that needs.
- The fifth validation rule ("No requirement is deleted while tasks still reference it..."). The spec says it is "Enforced from M2, when tasks exist".
- Advisory LLM checks (vague wording, possible duplicates).
- Content hashing, `spec_version`, and the `SpecImported`, `SpecValidated` and `SpecApproved` events and their payloads.
- Projection tables and replay.
- CLI commands `init`, `validate`, `approve spec`, `events`.
- A `policies.yaml` model.
- `domain/states.py` task state machine; `Task`, `AgentRun` and `Gate` models.
- Reporting of structurally malformed input (a missing `title`, a wrong type). The models raise `pydantic.ValidationError` for those; turning that into user-facing output belongs to the loader task.

## Acceptance criteria
Each criterion cites the spec heading it traces to. "Validation rules" means the list "Validation rules (deterministic, run by `openfactory validate`)" under "Spec input format". Criteria AC2 to AC6 depend on the Interpretations below being confirmed.

- [ ] AC1 ("Spec input format": the `requirements.yaml` example; "Tech stack and repo layout": `models.py # Requirement, Task, AgentRun, Gate, ...` and "the domain never imports infrastructure"): the requirement in the spec's example, given as a Python dict, validates into a `Requirement` with fields `id`, `title`, `statement`, `priority`, `constrained_by`, `components` and `acceptance_criteria`, the last being a list of `AcceptanceCriterion` with `id` and `text`. A `SpecSet` holds `components`, `requirements` and `adrs` (each `Adr` has `id` and `status`). `validate_spec` on a spec set built from that example, with `auth` declared as a component and `ADR-001` present with status `accepted`, returns an empty list. `domain/models.py` and `domain/spec_validation.py` import nothing from `openfactory.adapters`, `openfactory.app` or `openfactory.ports` (checked by parsing imports with `ast`).
- [ ] AC2 (Validation rules: "IDs match `REQ-[A-Z]+-\d{3}`, `ADR-\d{3}`, `AC-...`"): `validate_spec` returns a violation with rule `id-format` naming the offending id for a requirement id that does not fully match `REQ-[A-Z]+-\d{3}` (for example `REQ-auth-001`, `REQ-AUTH-1`, `AUTH-001`), for an ADR id that does not fully match `ADR-\d{3}` (for example `ADR-1`), and for an acceptance criterion id that does not start with `AC-` followed by at least one character (for example `AUTH-001-1`). `REQ-AUTH-001`, `ADR-001` and `AC-AUTH-001-1` give no such violation.
- [ ] AC3 (Validation rules: "...and are unique"): two requirements with the same id, two ADRs with the same id, or two acceptance criteria with the same id (in the same requirement or in different requirements) each give a violation with rule `id-unique` naming the duplicated id.
- [ ] AC4 (Validation rules: "Every requirement has at least one acceptance criterion"): a requirement whose `acceptance_criteria` is empty or omitted gives a violation with rule `missing-acceptance-criteria` naming the requirement id.
- [ ] AC5 (Validation rules: "Every `constrained_by` reference points to an existing ADR with status `accepted`"): a `constrained_by` entry naming an ADR that is not in the spec set gives a violation with rule `constrained-by` naming the requirement id, and so does an entry naming an ADR whose status is not `accepted` (for example `proposed`). A requirement with an empty or omitted `constrained_by` gives none.
- [ ] AC6 (Validation rules: "Every component named by a requirement is declared in the top-level `components` list"; "deterministic"): a requirement naming a component that is not in `SpecSet.components` gives a violation with rule `undeclared-component` naming the requirement id. A spec set that breaks several rules at once returns all of the violations in one call rather than stopping at the first, and two calls on the same spec set return the same list.

## Interpretations
The spec leaves these open. They are proposals and must be confirmed by the human before tests are written.

1. Violations are returned, not raised. The models hold structure only (ids are plain strings), and `validate_spec` returns a list of `SpecViolation(rule, subject, message)`, where `rule` is one of `id-format`, `id-unique`, `missing-acceptance-criteria`, `constrained-by`, `undeclared-component` and `subject` is the id the violation is about. The spec says `validate` "checks the specs" but gives no output shape; a list lets `openfactory validate` print every problem at once.
2. Acceptance criterion ids: the spec writes the pattern as `AC-...`. Proposed rule: the id starts with `AC-` and has at least one more character. Nothing stricter is imposed.
3. Uniqueness scope: requirement ids are unique among requirements, ADR ids among ADRs, and acceptance criterion ids across the whole spec set.
4. Top-level `components`: the spec's `requirements.yaml` example does not show it. Proposed: `SpecSet.components` is a list of component names (strings). Which file it is read from is the loader task's question.
5. ADR fields: the spec says ADRs have "YAML front matter" but lists no fields. Proposed: `Adr` has `id` and `status` only (the two the rules and the `adrs` projection need), and `status` is any string, of which only `accepted` satisfies the `constrained_by` rule.
6. `priority`: the example shows `must` and the spec lists no other values. Proposed: a required string with no closed set. `constrained_by`, `components` and `acceptance_criteria` default to empty lists.

## Plan
1. Create branch `task/TASK-003-spec-models-validation` from an up-to-date main.
2. Write failing tests in `tests/unit/test_spec_validation.py`, one or more per criterion AC1 to AC6, building spec sets from Python dicts (no files, no YAML).
3. Add `src/openfactory/domain/models.py`: `AcceptanceCriterion`, `Requirement`, `Adr`, `SpecSet` as Pydantic v2 models.
4. Add `src/openfactory/domain/spec_validation.py`: `SpecViolation` and `validate_spec`, one small function per rule, results concatenated in a fixed rule order.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, and `uv run python scripts/check_docs.py` until all are green.
6. Update living docs and this record's Outcome; commit with trailers `Task: TASK-003` and `Milestone: M1`.

## Files expected to change
- `src/openfactory/domain/models.py` (new)
- `src/openfactory/domain/spec_validation.py` (new)
- `tests/unit/test_spec_validation.py` (new)
- `docs/architecture.md` (Components: add "Spec models" and "Spec validation")
- `docs/progress.md` (Current task, then Done)
- `docs/decisions.md` (rows for the confirmed interpretations)
- `docs/tasks/TASK-003-spec-models-validation.md` (this record; Outcome at close)

## Living docs to update
- `docs/architecture.md`: Components.
- `docs/progress.md`: Current and Done.
- `docs/decisions.md`: the confirmed interpretations.
- `CHANGELOG.md`: no entry expected (no user-visible change).
- `README.md`: no change expected.

## New dependencies
None. Pydantic v2 is already declared in `pyproject.toml`.

## Outcome
<!-- filled at close: what was built, deviations from plan, follow-ups -->
