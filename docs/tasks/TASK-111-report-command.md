# TASK-111: `report` command

- Milestone: M7
- Status: done
- Branch: `task/TASK-111-report-command`
- Tests: acceptance
- ADR: ADR-011 (accepted), ADR-018 (accepted) and ADR-020 (accepted). No new ADR is needed.
  - ADR-011: `cli.py` is the composition root. It formats, prints and sets exit codes.
  - ADR-018: the `Traces` read and `RequirementTrace`. The `report` blocks reuse the `trace` lines.
  - ADR-020: "No new port … `report` reads the links through `Traces`"; "`report` lists approved plans only, so its rows do not double-count."
  - The task adds no port, adapter, event type, payload field, table, dependency or convention. The answers to the open questions (the Markdown layout) go in one row of `docs/decisions.md`.
- Spec impact: wording (see Spec gaps). The meaning is clear. The exact Markdown text is not fully given, and the four "Spec wording" lines TASK-110 left under "Later" in `docs/progress.md` apply here.
- Spec sections (spec v1.20):
  - "CLI commands" table row: "`openfactory report` | Final traceability report as Markdown".
  - "CLI commands" › "Output", `report` bullet (SC-205), quoted in full in TASK-110. In short: "`report` prints Markdown on standard output: the line `# OpenFactory report`; a line `plan <plan id> · spec <spec version id>` … `## Requirements`, then … a heading `### <id>  <title>`, with ` (deprecated)` … and a fenced block holding the lines `trace <id>` prints (empty when it prints none); then `## Cost`, a table `| Plan | Kind | Runs | Tokens in | Tokens out | Cost USD |` … then a row `total` with the sums of the rows above. It records no events, does not repair the plan, and exits 0. With no approved plan it refuses with `no approved plan` on standard error and exits 1."
  - "CLI commands" › "Output", output-stream bullet (SC-216): "Command results (… `stats` lines and the `report` text) go to standard output. Failure messages (… the refusals of … `report` …) … go to standard error."
  - "CLI commands" › "Output", `trace` bullet: "prints `task  <task id>  <state>` for each task linked to the requirement (a requirement is linked to a task by a requirement → task `contract` link, whatever its spec version or `deprecated`); then `commit  <sha>  <task id>` for each commit of those tasks …".
  - "CLI commands" › "Other commands": fail with "run `openfactory init` first" if `./.openfactory/` is missing.
  - "Metrics": "The final report includes total cost of the initial build and of the replan, which shows the saving from re-executing only impacted work (see `report` under CLI commands)."
  - "Milestones and definition of done", item 7: "Eval suite with results, `stats`, `report`, …".

## Outline item
This is M7 outline item 4b in `docs/progress.md`: "`report` command: the Markdown, the per-requirement `trace` blocks, the cost table with its `total` row, the `no approved plan` refusal; covers `trace` after a supersede (Later, TASK-106) (SC-205, SC-216)".

It wires `build_report` (TASK-110). It also closes the Later line "TASK-106: `trace` after a supersede (an invalidated task and its replacement) has no end-to-end check yet; for M7's `report` task".

## Objective
`openfactory report` calls `build_report` and prints its result as the Markdown the spec's `report` bullet gives, on standard output. On refusal it writes `no approved plan` to standard error and exits 1. A CLI-level test also covers `trace` and `report` after a replan has superseded the build plan.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/cli.py`:
  - A new top-level `report` command with no arguments. It calls `require_init()`, then opens `_open_adapters(database)` together with `closing(SqliteEventStore(database))`, as `stats` does. It calls `build_report(plans=, versions=, traces=, runs=, events=)` and prints after the adapters are closed.
  - A private `_report_lines(report: Report) -> list[str]` that builds the Markdown. It reuses `_trace_lines` for each fenced block, and a cost-row formatter that uses the `stats` number format.
- New `tests/integration/test_cli_report.py`. It seeds events through `SqliteEventRecorder`, so the real projector (including the TASK-097 supersede) builds the tables, and drives the Typer app with `CliRunner`, as `test_cli_trace.py` and `test_cli_stats.py` do.

Out:
- Any change to `app/report.py`, `app/cost.py`, `app/trace.py`, `domain/`, `ports/`, `adapters/`, the projector, payloads, tables or events.
- Any edit to `test_m6_close.py` or other existing tests.
- Eval (item 5) and the demo (item 6).

