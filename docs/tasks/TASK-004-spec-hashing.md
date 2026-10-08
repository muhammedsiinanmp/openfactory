# TASK-004: Spec model fields from v1.4 and canonical spec hashing

- Milestone: M1
- Status: done
- Tests: acceptance
- Spec sections (spec v1.4): "Spec input format" ("Spec field rules" and "Hashing"); "Tech stack and repo layout"

## Objective
Add the two spec model fields that spec v1.4 introduced (`deprecated` on a requirement, `body` on an ADR) and a pure domain function that computes the canonical JSON and SHA-256 hash of an acceptance criterion, a requirement, an ADR and a whole spec set, so later M1 tasks (loader, payload models, projector, `validate`, `approve spec`) have stable hashes to build on.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- `Requirement.deprecated` and `Adr.body` in `domain/models.py`.
- A new pure module `domain/spec_hash.py` with two functions:
  - `canonical_json(item) -> bytes`
  - `content_hash(item) -> str`
  where `item` is an `AcceptanceCriterion`, a `Requirement`, an `Adr` or a `SpecSet`.
- Unit tests for the fields and the hashing, building models from Python dicts (no files, no YAML).

Out (follow-up M1 tasks, not this one):
- The YAML loader: reading `specs/requirements.yaml` and `specs/adrs/*.md`, front matter parsing, line-ending normalisation of the ADR body, the PyYAML dependency, and the `schema` rule that converts `pydantic.ValidationError` into `SpecViolation` (stays in `docs/progress.md` under Later).
- `policies.yaml` model and its hash (the policy hash is recorded with a plan, which is M2).
- Payload models for `SpecImported`, `SpecValidated` and `SpecApproved` (`domain/payloads.py`).
- Projection tables `spec_versions`, `requirements`, `adrs`, the projector and rebuild.
- Spec version ids (`sv_NN`), the draft and approved logic, and the `validate` and `approve spec` use cases.
- CLI commands `init`, `validate`, `approve spec`, `events`.
- The fifth validation rule (deleted requirements), enforced from M2, and the planner's handling of deprecated requirements.
- The structural diff (`added`, `removed`, `modified`, `unchanged`), which is M6. This task only provides the hash it will compare.
- Versioning the hash. The spec handles a change of canonical form by discarding the development database.
- Payload depth limit (stays under Later).

## Acceptance criteria
Each criterion cites the spec v1.4 heading it traces to. "Field rules" means the list "Spec field rules" and "Hashing" the block of that name, both under "Spec input format". In every criterion, "hash" means the result of `content_hash` and "canonical JSON" the result of `canonical_json`.

- [x] AC1 (Field rules: "`deprecated` is an optional boolean on a requirement and defaults to `false`. A deprecated requirement is validated like any other"; "Other front matter fields are ignored. The ADR model also holds the `body`"; "Tech stack and repo layout": "the domain never imports infrastructure"): a `Requirement` built without `deprecated` has `deprecated` equal to `False`, and one built with `deprecated: true` has `True`. An `Adr` built with `id`, `status` and `body` exposes `body` as the given string, and still ignores other fields such as `title` and `date`. An `Adr` built without `body` has `body` equal to the empty string. `validate_spec` on a deprecated requirement with no acceptance criteria still returns a `missing-acceptance-criteria` violation for it. `domain/spec_hash.py` imports nothing from `openfactory.adapters`, `openfactory.app` or `openfactory.ports` (checked by parsing imports with `ast`). The existing tests in `tests/unit/test_spec_validation.py` pass unchanged.
- [x] AC2 (Hashing: "Canonical JSON is the model dumped in JSON mode, with sorted keys, separators `,` and `:` with no spaces, non-ASCII characters left as they are, encoded as UTF-8"): `canonical_json` of the acceptance criterion with id `AC-AUTH-001-1` and text `Café ≥ 1` returns exactly the UTF-8 encoding of `{"id":"AC-AUTH-001-1","text":"Café ≥ 1"}`: no spaces, keys in sorted order, and no `\u` escapes. `canonical_json` of a requirement returns bytes whose top-level keys, read back with `json.loads`, are in sorted order and include `deprecated` and `priority`, with `priority` as the plain string (for example `"must"`).
- [x] AC3 (Hashing: "The hash of a thing is the SHA-256 of the canonical JSON of its parsed model, written as 64 lowercase hex characters"; "An acceptance criterion's hash covers `id` and `text`"): for an acceptance criterion, a requirement, an ADR and a spec set, `content_hash(item)` equals `hashlib.sha256(canonical_json(item)).hexdigest()` and matches `^[0-9a-f]{64}$`. The hash of the AC2 criterion equals the SHA-256 of the literal bytes given in AC2, computed in the test without calling `canonical_json`. Changing a criterion's `id` or its `text` changes its hash. Two calls on equal models return the same hash.
- [x] AC4 (Hashing: "The models are hashed, not the files ... an omitted optional field hashes the same as its default"; "An ADR's hash covers `id`, `status` and `body`"): a requirement built with `constrained_by`, `components`, `acceptance_criteria` and `deprecated` omitted has the same hash as one built with them given as `[]`, `[]`, `[]` and `false`. Two ADRs that differ only in ignored front matter fields (for example `title`) have the same hash. Changing an ADR's `id`, its `status` or its `body` each changes its hash.
- [x] AC5 (Hashing: "Order in the files does not matter: before hashing, `requirements` and `adrs` are sorted by `id`, `acceptance_criteria` by `id`, and `components` and `constrained_by` as strings"): two spec sets with the same content, with unique ids, but with the requirements, the ADRs, the top-level `components`, and each requirement's `acceptance_criteria`, `components` and `constrained_by` listed in a different order have the same spec set hash. A requirement has the same hash whatever the order of its `acceptance_criteria`, `components` and `constrained_by`. In the canonical JSON of the reordered spec set, `requirements` and `adrs` appear in ascending `id` order. Items are sorted by (`id`, canonical JSON of the item), so two spec sets that hold the same two requirements with the same `id` but different content, listed in opposite orders, also have the same spec set hash.
- [x] AC6 (Hashing: "Strings are hashed as parsed: no trimming, no case folding, no Unicode normalisation"; "A requirement's hash covers the whole requirement, including its acceptance criteria"; "The spec set's hash covers the components, the requirements and the ADRs"): a requirement's hash changes when its `statement` gains a trailing space, when a letter changes case, and when `é` is written as one code point instead of `e` plus a combining accent. Changing the `text` of one acceptance criterion, or setting `deprecated` to `true`, changes that requirement's hash and the spec set hash, while the hash of another, untouched requirement in the same spec set stays the same. The spec set hash also changes when a component is added to the top-level `components`, and when an ADR's `body` changes.

