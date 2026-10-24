# TASK-101: Replan prompt

- Milestone: M6
- Status: done
- Tests: acceptance
- ADR: ADR-019 (accepted, with its 2026-10-24 amendment). Its Consequences say "the replan prompt tells the planner to rewrite or delete them". The amendment says a replan's dependency rule "and the replan prompt" accept only untouched tasks that are neither `abandoned` nor `invalidated`. The task adds one pure `app` module and one optional keyword to `build_planner_prompt`. It adds no port, adapter, event type, payload change, table, dependency or convention, so no new ADR is needed. Each answered design choice becomes a row in `docs/decisions.md`.
- Spec impact: wording (see Spec gaps; none blocks)
- Spec sections (spec v1.19; SC-163, SC-166, SC-189):
  - "Spec diff and impact analysis" › "Step 5: replan": "The replan prompt is the planner prompt (see Planning) plus: the contracts of the impacted and downstream tasks; the files, tests, obsolete criteria and new work of the `ImpactComputed`; and, as fixed context, the untouched tasks that are not `invalidated`, each with its id, objective, state, requirements and acceptance criteria. It tells the planner to plan tasks only for the impacted work and the `added` requirements, that a new task may depend on an untouched task that is neither `abandoned` nor `invalidated`, and that the new tasks rewrite or delete the obsolete code and tests, with `allowed_paths` covering them."
  - "Spec diff and impact analysis" › "Step 3: traversal (deterministic)": "The untouched tasks are the other tasks of the approved plan."
  - "Task contract" › "Planning": the content of the planner prompt (the bullet "The planner receives one prompt and no tools: …").
  - "Task contract" › "Plan checks", last paragraph: "is retried once with the same prompt and the rejection lines added to it".
  - "Task contract" › "Plan checks" table, the replan rules of `unknown-dependency` and `uncovered`, and `task-id-in-use`.

## Outline item
M6 outline item 6, first piece (6a). 6b is the `replan` use case and 6c the `replan` command.

Proposed split of item 6:
- **6a (TASK-101):** the replan prompt, a pure function (SC-163, SC-166, SC-189).
- **6b:** the `replan` use case. It covers the six refusals in order, reading `ImpactComputed` through `EventStore`, the planner call through `run_planner` with the replan prompt, `ids_in_use` and `untouched`, and the draft `PlanCreated` for the latest approved version (SC-163, SC-174, SC-188). Its criteria must check that `ids_in_use` is passed (Later line from TASK-100).
- **6c:** the `replan` command and its output: printing as `plan` does, the refusal lines, and the warning placed after the first four refusals (SC-197).

## Objective
Add a new pure `app/replan_prompt.py` with `build_replan_prompt`. It returns the planner prompt plus the replan sections, or with rejections the retry prompt. It also has `untouched_tasks`, the spec's set of untouched tasks, which the 6b use case will pass to `check_plan`.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- New `src/openfactory/app/replan_prompt.py`. It is pure, and imports only `openfactory.domain` and `openfactory.app.planner_prompt`. It has two functions:
  - `untouched_tasks(plan_tasks: Sequence[Task], impact: ImpactComputedPayload) -> list[Task]` returns the tasks whose id is in neither `impact.tasks` nor `impact.downstream`. Every state is kept, sorted by id as strings.
  - `build_replan_prompt(spec: SpecSet, policy: Policy, tracked_files: Sequence[str], impact: ImpactComputedPayload, plan_tasks: Sequence[Task], rejections: Sequence[PlanRejection] = ()) -> str`.
- `src/openfactory/app/planner_prompt.py`: `build_planner_prompt` gains a keyword `extra: Sequence[str] = ()`. These sections are placed after "Tracked files" and before the rejections section. With `extra` empty, the text is the same as today, byte for byte, so `context_hash` does not change (Design choice 1).
- New `tests/unit/test_replan_prompt.py`.

Out:
- The `replan` use case: its refusals, reading `ImpactComputed`, the run events, `context_hash`, passing `untouched` and `ids_in_use`, and `PlanCreated` (6b).
- The `replan` command and output (6c).
- The Later spec gap that a second replan's prompt omits the ids of tasks invalidated earlier. It stays open.
- The Later spec gap that no task can be planned only to delete the code of a deprecated or removed requirement (`min_length=1`).
- Any change to `domain/`, ports, adapters, `cli.py` or `app/plan.py`.

## Acceptance criteria
- [x] **AC1** ("Step 5": "The replan prompt is the planner prompt (see Planning) plus"; "Plan checks": "retried once with the same prompt and the rejection lines added to it"):
  - `build_replan_prompt` returns `build_planner_prompt(spec, policy, tracked_files, rejections, extra=<the replan sections>)`.
  - So the planner prompt's sections come first, unchanged, then the replan sections. With rejections, the rejections section comes last.
  - `build_planner_prompt` without `extra` gives the same text as before. The existing tests of `planner_prompt`, `plan` and `context_pack` pass without edits.
