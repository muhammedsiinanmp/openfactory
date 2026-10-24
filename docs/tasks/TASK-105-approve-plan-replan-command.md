# TASK-105: `approve plan` command output after a replan

- Milestone: M6
- Status: done
- Tests: acceptance
- ADR: ADR-019 (accepted, with its 2026-10-24 amendment) and ADR-011 (accepted).
  - ADR-019's "Invalidation at approval" covers what `approve plan` does after a replan. TASK-104 built that into the use case.
  - ADR-011 makes `cli.py` the composition root, which formats and prints.
  - This task only formats the `ApprovePlanResult` that TASK-104 already returns. It adds no port, adapter, event type, payload or schema change, dependency or convention, so no new ADR is needed. Each answered Design choice becomes a row in `docs/decisions.md`.
- Spec impact: none (see Spec gaps: readings only)
- Spec sections (spec v1.19; SC-165, SC-176, SC-191, SC-192):
  - "CLI commands" › "Output", the `approve plan` bullet: "`approve plan` prints one line per task it invalidated as `task_id  invalidated`, then one line per task made ready as `task_id  ready`, each in ascending task id as strings, then the status line `approved plan_NN`, and exits 0. It refuses with one line on standard error and exits 1, checked in this order: `no draft plan`; `plan_NN was made for sv_NN; run openfactory replan` when the draft's spec version is not the latest approved one and an approved plan exists, or `plan_NN was made for sv_NN; run openfactory plan` when none does; `<task id> is <state>; run openfactory run first` when a task it would invalidate is `running` or `gating`, naming the lowest such task id as strings."
  - "CLI commands", table row: "`openfactory approve plan` | Marks the latest draft plan approved; after a replan, invalidates the impacted tasks; `pending` tasks whose dependencies have passed become `ready`".
  - "Spec diff and impact analysis" › "Approving a replan": "reads, through the `EventStore` port, the latest `ImpactComputed` recorded before the draft's `PlanCreated` whose `from_version` is the approved plan's spec version and whose `to_version` is the draft's. … It records `PlanApproved`, and the projector supersedes the earlier plan and moves its tasks into the new one … records `TaskStateChanged` to `invalidated`, with reason `spec change <to_version>` … Untouched tasks keep their state and commits."
  - "Domain model and storage" › "Streams and actors": "`approve plan` records `PlanApproved`, with no `causation_id`, then, after a replan, one `TaskStateChanged` to `invalidated` per task it invalidates …, then one `TaskStateChanged` to `ready` per `pending` task whose dependencies have all passed …, each group in ascending task id as strings, each pointing at `PlanApproved`."
  - "Event envelope rules" (SC-191): "Between events, 'latest', 'earlier', 'before' and 'after' compare `seq`."
  - "CLI commands" › "Output": "Command results (… status lines; task … lines …) go to standard output. Failure messages (… the refusals of … `approve plan` …) … go to standard error"; "A command that fails exits 1".

## Outline item
M6 outline item 7b in `docs/progress.md`.
- It depends on TASK-104 (7a, done).
- Item 8, the M6 close integration test, comes next.

