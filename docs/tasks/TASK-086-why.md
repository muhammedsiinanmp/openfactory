# TASK-086: `why` use case and command

- Milestone: M5
- Status: done
- Tests: acceptance
- ADR: ADR-018 (accepted) covers the `Traces` port and its `file_trace` read, which this task only calls. ADR-011 (accepted) makes `cli.py` the composition root. The task adds no port, adapter, dependency, event type, payload, storage schema or convention, so no new ADR is needed. Design choices 1 to 3 go in `docs/decisions.md`, one row each.
- Spec impact: wording (F-6, already in progress.md "Later"; see Spec gaps)
- Spec sections (spec v1.17; SC-131):
  - "CLI commands" table row: "`openfactory why PATH` | File to requirements and ADRs".
  - "Traceability" › "Queries": "`openfactory why app/auth/login.py`: file → commits → tasks → requirements and ADRs; the ADRs are those of the latest approved spec version."
  - "CLI commands" › "Output": "`why PATH` compares PATH as a string with the files of `trace_links` (relative to the repo root, `/` separators, no normalisation). It prints `commit  <sha>  <task id>` for each commit that changed the file, by task id, then sha; then `task  <task id>  <state>` for each of their tasks; then `requirement  <id>` for each requirement linked to those tasks; then `adr  <id>` for each ADR those requirements are constrained by in the latest approved spec version; and exits 0. It refuses with `no commit changed <PATH>` and exits 1."
  - "CLI commands" › "Output": "`trace`, `why` and `coverage` record no events and do not repair the plan. Their lines separate fields by exactly two spaces; groups come in the order given, and each group is sorted as strings."
  - "CLI commands" › "Output": "Failure messages (... "run `openfactory init` first", the refusals of ... `why` ...) ... go to standard error"; "A command that fails exits 1".
  - "CLI commands" › "Other commands": "fail with "run `openfactory init` first" if `./.openfactory/` is missing."

## Outline item
M5 outline item 1 in `docs/progress.md`, the remaining part: "`why` use case and command (TASK-086)". It depends on TASK-085 (`Traces.file_trace`, done) and TASK-082 (`_Adapters.traces`, done). It is built the way TASK-084 built `trace` on `requirement_trace`.

## Objective
`openfactory why PATH` prints the file's commit, task, requirement and ADR lines in the spec's order and exits 0. When no commit changed PATH, it writes `no commit changed <PATH>` to standard error and exits 1.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- New `src/openfactory/app/why.py`. It imports only `domain`, `ports`, Pydantic and the standard library.
  - `WhyRefusal(StrEnum)` has one member, `no_commit_changed`.
  - `WhyReport` is frozen with `extra="forbid"`. It holds `refusal: WhyRefusal | None = None` and `trace: FileTrace | None = None`.
  - `why_file(path: str, *, traces: Traces) -> WhyReport` calls `traces.file_trace(path)` with `path` unchanged.
    - If that returns `None`, the use case refuses.
    - Otherwise it returns the trace as given, already ordered by the adapter (TASK-085 decision 4).
  - It takes no recorder, so it cannot record an event. It takes no `versions` (Design choice 1).
- `src/openfactory/cli.py`:
  - New top-level command `why` with one positional argument, `path: str`. It is typed `str`, not `pathlib.Path`, so Typer applies no normalisation (Design choice 3).
  - It calls `require_init()`, opens `_open_adapters` and calls `why_file(path, traces=adapters.traces)`. It prints after the adapters are closed.
  - When `report.trace is None`, it writes `no commit changed <PATH>` to standard error, with `<PATH>` exactly as given, and exits 1.
  - Otherwise the new `_why_lines(trace: FileTrace) -> list[str]` builds, in order:
    1. `commit  <sha>  <task id>`
    2. `task  <task id>  <state>`
    3. `requirement  <id>`
    4. `adr  <id>`

    The lines go to standard output and the exit code is 0.
