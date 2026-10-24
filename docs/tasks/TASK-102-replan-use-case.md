# TASK-102: `replan` use case

- Milestone: M6
- Status: done
- Tests: acceptance
- ADR: ADR-019 (accepted, with its 2026-10-24 amendment) and ADR-013 (accepted).
  - ADR-019 says `replan` records a draft `PlanCreated` holding only the new tasks and invalidates nothing. It also says `ImpactComputed` is read through `EventStore`, with "No new port".
  - ADR-013 is "a pattern for a command whose output the spec places at a time between two pieces of work". `replan`'s warning sentence is such a case (SC-197).
  - The task adds one `app` module and two optional keywords to `run_planner`. It adds no port, adapter, event type, payload change, table, dependency or convention, so no new ADR is needed. Each answered design choice becomes a row in `docs/decisions.md`.
- Spec impact: none (see "Spec notes"; nothing there blocks)
- Spec sections (spec v1.19; SC-163, SC-174, SC-188):
  - "Spec diff and impact analysis" › "Step 5: replan": "`openfactory replan` uses the latest `ImpactComputed` whose `from_version` is the approved plan's spec version and whose `to_version` is the latest approved version, as recorded, even when a `run` has changed the links since. It makes the planner call as `plan` does and records the same events, then `PlanCreated` of a draft plan for the latest approved version that holds only the new tasks. It invalidates nothing. Running `replan` again supersedes the draft, as for `plan`." Also: "The plan checks apply with their replan rules (see Plan checks)."
  - "Spec diff and impact analysis" › "Step 3: traversal (deterministic)": "The untouched tasks are the other tasks of the approved plan."
  - "CLI commands" › "Output", the `replan` bullet: "It refuses with one line on standard error and exits 1, checked in this order: `no approved plan`; `run openfactory impact first` when no `ImpactComputed` has the approved plan's spec version as `from_version` and the latest approved version as `to_version`; `nothing to replan` when the latest such event lists no task and no `added` requirement; `policy is invalid; run openfactory validate`; `git ls-files failed: <error>`; `planner call failed: <error>`. The first three come before any event. It writes `plan`'s warning `spec files differ from approved sv_NN` after its first four refusals have been checked and before `git ls-files` runs."
  - "Tech stack and repo layout" › ports paragraph (M6): "`ImpactComputed` is read from the stream `spec:<version id>` through the `EventStore` port."
  - "Task contract" › "Plan checks": the `task-id-in-use` row ("a `task_id` is already in the `tasks` projection, outside the draft being replaced"). Also the replan rules of `unknown-dependency` and `uncovered`, the retry paragraph, and "A reply with no tasks is accepted only when `uncovered` accepts it".
  - "Domain model and storage" › "Streams and actors": "`impact` and `replan` record their events as `plan` does: each points at the event recorded just before it in the same command, and the first has none."

## Outline item
M6 outline item 6b. 6a (TASK-101) built `build_replan_prompt` and `untouched_tasks`. 6c is the `replan` command and its output: printing as `plan` does, the refusal lines, and the warning after the first four refusals. 6c is not in this task.

## Objective
Add a new `app/replan.py` that makes `replan` two use-case calls, as `plan` is (ADR-013):
- `prepare_replan` checks the first four refusals in the spec's order and reads the matching `ImpactComputed` through `EventStore`.
- `create_replan` reads the tracked files and the task ids in use. It then calls `run_planner` with the replan prompt, `ids_in_use` and `untouched`, which ends in a draft `PlanCreated` for the latest approved version.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- New `src/openfactory/app/replan.py`. It imports only `openfactory.domain`, `openfactory.ports`, `openfactory.app` modules (`plan`, `replan_prompt`, `spec_loader`), Pydantic and the standard library. It contains:
  - `ReplanRefusal` (`StrEnum`: `no_approved_plan`, `no_impact`, `nothing_to_replan`, `invalid_policy`).
  - `ReplanRefused` (frozen, `extra="forbid"`: `reason`).
  - `ReplanInputs` (frozen, `extra="forbid"`): `plan_id` (the approved plan), `spec_version` (the latest approved), `spec` (its stored set), `policy`, `impact: ImpactComputedPayload` and `spec_files_differ`.
  - `prepare_replan(files: SpecFiles, versions: SpecVersions, plans: Plans, events: EventStore) -> ReplanRefused | ReplanInputs`. It records nothing and only reads `events`.
  - `create_replan(inputs, *, git, llm, runs, plans, recorder) -> PlannerResult`.
    - It calls `GitProvider.tracked_files()` once. A `GitError` gives `git_failed` with the whole text, and nothing further is read or called.
    - It then reads `Plans.task_ids_in_use()` once and `Plans.tasks(inputs.plan_id)` once.
    - It then calls `run_planner(inputs.spec_version, inputs.spec, inputs.policy, tracked_files, ..., ids_in_use=<the read>, untouched=untouched_tasks(plan_tasks, inputs.impact), build_prompt=<the replan prompt>)`.
