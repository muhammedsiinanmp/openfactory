# TASK-108: Cost attribution of runs to tasks and plans

- Milestone: M7
- Status: done
- Branch: `task/TASK-108-cost-attribution`
- Tests: acceptance
- ADR: ADR-020 (accepted). Its Decision says a task's runs count for the latest `PlanCreated` listing it, a plan gets its planner runs "through that event's `causation_id` chain" and a replan gets "the classifier runs of the latest `ImpactComputed` recorded before that `PlanCreated`". It also says "No new port … `PlanCreated`, `PlanApproved` and `ImpactComputed` events and their chains are read through `EventStore`". Its Consequences say "the use cases follow the `causation_id` chains of events read through `EventStore`". The task adds no port, adapter, event type, payload field, table, dependency or convention, so no new ADR is needed. The answers to Open questions 1 to 3 go in one row of `docs/decisions.md`.
- Spec impact: none
- Spec sections (spec v1.20):
  - "Metrics", bullet: "A task's runs count for the latest `PlanCreated` that lists the task (a superseded draft's ids may be reused). A plan's figures are over the runs of those tasks, the planner runs of the command that recorded its `PlanCreated`, found through its `causation_id` chain, and, for a plan whose `PlanCreated` was recorded while another plan was approved (a replan), the classifier runs of the latest `ImpactComputed` recorded before that `PlanCreated`, found through that event's chain. The planner runs of a command that recorded no `PlanCreated`, and classifier runs no replan used, belong to no plan and count only in the role figures." (SC-204)
  - "Metrics", bullet: "A run with no `AgentRunFinished` counts in the number of runs, adds nothing to tokens, cost or duration, and is not in the percentiles." (SC-210)
  - "Metrics", bullet: "A task's figures cover all its runs, those before a `resolve --retry` included; `tasks.cost_usd` is only the budget the cost check reads." (SC-211)
  - "CLI commands" › "Output", `stats` bullet: "`<runs>` is the number of runs; the other figures are sums, a null counting as 0 (see Metrics for the runs a task and a plan cover)", and "`plan  <plan id>` … for each plan that has a `PlanCreated`". This bullet is item 3's consumer. It is quoted only to fix the five figures and which plans are listed.
  - "Domain model and storage", M7 paragraph: "`Runs` also gives every run …" (SC-209). The read comes from TASK-107.

## Outline item
This is M7 outline item 2 in `docs/progress.md`. Item 3 (`stats`) and item 4 (`report` cost table) consume its result. Nothing calls it in this task.

## Objective
A new app module gives the figures for each task and for each plan: number of runs, `tokens_in`, `tokens_out`, `cost_usd` and `duration_s`. It attributes runs as the spec's Metrics section says, reading only `Runs.all_runs()` and `EventStore.read()`.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- New `src/openfactory/app/cost.py`, importing only `openfactory.domain` and `openfactory.ports`. It holds:
  - a frozen `Figures` model: `runs: int`, `tokens_in: int`, `tokens_out: int`, `cost_usd: float`, `duration_s: float`, all `extra="forbid"`
  - `sum_figures(runs: Iterable[RunRecord]) -> Figures`
  - a frozen `CostAttribution` with `tasks: dict[str, Figures]` and `plans: dict[str, Figures]`
  - `attribute_costs(*, runs: Runs, events: EventStore) -> CostAttribution`
- New `tests/unit/test_cost.py`. It uses in-memory fakes of `Runs` and `EventStore`, built from real payload models, plus one integration test in `tests/integration/test_cost_sqlite.py` that runs through `SqliteEventRecorder`, `SqliteEventStore` and `SqliteRuns`.

Out:
- Role figures, latency percentiles, rounding and printing, and the `stats` command (item 3).
- `report` and its `build`/`replan` rows (item 4).
- Any change to `ports/`, `adapters/`, `domain/`, `cli.py`, the projector, payloads, tables or events.

## Acceptance criteria
- [ ] **AC1** ("Metrics": "A run with no `AgentRunFinished` counts in the number of runs, adds nothing to tokens, cost or duration"; `stats` bullet: "the other figures are sums, a null counting as 0"):
  - `sum_figures` counts every run in `runs`.
  - It sums `tokens_in`, `tokens_out`, `cost_usd` and `duration_s`, with `None` counting as 0.
  - An unfinished run (`exit` `None`) adds 1 to `runs` and 0 to everything else.
  - No runs gives all zeros.