- [x] **AC2** ("Step 5": "the contracts of the impacted and downstream tasks"):
  - The replan sections hold the full contract (`model_dump_json(indent=2)`) of each task in `impact.tasks` and in `impact.downstream`, read from `plan_tasks`, in ascending task id as strings.
  - Impacted and downstream tasks are under separate headings.
  - A task in neither list does not appear with its contract.
- [x] **AC3** ("Step 5": "the files, tests, obsolete criteria and new work of the `ImpactComputed`"):
  - The replan sections list `impact.files`, `impact.tests`, and the `obsolete_criteria` of every entry of `impact.requirements` once each, sorted as strings.
  - They also list `new_work` as `<requirement id>: <text>` in requirement order.
  - An empty group shows `(none)`, as in the planner prompt.
- [x] **AC4** ("Step 5": "as fixed context, the untouched tasks that are not `invalidated`, each with its id, objective, state, requirements and acceptance criteria"; "Step 3": "The untouched tasks are the other tasks of the approved plan"):
  - `untouched_tasks` returns the plan tasks in neither `impact.tasks` nor `impact.downstream`, in every state, `abandoned` and `invalidated` included, in ascending id.
  - The prompt lists those that are not `invalidated`, each with its id, objective, state, requirements and acceptance criteria, and not its full contract. An `abandoned` one is listed with state `abandoned`.
- [x] **AC5** ("Step 5": "It tells the planner to plan tasks only for the impacted work and the `added` requirements, that a new task may depend on an untouched task that is neither `abandoned` nor `invalidated`, and that the new tasks rewrite or delete the obsolete code and tests, with `allowed_paths` covering them"):
  - The replan instructions are fixed text, the same whatever the arguments, and state these three points.
  - They also state the wording the human picks under Design choices 2 and 3.
- [x] **AC6** ("Event payloads": "`context_hash`: the SHA-256 of the run's prompt text encoded as UTF-8"; CLAUDE.md "app: use cases, depends on domain + ports only"):
  - Equal arguments give equal text, and the inputs are not mutated.
  - A change to one untouched task's state, or to one `impact.files` entry, gives a different `context_hash`.
  - `app/replan_prompt.py` imports nothing from `openfactory` outside `openfactory.domain` and `openfactory.app.planner_prompt`.

## Architecture rules that apply
- Pure `app` module: no I/O, no ports, no events, no projections. The caller (6b) takes `context_hash`, as `plan.py` does.
- The prompt holds no file contents, only names (as in the planner prompt).

## Plan
1. Create branch `task/TASK-101-replan-prompt` from an up-to-date main.
2. Record the human's answers to the Design choices and Open questions in this record.
3. Test-writer: write failing `test_task101_ac<N>_…` tests in the new `tests/unit/test_replan_prompt.py`. Build a small approved plan inline:
   - AUTH-001 passed and untouched;
   - AUTH-002 passed and impacted;
   - AUTH-003 pending and downstream of AUTH-002;
   - AUTH-004 abandoned and untouched;
   - AUTH-005 invalidated and untouched.
   Add an `ImpactComputedPayload` with files, tests, obsolete criteria and new work, and an `added` requirement.