- `src/openfactory/app/plan.py`: `run_planner` gains two keyword-only arguments (Design choice 2):
  - `untouched: Sequence[Task] = ()`, passed through `_attempt` to `check_plan(..., untouched=untouched)` on both attempts.
  - `build_prompt: Callable[[Sequence[PlanRejection]], str] | None = None`. `None` keeps today's `build_planner_prompt(spec, policy, tracked_files, rejections)`.
  - Called without the new keywords, `run_planner` behaves exactly as today.
  - The module docstring is updated.
- New `tests/unit/test_replan.py`, using in-memory fakes of `SpecFiles`, `SpecVersions`, `Plans`, `EventStore`, `GitProvider`, the LLM, `Runs` and the recorder.

Out:
- `cli.py` and the `replan` command, its output, refusal lines and warning (6c).
- `approve plan` after a replan: the impact read, the invalidations and the readies (item 7).
- Any change to `domain/`, ports, adapters, `app/replan_prompt.py` or `app/impact.py`.
- The existing Later spec gaps (a second replan omits invalidated ids from the prompt; no deletion-only task). They stay open.

## Acceptance criteria
- [x] **AC1** ("Output", `replan` bullet, the first three refusals and "The first three come before any event"; "Tech stack" M6 ports: "`ImpactComputed` is read from the stream `spec:<version id>` through the `EventStore` port"; "Step 5": "the latest `ImpactComputed` whose `from_version` is the approved plan's spec version and whose `to_version` is the latest approved version"):
  - `prepare_replan` returns `no_approved_plan` when `Plans.approved()` is `None`.
  - It returns `no_impact` when `EventStore.read("spec:<latest approved id>")` holds no `ImpactComputed` whose `from_version` is the approved plan's spec version. That includes an event whose `from_version` is another version.
  - It returns `nothing_to_replan` when the latest matching event (highest `seq`) has empty `tasks` and no requirement with `change == "added"`. This holds even when an earlier matching event listed tasks.
  - Each refusal is checked in that order, records no event, never calls `append`, and does not read the policy.
- [x] **AC2** ("Output", `replan` bullet: `policy is invalid; run openfactory validate` as the fourth refusal, and the warning "after its first four refusals have been checked and before `git ls-files` runs"; "Step 5": "a draft plan for the latest approved version"):
  - With a valid impact, an invalid or missing policy gives `invalid_policy`.
  - Otherwise `prepare_replan` returns `ReplanInputs`, with:
    - `spec_version` the latest approved id;
    - `spec` its stored set from `SpecVersions.spec_set`;
    - `impact` the latest matching payload, validated with `ImpactComputedPayload`;
    - `plan_id` the approved plan's id;
    - `spec_files_differ` true when the spec files cannot be loaded or their `content_hash` differs from the latest approved version's hash, else false.
  - It does not call `GitProvider`.
- [x] **AC3** ("Step 5": "the replan prompt is the planner prompt ... plus"; "makes the planner call as `plan` does and records the same events"; "Output": `git ls-files failed: <error>`, `planner call failed: <error>`):
  - Each planner run's `AgentRunStarted` (role `planner`, no task) has `context_hash` equal to `context_hash(build_replan_prompt(spec, policy, tracked_files, impact, plan_tasks))`.
  - On a retry, the second run's hash is that of the same call with the first reply's rejections.
  - A `GitError` from `tracked_files` gives `git_failed` with no event, no LLM call and no `task_ids_in_use` call.
  - An `LLMError` gives `failed` with `error` the run's `AgentRunFinished.error`, and no `PlanCreated`.
- [x] **AC4** ("Plan checks": the replan rules of `unknown-dependency` and `uncovered`; "A reply with no tasks is accepted only when `uncovered` accepts it"; "Step 3": "The untouched tasks are the other tasks of the approved plan"):
  - `create_replan` passes `untouched_tasks(Plans.tasks(plan_id), impact)` to the checks. A reply whose new task depends on an untouched `passed` task is accepted.
  - A reply that leaves a requirement covered only by an untouched task that is not `invalidated` is accepted. A reply `{"tasks": []}` is accepted when untouched tasks cover every requirement that is not deprecated, and records `PlanCreated` with no tasks.
  - A new task that depends on an `impacted` task, or on an untouched `abandoned` one, is rejected with `unknown-dependency`.
