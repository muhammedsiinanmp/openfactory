# TASK-003: Spec domain models and deterministic validation rules

- Milestone: M1
- Status: done
- Tests: acceptance
- Spec sections (spec v1.3): "Spec input format" (the `requirements.yaml` example, "Validation rules (deterministic, run by `openfactory validate`)" and "Spec field rules"); "Tech stack and repo layout"

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
- Reporting of structurally malformed input (a missing `title`, a wrong type, a `priority` or ADR `status` outside its closed set). The models raise `pydantic.ValidationError` for those; turning that into user-facing output belongs to the loader task.

## Acceptance criteria
Each criterion cites the spec v1.3 heading it traces to. "Validation rules" means the list "Validation rules (deterministic, run by `openfactory validate`)" and "Spec field rules" the list of that name, both under "Spec input format".

- [x] AC1 ("Spec input format": the `requirements.yaml` example; Spec field rules: `components`, `priority`, optional fields, ADR front matter; "Tech stack and repo layout": `models.py # Requirement, Task, AgentRun, Gate, ...` and "the domain never imports infrastructure"): the spec's `requirements.yaml` example, given as a Python dict, validates into a `SpecSet` with `components` (`list[str]`), `requirements` and `adrs`. A `Requirement` has `id`, `title`, `statement`, `priority`, `constrained_by`, `components` and `acceptance_criteria`, the last a list of `AcceptanceCriterion` with `id` and `text`; `constrained_by`, `components` and `acceptance_criteria` default to empty lists when omitted. An `Adr` has `id` and `status`. `priority` accepts `must`, `should` and `could` and `status` accepts `proposed`, `accepted` and `superseded`; any other value raises `pydantic.ValidationError`. `validate_spec` on the example spec set, with `ADR-001` present with status `accepted`, returns an empty list. `domain/models.py` and `domain/spec_validation.py` import nothing from `openfactory.adapters`, `openfactory.app` or `openfactory.ports` (checked by parsing imports with `ast`).
- [x] AC2 (Validation rules: "IDs match `REQ-[A-Z]+-\d{3}`, `ADR-\d{3}` and `AC-[A-Z]+-\d{3}-\d+`"): `validate_spec` returns a violation with rule `id-format` and the offending id as subject for a requirement id that does not fully match `REQ-[A-Z]+-\d{3}` (for example `REQ-auth-001`, `REQ-AUTH-1`, `AUTH-001`), for an ADR id that does not fully match `ADR-\d{3}` (for example `ADR-1`), and for an acceptance criterion id that does not fully match `AC-[A-Z]+-\d{3}-\d+` (for example `AUTH-001-1`, `AC-AUTH-001`, `AC-auth-001-1`, `AC-AUTH-1-1`). `REQ-AUTH-001`, `ADR-001`, `AC-AUTH-001-1` and `AC-AUTH-001-12` give no such violation.
- [x] AC3 (Validation rules: "...and are unique across the whole spec set"): two requirements with the same id, two ADRs with the same id, or two acceptance criteria with the same id (in the same requirement or in different requirements) each give a violation with rule `id-unique` and the duplicated id as subject.
- [x] AC4 (Validation rules: "Every requirement has at least one acceptance criterion"; Spec field rules: "reported by validation rather than rejected while parsing"): a requirement whose `acceptance_criteria` is empty or omitted parses without error and gives a violation with rule `missing-acceptance-criteria` and the requirement id as subject.
- [x] AC5 (Validation rules: "Every `constrained_by` reference points to an existing ADR with status `accepted`"; Spec field rules: "Only `accepted` satisfies `constrained_by`"): a `constrained_by` entry naming an ADR that is not in the spec set gives a violation with rule `constrained-by` and the requirement id as subject, and so does an entry naming an ADR whose status is `proposed` or `superseded`. A requirement with an empty or omitted `constrained_by` gives none.
- [x] AC6 (Validation rules: "Every component named by a requirement is declared in the top-level `components` list"; Spec field rules: "Validation returns every violation in one run, each with the rule name, the ID it concerns, and a message. It never stops at the first."): a requirement naming a component that is not in `SpecSet.components` gives a violation with rule `undeclared-component` and the requirement id as subject. Every `SpecViolation` has `rule`, `subject` and a non-empty `message`. A spec set that breaks several rules at once returns all of the violations in one call, and two calls on the same spec set return the same list.

## Decisions
Confirmed by the human on 2026-10-08; items 2, 4, 5 and 6 are also written into spec v1.3 ("Spec field rules").

