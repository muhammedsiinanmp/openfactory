# TASK-008: Policy model and loader

- Milestone: M1
- Status: done
- Tests: acceptance
- Spec sections (spec v1.6): "Spec input format" ("Policies", "Loading", "Validation rules"); "Tech stack and repo layout"; "CLI commands" ("Output")

## Objective
Add the pure `Policy` model for `specs/policies.yaml`, the baseline forbidden paths as a constant in code, and an application-layer `load_policy` that reads the file through the `SpecFiles` port and returns either a `Policy` or the full list of `schema` problems, so the `validate` use case (and `plan` in M2) has one function to load the policy with.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- `Policy` in a new pure module `domain/policy.py`: `protected_branches`, `forbidden_paths`, `max_attempts`, `max_runtime_s`, `max_cost_usd`, each optional with the spec's default, the three limits greater than zero, unknown keys rejected, frozen like the other domain models. The default of `forbidden_paths` is the empty list; the field holds only what the policy file adds.
- `BASELINE_FORBIDDEN_PATHS` in `domain/policy.py`: the four baseline paths of spec v1.6, `specs/**`, `.openfactory/**`, `.env` and `.env.*`, in that order, as an immutable tuple of strings. It is not a field of `Policy` and cannot be set from the policy file.
- `load_policy(files: SpecFiles) -> PolicyLoadResult` in `app/spec_loader.py`. It reads only `policies.yaml`, parses it with the existing duplicate-key-rejecting YAML loader, and turns every problem into a `SpecViolation` with rule `schema` and subject `specs/policies.yaml`.
- A missing `policies.yaml` reported as one `schema` violation with the message "missing; run openfactory init" (decision of 2026-10-08, TASK-006 row in `docs/decisions.md`).
- Unit tests using an in-memory fake `SpecFiles`. No filesystem, no database.

Out (follow-up tasks, not this one):
- The `validate` use case and CLI command: printing policy problems, the count line, exit code 1, and keeping policy problems out of `SpecValidated`. This task only produces the violations.
- `openfactory init` writing the default `specs/policies.yaml`.
- Merging the baseline, the policy's `forbidden_paths` and the planner's into a task contract, and giving the baseline to the planner prompt. This task only defines the constant. M2.
- The policy's hash and recording it with a plan (`PlanCreated.policy_hash`), `plan` refusing to run while the policy is invalid, and the `Limits` model. All M2.
- The meaning or validity of a glob pattern in `forbidden_paths`. Entries are plain strings here; the glob syntax stays undefined until M3 (decided by the human, 2026-10-09).
- `protected_branches` enforcement (M3).
- Any change to `load_spec`'s behaviour, the `SpecFiles` port, `FilesystemSpecFiles`, `SpecSet` or `content_hash`.
- The projector, the `EventRecorder` and `SpecVersions` ports, projection tables, spec version ids, and the events `SpecImported`, `SpecValidated`, `SpecApproved`.
- Hardening against exotic inputs: numeric strings, booleans or fractional values where an integer is expected, empty strings in the lists, a byte order mark.
- Payload depth limit (stays under Later).

## Acceptance criteria
Each criterion cites the spec v1.6 heading it traces to. "Policies", "Loading" and "Validation rules" mean the blocks of those names under "Spec input format". In every criterion the loader is called with an in-memory fake `SpecFiles`, "result" is what `load_policy` returns, and a "`schema` violation" is a `SpecViolation` whose `rule` has the value `"schema"`.