- [x] **AC5** ("Plan checks", `task-id-in-use`: "a `task_id` is already in the `tasks` projection, outside the draft being replaced"; Later line from TASK-100: `replan` must pass `ids_in_use`):
  - `create_replan` calls `Plans.task_ids_in_use()` exactly once and passes its result as `ids_in_use`.
  - A first reply that reuses the id of an impacted task is rejected with `task-id-in-use  <id>  task id '<id>' is already in use` in its `AgentRunFinished.error`. That id is in `task_ids_in_use()` and not among the untouched tasks, so only `ids_in_use` can reject it. The retry prompt carries the same rejection lines.
  - A fake `task_ids_in_use()` returning an id outside the approved plan (any id the fake lists) also rejects a reply that uses it.
  - Called without `ids_in_use`, `run_planner` still accepts such a reply (default unchanged).
- [x] **AC6** ("Step 5": "then `PlanCreated` of a draft plan for the latest approved version that holds only the new tasks. It invalidates nothing"; "as recorded, even when a `run` has changed the links since"; "Streams and actors": `replan` causation "as `plan` does"):
  - An accepted reply records exactly `AgentRunStarted`, `AgentRunFinished` (twice on a retry) and then `PlanCreated`, each pointing at the event before it, the first with none. There is no `TaskStateChanged` and no `ImpactComputed`.
  - `PlanCreated` has `plan_id` `Plans.next_id()`, `spec_version` the latest approved id, `run_id` the accepted run, and `tasks` only the reply's tasks completed with `complete_contract` and sorted by id.
  - `app/replan.py` takes no `Traces` and no `LLMProvider` call outside `run_planner`, and imports nothing from `adapters` or `cli`.
  - The existing tests of `plan`, `planner_prompt`, `replan_prompt` and `impact` pass without edits.

## Architecture rules that apply
- `app` depends on `domain` and `ports` only. `replan.py` reuses `app/plan.py` (`run_planner`, `PlannerResult`, `PlannerOutcome`) and `app/replan_prompt.py`.
- `EventStore` is used for reading only; nothing calls `append` (the ADR-010 Later line).
- All state changes go through `EventRecorder.record`. The LLM reply is validated by `PlannerReply` and the checks before use, as in `plan`.
- Use cases return data and print nothing. `cli.py` builds the lines in 6c.

## Plan
1. Create branch `task/TASK-102-replan-use-case` from an up-to-date main.
2. Record the human's answers to the Design choices and Open questions in this record.
3. Test-writer: write failing `test_task102_ac<N>_…` tests in the new `tests/unit/test_replan.py`. Use an approved plan on `sv_01`, with the latest approved version `sv_02`:
   - AUTH-001 passed and untouched;
   - AUTH-002 passed and impacted;
   - AUTH-003 pending and downstream;
   - AUTH-004 abandoned and untouched.

   Fake `EventStore` streams hold `ImpactComputed` events (one with `from_version` `sv_00`, two matching ones). Use a scripted fake LLM.