- [ ] **AC2** ("Metrics": "A task's figures cover all its runs, those before a `resolve --retry` included"):
  - `CostAttribution.tasks` has one entry per task id that has at least one run, and it covers all of that task's implementer and reviewer runs, including runs recorded before a `TaskResolved` `retry`. The figures do not come from `tasks.cost_usd`.
  - Planner and classifier runs (`task_id` `None`) are in no task entry.
- [ ] **AC3** ("Metrics": "A task's runs count for the latest `PlanCreated` that lists the task (a superseded draft's ids may be reused)"; `stats` bullet "each plan that has a `PlanCreated`"):
  - `CostAttribution.plans` has one entry per plan id that has a `PlanCreated`, including a plan with no runs, whose entry is all zeros.
  - A task's runs count only for the plan of the latest `PlanCreated` (highest `seq`) that lists the task. A task id listed by an earlier draft and again by a later plan counts only for the later plan.
- [ ] **AC4** ("Metrics": "the planner runs of the command that recorded its `PlanCreated`, found through its `causation_id` chain … The planner runs of a command that recorded no `PlanCreated` … belong to no plan"):
  - A plan's figures include the planner run, or both runs of a retried call, found by following `causation_id` back from its `PlanCreated`.
  - The planner runs of a `plan` or `replan` that ended rejected or failed (no `PlanCreated`) are in no plan's figures.
- [ ] **AC5** ("Metrics": "for a plan whose `PlanCreated` was recorded while another plan was approved (a replan), the classifier runs of the latest `ImpactComputed` recorded before that `PlanCreated`, found through that event's chain … classifier runs no replan used, belong to no plan"):
  - A plan whose `PlanCreated` comes after a `PlanApproved` of another plan also gets the classifier runs (one, or two after a retry) on the chain of the latest `ImpactComputed` recorded before that `PlanCreated`.
  - A plan created with no earlier `PlanApproved` gets no classifier runs.
  - An `ImpactComputed` with a null `causation_id` (no classifier call) adds no runs.
  - The classifier runs of an earlier `ImpactComputed` that no replan used are in no plan.
  - Two replan drafts in a row after the same `ImpactComputed` both get its classifier runs (ADR-020 Consequences).
- [ ] **AC6** (CLAUDE.md architecture rules; ADR-020 "No new port"):
  - `app/cost.py` imports only `openfactory.domain` and `openfactory.ports`.
  - `attribute_costs` calls only `Runs.all_runs` and `EventStore.read`. It never calls `append` and records nothing.
  - Nothing under `domain/`, `ports/`, `adapters/` or `cli.py` changes.
  - The integration test on real SQLite gives the same figures as the fakes for one build and one replan.
  - The full suite passes, and no existing test is edited.

## Architecture rules that apply
- App use case: depends on domain and ports only. No I/O of its own.
- Payloads read from `StoredEvent.payload` are validated with their `PAYLOAD_MODELS` / payload classes before use.
- Reads only: "All state changes go through the events table" is untouched, because nothing is written.

