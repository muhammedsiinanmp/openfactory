# TASK-028: The `schema` plan rule and `depends_on` without duplicates

- Milestone: M2
- Status: done
- Tests: acceptance
- ADR: none. No new port, adapter, dependency, event type, payload model or storage change. ADR-008 (accepted) covers contract completion, and the `depends_on` rule is the human's decision of 2026-10-11 (SC-45 row in `docs/decisions.md`, spec v1.11). ADR-008's Decision lists three bullets and the spec now has four; amending an accepted ADR is the human's, so it becomes a Later line. The `schema` rule is the SC-44 row. Names and modules are rows in `docs/decisions.md` (Open questions 1 to 5).
- Spec impact: wording. Two items, neither blocks (see "Spec gaps").
- Spec sections (spec v1.11): "Task contract" (the class block; "The planner does not emit `required_gates` or `limits`; a reply that contains either fails validation"; the four bullets after "For every task, the orchestrator:"; "Planning": the reply shape; "Plan checks": the `schema` row and the paragraph after the table); "Tech stack and repo layout" (the "Planner and diff LLM calls" row; "An envelope that parses but whose structured result is missing or fails Pydantic validation is a rejected reply"; "the domain never imports infrastructure")

## Objective
Add the reply model for `{"tasks": [PlannedTask, ...]}` and the pure domain function that turns a planner's structured result into either validated tasks or `schema` rejections (SC-44), and make `complete_contract` drop a repeated `depends_on` entry (SC-45), so the plan use case can reject, retry and store a reply.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings.

## Scope
In:
- `src/openfactory/domain/contracts.py`:
  - `PlannerReply`: frozen, `extra="forbid"`, one field `tasks: list[PlannedTask]` (Open questions 1 and 4).
  - `complete_contract` sets `depends_on` to the planner's list with each id kept at its first position.
  - The module docstring and the function docstring name `depends_on` among what the orchestrator sets (audit F-8 of the v1.11 proposal audit).
- `src/openfactory/domain/plan_checks.py` (names per Open question 1):
  - `ParsedReply`: frozen, with `tasks: list[PlannedTask] | None` and `rejections: list[PlanRejection]`. As `parse_reply` returns it, it holds tasks or rejections, never both.
  - `parse_reply(structured: object | None) -> ParsedReply`. `None` gives the `no structured result` rejection. Otherwise it validates with `PlannerReply` and returns one `schema` rejection per Pydantic error.
  - The module docstring no longer says the `schema` rule is not built.
- Unit tests built from Python values. No files, no database, no LLM.