- [x] AC1 (Policies: "`specs/policies.yaml` has five keys. Each is optional with the default shown" and the example file; "Four baseline paths are always forbidden: `specs/**`, `.openfactory/**`, `.env` and `.env.*`. They are defined in code, not in the policy file"; "Tech stack and repo layout": "`domain/ # pure models, state machine, rules; no I/O`"): `Policy()` has `protected_branches` `["main", "master"]`, `forbidden_paths` `[]`, `max_attempts` `2`, `max_runtime_s` `1200` and `max_cost_usd` `1.50`. With `policies.yaml` holding the spec's example text, the result has no violations and a `Policy` equal to `Policy()`. `BASELINE_FORBIDDEN_PATHS`, imported from `openfactory.domain.policy`, equals `("specs/**", ".openfactory/**", ".env", ".env.*")`. `openfactory.domain.policy` imports nothing from `openfactory.adapters`, `openfactory.app` or `openfactory.ports` (checked by parsing its imports with `ast`).
- [x] AC2 (Policies: "Each is optional with the default shown"; "`forbidden_paths` adds to the baseline; it never replaces it"): a `policies.yaml` holding only `max_attempts: 3` gives a `Policy` with `max_attempts` `3` and the other four fields at their defaults. A file holding only `forbidden_paths: [secrets/**]` gives a `Policy` whose `forbidden_paths` is exactly `["secrets/**"]`, with no baseline path in it, and whose other four fields are at their defaults. A file holding `{}`, an empty file, and a file holding only a comment each give a `Policy` equal to `Policy()`. None of these has violations.
- [x] AC3 (Policies: "unknown keys are rejected" and "prints policy problems under the rule `schema`, with the file path as subject"; "Tech stack and repo layout": "`yaml.load` with a `SafeLoader` subclass that rejects duplicate keys"; Loading: "Parsing YAML and ADR front matter happens in the application layer"): a `policies.yaml` with an extra key `max_retries: 3` gives a result with no policy and one `schema` violation with subject `specs/policies.yaml` whose message names `max_retries`. A file with `max_attempts` written twice, a file with a YAML syntax error, and a file whose top level is a list each give a result with no policy and one `schema` violation with subject `specs/policies.yaml` and a non-empty message.
- [x] AC4 (Policies: "`max_attempts`, `max_runtime_s` and `max_cost_usd` must be greater than zero"; "CLI commands", Output: "`validate` prints one line per violation and per policy problem"): `max_attempts: 0`, `max_runtime_s: -1` and `max_cost_usd: 0` each, on their own, give a result with no policy and one `schema` violation with subject `specs/policies.yaml` whose message names that key. A file with all three gives three `schema` violations, one naming each key. `max_cost_usd: 0.01` loads with no violations.
- [x] AC5 (Policies: "A missing file is an error that says to run `openfactory init`"; Validation rules: "a file that is not valid UTF-8"; Loading: the `SpecFiles` port "returns each file's text by path relative to `specs/` (`requirements.yaml`, `adrs/*.md`, `policies.yaml`)"): when the fake returns `None` for `policies.yaml`, the result has no policy and exactly one `schema` violation with subject `specs/policies.yaml` whose message contains "run openfactory init". When the fake raises `UnicodeDecodeError` for `policies.yaml`, the result has no policy and exactly one `schema` violation with subject `specs/policies.yaml` whose message contains "not valid UTF-8". Whenever a result has any violation its policy is `None`, and whenever it has none its policy is a `Policy`.
- [x] AC6 (Policies: "The policy is not part of the spec set and is not covered by a spec version's hash"; Validation rules: "Policy problems do not count here"): `load_policy` reads `policies.yaml` and nothing else: with a fake that records its calls, `read` is called only with `"policies.yaml"` and `list_adrs` is never called, and a valid `policies.yaml` loads with no violations when `requirements.yaml` is missing. With a valid `requirements.yaml`, `load_spec` returns the same `SpecLoadResult` whether `policies.yaml` is valid, missing or has an unknown key.

## Decisions
Confirmed by the human on 2026-10-09; to be recorded in `docs/decisions.md` in this task's commit.

1. Function and result shape: `load_policy(files: SpecFiles) -> PolicyLoadResult`, where `PolicyLoadResult` is a frozen model with `policy: Policy | None` and `violations: list[SpecViolation]`, exactly one of them filled, mirroring `SpecLoadResult`. Policy problems are `SpecViolation` objects with rule `schema`.
2. `load_policy` and `PolicyLoadResult` live in `app/spec_loader.py` next to `load_spec`, reusing the module's private helpers with no refactor of tested code.
3. `Policy` lives in a new module `domain/policy.py`, since `domain/models.py` holds the spec set models and the policy is not part of the spec set.
4. Forbidden paths follow spec v1.6: the baseline is a constant in code and the policy's `forbidden_paths` (default `[]`) only adds to it. `Policy.forbidden_paths` holds the policy file's list as written; nothing is merged in the model. The constant is `BASELINE_FORBIDDEN_PATHS` in `domain/policy.py`; the name and place were chosen when the record was updated and confirmed by the human at review.
5. An empty `policies.yaml`, or one holding only comments, is a valid policy with all defaults.
6. One `schema` violation per Pydantic error with the field path in the message, as the loader already does (decision of 2026-10-08, TASK-007); the subject is always `specs/policies.yaml`. A top level that is a list or a scalar is one `schema` violation, "top level is not a mapping".
7. A `policies.yaml` that is not valid UTF-8 is a `schema` violation "not valid UTF-8" with subject `specs/policies.yaml`.
8. Field types: `protected_branches: list[str]`, `forbidden_paths: list[str]`, `max_attempts: int` and `max_runtime_s: int` with `gt=0`, `max_cost_usd: float` with `gt=0`, matching the `Limits` model in "Task contract". Empty lists are accepted.

Kept as already decided (`docs/decisions.md`, 2026-10-08): a missing `policies.yaml` is a `schema` line with subject `specs/policies.yaml` and message "missing; run openfactory init"; `specs/` is prefixed to the port's paths in subjects; YAML is parsed with `yaml.load` and the duplicate-key-rejecting `SafeLoader` subclass; `SpecFiles.read` returns `None` for a missing file.

