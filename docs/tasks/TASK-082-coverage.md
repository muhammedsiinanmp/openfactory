# TASK-082: `coverage` use case and command

- Milestone: M5
- Status: done
- Tests: acceptance
- ADR: ADR-018 (accepted) covers the `Traces` port this task uses. ADR-011 (accepted) makes `cli.py` the composition root. The task adds no port, adapter, dependency, event type, payload, storage schema or convention, so no new ADR is needed. Design choice 1 gets a row in `docs/decisions.md`.
- Spec impact: none
- Spec sections (spec v1.17; SC-130):
  - "Traceability" › "Queries": "`openfactory coverage`: requirements with no passing tagged test. A test in `trace_links` passed: a collection is recorded only for an attempt whose gates all passed."
  - "CLI commands" table row: "`openfactory coverage` | Requirements with no passing tagged test".
  - "CLI commands" › "Output": "`coverage` prints, as its id, each requirement of the latest approved spec version that is not deprecated and has no `test_tag` link from a test, and exits 0; with every requirement covered it prints nothing. With no approved spec version it refuses with `no approved spec version` and exits 1."
  - "CLI commands" › "Output": "`trace`, `why` and `coverage` record no events and do not repair the plan. Their lines separate fields by exactly two spaces; groups come in the order given, and each group is sorted as strings."
  - "CLI commands" › "Output": "Failure messages (... "run `openfactory init` first", the refusals of ... `coverage` ...) ... go to standard error"; "A command that fails exits 1".
  - "CLI commands" › "Other commands": "fail with "run `openfactory init` first" if `./.openfactory/` is missing."
  - "Domain model and storage" › "Ids", M5 paragraph: "The `Traces` port, read-only, whose adapter is `sqlite_traces`, gives the queries of `trace`, `why` and `coverage` ..."

## Outline item
This is M5 outline item 1 in `docs/progress.md`. It depends on TASK-081 (`Traces.untested_requirements`, done).

## Objective
`openfactory coverage` prints, one per line, the id of each requirement of the latest approved spec version that is not deprecated and has no `test_tag` link from a test, and exits 0. With no approved spec version it writes `no approved spec version` to standard error and exits 1.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- New `src/openfactory/app/coverage.py`. It imports only `domain` and `ports`.
  - `requirement_coverage(*, versions: SpecVersions, traces: Traces) -> CoverageReport`.
  - `CoverageReport` is frozen and holds `refusal` (a one-member `CoverageRefusal.no_approved_spec`, or `None`) and `untested: list[str]`.
  - The use case reads `versions.latest_approved()`. If that is `None` it refuses; otherwise it returns `traces.untested_requirements(ref.id)` as given, already sorted by the adapter (TASK-081 decision 3).
  - It has no recorder parameter, so it cannot record an event.
- `src/openfactory/cli.py`:
  - `_Adapters` gains `traces: SqliteTraces`, opened in `_open_adapters` after the recorder (see Design choice 1).
  - New top-level command `coverage`, no arguments. It calls `require_init()`, opens `_open_adapters` and calls `requirement_coverage(versions=adapters.versions, traces=adapters.traces)`. It prints after the adapters are closed.
  - A refusal writes `no approved spec version` to standard error and exits 1.
  - Otherwise it prints one id per line on standard output and exits 0.
- New `tests/unit/test_coverage.py`, with fake `SpecVersions` and `Traces`.
- New `tests/integration/test_cli_coverage.py`. It seeds events through `SqliteEventRecorder` (`SpecImported`, `SpecApproved`, `TestsCollected`) and drives the Typer app with `CliRunner`, as `test_cli_status.py` does.

Out:
- The `trace` and `why` reads and commands (outline items 2 and 3).
- The `GitProvider` commit listing and the rebuild from git (item 4), and the M5 close test (item 5).
- Any change to `Traces`, `SqliteTraces`, the projector, payloads, `SpecVersions` or `domain/`.

## Acceptance criteria
- [ ] **AC1** ("Output", `coverage`: "prints, as its id, each requirement of the latest approved spec version that is not deprecated and has no `test_tag` link from a test, and exits 0"):
  - Seed an approved version with three requirements, one deprecated, and a `TestsCollected` that tags one of the other two.
  - `coverage` prints exactly the one untagged, non-deprecated id on standard output.
  - Standard error is empty and the exit code is 0.
- [ ] **AC2** (same bullet: "with every requirement covered it prints nothing"): when every non-deprecated requirement is tagged, standard output is empty and the exit code is 0.
- [ ] **AC3** (same bullet: "of the latest approved spec version"; "each group is sorted as strings"):
  - With `sv_01` and `sv_02` approved and holding different requirements, only `sv_02`'s untagged ids are printed.
  - The ids come in string order. The data must include ids whose numeric and string orders differ, for example `REQ-A-10` before `REQ-A-2`.
  - A draft (imported, not approved) version after `sv_02` does not change the output.