## Interpretations
The spec leaves these open. All three were confirmed by the human on 2026-10-08.

1. `Adr.body` when it is not given. The spec says "The ADR model also holds the `body`" and does not say whether the field is required. Confirmed: `body: str = ""`. The loader always fills it, and the fixed TASK-003 tests, which build ADRs from `id` and `status` alone, stay unchanged. With the default, an ADR file whose body is empty and a model built without a body hash the same, which matches "an omitted optional field hashes the same as its default".
2. Module and function names. The spec's layout lists `models.py`, `states.py`, `events.py` and `payloads.py` under `domain/` and names no hashing module. Confirmed: hashing lives in `domain/spec_hash.py`, as `spec_validation.py` was added in TASK-003, with one `content_hash` function for all four models because the spec gives one rule for "the hash of a thing".
3. Duplicate ids. Sorting by `id` alone does not fix the order of two items with the same id, so the hash of a spec set with duplicate ids could depend on file order. Such a spec set always fails the `id-unique` rule, but `validate` hashes it and records `SpecImported` before the rules run. Confirmed: items are sorted by (`id`, canonical JSON of the item), so the hash depends only on content, never on file order. Covered by one test under AC5.

## Plan
1. Create branch `task/TASK-004-spec-hashing` from an up-to-date main.
2. Get the human's answer to Interpretations, item 1 (done: see Interpretations).
3. Write failing tests in `tests/unit/test_spec_hash.py`, one or more per criterion AC1 to AC6, building models from Python dicts.
4. In `src/openfactory/domain/models.py`, add `deprecated: bool = False` to `Requirement` and `body: str = ""` to `Adr`.
5. Add `src/openfactory/domain/spec_hash.py`: a private step that returns the sorted form of an item (requirements, ADRs and acceptance criteria by (`id`, canonical JSON of the item), `components` and `constrained_by` as strings); `canonical_json`, which dumps that form with `model_dump(mode="json")` and `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)` and encodes it as UTF-8; and `content_hash`, the SHA-256 hex digest of those bytes.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, and `uv run python scripts/check_docs.py` until all are green.
7. Update living docs and this record's Outcome; commit with trailers `Task: TASK-004` and `Milestone: M1`.

## Files expected to change
- `src/openfactory/domain/models.py` (two fields added)
- `src/openfactory/domain/spec_hash.py` (new)
- `tests/unit/test_spec_hash.py` (new)
- `docs/architecture.md` (Components: update "Spec models", add "Spec hashing")
- `docs/progress.md` (Current task, then Done)
- `docs/decisions.md` (rows for the confirmed interpretations)
- `docs/tasks/TASK-004-spec-hashing.md` (this record; Outcome at close)

## Living docs to update
- `docs/architecture.md`: Components.
- `docs/progress.md`: Current and Done.
- `docs/decisions.md`: the confirmed interpretations.
- `CHANGELOG.md`: no entry expected (no user-visible change).
- `README.md`: no change expected.

## New dependencies
None. `hashlib` and `json` are in the standard library. PyYAML is added by the loader task, not this one.

## Outcome
Built as planned:
- `Requirement.deprecated: bool = False` and `Adr.body: str = ""` in `domain/models.py`.
- `domain/spec_hash.py` with `canonical_json` and `content_hash` for an acceptance criterion, a requirement, an ADR and a spec set. Lists are sorted innermost first; items with an id sort by (`id`, canonical JSON of the item).
- 28 tests in `tests/unit/test_spec_hash.py`.

Deviations from plan:
- Two edits to test-writer tests, both approved by the human on 2026-10-08, neither changing what a test asserts:
  - `test_ac1_deprecated_requirement_is_still_validated` read `v.id` on a `SpecViolation`, which has no such field; changed to `v.subject`.
  - `test_ac6_strings_are_hashed_as_parsed` held the two forms of `é` as literal characters; replaced with the escapes `\u00e9` and `e\u0301` so an editor cannot normalise them on save.
- `docs/progress.md` Later: removed the six items that spec v1.4 resolved (payload shapes, spec hash, projection DDL, `policies.yaml` schema, YAML dependency, `deprecated` field), at the human's request.

Follow-ups: none beyond the out-of-scope list above.