## Acceptance criteria
- [x] **AC1** ("Output", `report` bullet: "With no approved plan it refuses with `no approved plan` on standard error and exits 1"; "Other commands": "run `openfactory init` first")
  - In an initialised repo with an approved spec version and only a draft plan, `report` writes exactly `no approved plan` to standard error, prints nothing on standard output and exits 1.
  - In a directory without `.openfactory/`, it writes "run `openfactory init` first" to standard error and exits 1.
- [x] **AC2** ("Output", `report` bullet: "the line `# OpenFactory report`; a line `plan <plan id> · spec <spec version id>` for the approved plan and the latest approved spec version"; output-stream bullet: "the `report` text … go[es] to standard output")
  - With an approved plan, standard output starts with `# OpenFactory report`, then the line `plan <plan id> · spec <spec version id>`. The separator is U+00B7 with one space on each side.
  - Standard error is empty and the exit code is 0.
  - When `sv_02` is approved but no replan has been made yet, the line is `plan plan_01 · spec sv_02`.
- [x] **AC3** ("Output", `report` bullet: "`## Requirements`, then, for each requirement of the latest approved version in ascending id as strings, a heading `### <id>  <title>`, with ` (deprecated)` after the title when it is deprecated, and a fenced block holding the lines `trace <id>` prints (empty when it prints none)")
  - `## Requirements` is followed by one `### <id>  <title>` heading per requirement of the latest approved version, in ascending id as strings. `REQ-AUTH-010` comes after `REQ-AUTH-002`.
  - A deprecated requirement's heading ends in ` (deprecated)`.
  - A requirement found only in an older version has no heading.
  - Each heading is followed by a fenced block whose lines equal, line for line, the standard output of `openfactory trace <id>` on the same database.
  - A requirement with no links gets an empty block: the opening fence directly followed by the closing fence (see Open question 4).
- [x] **AC4** ("Output", `report` bullet: "then `## Cost`, a table `| Plan | Kind | Runs | Tokens in | Tokens out | Cost USD |` with one row per plan that has a `PlanApproved`, in ascending plan id as strings, `Kind` `build` for the first and `replan` for the others and the plan's figures as for `stats`, then a row `total` with the sums of the rows above"; "Metrics": "total cost of the initial build and of the replan")
  - After the requirements comes `## Cost`, then the header row exactly as the spec gives it, then the separator row (Open question 2).
  - There is one row per approved plan in ascending id, `build` first and then `replan`. A draft-only plan has no row.
  - `Runs`, `Tokens in` and `Tokens out` are integers, and `Cost USD` has four decimals, as in the `stats` `plan` line for the same plan.
  - The last row is `total` with the column sums (Open questions 1 and 3).
  - With an approved plan and no run, the build row and the `total` row show `0`, `0`, `0` and `0.0000`.
- [x] **AC5** (TASK-106 Later line; `trace` bullet: "a requirement is linked to a task by a requirement → task `contract` link, whatever its spec version"; `report` bullet)
  - Seed this sequence:
    1. Build `plan_01` with `AUTH-001` and `AUTH-002` for `REQ-AUTH-001`, and a commit for each.
    2. Approve `sv_02`, then record `ImpactComputed` and `plan_02` (`AUTH-004` for `REQ-AUTH-001`).
    3. Record `PlanApproved` for `plan_02`, which supersedes `plan_01`.
    4. Move `AUTH-002` to `invalidated`, then give `AUTH-004` a commit and move it to `passed`.
  - `trace REQ-AUTH-001` then prints `task  AUTH-002  invalidated` beside the `AUTH-001` and `AUTH-004` task lines, and the commits of all three tasks.
  - The report's `REQ-AUTH-001` block holds exactly those lines.
  - The plan line reads `plan plan_02 · spec sv_02`.
  - The cost table has `plan_01 | build` and `plan_02 | replan` rows. The `total` row equals their sums.
- [x] **AC6** ("Output", `report` bullet: "It records no events, does not repair the plan, and exits 0"; CLAUDE.md architecture rules; ADR-011)
  - Seed a task left `running` with an unfinished implementer run, as after a killed `run`. `report` exits 0, and afterwards:
    - the `events` row count is unchanged;
    - the task is still `running`;
    - its run is still unfinished.
  - Under `src/`, only `cli.py` changes.
  - The full suite passes, and no existing test is edited.

## Architecture rules that apply
- `cli.py` formats, prints and sets exit codes (ADR-011). Sorting and sums stay in `build_report` (TASK-110 answer 1).
- Reads only. The recorder catch-up in `_open_adapters` writes projections but never an event, as for `status` and `stats`.