## Plan
1. Create branch `task/TASK-108-cost-attribution` from an up-to-date main.
2. Record the human's answers to the Open questions.
3. Test-writer: write failing tests for AC1 to AC6 in `tests/unit/test_cost.py` and `tests/integration/test_cost_sqlite.py`.
4. Implement `app/cost.py`:
   - Call `events.read()` once and index the events by `event_id`.
   - Walk the chain: follow `causation_id` until `None`, collecting `run_id` from the `AgentRunStarted` and `AgentRunFinished` payloads on it.
   - Map each task id to its latest `PlanCreated` by `seq`.
   - Mark a `PlanCreated` as a replan when any `PlanApproved` has a lower `seq`.
   - Pick the latest `ImpactComputed` with a lower `seq` for each replan.
   - Group `all_runs()` and apply `sum_figures`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`: a new "Cost attribution" section under the app use cases, and the wiring note that nothing calls it yet.
   - `docs/decisions.md`: one row for the answers to Open questions 1 to 3.
   - `docs/progress.md`: Current, a Done line, item 2 marked done.
   - This record's Outcome.
7. Commit `feat(app): attribute run costs to tasks and plans` with trailers `Task: TASK-108` and `Milestone: M7`. Do not push.

## Files expected to change
- `src/openfactory/app/cost.py` (new, about +110)
- `tests/unit/test_cost.py` (new, about +220)
- `tests/integration/test_cost_sqlite.py` (new, about +80)
- `docs/architecture.md`, `docs/decisions.md`, `docs/progress.md`, this record

Not expected to change: `domain/`, `ports/`, `adapters/`, `cli.py`, the projector, payloads, `docs/spec/`, `docs/adr/`.

## Spec gaps
None. Two reading notes, neither of them a gap:
- "Recorded while another plan was approved" can be read from the log alone. An approved plan stays approved until a later one supersedes it, so "a `PlanApproved` with a lower `seq` than this `PlanCreated`" is equivalent. A plan's own `PlanApproved` always comes after its `PlanCreated`.
- "The latest `ImpactComputed` recorded before that `PlanCreated`" has no version filter. `impact` always diffs to the latest approved version, and `replan` refuses unless the latest matching event exists, so the latest one before the `PlanCreated` is the one the replan used. The `from_version` cannot change either between that impact and the replan's `PlanCreated`, because it is the approved plan's spec version and changing it needs a `PlanApproved`.

## Open questions (each with a proposed answer)
1. **Module and names.** Proposed: `app/cost.py` with `Figures`, `sum_figures`, `CostAttribution` and `attribute_costs(*, runs, events)`. Alternative: put the attribution in a pure `domain/cost.py` that takes lists of `StoredEvent` and `RunRecord`, with a thin app wrapper. That adds a module for no caller other than the wrapper.
2. **Result shape.** Proposed: `dict[str, Figures]` keyed by task id and by plan id, unsorted and unrounded. Item 3 sorts the lines as strings and formats four decimals and one decimal. Alternative: sorted lists of `(id, Figures)` entries.
3. **Role figures and latency.** Proposed: leave both to item 3. Role grouping is `sum_figures` over `all_runs()` grouped by `role`, and the outline names the `role` and `latency` lines under item 3. Alternative: add `roles: dict[str, Figures]` here, so that every grouping lives in one place.
4. **Event read.** Proposed: one `events.read()` of all streams. Planner runs sit on their own stream, while `PlanCreated` is on `plan:<id>` and `ImpactComputed` on `spec:<id>`, so a chain crosses streams. Alternative: read per stream, which needs to know the planner's run stream.
5. **Chain walk.** Proposed: collect `run_id` from every `AgentRunStarted` and `AgentRunFinished` on the chain, and stop at a null `causation_id`. A `causation_id` that names no stored event also ends the walk, with no error; this cannot happen in a log the use cases wrote. No check is made that the runs found have role `planner` or `classifier`.

## Answers (human, 2026-10-25)
All five proposed answers accepted as written.

## Outcome
- `src/openfactory/app/cost.py` added as planned: one `events.read()`, chains walked through `causation_id` into a set of run ids, a task mapped to its latest `PlanCreated` in `seq` order, a replan's classifier runs taken from the latest `ImpactComputed` before its `PlanCreated` when some `PlanApproved` precedes it.
- Tests: 18 new (17 unit, 1 integration); full suite 2105 passed; ruff, pyright and check_docs clean.
- Test edits to the test-writer's tests (no pre-existing test edited):
  - Mechanical: `test_ac2_task_figures_cover_all_its_runs_including_before_a_retry` and `test_ac6_real_sqlite_gives_the_figures_of_one_build_and_one_replan` built `Figures(..., cost_usd=pytest.approx(...))`, which Pydantic rejects; they now compare `model_dump()` with a dict of the same five values, `cost_usd` still approximate. Ruff then dropped the unused `Figures` import in the integration test.
  - Non-mechanical, approved by the human (decisions.md rows of 2026-10-25): the replan's first planner run in three AC5 unit tests and the integration replan no longer points at the `ImpactComputed` (the unused `imp` names were dropped), matching `run_planner`; checked that with the `ImpactComputed` lookup disabled, those four tests fail. The AC6 unit test compares the event count with the count before the call instead of the literal 3.