- [ ] **AC4** (same bullet: "With no approved spec version it refuses with `no approved spec version` and exits 1"; refusals go to standard error):
  - In an initialised repo with no approved version (none at all, or only an imported draft), `coverage` writes exactly `no approved spec version` to standard error.
  - Standard output is empty and the exit code is 1.
- [ ] **AC5** ("`trace`, `why` and `coverage` record no events and do not repair the plan"):
  - Seed a task left in `running` with an unfinished implementer run.
  - After `coverage`, the `events` table's row count is unchanged and the task is still `running`.
  - The use case takes only `versions` and `traces`. `cli.py`'s `coverage` builds no git, worktree, executor, gate or LLM adapter.
- [ ] **AC6** ("Other commands": "fail with "run `openfactory init` first" if `./.openfactory/` is missing"): in a directory without `.openfactory/`, `coverage` writes that line to standard error and exits 1.

## Architecture rules that apply
- `app/coverage.py` depends on `domain` and `ports` only, does no I/O and returns data. `cli.py` prints and sets exit codes (ADR-011).
- Output is written after the adapters are closed, as in `status` and `resolve`.

## Plan
1. Create branch `task/TASK-082-coverage` from an up-to-date main.
2. Get the human's answers to Design choices 1 and 2 and record them here.
3. Test-writer: write failing tests.
   - `tests/unit/test_coverage.py`: the refusal, passing the latest approved id to `untested_requirements`, the result returned unchanged, and only reads called.
   - `tests/integration/test_cli_coverage.py`: AC1 to AC6.
4. Implement `app/coverage.py`, then the `traces` field in `_Adapters` and the `coverage` command in `cli.py`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`: a new "Coverage use case" section; a `coverage` bullet under "CLI"; `coverage` added to the `require_init()` and `_open_adapters` lists; `SqliteTraces` added to `_Adapters`; the "nothing calls it yet" sentence about `Traces` updated.
   - `docs/progress.md`: Current, a Done line, and item 1 removed from the outline (renumbering the rest).
   - `docs/decisions.md`: one row for Design choice 1.
   - Fill in the Outcome.
7. Commit `feat(cli): add the coverage command` with the trailers `Task: TASK-082` and `Milestone: M5`. Do not push.

## Files expected to change
- `src/openfactory/app/coverage.py` (new, about +35)
- `src/openfactory/cli.py` (about +25)
- `tests/unit/test_coverage.py` (new, about +70)
- `tests/integration/test_cli_coverage.py` (new, about +150)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-082-coverage.md` (this record)

Not expected to change: `ports/`, `adapters/`, `domain/`, other `app/` modules, any existing test, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 280 lines, about 60 of them in `src/`.

## Design choices to confirm at planning
1. **Where `SqliteTraces` is opened.**
   - Proposed: add `traces: SqliteTraces` to `_Adapters` and open it in `_open_adapters` after the recorder. The recorder creates the tables and catches up the projections (ADR-010). `trace` and `why` (items 2 and 3) then reuse it.
   - Alternative: open `SqliteTraces` only inside `coverage`, after `_open_adapters`. Other commands keep their current connections, but each traces command repeats the wiring.
   - Consequence of the proposed choice: every command that uses `_open_adapters` opens one more read connection. No test constructs `_Adapters` directly (the only call is `cli.py:104`), so no test edit follows.
2. **Sorting.** The use case does not sort again; it relies on the adapter's `ORDER BY id` (TASK-081 decision 3). AC3 pins the order end to end through the CLI. The alternative is a `sorted()` in the use case, which pins "sorted as strings" in `app` as `status` does (TASK-077 choice 3). Recommendation: keep TASK-081's decision, so the order is not decided in two places.

## Answers at planning (2026-10-22)
1. Accepted as proposed: `traces: SqliteTraces` is a field of `_Adapters`, opened in `_open_adapters` after the recorder.
2. Accepted as proposed: the use case does not sort again; the adapter's `ORDER BY id` gives string order, pinned end to end by AC3.

## Open questions
None.

## Spec gaps
None. Two readings, not gaps:
- "no approved spec version" is the same refusal text `plan` uses. The two refusals are separate, one per use case, and do not share an enum.
- The F-6 wording item in Later ("each group is sorted as strings" against the keys `trace` and `why` name) does not affect `coverage`, which prints a single group of ids.

## Outcome
- New `src/openfactory/app/coverage.py` (`CoverageRefusal`, frozen `CoverageReport`, `requirement_coverage`); it imports only `domain` and `ports` and takes no recorder.
- `cli.py`: `_Adapters.traces: SqliteTraces` opened after the recorder, and the `coverage` command (design choices 1 and 2 as answered; no second sort).
- Tests: `tests/unit/test_coverage.py` (4) and `tests/integration/test_cli_coverage.py` (7) cover AC1 to AC6. No test edits were made by the implementer.
- Docs: `docs/architecture.md`, `docs/progress.md` and a row in `docs/decisions.md` for design choice 1. No ADR needed.
- Full suite: 1659 passed.