## Objective
`openfactory approve plan` prints the `invalidated` lines, then the `ready` lines, then `approved plan_NN`. It writes the right stale-draft line and the `run openfactory run first` line. A test on a real database shows the whole replan approval working end to end.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/cli.py`, `approve_plan_command`:
  - On `approved`, print one `task_id  invalidated` line per id in `result.invalidated`, then the existing `task_id  ready` lines, then `approved <plan_id>`.
  - Map the refusals in a new `_approve_plan_refusal_line(result) -> str` (Design choice 1):
    - `no_draft` gives `no draft plan`;
    - `stale_draft` gives `<plan_id> was made for <spec_version>; run openfactory replan` when `approved_plan_exists`, else `…; run openfactory plan`;
    - `task_busy` gives `<task_id> is <state>; run openfactory run first`.

    The line goes to standard error with exit 1.
  - Fix the docstring, which today says only tasks with no dependencies become ready (closes the TASK-104 Later line).
- New `tests/integration/test_cli_approve_plan_replan.py` (Design choice 2):
  - It drives the Typer app with `CliRunner` in a `tmp_path` git repo.
  - It seeds through `SqliteEventRecorder`, with the seeding helpers copied (not imported) from `tests/integration/test_cli_replan.py`:
    - `sv_01` and `sv_02` approved;
    - `plan_01` approved on `sv_01`: AUTH-001 `passed` and untouched; AUTH-002 `passed` and impacted; AUTH-003 `pending`, downstream, depending on AUTH-002;
    - `ImpactComputed` events on `spec:sv_02`;
    - a draft `plan_02` on `sv_02`: AUTH-004 depends on AUTH-001; AUTH-005 depends on AUTH-004.
  - No stand-in `claude` or `git` is needed, because `approve plan` makes no LLM or git call.

Out:
- Any change under `app/`, `domain/`, `ports/` or `adapters/`.
- Any edit to existing tests. `tests/integration/test_cli_approve_plan.py` must pass unchanged.
- The M6 close test (item 8).
- Open Later items stay open:
  - the TASK-094 traversal "another plan" test;
  - the TASK-104 unit-coverage gaps;
  - the stale `test_ac5_takes_exactly_the_three_ports` name;
  - the missing-`ImpactComputed` gap;
  - the second-replan and deletion-only gaps;
  - F-16.

## Acceptance criteria
- [x] **AC1** ("Output", `approve plan`: "prints one line per task it invalidated as `task_id  invalidated`, then one line per task made ready as `task_id  ready`, each in ascending task id as strings, then the status line `approved plan_NN`, and exits 0"):
  - On the fixture, standard output is exactly these lines, in this order:
    1. `AUTH-002  invalidated`
    2. `AUTH-003  invalidated`
    3. `AUTH-004  ready`
    4. `approved plan_02`
  - Standard error is empty and the exit code is 0.
- [x] **AC2** ("Streams and actors": "`PlanApproved`, with no `causation_id`, then … `invalidated` … then … `ready` …, each pointing at `PlanApproved`"; "Approving a replan": "the projector supersedes the earlier plan and moves its tasks into the new one"; "Untouched tasks keep their state"):
  - **Events, in `seq` order:**
    - `PlanApproved` on `plan:plan_02`, actor `human`, null `causation_id`;
    - `TaskStateChanged` to `invalidated` for AUTH-002 (from `passed`) and AUTH-003 (from `pending`), reason `spec change sv_02`;
    - `pending` to `ready` for AUTH-004, reason null.

    The three task events have actor `orchestrator` and `causation_id` the `PlanApproved` event id.
  - **Projections:**
    - `plans`: `plan_01` is `superseded` and `plan_02` is `approved`;
    - every task has `plan_id` `plan_02`;
    - AUTH-001 is `passed`, AUTH-005 is `pending`, AUTH-002 and AUTH-003 are `invalidated`, AUTH-004 is `ready`.
- [x] **AC3** ("Approving a replan": "the latest `ImpactComputed` recorded before the draft's `PlanCreated` whose `from_version` is the approved plan's spec version"; "Event envelope rules": "'latest' … 'before' … compare `seq`"):
  - On the real event store, `spec:sv_02` holds three `ImpactComputed` events:
    - one recorded before `plan_02`'s `PlanCreated`, from `sv_01`, listing AUTH-002 and downstream AUTH-003;
    - one recorded before it, from `sv_00`, listing AUTH-001;
    - one recorded after it, from `sv_01`, listing AUTH-001.
  - Only AUTH-002 and AUTH-003 are printed as `invalidated`, and AUTH-001 stays `passed`.
- [x] **AC4** ("Output", `approve plan`: "`plan_NN was made for sv_NN; run openfactory replan` when the draft's spec version is not the latest approved one and an approved plan exists"):
  - With `plan_01` approved, draft `plan_02` on `sv_02` and then `sv_03` approved, standard error is exactly `plan_02 was made for sv_02; run openfactory replan`.
  - Standard output is empty, the exit code is 1 and the `events` row count is unchanged.
  - The no-approved-plan variant (`… run openfactory plan`) keeps passing in the unchanged `test_cli_approve_plan.py::test_ac4_stale_draft_is_refused`.
- [x] **AC5** ("Output", `approve plan`: "`<task id> is <state>; run openfactory run first` when a task it would invalidate is `running` or `gating`, naming the lowest such task id as strings"):
  - This is parametrized over `running` and `gating`.
  - With downstream AUTH-003 seeded through `ready` into that state, standard error is exactly `AUTH-003 is <state>; run openfactory run first`.
  - Standard output is empty, the exit code is 1, the `events` row count is unchanged and `plan_02` is still `draft`.
- [x] **AC6** (ADR-011; "Output", `approve plan` for a first plan, unchanged):
  - `tests/integration/test_cli_approve_plan.py` and every other existing test pass without edits.
  - Nothing under `src/openfactory/app`, `domain`, `ports` or `adapters` changes. This is a review check on the diff, not a test, as in TASK-103.

## Architecture rules that apply
- `cli.py` wires, formats, prints and sets exit codes (ADR-011). The use case returns data.
- `cli.py` records nothing itself. `SqliteEventStore` stays opened for reading only.

## Plan
1. Create branch `task/TASK-105-approve-plan-replan-command` from an up-to-date main.
2. Record the human's answers to the Design choices and Open questions in this record.
3. Test-writer: write failing `test_task105_ac<N>_…` tests in the new `tests/integration/test_cli_approve_plan_replan.py`.
4. Implement the `invalidated` lines, `_approve_plan_refusal_line` and the docstring fix in `cli.py`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`: line 237, the `approve plan` CLI bullet. It now says `approve_plan(versions, plans, recorder)` and lists only the ready and old stale lines; add `events=store`, the `invalidated` lines and the three refusal lines.
   - `docs/progress.md`: Current, a Done line, item 7b marked done, and the second TASK-104 Later line removed.
   - `docs/decisions.md`: one row per Design choice.
   - `CHANGELOG.md`: the `[Unreleased]` `approve plan` entry (Design choice 3).
   - This record's Outcome.