## Plan
1. Create branch `task/TASK-111-report-command` from an up-to-date main.
2. Record the human's answers to the open questions in this record.
3. Test-writer: write failing tests in `tests/integration/test_cli_report.py` for AC1 to AC6. Pin the full expected stdout for at least one fixture, using the answered layout.
4. Implement the `report` command and `_report_lines` in `cli.py`. Reuse `_trace_lines`, with numbers formatted as `_figures_line` does (integers, `:.4f`).
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`: a `report` CLI bullet; `report` added to the `require_init()` and `_open_adapters` lists; the "still to come (TASK-111)" sentences in the Report use case and `app/cost.py` sections.
   - `CHANGELOG.md`: an `[Unreleased]` line for `openfactory report`.
   - `docs/decisions.md`: one row for the answers.
   - `docs/progress.md`:
     - Current;
     - a Done line;
     - item 4b ticked;
     - mark the four TASK-110 "Spec wording" Later lines as answered in TASK-111 (they stay until the next `/spec-change`);
     - remove the TASK-106 `trace`-after-supersede Later line.
   - This record's Outcome.
7. Commit `feat(cli): add the report command` with trailers `Task: TASK-111` and `Milestone: M7`. Do not push.

## Files expected to change
- `src/openfactory/cli.py` (about +45)
- `tests/integration/test_cli_report.py` (new, about +250)
- `docs/architecture.md`, `docs/decisions.md`, `docs/progress.md`, `CHANGELOG.md`, this record

Not expected to change: `app/`, `domain/`, `ports/`, `adapters/`, `docs/spec/`, `docs/adr/`, any existing test.

Expected size: about 300 lines, about 45 of them under `src/`.

## Open questions (each with a proposed answer)
1. **The `total` row's cells.** Proposed: `Plan` is `total` and `Kind` is empty: `| total |  | <runs> | <in> | <out> | <cost> |`. Alternative: `-` in the `Kind` cell, as `status` and `impact` use `-` for "none".
2. **Table separator row.** The spec gives no separator row, but Markdown needs one for a table. Proposed: `| --- | --- | --- | --- | --- | --- |` right after the header. Cells have one space of padding on each side, with no column alignment.
3. **Number format.** "The plan's figures as for `stats`" is read as the `stats` format too: `Runs` and tokens as integers, `Cost USD` with four decimals (`:.4f`), also in the `total` row. No duration column is printed.
4. **Fences and blank lines.** Proposed:
   - Plain ```` ``` ```` fences with no info string.
   - An empty block is the opening fence directly followed by the closing fence.
   - One blank line separates each of these: the title, the plan line, `## Requirements`, each `###` heading, each fenced block, `## Cost` and the table.
   - The table rows are contiguous.
   - The output ends with a single line break after the `total` row.
   - No escaping of `|` or backticks in titles or trace lines, since the spec asks for none.
5. **How AC5 is set up.** Proposed: seed the events through `SqliteEventRecorder` in the new test file, so the real projector's `PlanApproved` supersede runs. Alternative: add tests to `tests/integration/test_m6_close.py` on the real replan flow. That is heavier, and it touches a file the reviewer would have to check for edits.

## Answers (human, 2026-10-25)
All five proposed answers accepted as written above. For Q5, the seeded `PlanCreated`/`PlanApproved`/`ImpactComputed` `causation_id` chain follows what the real use cases record (advisor note).

## Spec gaps
Spec impact is "wording". None of these blocks the task: the meaning is clear and the answers above settle the exact text. They were recorded under "Later" by the TASK-110 planner, for this task.
- "CLI commands" › "Output", `report` bullet: the `total` row gives no value for its `Kind` cell (Open question 1).
- Same bullet: the exact Markdown layout is not given: the blank lines, the table's separator row, the fence form (Open questions 2 and 4).
- Same bullet: "the plan's figures as for `stats`" does not say outright that the `stats` number format applies, including to the `total` row (Open question 3).
- Same bullet: "a fenced block … (empty when it prints none)" does not say whether an empty block holds a blank line (Open question 4).

## Outcome
All six acceptance criteria are met.
- `src/openfactory/cli.py`: new `report` command, `_report_lines` and `_cost_row`. It reuses `_trace_lines` and the `stats` number format. Nothing else changed under `src/`.
- `tests/integration/test_cli_report.py`: 8 tests, covering AC1 to AC6 (AC5 seeded through `SqliteEventRecorder`).
- Full suite: 2146 tests pass.
- Test edits: none. No mechanical test fixes were needed.
- The five answers are recorded in one row of `docs/decisions.md`. No ADR was needed.
