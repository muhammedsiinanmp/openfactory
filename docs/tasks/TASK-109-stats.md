# TASK-109: `stats` use case and command

- Milestone: M7
- Status: done
- Branch: `task/TASK-109-stats`
- Tests: acceptance
- ADR: ADR-020 (accepted) and ADR-011 (accepted).
  - ADR-020 Decision: "No new port. `Runs` also gives every run with its task id, role, exit, tokens, cost and `duration_s`. `PlanCreated`, `PlanApproved` and `ImpactComputed` events and their chains are read through `EventStore`". It also says how a run counts for a plan, which TASK-108 built as `attribute_costs`.
  - ADR-011 makes `cli.py` the composition root that prints and sets exit codes.
  - The task adds no port, adapter, event type, payload field, table, dependency or convention, so no new ADR is needed. The answers to the Open questions go in one row of `docs/decisions.md`.
- Spec impact: none (see Spec gaps: reading notes only)
- Spec sections (spec v1.20):
  - "CLI commands" table row: "`openfactory stats` | Tokens, cost and latency".
  - "CLI commands" › "Output", `stats` bullet (SC-203): "`stats` prints `task  <task id>  <runs>  <tokens_in>  <tokens_out>  <cost_usd>  <duration_s>` for each task that has a run, in ascending task id as strings; then `plan  <plan id>` with the same five figures for each plan that has a `PlanCreated`, in ascending plan id as strings; then `role  <role>` with the same five figures for each role that has a run, in ascending role as strings; then `latency  p50  <s>  p95  <s>`. `<runs>` is the number of runs; the other figures are sums, a null counting as 0 (see Metrics for the runs a task and a plan cover); `cost_usd` has four decimals and every duration one. The percentiles are nearest-rank over the `duration_s` of every run with `exit: ok`, `-` when there is none. Fields are separated by exactly two spaces. It records no events, does not repair the plan, and exits 0; with no run it prints only `latency  p50  -  p95  -`."
  - "CLI commands" › "Output", output-stream bullet (SC-216): "Command results (… `stats` lines and the `report` text) go to standard output."
  - "CLI commands" › "Other commands": "run against the current directory and fail with "run `openfactory init` first" if `./.openfactory/` is missing."
  - "Metrics": "`openfactory stats` prints totals per task, per plan, and per role, plus p50 and p95 run latency"; "A run with no `AgentRunFinished` counts in the number of runs, adds nothing to tokens, cost or duration, and is not in the percentiles." (SC-210); "A task's figures cover all its runs, those before a `resolve --retry` included" (SC-211); the "A task's runs count for the latest `PlanCreated` …" bullet (SC-204), already built in TASK-108.
  - "Milestones and definition of done", item 7: "Eval suite with results, `stats`, `report`, …".

## Outline item
M7 outline item 3 in `docs/progress.md`: "`stats` use case and command: the `task`, `plan`, `role` and `latency` lines, nearest-rank percentiles over runs with `exit: ok` (SC-203, SC-216)". It is the first caller of `attribute_costs` (TASK-108) and `Runs.all_runs` (TASK-107). Item 4 (`report`) comes next.

## Objective
`openfactory stats` prints the `task`, `plan` and `role` figure lines and the `latency` line, as "CLI commands" › "Output" says. The task and plan figures come from `attribute_costs`. The role figures and the nearest-rank p50 and p95 come from `Runs.all_runs()`. The command records no events and exits 0.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- New `src/openfactory/app/stats.py`, importing only `openfactory.domain`, `openfactory.ports` and `openfactory.app.cost`. It holds:
  - a frozen `StatsReport` with these fields, all `extra="forbid"`:
    - `tasks: list[tuple[str, Figures]]`, sorted by id as strings
    - `plans: list[tuple[str, Figures]]`, sorted the same way
    - `roles: list[tuple[str, Figures]]`, sorted the same way
    - `p50: float | None`
    - `p95: float | None`
  - `nearest_rank(values: Sequence[float], percent: int) -> float`
  - `run_stats(*, runs: Runs, events: EventStore) -> StatsReport`
  - The use case has no recorder parameter and no refusal.