1. Violations are returned, not raised. `validate_spec` returns `list[SpecViolation(rule, subject, message)]` and collects every violation. `rule` is one of `id-format`, `id-unique`, `missing-acceptance-criteria`, `constrained-by`, `undeclared-component`; `subject` is the id the violation is about.
2. Acceptance criterion ids must match `^AC-[A-Z]+-\d{3}-\d+$`.
3. Requirement ids are unique among requirements, ADR ids among ADRs, and acceptance criterion ids across the whole spec set.
4. `components` is a top-level list in `requirements.yaml`; `SpecSet.components` is `list[str]`.
5. `Adr` has `id` and `status`; `status` is a closed set: `proposed`, `accepted`, `superseded`. Only `accepted` satisfies `constrained_by`.
6. `priority` is a closed set: `must`, `should`, `could`. `constrained_by`, `components` and `acceptance_criteria` default to empty lists.

7. The two closed sets are enforced by the models, so a value outside them raises `pydantic.ValidationError` at parse time instead of producing a `SpecViolation`. The spec singles out only missing acceptance criteria as "reported by validation rather than rejected while parsing". Confirmed by the human at review; the loader task converts these errors into violations (see `docs/progress.md`, Later).
8. `AcceptanceCriterion`, `Requirement` and `SpecSet` reject unknown fields (`extra="forbid"`); `Adr` ignores them (`extra="ignore"`), since ADR front matter normally has extra fields such as title and date. Confirmed by the human at review.

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
- `docs/decisions.md` (rows for the confirmed decisions)
- `docs/tasks/TASK-003-spec-models-validation.md` (this record; Outcome at close)

## Living docs to update
- `docs/architecture.md`: Components.
- `docs/progress.md`: Current and Done.
- `docs/decisions.md`: the confirmed decisions.
- `CHANGELOG.md`: no entry expected (no user-visible change).
- `README.md`: no change expected.

## New dependencies
None. Pydantic v2 is already declared in `pyproject.toml`.

## Outcome
Closed 2026-10-08.

### What was built
- `src/openfactory/domain/models.py`:
  - `Priority`: a `StrEnum` with the closed set `must`, `should`, `could`.
  - `AdrStatus`: a `StrEnum` with the closed set `proposed`, `accepted`, `superseded`.
  - `AcceptanceCriterion`: a frozen Pydantic v2 model with `id` and `text`, forbidding unknown fields.
  - `Requirement`: a frozen Pydantic v2 model with `id`, `title`, `statement`, `priority` (`Priority`), `constrained_by`, `components`, and `acceptance_criteria` (list of `AcceptanceCriterion`). The latter three default to empty lists when omitted. Unknown fields are forbidden.
  - `Adr`: a frozen Pydantic v2 model with `id` and `status` (`AdrStatus`), ignoring unknown fields.
  - `SpecSet`: a frozen Pydantic v2 model with `components` (list of strings), `requirements` (list of `Requirement`), and `adrs` (list of `Adr`), forbidding unknown fields.
- `src/openfactory/domain/spec_validation.py`:
  - `Rule`: an enum with five rule names: `id-format`, `id-unique`, `missing-acceptance-criteria`, `constrained-by`, `undeclared-component`.
  - `SpecViolation`: a model with `rule` (`Rule`), `subject` (the id), and `message` (a string).
  - `validate_spec(spec: SpecSet) -> list[SpecViolation]`: applies the first four deterministic validation rules from the spec in a fixed order (the fifth, on deleted requirements, is M2 and not implemented), collects every violation, and returns a list (possibly empty). The rules check: ID format (regex), ID uniqueness (global for criterion ids, scoped for requirement and ADR ids), missing acceptance criteria, undeclared ADR references or non-`accepted` ADR status, and undeclared components.
- `tests/unit/test_spec_validation.py`: 37 test cases covering AC1 to AC6. Full suite: 292 passed. ruff clean; `check_docs` passes.

### Deviations from the plan
None in code. The models additionally define the `Priority`, `AdrStatus` and `Rule` enums, and `AcceptanceCriterion`, `Requirement` and `SpecSet` forbid unknown fields while `Adr` ignores them. Neither was in the plan; both were confirmed by the human at review (Decisions 7 and 8).

### Follow-ups
- YAML loader task: read `specs/requirements.yaml` from disk and parse into a `SpecSet`, handling `pydantic.ValidationError` for structural errors.
- `openfactory validate` CLI command: run `validate_spec` and report violations as user-facing errors.
- Spec hashing and `spec_version`: define the canonical form and hash algorithm for `SpecImported`, `SpecValidated` and `SpecApproved` events and their payloads.
- Projection table DDL: the types, keys and id formats for `spec_versions`, `requirements` and `adrs` tables.
- `policies.yaml` schema and model.
- The YAML parser dependency the loader task will need.
- Requirement `deprecated` field for M2 deletion rule.
