# TASK-110: `report` use case

- Milestone: M7
- Status: done
- Branch: `task/TASK-110-report-use-case`
- Tests: acceptance
- ADR: ADR-020 (accepted), ADR-018 (accepted) and ADR-011 (accepted).
  - ADR-020 Decision: "No new port. `Runs` also gives every run … `PlanCreated`, `PlanApproved` and `ImpactComputed` events and their chains are read through `EventStore`; `report` reads the links through `Traces`."
  - ADR-020 Consequences: "`report` lists approved plans only, so its rows do not double-count."
  - ADR-018 defines the `Traces` read and `RequirementTrace`. ADR-011 leaves formatting and printing to `cli.py`, which is TASK-111.
  - The task adds no port, adapter, event type, payload field, table, dependency or convention, so it needs no new ADR. The answers to the open questions go in one row of `docs/decisions.md`.
- Spec impact: none. The `report` bullet settles everything the use case returns; the Markdown details belong to TASK-111 (see "Looking ahead to TASK-111").
- Spec sections (spec v1.20):
  - "CLI commands" table row: "`openfactory report` | Final traceability report as Markdown".
  - "CLI commands" › "Output", `report` bullet (SC-205): "`report` prints Markdown on standard output: the line `# OpenFactory report`; a line `plan <plan id> · spec <spec version id>` for the approved plan and the latest approved spec version; `## Requirements`, then, for each requirement of the latest approved version in ascending id as strings, a heading `### <id>  <title>`, with ` (deprecated)` after the title when it is deprecated, and a fenced block holding the lines `trace <id>` prints (empty when it prints none); then `## Cost`, a table `| Plan | Kind | Runs | Tokens in | Tokens out | Cost USD |` with one row per plan that has a `PlanApproved`, in ascending plan id as strings, `Kind` `build` for the first and `replan` for the others and the plan's figures as for `stats`, then a row `total` with the sums of the rows above. It records no events, does not repair the plan, and exits 0. With no approved plan it refuses with `no approved plan` on standard error and exits 1."
  - "Metrics": "The final report includes total cost of the initial build and of the replan, which shows the saving from re-executing only impacted work (see `report` under CLI commands)"; the "A task's runs count for the latest `PlanCreated` …" bullet (SC-204, built in TASK-108); "A task's figures cover all its runs …" (SC-211).
  - "Domain model and storage", M7 paragraph (SC-209): "`report` reads the links through `Traces` as `trace` does."
  - "Milestones and definition of done", item 7: "Eval suite with results, `stats`, `report`, …".

## Outline item
M7 outline item 4 in `docs/progress.md`, first half (4a, the use case). 4b (TASK-111) adds the command, the Markdown, and the end-to-end check of `trace` after a supersede from the TASK-106 Later line. The use case is the second caller of `attribute_costs` and the first caller of `Traces.requirement_trace` outside `trace`.

## Objective
A pure use case gathers the data `openfactory report` prints:
- the approved plan's id and the latest approved spec version's id;
- per requirement of that version, its title, its deprecated flag and its `trace`;
- one cost row per plan that has a `PlanApproved` (`build` for the first, `replan` for the rest), with the `attribute_costs` figures;
- a `total` row;
- or the `no approved plan` refusal.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- A new `src/openfactory/app/report.py`. It imports only `openfactory.domain`, `openfactory.ports` and `openfactory.app.cost`, and holds:
  - `ReportRefusal(StrEnum)` with `no_approved_plan`.
  - A frozen `ReportRequirement` (`id`, `title`, `deprecated: bool`, `trace: RequirementTrace`), `extra="forbid"`.
  - A frozen `CostRow` (`plan_id`, `kind: Literal["build", "replan"]`, `figures: Figures`), `extra="forbid"`.
  - A frozen `Report` with `refusal: ReportRefusal | None = None`, `plan_id: str | None = None`, `spec_version: str | None = None`, `requirements: list[ReportRequirement] = []`, `costs: list[CostRow] = []` and `total: Figures | None = None`, `extra="forbid"`.
  - `build_report(*, plans: Plans, versions: SpecVersions, traces: Traces, runs: Runs, events: EventStore) -> Report`, with no recorder parameter.
- A new `tests/unit/test_report.py` with in-memory fakes of the five ports, built from real payload models as in `tests/unit/test_cost.py` and `tests/unit/test_stats.py`.

Out:
- The `report` command, the Markdown text, number formatting, `cli.py`, and the CLI-level `trace` after a supersede check (all TASK-111).
- Any change to `app/cost.py`, `app/trace.py`, `app/stats.py`, `domain/`, `ports/`, `adapters/`, the projector, payloads, tables or events.