- `src/openfactory/cli.py`:
  - a new top-level `stats` command with no arguments. It calls `require_init()` and opens `_open_adapters` together with `closing(SqliteEventStore(database))`, as `plan` does. It calls `run_stats(runs=adapters.runs, events=store)` and prints after the adapters are closed.
  - a private `_figures_line(kind, key, figures) -> str` that prints `runs` and tokens as integers, `cost_usd` as `f"{x:.4f}"` and `duration_s` as `f"{x:.1f}"`.
  - a private `_latency_line(p50, p95) -> str` that prints `f"{x:.1f}"` or `-`.
- New `tests/unit/test_stats.py`, using in-memory fakes of `Runs` and `EventStore` built from real payload models, as in `tests/unit/test_cost.py`.
- New `tests/integration/test_cli_stats.py`, which seeds events through `SqliteEventRecorder` and drives the Typer app with `CliRunner`, as `test_cli_status.py` does.

Out:
- `report` and its cost table (item 4).
- Any change to `app/cost.py`, `domain/`, `ports/`, `adapters/`, the projector, payloads, tables or events.
- Repair, git, worktree, gate or LLM adapters for `stats`.

## Acceptance criteria
- [ ] **AC1** ("Output", `stats` bullet: "`task  <task id>  <runs>  <tokens_in>  <tokens_out>  <cost_usd>  <duration_s>` for each task that has a run, in ascending task id as strings … the other figures are sums, a null counting as 0 … `cost_usd` has four decimals and every duration one"; "Metrics": "A task's figures cover all its runs, those before a `resolve --retry` included" and "A run with no `AgentRunFinished` counts in the number of runs, adds nothing"):
  - One `task` line per task id with at least one run (implementer or reviewer), in ascending string order (`AUTH-010` after `AUTH-002`), fields separated by exactly two spaces.
  - Runs before a `TaskResolved` `retry` are included.
  - An unfinished run adds 1 to `<runs>` and 0 to the other figures.
  - Tokens or cost the runtime did not report count as 0.
  - Cost is printed with four decimals (for example `0.1235` for 0.12345 plus nothing else) and duration with one.
- [ ] **AC2** ("Output", `stats` bullet: "then `plan  <plan id>` with the same five figures for each plan that has a `PlanCreated`, in ascending plan id as strings"; "(see Metrics for the runs a task and a plan cover)"):
  - After the `task` lines comes one `plan` line per plan id with a `PlanCreated`, in ascending string order. This includes a superseded draft and a replan draft.
  - The figures are those of `attribute_costs` for that plan. For example, after one build and one replan, the replan's line includes its own planner runs and the classifier runs of the `ImpactComputed` it used, and leaves out the build's tasks.
- [ ] **AC3** ("Output", `stats` bullet: "then `role  <role>` with the same five figures for each role that has a run, in ascending role as strings"; "Metrics": "… belong to no plan and count only in the role figures"):
  - After the `plan` lines comes one `role` line per role among `classifier`, `implementer`, `planner` and `reviewer` that has at least one run, in that string order. A role with no run has no line.
  - The figures are summed over every run of that role. For example, the planner runs of a `plan` that was rejected twice count in `role  planner` and in no `plan` line.
- [ ] **AC4** ("Output", `stats` bullet: "then `latency  p50  <s>  p95  <s>` … The percentiles are nearest-rank over the `duration_s` of every run with `exit: ok`, `-` when there is none"; "Metrics": "… and is not in the percentiles"):
  - The last line is `latency  p50  <s>  p95  <s>`.
  - The values come from `nearest_rank`: the value at 1-based rank ceil(P/100 × N) in the ascending `duration_s` of the runs with `exit` `ok`, across all roles.
  - Runs with `exit` `error`, with `exit` `timeout`, and unfinished runs are left out.
  - Examples: 1 to 10 s give `p50  5.0  p95  10.0`. A single ok run of 2.34 s gives `2.3` for both.
  - Finished runs that are none of them `ok` give `latency  p50  -  p95  -` after the other lines.