4. Implement:
   - `extra` in `build_planner_prompt`;
   - `app/replan_prompt.py`: `_REPLAN_INSTRUCTIONS`, the section helpers, `untouched_tasks` and `build_replan_prompt`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`: a new "Replan prompt" section after "Classifier prompt", and the `extra` keyword in "Planner prompt".
   - `docs/progress.md`: Current, a Done line, item 6 split into 6a, 6b and 6c with 6a marked done.
   - `docs/decisions.md`: one row per answered design choice.
   - This record's Outcome.
7. Commit `feat(app): add the replan prompt` with trailers `Task: TASK-101` and `Milestone: M6`. Do not push.

## Files expected to change
- `src/openfactory/app/replan_prompt.py` (new, about +120)
- `src/openfactory/app/planner_prompt.py` (about +5)
- `tests/unit/test_replan_prompt.py` (new, about +180)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, this record

Not expected to change: `app/plan.py`, `app/impact.py`, `domain/`, ports, adapters, `cli.py`, `docs/spec/`, `docs/adr/`.

## Design choices to confirm at planning
1. **How to reuse the planner prompt.**
   - Proposed: an `extra` keyword on `build_planner_prompt` (empty by default, text unchanged). The replan sections then sit before the rejections section, and nothing is duplicated.
   - Alternative: `build_replan_prompt` strips the trailing newline from `build_planner_prompt(...)`, appends its sections, and rebuilds the rejections section itself. This leaves `planner_prompt.py` untouched but copies its rejection heading.
2. **The planner prompt's own rules clash with a replan.** "Every requirement below … is covered by at least one task" and "depends_on: the task_ids of tasks in this plan" are wrong for a replan.
   - Proposed: the replan instructions open with "These replan instructions take precedence over the rules above". They then state the replan rules of the checks in plain words, following TASK-093 Design choice 3:
     - a requirement or criterion already covered by an untouched task that is not `invalidated` needs no new task;
     - a new task's `task_id` must not be the id of any task shown in this prompt.
   - Alternative: state only the three points the spec lists.
3. **Empty reply** (SC-188).
   - Proposed: one sentence, "When no new task is needed, reply {"tasks": []}". A replan whose seeds are all `removed` or `deprecated` can only end that way.
   - Alternative: say nothing and leave it to the `uncovered` check.
4. **Where `untouched_tasks` lives.**
   - Proposed: in `app/replan_prompt.py`, and the 6b use case imports it, as `plan.py` imports from `planner_prompt.py`.
   - Alternative: a new pure function in `domain/`, for example next to `check_plan`, as a domain rule.
5. **Contracts of the impacted and downstream tasks** use `model_dump_json(indent=2)`, as in the context pack. The untouched tasks are one block each: id, objective, state, then requirements and criteria comma-joined.

## Spec gaps
- **"Spec diff and impact analysis" › "Step 5: replan": "It tells the planner to plan tasks only for the impacted work and the `added` requirements".**
  - Unclear: the list of prompt content does not include the ids of the `added` requirements, but the planner is told to plan for them. It can only infer them, for example as the requirements no task covers.
  - Why it does not block: the instruction can be written without the ids, and `uncovered` rejects a reply that misses one. Whether to name them changes only prompt text and `context_hash`, and no deterministic behaviour.
  - This task does not assume an answer: see Open question 1.
- **Existing Later lines** (a second replan omits the ids of invalidated tasks; no deletion-only task is possible). They are not new and are not addressed here.

## Open questions
1. Should the instruction "plan tasks only for … the `added` requirements" name those requirements, taken from `impact.requirements` with `change == "added"`? Or does the prompt stay at the content the spec lists? If the answer is to name them, is that a decisions.md row, or a `/spec-change` (wording)?
2. Do you accept Design choices 1 to 5 as proposed?
3. Do you accept the split of item 6 into 6a (this task), 6b (use case) and 6c (command)?

## Answers (human, 2026-10-24)
1. Yes: the replan instructions name the `added` requirement ids, taken from `impact.requirements` with `change == "added"`, sorted as strings, or `(none)`. Recorded as a `docs/decisions.md` row; the Spec wording Later line stays; no `/spec-change` now.
2. Design choices 1 to 5 accepted as proposed. Note: the plain-word id rule of choice 2 ("not the id of any task shown in this prompt") is narrower than `task-id-in-use`, which also rejects ids of `invalidated` tasks the prompt leaves out (the existing Later gap).
3. Split accepted: 6a (this task), 6b (use case), 6c (command).

## Outcome
Built:
- `src/openfactory/app/replan_prompt.py` (new, pure): `build_replan_prompt` returns `build_planner_prompt(..., extra=<replan sections>)`; `untouched_tasks` returns the plan tasks in neither `impact.tasks` nor `impact.downstream`, every state, by id. The sections are the instructions, the `added` requirement ids, the impacted and downstream contracts, the impact's files, tests, obsolete criteria and new work, and the untouched tasks that are not `invalidated`.
- `src/openfactory/app/planner_prompt.py`: keyword `extra`, default text byte-identical.
- `tests/unit/test_replan_prompt.py` (new).
- Docs: `architecture.md` (Replan prompt, Planner prompt), `progress.md`, `decisions.md` (one row per answer, plus the test edit).

Test edit (non-mechanical, approved by the human following the advisor): the helper `contract_json(n)` in `tests/unit/test_replan_prompt.py` now reads the contract from `plan_tasks()` instead of a fresh `make_task(n, ...)` with no dependencies, because AUTH-003's fixture contract depends on AUTH-002. It affects `test_task101_ac2_contracts_of_impacted_and_downstream_in_ascending_id` and `test_task101_ac2_ids_sorted_as_strings_and_other_tasks_have_no_contract`. Assertions and intent unchanged.

Checks: 2012 passed; ruff, pyright and check_docs clean.

No new ADR. The Spec wording Later line stays in `progress.md`.