## Acceptance criteria
- [x] **AC1** ("Output", `report` bullet: "With no approved plan it refuses with `no approved plan` … It records no events, does not repair the plan")
  - With `Plans.approved()` returning `None`, `build_report` returns `refusal` `no_approved_plan` with every other field at its default.
  - It does so even when an approved spec version, runs and events exist.
  - Nothing is recorded: `build_report` takes no recorder, and the `EventStore` fake sees no `append`.
- [x] **AC2** ("Output", `report` bullet: "a line `plan <plan id> · spec <spec version id>` for the approved plan and the latest approved spec version")
  - `plan_id` is `Plans.approved().id` and `spec_version` is `SpecVersions.latest_approved().id`.
  - The two are reported as they are even when they differ. Example: `plan_01` made for `sv_01`, after `approve spec` recorded `sv_02` and before any replan, gives `plan_01` and `sv_02`.
- [x] **AC3** ("Output", `report` bullet: "for each requirement of the latest approved version in ascending id as strings, a heading `### <id>  <title>`, with ` (deprecated)` after the title when it is deprecated, and a fenced block holding the lines `trace <id>` prints (empty when it prints none)"; M7 paragraph: "`report` reads the links through `Traces` as `trace` does")
  - `requirements` has one entry per requirement of `SpecVersions.spec_set(<latest approved id>)`, deprecated ones included.
  - Entries are in ascending id as strings: `REQ-AUTH-010` comes after `REQ-AUTH-002`, even when the fake returns them in another order.
  - Each entry carries its `title` and `deprecated` flag.
  - Each entry's `trace` is exactly the `RequirementTrace` that `Traces.requirement_trace(<id>)` returns, with the adapter's order kept.
  - A requirement with no links has a trace with four empty lists.
  - Requirements found only in older spec versions get no entry.
- [x] **AC4** ("Output", `report` bullet: "one row per plan that has a `PlanApproved`, in ascending plan id as strings, `Kind` `build` for the first and `replan` for the others and the plan's figures as for `stats`"; "Metrics": "The final report includes total cost of the initial build and of the replan")
  - `costs` has one `CostRow` per distinct `plan_id` among the `PlanApproved` events, in ascending plan id as strings.
  - The first row's `kind` is `build`; every later row is `replan`.
  - A plan with only a `PlanCreated` has no row. This covers a draft superseded by a second `plan` and a replan draft not yet approved.
  - A superseded plan that was approved keeps its row.
  - Each row's `figures` equal `attribute_costs(runs=, events=).plans[plan_id]`.
  - Example (one build, then `impact`, `replan`, `approve plan`): the `replan` row holds its own planner runs, the classifier runs of the `ImpactComputed` it used, and the runs of its new tasks. It holds none of the build's task runs.
- [x] **AC5** ("Output", `report` bullet: "then a row `total` with the sums of the rows above"; ADR-020: "`report` lists approved plans only, so its rows do not double-count")
  - `total` is a `Figures` whose `runs`, `tokens_in`, `tokens_out`, `cost_usd` and `duration_s` are the sums over `costs`.
  - Runs counted in no row are not in `total`: the planner runs of a twice-rejected `plan`, classifier runs no approved replan used, and the planner runs of an unapproved draft.
  - With an approved plan and no run, `total` is all zeros.
  - When an approved plan exists, `total` is never `None`.
- [x] **AC6** (CLAUDE.md architecture rules; ADR-020 "No new port"; ADR-011; `report` bullet "It records no events, does not repair the plan")
  - `app/report.py` imports only `openfactory.domain`, `openfactory.ports` and `openfactory.app.cost`.
  - Its fakes see only read methods called: `Plans.approved`, `SpecVersions.latest_approved` and `spec_set`, `Traces.requirement_trace`, `Runs.all_runs` and `EventStore.read`. No `append`, and no `Plans` method beyond `approved`.
  - `cli.py`, `domain/`, `ports/`, `adapters/`, `app/cost.py` and `app/trace.py` are unchanged.
  - The full suite passes and no existing test is edited.

## Architecture rules that apply
- `app/report.py` depends on `domain` and `ports`, plus `app/cost.py` in the same layer. It does no I/O, returns data and prints nothing.
- Sorting and grouping happen in `app`, as for `status` and `stats` (TASK-109 answer 1). Rounding and Markdown happen in `cli.py` (TASK-111).