- [ ] **AC5** ("Output", `stats` bullet: "It records no events, does not repair the plan, and exits 0; with no run it prints only `latency  p50  -  p95  -`"; output-stream bullet "`stats` lines … go to standard output"):
  - In an initialised repo with no run, `stats` prints exactly `latency  p50  -  p95  -` on standard output, nothing on standard error, and exits 0.
  - With a task left `running` and an unfinished implementer run (a killed `run`), `stats` exits 0. The `events` row count is unchanged, and the task is still `running` and its run still unfinished: no repair.
  - The lines come in group order `task`, `plan`, `role`, `latency`.
- [ ] **AC6** ("Other commands": "fail with "run `openfactory init` first""; CLAUDE.md architecture rules; ADR-020 "No new port"):
  - In a directory without `.openfactory/`, `stats` writes that line to standard error and exits 1.
  - `app/stats.py` imports only `openfactory.domain`, `openfactory.ports` and `openfactory.app.cost`, and `run_stats` takes no recorder. Its fakes see only `Runs.all_runs` and `EventStore.read` called, never `append`.
  - Nothing under `domain/`, `ports/` or `adapters/` changes, and neither does `app/cost.py`.
  - The full suite passes, and no existing test is edited.

## Architecture rules that apply
- `app/stats.py` depends on `domain` and `ports` (and on `app/cost.py`, another use case module in the same layer), does no I/O and returns data.
- `cli.py` formats, prints and sets exit codes (ADR-011), and writes its output after the adapters are closed, as `status` does.
- Reads only. `_open_adapters`' recorder catch-up writes projections but never an event, as for `status` (TASK-077 design choice 1).

## Plan
1. Create branch `task/TASK-109-stats` from an up-to-date main.
2. Record the human's answers to the Open questions in this record.
3. Test-writer: write failing tests:
   - `tests/unit/test_stats.py`: AC1 to AC4 at use-case level, `nearest_rank`, and the AC6 import and read checks.
   - `tests/integration/test_cli_stats.py`: AC1 to AC6 through `CliRunner`, with events seeded through `SqliteEventRecorder`.
4. Implement `app/stats.py`:
   - `records = runs.all_runs()`
   - `attribution = attribute_costs(runs=runs, events=events)`
   - roles by grouping `records` with `sum_figures`
   - `ok = sorted(r.duration_s for r in records if r.exit == "ok")`
   - `nearest_rank` for p50 and p95, or `None` when `ok` is empty
   - sort the three groups by key
5. Add the `stats` command, `_figures_line` and `_latency_line` to `cli.py`.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
7. Update the docs:
   - `docs/architecture.md`: a new "Stats use case" section; a `stats` bullet under "CLI"; `stats` added to the `require_init()` and `_open_adapters` lists; the "Nothing calls it yet" sentences for `app/cost.py` and `Runs.all_runs` changed to name `stats` as the caller, with `report` still to come.
   - `CHANGELOG.md`: an `[Unreleased]` line for `openfactory stats`.
   - `docs/decisions.md`: one row for the answers to the Open questions.
   - `docs/progress.md`: Current, a Done line, item 3 marked done.
   - This record's Outcome.
8. Commit `feat(cli): add the stats command` with trailers `Task: TASK-109` and `Milestone: M7`. Do not push.

## Files expected to change
- `src/openfactory/app/stats.py` (new, about +60)
- `src/openfactory/cli.py` (about +40)
- `tests/unit/test_stats.py` (new, about +120)
- `tests/integration/test_cli_stats.py` (new, about +110)
- `docs/architecture.md`, `docs/decisions.md`, `docs/progress.md`, `CHANGELOG.md`, this record

Not expected to change: `app/cost.py`, `domain/`, `ports/`, `adapters/`, the projector, payloads, `docs/spec/`, `docs/adr/`.