Out (not this task):
- Every caller: running `parse_reply` and then `check_plan`, the retry, the rejection lines and their sort, `AgentRunFinished.error`, the prompt (outline items 9 and 10).
- `LLMProvider`, the envelope, how the adapter finds or misses the structured result, and the JSON Schema passed to `--json-schema` (item 7).
- Any change to `check_plan`, the eight content rules, `PlanRule`, `PlanRejection`, `PlannedTask`, `TaskContract`, `Limits`, `domain/payloads.py`, the projector, `app/`, `ports/`, `adapters/` and `cli.py`.
- A rule against an empty `tasks` list. The model has no minimum length; `uncovered` reports such a plan.
- Exact Pydantic message text. Criteria assert the field path only.
- Hardening against exotic inputs: a task entry that is not a mapping, a `task_id` string with a line break, non-string keys, a reply that is not a mapping.
- Amending ADR-008 (the human's).

## Acceptance criteria
"Plan checks" and "Planning" are under "Task contract". "The planned example" is the YAML block under "Task contract" that starts `task_id: AUTH-002`, without `required_gates` and `limits`, as a plain dict. "A second task" is the same dict with `task_id: AUTH-003`. Names follow the proposals under Open questions; if the human answers otherwise, the names change and the assertions do not. "Names path P" means the string P is in `message`.

- [x] AC1 ("Planning": "The planner replies with `{"tasks": [PlannedTask, ...]}`"; "Tech stack and repo layout": "validated by Pydantic"):
  - `parse_reply({"tasks": [the planned example, a second task]})` returns no rejections and two `PlannedTask` objects, in the reply's order, equal to `PlannedTask.model_validate` of each dict.
  - `PlannerReply` has exactly one field, `tasks`.
  - `parse_reply({"tasks": []})` returns `tasks == []` and no rejections.
- [x] AC2 ("Plan checks": "`schema` | Pydantic rejects the reply", "A `schema` rejection has the field path in its message" and "There is one `schema` rejection per Pydantic error"; "Task contract": "a reply that contains either fails validation"):
  - With the second task lacking `objective`, there is exactly one rejection: rule `schema`, subject `AUTH-003`, naming path `tasks.1.objective`.
  - With one task lacking `objective` and having `role: reviewer`, there are two rejections with that task's id as subject, naming `tasks.0.objective` and `tasks.0.role`.
  - With one error in each of two tasks, there are two rejections, each with its own task's id as subject.
  - With a task that contains `required_gates`, there is one rejection naming `tasks.0.required_gates`; with `limits`, one naming `tasks.0.limits`.
- [x] AC3 ("Plan checks", the `schema` row's Subject: "the `task_id` of the task the error lies in when that value is a string, otherwise `reply`"):
  - With a task whose `task_id` is `auth-1` (a string the pattern rejects), the rejection's subject is `auth-1`.
  - With a task whose `task_id` is the integer `7`, and with a task that has no `task_id`, the subject is `reply`.
  - `parse_reply({})` and `parse_reply({"tasks": "x"})` each return one rejection with subject `reply`, naming `tasks`.
- [x] AC4 ("Plan checks": "A reply whose structured result is missing is one `schema` rejection with subject `reply` and the message `no structured result`"; "Tech stack and repo layout": "An envelope that parses but whose structured result is missing ... is a rejected reply"):
  - `parse_reply(None)` returns exactly one rejection: rule `schema`, subject `reply`, message equal to `no structured result`.
- [x] AC5 ("Plan checks": "when there is one the other checks are not run"):
  - In every rejected case of AC2 to AC4, `tasks` is `None`, so the caller has nothing to pass to `check_plan`.
  - A reply with one valid task and one invalid task returns `tasks` as `None` and only `schema` rejections.
  - Every rejection `parse_reply` returns has rule `schema`.
- [x] AC6 ("Task contract": "sets `depends_on` to the planner's list without duplicates, each id at its first position"):
  - With planner `depends_on` `[AUTH-001, AUTH-003, AUTH-001, AUTH-003, AUTH-002]`, the contract's `depends_on` is `[AUTH-001, AUTH-003, AUTH-002]`.
  - With `[AUTH-003, AUTH-001]` it is unchanged, in the planner's order.
  - The planned task's own `depends_on` is unchanged after the call.

## Architecture rules that apply
- `src/openfactory/domain` stays pure: no I/O, no import from `adapters`, `app` or `ports`. The existing import-guard tests for both modules keep covering this.
- All LLM output is validated by a Pydantic model before use; `PlannerReply` is that model for the planner.
- No event is recorded, no projection is read or written, no LLM call is made.
- Tests from the test-writer are fixed. No existing test is changed.
- No hardening beyond the spec's rules.

## Plan
1. Create branch `task/TASK-028-plan-reply-schema-rule` from an up-to-date main and commit this record.
2. Get the human's answers to the Open questions; record them here and as rows in `docs/decisions.md`.
3. Write failing tests:
   - `tests/unit/test_plan_reply.py` (new) for AC1 to AC5, with one helper that returns the planned example as a dict.
   - Two or three tests added to `tests/unit/test_contract_completion.py` for AC6. Its `test_ac4_planned_fields_are_copied_in_order` has one dependency and still passes.
4. In `domain/contracts.py`, add `PlannerReply`, change the `depends_on` line to `list(dict.fromkeys(planned.depends_on))` and update the two docstrings.
5. In `domain/plan_checks.py`, add `ParsedReply` and `parse_reply`:
   - `None` gives the single `no structured result` rejection.
   - Otherwise call `PlannerReply.model_validate(structured)`.
   - On `ValidationError`, return one rejection per entry of `error.errors()`. The message is the dotted `loc`, then `: `, then Pydantic's `msg`, as `_from_validation_error` in `app/spec_loader.py` does.
   - The subject is `structured["tasks"][i]["task_id"]` when `loc` starts `("tasks", i, ...)` and that value is a string; otherwise `reply`.
   - Pyright will need `isinstance` narrowing and `cast` on the raw value, as the spec loader uses.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until green.
7. Update the living docs and the Outcome. Commit `feat(domain): add the schema plan rule and drop repeated dependencies` with trailers `Task: TASK-028` and `Milestone: M2`.

## Files expected to change
- `src/openfactory/domain/contracts.py` (about 12 lines)
- `src/openfactory/domain/plan_checks.py` (about 50 lines added)
- `tests/unit/test_plan_reply.py` (new, about 140 lines)
- `tests/unit/test_contract_completion.py` (about 25 lines added; nothing existing changed)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-028-plan-reply-schema-rule.md`

About 60 lines of source and 165 of tests.

Not expected to change: every other file under `src/`, `tests/unit/test_plan_checks.py`, `tests/unit/test_spec_conformance.py`, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

## Living docs to update
- `docs/architecture.md`:
  - "Task contract models" gains `PlannerReply` and the `depends_on` rule of `complete_contract`.
  - "Plan checks" gains `ParsedReply` and `parse_reply`, and drops "which is not built yet".
  - "Data flow" gets one sentence: no use case calls `parse_reply` yet.
- `docs/progress.md`:
  - Current, then Done; remove outline item 6.
  - Later line: ADR-008's Decision lists three things the orchestrator sets and spec v1.11 has four (`depends_on`); amending an accepted ADR is the human's (audit F-8 / M-3).
  - Later line: the two wording items under "Spec gaps", and audit F-6 (the retry sentences do not name a reply with no structured result), to settle by `/spec-change` before outline item 9 is planned.
- `docs/decisions.md`: rows for the answered questions.
- `CHANGELOG.md`, `README.md`: no change (no command or output is added).

## New dependencies
None.

## Spec gaps
Spec impact is "wording". Neither item blocks: the SC-44 sentences in the same paragraph and the SC-44 row in `docs/decisions.md` state the meaning.

1. "Task contract" › "Plan checks", the `schema` row's "Rejected when" cell: "Pydantic rejects the reply".
   - Unclear: the cell does not cover a missing structured result, which the paragraph under the table also makes a `schema` rejection.
   - Does not block: that sentence is explicit, and AC4 follows it.
   - Audit F-2; proposed text "Pydantic rejects the reply, or its structured result is missing".
2. "Task contract" › "Plan checks", the paragraph after the table: "A `schema` rejection has the field path in its message, and when there is one the other checks are not run."
   - Unclear: the message `no structured result` has no field path.
   - Does not block: the message is given literally, and "when there is one" is read as any `schema` rejection, so AC5 covers the missing-result case too.
   - Audit F-3; the advisor's text is "A `schema` rejection for a Pydantic error has the field path in its message. When there is any `schema` rejection, the other checks are not run."

Not this task's, recorded so it is not lost: "Tech stack and repo layout" ("If a reply fails Pydantic validation, the call is retried once") and "Plan checks" ("A reply rejected by Pydantic or by the plan checks is retried once") do not name a reply with no structured result (audit F-6). It concerns the retry in outline item 9 and may block that task.

Readings, not gaps:
- "The task the error lies in" is the entry of `tasks` whose index is in the Pydantic error's location. An error outside any task has subject `reply`.
- "When that value is a string" includes a string the `task_id` pattern rejects (SC-44 row: it replaces "when it can be read").
- An empty `tasks` list is not a `schema` rejection: the spec gives the list no minimum, and `uncovered` reports what it misses.
- A repeat in `depends_on` is an equal string. The planned task keeps its list as the planner gave it; only the contract drops the repeat.
- `_unknown_dependency` already reports once per id and `_cycle` is unaffected by a repeat, so `check_plan` needs no change for SC-45.

## Open questions
None is a spec decision; each has a proposal.

Answered 2026-10-11: the human approved the proposed answer to all six (the advisor agreed with each). For question 4, the reason is that the JSON Schema sent to the planner is generated from the same model and so says the same thing; "as every other model in the repo" is not accurate, since `Adr` has `extra="ignore"`.

1. **Names and modules.** Proposed: `PlannerReply` in `domain/contracts.py`, beside `PlannedTask`; `ParsedReply` and `parse_reply` in `domain/plan_checks.py`, beside `PlanRejection`. Alternative: a new `domain/plan_reply.py` holding all three.
2. **How a missing structured result reaches the function.** Proposed: `parse_reply(structured: object | None)`, where `None` means missing, so one function produces every `schema` rejection. A JSON `null` result is treated the same. How the adapter reports a missing result is item 7's. Alternative: `parse_reply` takes a present value only, and a constant or small function gives the `no structured result` rejection for the use case to pick.
3. **Message form.** Proposed: `<dotted field path>: <Pydantic msg>` with the list index in the path (`tasks.1.objective: Field required`), as the spec loader writes it. An error at the reply's root has an empty path and takes Pydantic's message alone. Tests assert the path only. Alternative: a path relative to the task, since the subject already names it.
4. **Unknown keys beside `tasks`.** Proposed: `PlannerReply` has `extra="forbid"`, as every other model in the repo, and no criterion asserts it. Alternative: ignore extra top-level keys.
5. **A combined function.** Proposed: none in this task; the plan use case (item 9) calls `parse_reply`, then `check_plan` when `tasks` is not `None`. Alternative: add `check_reply(structured, spec)` here, which runs both.
6. **ADR-008.** Proposed: a Later line only. Alternative: the human amends ADR-008's Decision with the `depends_on` bullet now.

## Outcome
Built as planned.
- `domain/contracts.py`: `PlannerReply` (frozen, `extra="forbid"`, one field `tasks: list[PlannedTask]`); `complete_contract` sets `depends_on` to `list(dict.fromkeys(planned.depends_on))`; the module and function docstrings name `depends_on`.
- `domain/plan_checks.py`: frozen `ParsedReply`, `parse_reply(structured)` and the private helper `_schema_subject`; the module docstring no longer says the `schema` rule is not built. `check_plan` is unchanged.
- Tests: `tests/unit/test_plan_reply.py` (new, 20 tests, AC1 to AC5) and three AC6 tests appended to `tests/unit/test_contract_completion.py`. 889 tests pass; ruff, pyright and check_docs are clean.
- Deviations from the plan: none.
- Test edits: none. No test from the test-writer was changed and no existing test was edited.
- Open questions 1 to 6: answered as proposed (rows in `docs/decisions.md`); for question 4 the reason recorded is that the planner's JSON Schema is generated from the same model.
- Follow-ups, in `docs/progress.md` "Later": ADR-008's Decision lists three things the orchestrator sets and spec v1.11 has four (the human's to amend); spec gap before outline item 9, the retry sentences do not name a reply with no structured result (audit F-6), and whether a JSON `null` result is "missing" (reviewer); the two spec wording items (audit F-2, F-3), added when the plan was saved.
- After review, on the human's request, the reviewer's four non-blocking notes were applied: six cases added to the parametrised AC5 test (`test_ac5_a_rejected_reply_has_no_tasks_and_only_schema_rules`) so it covers every rejected case of AC2 to AC4, with no assertion changed; the JSON `null` reading added to the spec-gap line; outline item 9's dependency list and this Outcome corrected; `docs/architecture.md` says `parse_reply`, not the `ParsedReply` model, guarantees tasks or rejections and never both.