## Plan
1. Create branch `task/TASK-110-report-use-case` from an up-to-date main.
2. Record the human's answers to the open questions in this record.
3. Test-writer: write failing tests in `tests/unit/test_report.py` for AC1 to AC6. Use fakes of `Plans`, `SpecVersions`, `Traces`, `Runs` and `EventStore`; events come from real payload models (`PlanCreatedPayload`, `PlanApprovedPayload`, `ImpactComputedPayload`, the run payloads) with `causation_id` chains as in `test_cost.py`.
4. Implement `build_report`:
   - Read `plan = plans.approved()`, and refuse if it is `None`.
   - Read `version = versions.latest_approved()` and `spec = versions.spec_set(version.id)`, asserting both are not `None`.
   - Build `requirements` from `sorted(spec.requirements, key=id)`, each with `traces.requirement_trace(id)`, asserted not `None`.
   - Collect the approved plan ids from `events.read()`, keeping `PlanApproved` events, then sort them. This read comes before the `attribute_costs` call.
   - Call `attribute_costs(runs=, events=)` and build `costs` (`build` first, then `replan`).
   - Compute `total` by summing the fields.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`: a new "Report use case" section; `app/cost.py` now has a second caller, with the `report` command still to come.
   - `docs/decisions.md`: one row for the answers.
   - `docs/progress.md`: Current, a Done line, item 4 split into 4a done and 4b next.
   - This record's Outcome.
7. Commit `feat(app): add the report use case` with trailers `Task: TASK-110` and `Milestone: M7`. Do not push.

## Files expected to change
- `src/openfactory/app/report.py` (new, about +75)
- `tests/unit/test_report.py` (new, about +180)
- `docs/architecture.md`, `docs/decisions.md`, `docs/progress.md`, this record

Not expected to change: `cli.py`, `app/cost.py`, `app/trace.py`, `app/stats.py`, `domain/`, `ports/`, `adapters/`, `docs/spec/`, `docs/adr/`, `CHANGELOG.md` (its line comes with the command in TASK-111).

Expected size: about 260 lines, about 75 of them under `src/`.

## Reading notes (none of them a spec gap)
- **"The first" plan:** this is the lowest approved plan id. Plan ids only grow, and only one draft exists at a time, so id order and approval order agree. A draft superseded before approval has no `PlanApproved` and so no row. The build is then the lowest id that was approved, for example `plan_02` after `plan_01` was replaced.
- **"The plan's figures as for `stats`":** the figures are those of `attribute_costs` (SC-204). The table shows runs, tokens and cost but no duration. `Figures.duration_s` is still carried, which does no harm.
- **The `trace` lines of a requirement of the latest approved version:** `trace` would never refuse here, because `Traces.requirement_trace` returns `None` only when no approved version has the id. Open question 2 covers the fallback.
- **The report header's spec version is the latest approved one**, not the plan's own version. AC2 pins this.

## Open questions (answered by the human, 2026-10-25: "do as the advisor says")
1. **Result shape and who sums `total`.** `build_report` returns `Report` with sorted `requirements` and `costs`, and `total` computed in `app` (TASK-109 answer 1); `cli.py` only formats.
2. **`None` from `Traces.requirement_trace`** (cannot happen for a requirement of an approved version). `build_report` asserts it is not `None`, as `app/replan.py` and `app/impact.py` assert their invariants (TASK-102, TASK-104 rows); the same for `SpecVersions.latest_approved()` and `spec_set()` while an approved plan exists. No fallback and no test for the unreachable branch.
3. **Reading the `PlanApproved` events.** `build_report` calls `events.read()` itself for the approved plan ids, and `attribute_costs` reads the log again (TASK-109 answer-3 precedent); `app/cost.py` stays unchanged. The approved ids are read before `attribute_costs` is called, so every id is a key of `attribution.plans`.
4. **Names.** Module `app/report.py`, function `build_report`, models `Report`, `ReportRequirement` and `CostRow`, refusal `ReportRefusal.no_approved_plan`.

## Looking ahead to TASK-111 (spec wording, does not block TASK-110)
Recorded under "Later" in `docs/progress.md` as "Spec wording" lines: the `total` row's `Kind` cell, the exact Markdown layout (blank lines, table separator row, fence), the table's number format, and the empty fenced block.

## Outcome
- Files changed: `src/openfactory/app/report.py` (new), `tests/unit/test_report.py` (new, 11 tests), `docs/architecture.md`, `docs/decisions.md`, `docs/progress.md`, this record.
- Test edits: none. The implementer did not edit the test-writer's tests.
- AC6: the import limit and the read-only calls are checked by the unit tests. "`cli.py`, `domain/`, `ports/`, `adapters/`, `app/cost.py` and `app/trace.py` unchanged" and "full suite passes, no existing test edited" are checked by the diff and the suite (2138 passed), not by a unit test.
- Checks: ruff, pyright and check_docs clean.
- Decisions: one row in `docs/decisions.md` for the four answers. No ADR needed. `CHANGELOG.md` has no line; it comes with the command in TASK-111.
- Next: TASK-111 (4b), the `report` command; the "Spec wording" Later lines apply.