7. Commit `feat(cli): print invalidated tasks and replan refusals in approve plan` with the trailers `Task: TASK-105` and `Milestone: M6`. Do not push.

## Files expected to change
- `src/openfactory/cli.py` (about +20)
- `tests/integration/test_cli_approve_plan_replan.py` (new, about +260, most of it copied seeding helpers)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, `CHANGELOG.md`, this record

Not expected to change: `app/`, `domain/`, `ports/`, `adapters/`, any existing test, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 300 lines, about 20 of them in `src/`.

## Design choices to confirm at planning
1. **Refusal-line mapping.**
   - Proposed: a private `_approve_plan_refusal_line(result: ApprovePlanResult) -> str` covering `no_draft`, `stale_draft` and `task_busy`, ending in `assert_never` on the refusal outcomes. This follows `_replan_refusal_line` and `_run_refusal_line`.
   - **Answer (human, 2026-10-24):** accepted, amended: `ApprovePlanOutcome` also holds `approved`, so the mapper handles `ApprovePlanOutcome.approved` with an explicit branch that raises `AssertionError` before `assert_never`, so pyright narrows the enum.
   - Alternative: keep the inline `if` branches in `approve_plan_command` and add a third one.
2. **Test location.**
   - Proposed: a new `tests/integration/test_cli_approve_plan_replan.py` with the seeding helpers copied from `test_cli_replan.py`, so no existing test file is touched.
   - Alternative: add the tests to `test_cli_approve_plan.py`. That means touching a file whose tests are fixed.
   - **Answer (human, 2026-10-24):** accepted as proposed.
3. **CHANGELOG.**
   - Proposed: rewrite the existing `[Unreleased]` `approve plan` entry to name the `invalidated` lines and the `replan` and `run first` refusals.
   - Alternative: leave CHANGELOG to the M6 release.
   - **Answer (human, 2026-10-24):** accepted as proposed.

## Spec gaps
None blocking; Spec impact is none. These are readings:
1. **`sv_NN` in the stale lines** is the draft's spec version, as today, which fits "`plan_NN` was made for `sv_NN`".
2. **The `run openfactory run first` refusal and events.** The bullet does not say "before any event". `approve_plan` already records nothing on `task_busy`, and AC5 asserts that as observed behaviour.
3. **"Untouched tasks keep their … commits".** This is not checked at the CLI level, because the fixture seeds no commits and the projector's move changes only `tasks.plan_id` (TASK-097). Item 8 covers it on a real run.

## Open questions
1. Do you accept Design choices 1 to 3 as proposed?
2. Should AC2 also seed a `CommitRecorded` for AUTH-001 and assert its `commits` row is unchanged, to check "keep their … commits" here rather than leave it to item 8? It adds about 15 lines.
   - **Answer (human, 2026-10-24):** no; left to item 8. The M6 outline's item 8 line in `docs/progress.md` now names "Untouched tasks keep their state and commits" so its planner checks it.

## Outcome

- `approve_plan_command` in `src/openfactory/cli.py` prints the `task_id  invalidated` lines, then the `ready` lines, then `approved <plan_id>`. Refusals go through the new `_approve_plan_refusal_line` (`no draft plan`; the stale draft line naming `replan` when an approved plan exists, else `plan`; `<task id> is <state>; run openfactory run first`), with an explicit `approved` branch before `assert_never`. The docstring is fixed.
- New `tests/integration/test_cli_approve_plan_replan.py` covers AC1 to AC5 on a real database. AC6 is a review check: nothing under `app/`, `domain/`, `ports/` or `adapters/` changed.
- Design choices 1 to 3 and Open question 2 are recorded in `docs/decisions.md`; the commits check stays with item 8.
- Test edits: none.
- Checks: 2071 passed; ruff, pyright and `check_docs` clean.
- Docs updated: `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, `CHANGELOG.md`.