- New `tests/unit/test_why.py`, with a fake `Traces`. It covers:
  - the refusal on `None`;
  - the path passed through unchanged;
  - the trace returned unchanged;
  - only `file_trace` being called.
- New `tests/integration/test_cli_why.py`.
  - It seeds events through `SqliteEventRecorder` (`SpecImported`, `SpecApproved`, `PlanCreated`, `PlanApproved`, `TaskStateChanged`, `CommitRecorded`, `TestsCollected`), as `test_cli_trace.py` does.
  - It drives the Typer app with `CliRunner`.

Out:
- Any change to `Traces`, `SqliteTraces`, `domain/traces.py`, the projector, payloads, `SpecVersions`, `_Adapters`, `_open_adapters` or the `trace` and `coverage` commands.
- The `GitProvider` commit listing and the rebuild (outline item 2). The M5 close test (item 3), including the "Phase 1 is done when" check that every changed file resolves in `why`.
- Validating or normalising PATH. The spec says "no normalisation".

## Acceptance criteria
- [x] **AC1** ("Output", `why PATH` line order; "exactly two spaces"; "groups come in the order given"; "by task id, then sha"):
  - Seed one path changed by commits of two tasks. One task has two commits on the path, and sha order differs from task-id order across the tasks. One task has a later state set by `TaskStateChanged`.
  - Seed requirements so that one is linked to both tasks and one task has two requirements. Seed ADRs on those requirements.
  - Standard output is exactly:
    1. the `commit` lines, by task id then sha;
    2. then the `task` lines, each task once, with its current state;
    3. then the `requirement` lines, each once, sorted as strings;
    4. then the `adr` lines, each once, sorted as strings.
  - Fields are separated by exactly two spaces, with no padding. Standard error is empty and the exit code is 0.
- [x] **AC2** ("Traceability" › "Queries": "the ADRs are those of the latest approved spec version"):
  - Approve `sv_01`, then `sv_02`.
  - An ADR in only `sv_01`'s `constrained_by` for a traced requirement gets no `adr` line.
  - An ADR added in `sv_02` gets an `adr` line.
- [x] **AC3** ("compares PATH as a string … no normalisation"; "refuses with `no commit changed <PATH>` and exits 1"):
  - Each of the following writes exactly `no commit changed <PATH>` to standard error, with PATH as given. Standard output is empty and the exit code is 1:
    - a path no commit changed;
    - `./<changed path>`;
    - a directory prefix of a changed path (`app/` and `app`);
    - a path that is only a test's file.
  - The exact changed path exits 0.
- [x] **AC4** ("record no events and do not repair the plan"):
  - Seed a task left in `running`, with an unfinished implementer run, a commit on the path and a contract link to a requirement.
  - After `why`, the `events` row count is unchanged and the task is still `running`. Its line reads `task  <id>  running`.
  - The use case takes only `path` and `traces`.
  - The `why` command in `cli.py` uses no recorder, git, worktree, executor, gate or LLM adapter. This is an AST check, as in `test_cli_trace.py`.
- [x] **AC5** ("fail with "run `openfactory init` first""): without `.openfactory/`, `why app/auth/login.py` writes that line to standard error, exits 1 and creates nothing.

## Architecture rules that apply
- `app/why.py` depends on `domain` and `ports` only, does no I/O and returns data.
- `cli.py` formats, prints and sets exit codes (ADR-011). Output is written after the adapters are closed, as in `status`, `coverage` and `trace`.

## Plan
1. Create branch `task/TASK-086-why` from an up-to-date main.
2. Record the human's answers to Design choices 1 to 3.
3. Test-writer: write failing tests in `tests/unit/test_why.py` and `tests/integration/test_cli_why.py` (AC1 to AC5).
4. Implement `app/why.py`, then `_why_lines` and the `why` command in `cli.py`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`:
     - a new "Why use case" section;
     - a `why PATH` bullet in the CLI section;
     - `why` added to the `require_init()` list and the `_open_adapters` list;
     - the commands that call `file_trace`.
   - `docs/progress.md`: Current, a Done line, and outline item 1 marked done.
   - `docs/decisions.md`: one row per Design choice.
   - Fill in the Outcome.
7. Commit `feat(cli): add the why command` with the trailers `Task: TASK-086` and `Milestone: M5`. Do not push.

## Files expected to change
- `src/openfactory/app/why.py` (new, about +35)
- `src/openfactory/cli.py` (about +30)
- `tests/unit/test_why.py` (new, about +60)
- `tests/integration/test_cli_why.py` (new, about +200)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-086-why.md`