## Architecture rules that apply
- `src/openfactory/domain` stays pure: `domain/policy.py` is a Pydantic model and a constant only, with no I/O and no import from `app`, `ports` or `adapters`.
- `src/openfactory/app` depends on domain and ports only: `load_policy` takes a `SpecFiles` and never imports `openfactory.adapters` or opens files.
- `src/openfactory/ports` holds Protocols only; no port is added or changed.
- No adapter is added or changed, so no new `TYPE_CHECKING` conformance assertion is needed.
- All state changes go through the events table: the loader records no events and writes nothing.
- No LLM call is made. The policy is still built only through Pydantic validation.

## Plan
1. Create branch `task/TASK-008-policy-model-loader` from an up-to-date main.
2. Write failing tests in `tests/unit/test_policy_loader.py`, one or more per criterion AC1 to AC6, with a small in-memory fake `SpecFiles` that records its calls.
3. Add `src/openfactory/domain/policy.py`: `BASELINE_FORBIDDEN_PATHS` and the frozen `Policy` model with `extra="forbid"`, the five fields and their defaults.
4. Add `PolicyLoadResult` and `load_policy` to `src/openfactory/app/spec_loader.py`: read `policies.yaml`, return the "missing; run openfactory init" violation for `None`, parse the YAML, treat an empty document as an empty mapping, reject any other top level that is not a mapping, validate through `Policy`, and convert a `ValidationError` with `_from_validation_error`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
6. Update living docs and this record's Outcome; commit with trailers `Task: TASK-008` and `Milestone: M1`.

## Files expected to change
- `src/openfactory/domain/policy.py` (new)
- `src/openfactory/app/spec_loader.py` (add `PolicyLoadResult` and `load_policy`; module docstring; `load_spec` unchanged)
- `tests/unit/test_policy_loader.py` (new)
- `docs/architecture.md` (Components: add "Policy model" and "Policy loader", and correct the Spec loader line "`policies.yaml` is not read" to say `load_spec` does not read it; Data flow: `load_policy` exists and nothing calls it yet)
- `docs/progress.md` (Current task, then Done; in Later, reword the `validate` item on a missing `policies.yaml`: the loader now produces the line, printing it and exiting 1 remain for the `validate` task)
- `docs/decisions.md` (rows for the decisions above)
- `docs/tasks/TASK-008-policy-model-loader.md` (this record; Outcome at close)

Not expected to change: `src/openfactory/domain/models.py`, `src/openfactory/domain/spec_validation.py`, `src/openfactory/domain/spec_hash.py`, `src/openfactory/domain/payloads.py`, everything under `src/openfactory/ports/` and `src/openfactory/adapters/`, `pyproject.toml`, and every existing test file.

## Living docs to update
- `docs/architecture.md`: Components and Data flow.
- `docs/progress.md`: Current, Done and Later.
- `docs/decisions.md`: the decisions above.
- `CHANGELOG.md`: no entry expected (no user-visible change).
- `README.md`: no change expected.

## New dependencies
None. PyYAML and Pydantic v2 are already declared in `pyproject.toml`.

## Open questions
None open. An empty `policies.yaml` means all defaults (Decisions, item 5). The glob syntax of `forbidden_paths` stays undefined until M3; this task stores the entries as strings and checks nothing about them.

## Outcome
Built:
- `src/openfactory/domain/policy.py`: `BASELINE_FORBIDDEN_PATHS` and the frozen `Policy` model, with the five keys, the spec v1.6 defaults (`forbidden_paths` is `[]`), the three limits greater than zero, and unknown keys rejected.
- `src/openfactory/app/spec_loader.py`: `PolicyLoadResult` and `load_policy`. It reads only `policies.yaml`, reuses the module's read, YAML and violation helpers, treats an empty or comment-only file as the default policy, and reports every problem as a `schema` violation with subject `specs/policies.yaml`. `load_spec` is unchanged.
- `tests/unit/test_policy_loader.py`: 25 tests (counting parametrised cases) for AC1 to AC6, written by the test-writer. No test was edited after it was written.

Deviations from plan: none.

Follow-ups:
- The `validate` use case prints the policy violations and exits 1; `init` writes the default `specs/policies.yaml`.
- M2: merge `BASELINE_FORBIDDEN_PATHS`, the policy's list and the planner's into each task contract, give the baseline to the planner prompt, and hash the policy for `PlanCreated`.
- A present key replaces its default entirely, so a policy that sets `protected_branches` drops `main` and `master` unless it repeats them. That is the plain reading of spec v1.6, which made only `forbidden_paths` additive.
