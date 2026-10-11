# TASK-026: Contract completion and the policy hash

- Milestone: M2
- Status: done
- Tests: acceptance
- ADR: ADR-008 (accepted). It decides the whole completion rule: "`forbidden_paths` is the baseline, then the policy's list, then the planner's, without duplicates; `required_gates` is `[path_check, ruff, pytest, gitleaks, review]`; `limits` comes from the policy's `max_runtime_s`, `max_attempts` and `max_cost_usd`". The policy hash's canonical form is the human's decision of 2026-10-11 in `docs/decisions.md` (SC-32, spec v1.10). No new port, adapter, dependency, event type, payload or storage change. Function names and their modules are rows in `docs/decisions.md` (Open questions 1 to 3).
- Spec impact: none
- Spec sections (spec v1.10): "Task contract" (the YAML example, the class block, the three bullets after "For every task, the orchestrator:", and the paragraph that follows them); "Spec input format" ("Hashing", "Policies"); "Domain model and storage" ("Event payloads"); "Tech stack and repo layout"

## Objective
Add the pure domain functions that complete a `PlannedTask` into a `TaskContract` from a `Policy` (merged forbidden paths, the fixed gates, the policy's limits) and that hash a `Policy`, so the plan use case can build `PlanCreated` with complete contracts and its `policy_hash`.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings.

## Scope
In:
- `src/openfactory/domain/contracts.py`:
  - a constant `REQUIRED_GATES` holding the five gate names in the spec's order;
  - `complete_contract(planned: PlannedTask, policy: Policy) -> TaskContract` (names per Open question 1).
- `src/openfactory/domain/spec_hash.py`: `policy_hash(policy: Policy) -> str` (name and module per Open question 2). It dumps the policy in JSON mode and serialises it with the module's existing `_dumps`, without `_ordered`: `canonical_json` sorts every list, and the policy's lists are hashed in file order.
- Unit tests that build `PlannedTask` and `Policy` from Python values. No files, no database, no LLM.
- One conformance test added to `tests/unit/test_spec_conformance.py` (Open question 4).

Out (not this task):
- Every caller: the plan use case, building `PlanCreated`, sorting `PlanCreated.tasks` by `task_id`, and `plan` refusing to run while the policy is invalid (outline items 9 and 10).
- The planner prompt, which also lists the baseline and the policy's forbidden paths and the gate names (item 9).
- The plan checks, and turning `pydantic.ValidationError` into `schema` rejections (item 6).
- `LLMProvider`, `GitProvider` and their adapters (items 7, 8).
- Any change to `Policy`, `BASELINE_FORBIDDEN_PATHS`, `PlannedTask`, `Limits`, `TaskContract`, `load_policy`, `canonical_json`, `content_hash`, `domain/payloads.py`, the projector, `app/` and `cli.py`.
- Glob syntax of `allowed_paths` and `forbidden_paths` (Later, F-9, before M3). Entries are plain strings; two entries are duplicates when the strings are equal. Two different globs that match the same files are both kept.
- A repeated entry in `depends_on` (Later, TASK-022, to settle before the plan use case). Completion copies `depends_on` as the planner gave it and removes nothing from it.
- Any check that `allowed_paths` and `forbidden_paths` overlap. No spec text asks for one.
- Hardening against exotic inputs: empty strings in a path list, paths that differ only in case or by a trailing slash, `NaN` limits.

## Acceptance criteria
"Hashing" and "Policies" are under "Spec input format"; "Event payloads" is under "Domain model and storage". "The planned example" is the YAML block under "Task contract" that starts `task_id: AUTH-002`, without `required_gates` and `limits`, as a `PlannedTask`. "The default policy" is `Policy()`. Names follow the proposals under Open questions; if the human answers otherwise, the names change and the assertions do not.

- [x] AC1 ("Task contract": "sets `forbidden_paths` to the baseline paths, then the policy's list, then the planner's, without duplicates"; "Policies": "Four baseline paths are always forbidden: `specs/**`, `.openfactory/**`, `.env` and `.env.*`" and "`forbidden_paths` adds to the baseline; it never replaces it"):
  - With the default policy and a planned task whose `forbidden_paths` is `[]`, the contract's `forbidden_paths` is `["specs/**", ".openfactory/**", ".env", ".env.*"]`.
  - With policy `forbidden_paths` `["secrets/**", "infra/**"]` and planner `forbidden_paths` `["migrations/**", "docs/private/**"]`, the result is the four baseline paths, then `secrets/**`, `infra/**`, then `migrations/**`, `docs/private/**`, each group in the order given.
  - With policy `["secrets/**", ".env"]` and planner `["specs/**", "secrets/**", "migrations/**", "migrations/**"]`, the result is the four baseline paths, `secrets/**`, `migrations/**`: each path appears once, at its first position.
- [x] AC2 ("Task contract": "sets `required_gates` to `[path_check, ruff, pytest, gitleaks, review]`" and "So the planner can never ... drop a gate"):
  - The contract's `required_gates` is `["path_check", "ruff", "pytest", "gitleaks", "review"]`, in that order, for the default policy and for a policy with every key set.
  - `REQUIRED_GATES` holds the same five names in the same order.
- [x] AC3 ("Task contract": "sets `limits` from the policy's `max_runtime_s`, `max_attempts` and `max_cost_usd`"; "Policies": "They are the limits of every task contract"):
  - With the default policy, `limits` equals `Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.50)`.
  - With a policy of `max_runtime_s` 600, `max_attempts` 3 and `max_cost_usd` 0.75, `limits` holds those three values, each in its own field.
- [x] AC4 ("Task contract": "the orchestrator completes each one into a `TaskContract`" and "The completed contract is what `PlanCreated` and `tasks.contract` hold"; "Event payloads": "the lists inside a contract keep their order"; "Tech stack and repo layout": "the domain never imports infrastructure"):
  - The result is a `TaskContract` whose `task_id`, `objective`, `requirements`, `acceptance_criteria`, `depends_on`, `components`, `role` and `allowed_paths` equal the planned task's, with every list in the planner's order.
  - Completing the planned example with the default policy gives a contract whose `model_dump(mode="json")` equals the spec's YAML contract example.
  - The planned task and the policy are unchanged after the call.
  - The module that holds the completion function and the module that holds the hash function import nothing from `openfactory.adapters`, `openfactory.app` or `openfactory.ports` (checked by parsing imports with `ast`).
- [x] AC5 ("Hashing": "The hash of a thing is the SHA-256 of the canonical JSON of its parsed model, written as 64 lowercase hex characters", "Canonical JSON is the model dumped in JSON mode, with sorted keys, separators `,` and `:` with no spaces, non-ASCII characters left as they are, encoded as UTF-8" and "The policy's hash covers its five keys with defaults filled in"):
  - `policy_hash(Policy())` equals the SHA-256 hex digest of the UTF-8 bytes of `{"forbidden_paths":[],"max_attempts":2,"max_cost_usd":1.5,"max_runtime_s":1200,"protected_branches":["main","master"]}`, written in the test as a literal.
  - A `Policy` built with the five default values given explicitly has the same hash as `Policy()`.
  - Changing any one of the five keys changes the hash.
  - A policy whose `forbidden_paths` holds a non-ASCII path hashes to the digest of the canonical JSON with that character left as it is (not `\u` escaped).
- [x] AC6 ("Hashing": "Unlike the spec set's lists, its lists are hashed in file order, because their order reaches the task contracts"):
  - A policy with `forbidden_paths` `["a/**", "b/**"]` and one with `["b/**", "a/**"]` have different hashes.
  - A policy with `protected_branches` `["main", "master"]` and one with `["master", "main"]` have different hashes.

## Architecture rules that apply
- `src/openfactory/domain` stays pure: both functions take and return domain models, with no I/O and no import from `adapters`, `app` or `ports`.
- The planner cannot set gates or limits, and neither it nor the policy can remove a baseline path (ADR-008). Completion is the one place the three bounds are set.
- `Policy.forbidden_paths` holds the policy file's list as written; merging belongs to the contract (ADR-008, "Alternatives considered"; decisions log, TASK-008). `Policy` is not changed.
- No event is recorded, no projection is written, no LLM call is made.
- Tests from the test-writer are fixed.

## Plan
1. Create branch `task/TASK-026-contract-completion-and-policy-hash` from an up-to-date main and commit this record.
2. Get the human's answers to Open questions 1 to 4; record them here and as rows in `docs/decisions.md`.
3. Write failing tests:
   - `tests/unit/test_contract_completion.py` for AC1 to AC4.
   - `tests/unit/test_policy_hash.py` for AC5 and AC6.
   - One test added to `tests/unit/test_spec_conformance.py` (Open question 4): the gate list parsed from the bullet "sets `required_gates` to `[...]`" under "Task contract" equals `REQUIRED_GATES`. By that file's convention it skips until the code exists.
   - No existing test is changed.
4. In `domain/contracts.py`, add `REQUIRED_GATES` and `complete_contract`: walk the baseline, the policy's list and the planner's list in that order and keep the first occurrence of each string; build `Limits` from the policy's three values; build the `TaskContract` from the planned task's fields plus the three completed ones.
5. In `domain/spec_hash.py`, add `policy_hash`: `_dumps(policy.model_dump(mode="json"))` encoded as UTF-8, then SHA-256. `_ordered` is not applied.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until green.
7. Update the living docs and the Outcome. Commit `feat(domain): complete task contracts from the policy and hash the policy` with trailers `Task: TASK-026` and `Milestone: M2`.

## Files expected to change
- `src/openfactory/domain/contracts.py` (about 30 lines added)
- `src/openfactory/domain/spec_hash.py` (about 10 lines added)
- `tests/unit/test_contract_completion.py` (new, about 110 lines)
- `tests/unit/test_policy_hash.py` (new, about 60 lines)
- `tests/unit/test_spec_conformance.py` (one test added; nothing existing changed)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-026-contract-completion-and-policy-hash.md`

About 40 lines of source and 180 of tests.

Not expected to change: `domain/policy.py`, `domain/payloads.py`, `domain/states.py`, everything under `app/`, `ports/` and `adapters/`, `cli.py`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, and every other existing test file.

## Living docs to update
- `docs/architecture.md`: "Task contract models" gains `REQUIRED_GATES` and `complete_contract`; "Spec hashing" gains `policy_hash` and the note that it does not sort lists. "Data flow": at most one sentence, since no use case calls them yet.
- `docs/progress.md`: Current, then Done; remove outline item 5.
- `docs/decisions.md`: rows for the answered questions.
- `CHANGELOG.md`, `README.md`: no change (no command or output is added).

## New dependencies
None.

## Spec gaps
None.

Readings, not gaps:
- "Without duplicates" after "the baseline paths, then the policy's list, then the planner's" means each path is kept at its first position in that order. A duplicate inside one list is removed the same way.
- A duplicate is an equal string. The glob syntax is not yet defined (Later, F-9, before M3), and nothing here interprets a path.
- "With defaults filled in" is what the `Policy` model already does: a `Policy` loaded from a file that omits a key holds the default, so the hash of the model covers all five keys.
- The policy is hashed as loaded: a duplicate in the policy's own `forbidden_paths` is part of its hash, and is removed only in the contract.
- `max_cost_usd` is a float in the model, so it is dumped as `1.5` whether the file says `1.50` or `1.5`.
- The hash covers the policy file's model only. The baseline paths are code, not policy, and are not hashed.

## Open questions
None is a spec decision; each has a proposal. Answered by the human on 2026-10-11: the proposed answer is accepted for all four (advisor: 4 AGREE).
1. **Name and module of the completion function.** Proposed: `complete_contract(planned: PlannedTask, policy: Policy) -> TaskContract` and the constant `REQUIRED_GATES` in `domain/contracts.py`, which then imports `domain/policy.py`. Alternative: a new `domain/completion.py`, leaving `contracts.py` as models only.
2. **Name and module of the policy hash.** Proposed: `policy_hash(policy: Policy) -> str` in `domain/spec_hash.py`, reusing its private `_dumps` and leaving `canonical_json`, `content_hash` and `SpecItem` unchanged. Alternatives: the function in `domain/policy.py` with its own `json.dumps` call; or widening `content_hash` to accept a `Policy`, which needs a branch that skips the list sorting.
3. **Type of `REQUIRED_GATES`.** Proposed: a tuple of the five names, as `BASELINE_FORBIDDEN_PATHS` is a tuple; the contract field stays a list. Alternative: a list.
4. **Conformance test in this task.** Proposed: one test in `tests/unit/test_spec_conformance.py` that reads the gate list from the spec's bullet and compares it with `REQUIRED_GATES`. The YAML contract example and the baseline paths already have conformance tests. Alternative: none; AC2 states the five names as literals.

## Outcome
Built:
- `domain/contracts.py`: `REQUIRED_GATES: Final` (tuple of the five gate names; `Final` inference keeps the literal element types) and `complete_contract(planned, policy) -> TaskContract`. Forbidden paths are the baseline, then the policy's list, then the planner's, each string kept at its first position (`dict.fromkeys`); `required_gates` is `list(REQUIRED_GATES)`; `limits` come from the policy's three values. The module now imports `domain/policy.py` (first import between the two; no cycle).
- `domain/spec_hash.py`: `policy_hash(policy) -> str`, the SHA-256 of `_dumps(policy.model_dump(mode="json"))` without `_ordered`, so the policy's lists are hashed in file order.
- Tests: `tests/unit/test_contract_completion.py` (AC1 to AC4), `tests/unit/test_policy_hash.py` (AC5, AC6) and `test_required_gates_match_the_spec_bullet` in `tests/unit/test_spec_conformance.py`.
- No use case calls either function yet.

Deviations from plan:
- None in scope. This record was not committed separately at plan step 1; it goes in the task's single commit.
- The two AC4 import-check cases passed before the implementation because they are guards.

Test edits: none. No existing test changed and no test-writer test was edited.
The test-writer's tests ran before the implementation (21 failed on the missing names, the conformance test skipped, 814 passed). Git cannot show that order, because the task is one commit; the test files were staged by the test-writer and are unchanged since.

Follow-ups: none.