Not expected to change: `ports/`, `adapters/`, `domain/`, other `app/` modules, any existing test, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 330 lines, about 65 of them in `src/` (TASK-084 had the same shape).

## Design choices to confirm at planning
1. **Use case inputs.**
   - Proposed: `why_file(path, *, traces)`. The "no commit changed" check is already in the read (`None`, TASK-085 choice 1).
   - Alternative: also take `versions`. Nothing would use it.
2. **Where lines are formatted.**
   - Proposed: in `cli.py`, in `_why_lines(trace)`, as `_trace_lines` does. The use case returns the domain `FileTrace`.
   - Alternative: the use case returns `list[str]`. That puts the output format in `app`, but ADR-011 gives it to `cli.py`.
3. **No second sort, and PATH typed `str`.**
   - The use case and `cli.py` keep the adapter's order (TASK-085 choice 4), and AC1 pins it end to end.
   - The Typer argument is `str`, not `Path`, because `pathlib` would rewrite `./app/x.py` to `app/x.py` and `app/` to `app`, which breaks "no normalisation" (AC3).

## Open questions
None beyond the Design choices.

## Spec gaps
- **"CLI commands" › "Output", "each group is sorted as strings" vs `why`'s "by task id, then sha"** (wording, F-6 of `docs/spec-audits/2026-10-22-proposal-v1.17.md`, already in progress.md "Later").
  - What is unclear: read literally, the commit group would be sorted by whole line, which is sha order. The `why` line names its own key.
  - Why it does not block: TASK-085 implemented the named key with the human's answer of 2026-10-22. This task only prints that order.
- **"requirements linked to those tasks"** (wording, TASK-085 review line already in "Later").
  - What is unclear: the spec does not say outright that these are the requirement → task `contract` links, with no spec-version or `deprecated` filter.
  - Why it does not block: TASK-085 settled this reading in the read. This task adds nothing to it.
- Readings, not gaps:
  1. `<PATH>` in `no commit changed <PATH>` is the argument exactly as given.
  2. The spec states no "prints nothing" case for `why`. A non-refused trace always has at least one commit and task line. The requirement and ADR groups may be empty.

## Outcome
- `why PATH` prints the `commit`, `task`, `requirement` and `adr` lines in the spec's order and exits 0; with no commit on the exact path it writes `no commit changed <PATH>` to standard error and exits 1. AC1 to AC5 are met.
- New `src/openfactory/app/why.py` (`WhyRefusal`, `WhyReport`, `why_file`); `cli.py` gains `_why_lines` and the `why` command (PATH typed `str`). New `tests/unit/test_why.py` and `tests/integration/test_cli_why.py`. No port, adapter, dependency, event, payload or schema change, so no ADR. Design choices 1 to 3 are rows in `docs/decisions.md`.
- Test edit for the reviewer (non-mechanical): in `tests/integration/test_cli_why.py` `world()`, sv_02's REQ-A-2 seed changed from [ADR-002, ADR-001] to [ADR-002], so ADR-001 is in sv_01 only as AC2 states. Expected output is unchanged. The original seed contradicted its own expected output, since the spec prints the ADRs of the latest approved version; the edit fixes the seed, not the assertions, and makes the sv_01-only ADR case run. Approved by the human, following the advisor.
- Docs updated: `docs/architecture.md` (Why use case, `why PATH` bullet, `require_init()` and `_open_adapters` lists, `file_trace` caller), `docs/progress.md`, `docs/decisions.md`.