Expected size: about 330 lines, about 100 of them under `src/`. TASK-077 (`status`) is the precedent for a use case and its command in one task. If the human prefers a smaller task, split it into 3a (use case: AC1 to AC4 and the app part of AC6) and 3b (command: AC5 and the CLI parts of AC6).

## Spec gaps
None. Reading notes, none of them a gap:
- **"Nearest-rank"** is a standard percentile method: the value at 1-based rank ceil(P/100 × N) of the sorted values, always one of the observed durations and never interpolated. The record pins it with examples in AC4.
- **"Every duration one"** covers the `<duration_s>` figure and the two latency values.
- **Four or one decimals** means Python's fixed-point formatting of the float sum (`:.4f`, `:.1f`). The spec names no rounding mode, and none is needed for the tests' values.
- **"With no run it prints only the latency line"** fits the plan rule. Every `PlanCreated` is preceded by at least one planner run on its chain, so a plan line without any run cannot arise from the commands.
- **"Each task that has a run" and "each role that has a run"** include unfinished runs, since "A run with no `AgentRunFinished` counts in the number of runs" (SC-210).
- **No refusal:** `stats` names none beyond the init check, so it runs with no approved plan or spec.

## Open questions (each with a proposed answer)
1. **Who sorts.** Proposed: `run_stats` returns the three groups as sorted lists of `(id, Figures)`, pinning "ascending … as strings" in `app` as `status` does (TASK-077 design choice 3), and `cli.py` only formats. Alternative: keep `dict`s, as `CostAttribution` does (the 2026-10-25 TASK-108 row: "sorting and rounding belong to the printer"), and sort in `cli.py`. Rounding stays in `cli.py` either way.
2. **Where `nearest_rank` lives.** Proposed: a public pure function in `app/stats.py`, tested directly, with no other caller. Alternative: a pure `domain/metrics.py`. That adds a module for one caller.
3. **Two reads of `agent_runs`.** Proposed: `run_stats` calls `runs.all_runs()` itself (roles, latency) and `attribute_costs(runs=, events=)` reads it again, so `app/cost.py` is unchanged. A `run` in another process could record a run between the two reads. The groups could then differ by that run, which is harmless for a read-only report. Alternative: change `attribute_costs` to also accept the records, or return them. That edits TASK-108's module and its approved signature.
4. **Opening the store.** Proposed: `_open_adapters` plus `closing(SqliteEventStore(database))`, as `plan`, `impact` and `replan` do, so the recorder's catch-up brings projections up to date before the reads. Alternative: open only `SqliteRuns` and `SqliteEventStore`. That skips catch-up, and `agent_runs` could lag the log.

## Answers (human, 2026-10-25)
Plan approved with every proposed answer: 1. `run_stats` returns sorted lists (this differs from the TASK-108 "sorting belongs to the printer" rationale, which decided only `app/cost.py`'s shape); 2. `nearest_rank` in `app/stats.py`; 3. two reads, `app/cost.py` unchanged; 4. `_open_adapters` plus `closing(SqliteEventStore(database))`.

## Outcome
Added `src/openfactory/app/stats.py` (`StatsReport`, `nearest_rank`, `run_stats`) and the `stats` command with `_figures_line` and `_latency_line` in `src/openfactory/cli.py`. The task and plan figures come from `attribute_costs`; roles and the nearest-rank p50 and p95 come from `Runs.all_runs()`. The command records no events and exits 0; `app/cost.py`, `domain/`, `ports/` and `adapters/` are unchanged. New tests: `tests/unit/test_stats.py` and `tests/integration/test_cli_stats.py`.

- Test edits: none. No test was edited.
- Checks: 2127 tests pass, ruff, pyright and check_docs clean.
- Docs: `docs/architecture.md` (Stats use case section, `stats` CLI bullet, `require_init` and `_open_adapters` lists, callers of `app/cost.py` and `Runs.all_runs`), `CHANGELOG.md`, `docs/decisions.md` (one row for the four answers), `docs/progress.md`.