4. Implement:
   - `untouched` and `build_prompt` in `run_planner` and `_attempt`;
   - `app/replan.py` with `prepare_replan`, `create_replan` and the result types.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`:
     - a new "Replan use case" section after "Impact use case";
     - "Plan use case: the planner call" for the two keywords;
     - "Plan checks", now that `replan` passes `untouched`;
     - the Data flow sentence on `EventStore.read` callers, adding `prepare_replan`.
   - `docs/progress.md`:
     - Current;
     - a Done line;
     - item 6b marked done;
     - delete the Later line "Item 6 (`replan`): its acceptance criteria should check that `replan` passes `ids_in_use`" (AC5 closes it).
   - `docs/decisions.md`: one row per answered design choice.
   - This record's Outcome.
7. Commit `feat(app): add the replan use case` with trailers `Task: TASK-102` and `Milestone: M6`. Do not push.

## Files expected to change
- `src/openfactory/app/replan.py` (new, about +120)
- `src/openfactory/app/plan.py` (about +15)
- `tests/unit/test_replan.py` (new, about +280)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, this record

Not expected to change: `cli.py`, `domain/`, `ports/`, `adapters/`, `app/replan_prompt.py`, `app/impact.py`, `app/approve_plan.py`, `docs/spec/`, `docs/adr/`.

## Design choices to confirm at planning
1. **Two calls (ADR-013).**
   - Proposed: `prepare_replan` (refusals 1 to 4, the impact read, the inputs and the `spec_files_differ` flag), then `create_replan` (`git ls-files`, the reads, the planner call). This mirrors `prepare_plan` and `create_plan`, so 6c can print the warning at the spec's time.
   - Alternative: one call that returns the flag. That breaks the warning's timing, which ADR-013 rejected for `plan`.
2. **How `run_planner` gets the replan prompt.**
   - Proposed: a keyword-only `build_prompt: Callable[[Sequence[PlanRejection]], str] | None = None`, plus `untouched: Sequence[Task] = ()`. `plan.py` does not import `replan_prompt.py`, and the retry stays in one place.
   - Alternative A: `run_planner` takes `impact` and `plan_tasks` and calls `build_replan_prompt` and `untouched_tasks` itself. That puts fewer duties on the caller but ties `plan.py` to the replan module.
   - Alternative B: a second call-with-retry loop in `replan.py`. Rejected because it duplicates `_attempt`.
3. **Reading the impact.**
   - Proposed: `EventStore.read(f"spec:{latest.id}")`, keep events of type `ImpactComputed`, validate each payload with `ImpactComputedPayload.model_validate`, keep those whose `from_version` is the approved plan's spec version, and take the last in `seq` order.
   - Every event on that stream has `to_version == latest.id`, because `impact` records on `spec:<to_version>`, so `to_version` is checked by the stream and not compared again. Should it also be compared, as a guard?
4. **"Lists no task".** Proposed: test `impact.tasks` only. `downstream` cannot be non-empty without `tasks`, because downstream tasks depend on impacted or downstream ones (Step 3).
5. **Reads in `create_replan`.** `task_ids_in_use()` and `Plans.tasks(plan_id)` are each read once, after `tracked_files()` succeeds and before the first attempt. Both attempts use the same values, as for `plan` (TASK-100, choice 3).
6. **Result types.** Reuse `PlannerResult` and `PlannerOutcome` from `plan.py` for `create_replan`, `git_failed` included, so 6c prints the result as `plan` does. Only the refusals get their own `ReplanRefusal` and `ReplanRefused` types.

## Spec notes (not gaps)
- When the approved plan's spec version is the latest approved one, `replan` refuses with `run openfactory impact first`, and that `impact` then refuses with `no spec change since sv_NN`. The behaviour is defined by the spec's text and is followed as written. This is a usability note only; no `/spec-change` is proposed.
- "Lists no task" (Design choice 4) follows from Step 3's definition of downstream, so no decision is missing.

## Open questions
1. Do you accept Design choices 1 to 6 as proposed? In particular, the `build_prompt` callable (choice 2) over `run_planner` taking `impact` and `plan_tasks`.
2. Should `prepare_replan` also compare `to_version` with the latest approved id (choice 3), or is the stream filter enough?
3. Size: with the tests, the task may slightly exceed ~300 lines. Keep it as one task, or split it into 6b-i (`prepare_replan`: AC1, AC2) and 6b-ii (`create_replan` and the `run_planner` keywords: AC3 to AC6)?
4. AC5's third bullet: keep it, or drop it? The impacted-id case already shows `ids_in_use` is passed.

## Answers (2026-10-24)
The human followed the advisor on every question.
1. Design choices 1 to 6 accepted as written, choice 2 included (`build_prompt` callable and `untouched` on `run_planner`).
2. The stream filter `spec:<latest id>` is enough; `to_version` is not compared again.
3. One task, not split.
4. AC5's third bullet stays: it is the only check that fails if `create_replan` derives the id set from the plan instead of passing `task_ids_in_use()`.

## Outcome
Built `src/openfactory/app/replan.py` with `ReplanRefusal`, `ReplanRefused`, `ReplanInputs`, `prepare_replan` (the first four refusals in order, the `ImpactComputed` read through `EventStore`, the `spec_files_differ` flag) and `create_replan` (`git ls-files`, one read each of `task_ids_in_use()` and the approved plan's tasks, then `run_planner`).
- `run_planner` in `src/openfactory/app/plan.py` gains keyword-only `untouched=()` and `build_prompt=None` (a callable taking the rejections); the defaults keep `plan` unchanged.
- 26 new tests in `tests/unit/test_replan.py`. No existing test edited, no test-writer test edited.
- No new port, adapter, event, table or dependency; no ADR needed.
- Full suite 2037 passed; ruff, pyright and check_docs clean.
- The Later line about item 6 passing `ids_in_use` is closed by AC5 and removed from progress.md.
- Follow-up: 6c (`replan` command, output, warning) and item 7.
