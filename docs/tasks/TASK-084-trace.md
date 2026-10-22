# TASK-084: `trace` use case and command

- Milestone: M5
- Status: done
- Tests: acceptance
- ADR: ADR-018 (accepted) covers the `Traces` port and its `requirement_trace` read, which this task only calls. ADR-011 (accepted) makes `cli.py` the composition root. The task adds no port, adapter, dependency, event type, payload, storage schema or convention, so no new ADR is needed. Design choices 1 to 3 are rows in `docs/decisions.md`.
- Spec impact: wording (F-6, already in progress.md "Later"; see Spec gaps)
- Spec sections (spec v1.17; SC-131):
  - "CLI commands" table row: "`openfactory trace REQ-ID` | Requirement to code and tests".
  - "Traceability" › "Queries": "`openfactory trace REQ-AUTH-001`: requirement → tasks → commits → files and tests, both the tests tagged with the requirement and the tests in those files."
  - "CLI commands" › "Output": "`trace REQ-ID` prints `task  <task id>  <state>` for each task linked to the requirement; then `commit  <sha>  <task id>` for each commit of those tasks, by task id, then sha; then `file  <path>` for each file of those commits, once; then `test  <node id>  tagged` for each test tagged with the requirement and `test  <node id>  file` for each other test whose file is one of those files, by node id. It exits 0, also when it prints nothing. It refuses with `unknown requirement <ID>` and exits 1 when no approved spec version has the requirement."
  - "CLI commands" › "Output": "`trace`, `why` and `coverage` record no events and do not repair the plan. Their lines separate fields by exactly two spaces; groups come in the order given, and each group is sorted as strings."
  - "CLI commands" › "Output": "Failure messages (... "run `openfactory init` first", the refusals of ... `trace` ...) ... go to standard error"; "A command that fails exits 1".
  - "CLI commands" › "Other commands": "fail with "run `openfactory init` first" if `./.openfactory/` is missing."

## Outline item
M5 outline item 1 in `docs/progress.md`. Depends on TASK-083 (`Traces.requirement_trace`, done) and TASK-082 (`_Adapters.traces`, done).

## Objective
`openfactory trace REQ-ID` prints the requirement's task, commit, file and test lines in the spec's order and exits 0. When no approved spec version has the requirement, it writes `unknown requirement <ID>` to standard error and exits 1.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- New `src/openfactory/app/trace.py`. It imports only `domain` and `ports`.
  - `TraceRefusal(StrEnum)` has one member, `unknown_requirement`.
  - `TraceReport` is frozen with `extra="forbid"`. It holds `refusal: TraceRefusal | None = None` and `trace: RequirementTrace | None = None`.
  - `trace_requirement(requirement_id: str, *, traces: Traces) -> TraceReport` calls `traces.requirement_trace(requirement_id)`. If that returns `None`, the use case refuses. Otherwise it returns the trace as given, already ordered by the adapter (TASK-083 decision 3).
  - No recorder parameter, so it cannot record an event. No `versions` parameter (Design choice 1).
- `src/openfactory/cli.py`:
  - New top-level command `trace` with one positional argument, `requirement_id: str`.
  - Calls `require_init()`, opens `_open_adapters` and calls `trace_requirement(requirement_id, traces=adapters.traces)`. Prints after the adapters are closed.
  - A refusal writes `unknown requirement <ID>` to standard error, `<ID>` exactly as given, and exits 1.
  - Otherwise `_trace_lines(trace: RequirementTrace) -> list[str]` builds, in order: `task  <id>  <state>`, `commit  <sha>  <task id>`, `file  <path>`, then `test  <node id>  tagged|file`. Printed on standard output, exit 0.
- New `tests/unit/test_trace.py`, with a fake `Traces`.
- New `tests/integration/test_cli_trace.py`. Seeds events through `SqliteEventRecorder` (`SpecImported`, `SpecApproved`, `PlanCreated`, `PlanApproved`, `TaskStateChanged`, `CommitRecorded`, `TestsCollected`), as `test_sqlite_traces.py` and `test_cli_coverage.py` do. Drives the Typer app with `CliRunner`.

Out:
- The `why` read and command, the `GitProvider` commit listing and the rebuild, and the M5 close test (M5 outline items 1 to 3 after this task).
- Any change to `Traces`, `SqliteTraces`, `domain/traces.py`, the projector, payloads, `SpecVersions`, `_Adapters` or `_open_adapters`.
- Sharing the `SqliteTraces` subqueries noted in "Later" (belongs to the `why` task).
- Checking the format of the REQ-ID argument. The spec asks only for the "unknown requirement" refusal.

## Acceptance criteria
- [x] **AC1** ("Output", `trace REQ-ID` line order; "exactly two spaces"; "groups come in the order given"):
  - Seed one approved requirement with two linked tasks in different states. One task has two commits. The commits change three files, two commits share one file. One tagged test and one untagged test in a traced file.
  - Standard output is exactly the expected lines: task lines, then commit lines, then file lines (each file once), then test lines.
  - Fields separated by exactly two spaces, no padding. Standard error empty, exit code 0.
- [x] **AC2** ("each group is sorted as strings"; "by task id, then sha"; "by node id"):
  - Commit lines by task id, then sha; data has sha order differing from task-id order across tasks.
  - File lines in string order; test lines in node-id order with `tagged` and `file` kinds interleaved.
  - Data includes values whose string and numeric orders differ, e.g. `test_10` before `test_2`.
- [x] **AC3** ("It exits 0, also when it prints nothing"): a requirement of an approved version with no links prints nothing on stdout or stderr and exits 0.
- [x] **AC4** ("refuses with `unknown requirement <ID>` and exits 1"):
  - Writes exactly `unknown requirement <ID>` to standard error, exits 1, empty stdout, for: an id in no version, and an id only in an imported, unapproved draft.
  - A requirement found only in an older approved version, or deprecated in an approved version, is not refused and exits 0.
- [x] **AC5** ("record no events and do not repair the plan"):
  - Seed a task left in `running` with an unfinished implementer run and a contract link to the requirement.
  - After `trace`, the `events` row count is unchanged and the task is still `running`. Its line reads `task  AUTH-001  running`.
  - The use case takes only `requirement_id` and `traces`. `cli.py`'s `trace` uses no recorder, git, worktree, executor, gate or LLM adapter (an AST check, as in `test_cli_coverage.py`).
- [x] **AC6** ("fail with "run `openfactory init` first""): without `.openfactory/`, `trace REQ-AUTH-001` writes that line to standard error, exits 1 and creates nothing.

## Architecture rules that apply
- `app/trace.py` depends on `domain` and `ports` only, does no I/O and returns data. `cli.py` formats, prints and sets exit codes (ADR-011).
- Output is written after the adapters are closed, as in `status`, `resolve` and `coverage`.

## Plan
1. Create branch `task/TASK-084-trace` from an up-to-date main.
2. Record the human's answers to Design choices 1 to 3.
3. Test-writer: failing tests in `tests/unit/test_trace.py` (refusal on `None`, id passed through, trace returned unchanged, only that read called) and `tests/integration/test_cli_trace.py` (AC1–AC6).
4. Implement `app/trace.py`, then `_trace_lines` and the `trace` command in `cli.py`.
5. Run pytest, ruff, pyright and check_docs until all pass.
6. Docs: `docs/architecture.md` (Trace use case section, `trace` CLI bullet, `require_init()`/`_open_adapters` lists, which commands call `requirement_trace`); `docs/progress.md`; `docs/decisions.md` (one row per Design choice); Outcome.
7. Commit `feat(cli): add the trace command` with trailers `Task: TASK-084`, `Milestone: M5`. Do not push.

## Files expected to change
- `src/openfactory/app/trace.py` (new, ~+35)
- `src/openfactory/cli.py` (~+30)
- `tests/unit/test_trace.py` (new, ~+60)
- `tests/integration/test_cli_trace.py` (new, ~+200)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-084-trace.md`

Not expected to change: `ports/`, `adapters/`, `domain/`, other `app/` modules, any existing test, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: ~330 lines, ~65 in `src/`.

## Design choices to confirm at planning
1. **Use case inputs.** Proposed: `trace_requirement(requirement_id, *, traces)`; the "no approved spec version" check is already in the read (`None`, TASK-083 choice 1). Alternative: also take `versions` for symmetry with `requirement_coverage`; nothing would use it.
2. **Where lines are formatted.** Proposed: `cli.py`, in `_trace_lines(trace)`; the use case returns the domain `RequirementTrace`, as `status` does with `_status_line`. Alternative: use case returns `list[str]`, putting output format in `app` (ADR-011 gives it to `cli.py`).
3. **No second sort.** Use case and `cli.py` keep the adapter's order (TASK-083 choice 3); AC1/AC2 pin it end to end. Alternative: re-sort in `app`; rejected so order is decided in one place, as in TASK-082 choice 2.

## Open questions
None beyond the Design choices.

Answered 2026-10-22: the human approved the plan with Design choices 1 to 3 as proposed (advisor: 3 AGREE).

## Spec gaps
- **"CLI commands" › "Output", "each group is sorted as strings" vs "by task id, then sha" (wording, F-6 of `docs/spec-audits/2026-10-22-proposal-v1.17.md`, already in progress.md "Later").** Literal reading sorts whole lines (sha order for commits); the next line states its own keys. TASK-083 implemented those keys with the human's answer of 2026-10-22; this task only prints that order. Does not block.
- Readings, not gaps:
  1. `<ID>` in `unknown requirement <ID>` is the argument exactly as given; no format check.
  2. "It exits 0, also when it prints nothing" covers an approved requirement with no links (AC3).

## Outcome
- Status: done. New `src/openfactory/app/trace.py` (`TraceRefusal`, `TraceReport`, `trace_requirement`) and, in `src/openfactory/cli.py`, the `trace` command and `_trace_lines`. The command checks `report.trace is None` for the refusal branch so pyright narrows the trace.
- Tests: 13 new (`tests/unit/test_trace.py`, `tests/integration/test_cli_trace.py`), AC1 to AC6. No existing test changed; no test edits by the implementer.
- Checks: full suite 1689 passed; ruff, pyright and check_docs clean.
- Docs: `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md` (one row per Design choice 1 to 3).
- No ADR needed; none drafted.
