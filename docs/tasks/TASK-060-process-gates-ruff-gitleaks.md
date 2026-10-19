# TASK-060: `process_gates` adapter for `ruff` and `gitleaks`, with `missing_tool()`

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-015, ADR-016 and ADR-017, all accepted.
  - ADR-015, "Ports and adapters": "`GateRunner`, adapter `process_gates`".
  - ADR-016 fixes `--exit-code 3`, adds `missing_tool()`, and says "The task that builds `process_gates` confirms on the installed gitleaks (8.30.1) that its own errors do not exit 3".
  - ADR-017 adds `finding`.
  - ADR-006 requires the `TYPE_CHECKING` assertion.
  - Nothing new triggers an ADR: no new port, no new dependency (`subprocess` and `shutil` only), and no change to events or storage. The text layout and the decoding become rows in `docs/decisions.md` (Open question 2).
- Spec impact: wording. Two items, neither blocks (see "Spec gaps").
- Spec sections (spec v1.16; SC-84, SC-94, SC-111, SC-115, SC-121):
  - "Gates and remediation", the gate table: the `ruff` and `gitleaks` rows.
  - "Gates and remediation" › "Running a gate that starts a process".
  - "Gates and remediation" › "Target repo": "`gitleaks` scans only what the path check staged ... and prints no secret"; "gitleaks 8.30 or later is required".
  - "Tech stack and repo layout": the `adapters/` line lists `process_gates`; "The gates that start a process (ruff, pytest, gitleaks) run behind the `GateRunner` port, whose adapter is `process_gates`".
  - "Domain model and storage", the M4 paragraph after "Ids": "`GateRunner`, whose adapter is `process_gates`, runs a gate that starts a process and names the first of `uv` and `gitleaks` missing from `PATH`".
  - "Execution" › "`run`": the `<tool> not found` refusal ("as `GateRunner.missing_tool()` gives it"). This task gives only the adapter's half.

## Outline item
M4 outline item 1, the second of its two pieces (decision of 2026-10-16). TASK-059 built the port and the models. Depends on TASK-059.

## Objective
Give `GateRunner` its adapter `process_gates`. It runs the `ruff` and `gitleaks` gates as the spec states and names the first missing tool. It also confirms on the installed gitleaks that only a finding exits 3.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In (names per Open question 4):

`src/openfactory/adapters/process_gates.py` (new) defines `ProcessGates(repo: Path)`, which implements `GateRunner`.

`missing_tool()`:
- Returns the first of `"uv"` and `"gitleaks"` that `shutil.which` does not find on `PATH`, else `None`.

`run("ruff", worktree, timeout_s)`:
- Starts `uv run ruff check`, then `uv run ruff format --check`.
- Each command starts with `cwd` set to `repo / worktree` and its own `timeout_s` limit.
- Both commands always run.
- `passed` is true when both exit 0. `finding` is false and `marker_lines` is `[]`.

`run("gitleaks", worktree, timeout_s)`:
- Starts `gitleaks git --pre-commit --staged --redact --no-banner --exit-code 3 .` from `PATH`, with `cwd` set to `repo / worktree`.
- Exit 0: `passed` is true.
- Exit 3: `passed` is false and `finding` is true.
- Any other exit, a timeout, or a command that cannot start: `passed` is false and `finding` is false.
- `marker_lines` is `[]` in every case.

The text, for every gate:
- For each command, in order: its command line, then its standard output, then its standard error (layout per Open question 2).
- A timeout or a command that cannot start gives a line that says why.
- A failure is returned, never raised.

`run("pytest", ...)` follows Open question 1 until outline item 2.

The module ends with `if TYPE_CHECKING: _: type[GateRunner] = ProcessGates`.

Tests:
- A new integration file on stand-in `uv` and `gitleaks` executables placed first on `PATH`.
- A new integration file on the real `gitleaks` and `git` (Open question 3).

Out:
- The `pytest` gate itself: the `openfactory_req` plugin, `PYTHONPATH`, `OPENFACTORY_REQ_OUT` and the marker lines (outline item 2).
- The tag rule and its lines (item 3).
- Any caller: the `<tool> not found` refusal and the gate order in `run_plan` (item 7).
- Writing the text through `RunFiles` (the use case, item 7).
- Any change to `domain/gates.py`, `ports/gate_runner.py`, `app/`, `cli.py`, the other adapters, `pyproject.toml` or the CI workflow.
- Removing or changing environment variables passed to `uv` or `gitleaks`. The caller's environment is passed as it is (see Readings).
- The M3 Later line on `--strict-mcp-config`, which concerns the agent run and not the gates.

## Acceptance criteria
- [x] **AC1** ("Running a gate that starts a process": "`GateRunner` also gives `missing_tool() -> str | None`, the first of `uv` and `gitleaks` that is not on `PATH`"; SC-111, ADR-016):
  - With executable `uv` and `gitleaks` on `PATH`, `missing_tool()` is `None`.
  - With only `gitleaks` missing, it is `"gitleaks"`.
  - With `uv` missing, or both missing, it is `"uv"`.
- [x] **AC2** (gate table, `ruff` row: "`uv run ruff check` and `uv run ruff format --check`"; "Each command runs in the worktree: `ruff` and `pytest` through `uv run`"; "A gate's commands all run; `passed` is true when every one exits 0"; SC-84):
  - `run("ruff", Path(".openfactory/worktrees/T-1"), 30)` starts the stand-in `uv` twice, with arguments `run ruff check`, then `run ruff format --check`. Both start with working directory `<repo>/.openfactory/worktrees/T-1`, also when the test's working directory is elsewhere.
  - The second command runs when the first exits non-zero.
  - `passed` is true only when both exit 0.
  - `finding` is false and `marker_lines` is `[]` in every case.
- [x] **AC3** (gate table, `gitleaks` row; "`gitleaks` from `PATH`"; "`finding` is true only when `gitleaks` exits 3, and false for every other gate and outcome"; "For `gitleaks`, exit status 3 (set by `--exit-code 3`) is a finding; any other failure of it is a failed gate that is not a finding"; SC-94, SC-115, SC-121, ADR-016, ADR-017):
  - `run("gitleaks", worktree, 30)` starts the stand-in `gitleaks` once, with arguments `git --pre-commit --staged --redact --no-banner --exit-code 3 .`, in the worktree.
  - Exit 0 gives `passed` true and `finding` false.
  - Exit 3 gives `passed` false and `finding` true.
  - Exits 1 and 2 give `passed` false and `finding` false.
  - `marker_lines` is `[]` in every case.
- [x] **AC4** ("Running a gate that starts a process": "The text holds, for each command, its command line, then its standard output, then its standard error"):
  - For `ruff`, the stand-in prints distinct markers to standard output and standard error for each command, on a pass and on a failure.
  - `text` holds, in this order: the first command line, its output, its error, the second command line, its output, its error.
  - Layout per Open question 2.
- [x] **AC5** ("Running a gate that starts a process": "`timeout_s` is the contract's `max_runtime_s`, applied to each command. A command that cannot be started or runs past `timeout_s` fails its gate, and the text says why"; "A gate's commands all run"):
  - A stand-in `uv` that sleeps past a 1 s limit on `ruff check` gives `passed` false and a text saying it timed out after 1 s. `ruff format --check` still runs and its lines are in the text.
  - `run("gitleaks", ...)` with no `gitleaks` on `PATH` returns `passed` false, `finding` false and a text saying it could not be started. It raises nothing.
  - `run("ruff", ...)` with no `uv` on `PATH` returns the same way.
- [x] **AC6** (ADR-016 Decision: "confirms on the installed gitleaks (8.30.1) that its own errors do not exit 3"; "Target repo": "`gitleaks` scans only what the path check staged ... and prints no secret"), on the real `gitleaks` and `git`:
  - In a git repo whose staged file holds a token that gitleaks's default rules detect, `run("gitleaks", ...)` gives `finding` true and `passed` false, and `text` does not contain the token.
  - Run on a directory that is not inside a git repo (a scan error), it gives `passed` false and `finding` false.
    - As built: a directory outside a git repo is not a scan error on 8.30.1 (it exits 0), so the test uses a staged repo with an invalid `.gitleaks.toml`, which exits 1. See the Outcome.
  - The token is built at runtime, so no source file holds a secret: CI runs `gitleaks-action` over this repo.
  - The installed version is recorded in the Outcome.
  - If gitleaks's own error exits 3, the task stops and goes to the human, since ADR-016's premise fails.

## Architecture rules that apply
- `adapters/process_gates.py` implements the port and ends with its `TYPE_CHECKING` assertion (ADR-006). It imports from `openfactory` only `domain` and `ports`.
- A relative `worktree` is resolved against the adapter's own repo (the F-7 rule of 2026-10-13).
- No event is recorded. No projection, `RunFiles` call, `app/` code or `cli.py` code is touched.
- No new dependency and no hardening beyond the spec. For example, no check that `uv` is a uv binary or that gitleaks is version 8.30 or later.

## Plan
1. Create branch `task/TASK-060-process-gates-ruff-gitleaks` from an up-to-date main and commit this record.
2. Get the human's answers to Open questions 1 to 5, and record them here and as rows in `docs/decisions.md`. Adjust the criteria before any test is written.
3. Test-writer: write failing tests for AC1 to AC5 in `tests/integration/test_process_gates.py` and for AC6 in `tests/integration/test_process_gates_gitleaks.py` (both new).
   - The stand-ins are scripts named `uv` and `gitleaks` in a directory set first on `PATH` with `monkeypatch.setenv`. Each records its arguments and working directory, as the `claude` stand-in of TASK-057 does.
   - No existing test is changed.
4. Implement `adapters/process_gates.py`.
5. Run AC6 on the installed gitleaks. Record the version and the exit statuses seen in the Outcome. If the error case exits 3, stop (see AC6).
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
7. Update the living docs and the Outcome. Commit `feat(adapters): add the process_gates adapter for ruff and gitleaks` with the trailers `Task: TASK-060` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/adapters/process_gates.py` (new, about 100 lines)
- `tests/integration/test_process_gates.py` (new, about 200 lines)
- `tests/integration/test_process_gates_gitleaks.py` (new, about 60 lines)
- `docs/architecture.md`:
  - a new Components section, "process_gates adapter";
  - the Data flow line on `GateRunner` (currently "The port has no adapter yet ... and nothing calls it") becomes "`ProcessGates` is the adapter for `ruff` and `gitleaks`; nothing calls it yet".
- `docs/progress.md`: Current, Done, outline item 1 removed, and the Later lines below.
- `docs/decisions.md`: rows for the answers.
- `docs/tasks/TASK-060-process-gates-ruff-gitleaks.md` (this record; Outcome at close).

Not expected to change: `domain/`, `ports/` (including `gate_runner.py`), `app/`, `cli.py`, other adapters, `pyproject.toml`, `.github/`, `docs/adr/`, `docs/spec/`, and every existing test.

Expected size: about 360 lines with tests, about 100 of them in `src/`. That is above the ~300 guideline, in line with TASK-048 and TASK-049. To split, move AC6 to its own task. ADR-016 places that check with this adapter, so the split is not proposed.

## Spec gaps
Spec impact is "wording". Two items, neither blocks.

1. **"Gates and remediation" › "Running a gate that starts a process"**: "The text holds, for each command, its command line, then its standard output, then its standard error."
   - Unclear: the spec gives the parts and their order, but not how a command line is written (a prefix, quoting), what separates the parts, whether a part that does not end in a line break gets one, or how the bytes are decoded.
   - Does not block: the parts and their order are fixed. The use case only appends lines (item 3) and writes the whole text (item 7), so the layout is an adapter choice inside the spec.
   - Not assumed: Open question 2 carries a proposal. The answer becomes a `docs/decisions.md` row, and the spec text is left to a later `/spec-change`.
2. **Same section**: "A command that cannot be started or runs past `timeout_s` fails its gate, and the text says why."
   - Unclear: the wording of the "why" line. The spec also does not say whether output captured before a timeout's kill goes in the text.
   - Does not block, for the same reason as item 1.
   - Not assumed: part of Open question 2.

Readings, not gaps:
- **"Not on `PATH`"** means `shutil.which(name)` is `None`, so a file that is not executable counts as missing. The subprocess resolves the name from the same `PATH`.
- **"A gate's commands all run"** covers a first command that timed out or could not start: the second still runs.
- **"In the target repo's environment"** is reached through `uv run` in the worktree. The caller's environment is passed unchanged, including `VIRTUAL_ENV` when OpenFactory itself runs under `uv run`. uv is expected to ignore a `VIRTUAL_ENV` that does not match the project and print a warning, which lands in the text. That was not confirmed; it goes in a Later line.
- **gitleaks resolves `.` against the worktree**, its `cwd`. With `--staged` it reads that worktree's index.

## Later lines in `docs/progress.md`
Taken: none.

To add at close:
- "`process_gates` passes the caller's environment to `uv`, `VIRTUAL_ENV` included. That uv ignores a mismatched `VIRTUAL_ENV` was not confirmed on a real run; look at it at the M4 close or the first real run (TASK-060, planner)."
- "The real-gitleaks tests in `tests/integration/test_process_gates_gitleaks.py` are skipped where `gitleaks` is not on `PATH`, including CI. Only a local run with gitleaks installed exercises them (TASK-060, planner)." This line applies only if Open question 3 is answered as proposed.
- The two "Spec wording" lines, completed with the answers.

## Open questions
None blocks planning. Each has a proposal and an alternative. All must be answered before the tests are written (Plan step 2).

1. **What `run("pytest", ...)` does until outline item 2.**
   - Proposed: raise `NotImplementedError("pytest gate: outline item 2")`, with no test. Nothing calls the port before item 7, which depends on item 2; a raise cannot be mistaken for a real failed gate; with no test, item 2 does not have to edit a fixed test. It goes against the port's "returned, not raised" docstring only for that one interim case.
   - Alternative (a): return `GateOutput(passed=False, text="pytest gate not built", finding=False, marker_lines=[])`. This keeps the docstring true, but returns a made-up failure.
   - Alternative (b): run the two spec commands as they are. They fail anyway, because `-p openfactory_req` cannot load without the plugin.
2. **The text layout and the "why" lines.**
   - Proposed: each command gives a line `$ <command line>`, written with `shlex.join`. Standard output and standard error follow, decoded as UTF-8 with `errors="replace"`, as `ClaudeCodeExecutor` decodes standard error. Each non-empty part ends with `\n`, added when missing. Empty parts are left out. Commands follow one another with nothing in between. A timeout gives the line `timed out after <timeout_s> s`, with no partial output. A command that cannot be started gives `<executable> could not be started: <OS error>`, after the `ClaudeCodeExecutor` texts.
   - Alternative: keep the partial output captured before a timeout's kill, then the timeout line.
3. **The real-gitleaks test (AC6) where `gitleaks` is not installed.**
   - Proposed: `pytest.mark.skipif(shutil.which("gitleaks") is None, ...)`. CI's `ci_local.sh` step runs on ubuntu with no `gitleaks` on `PATH`; `gitleaks-action` downloads its own binary in a later step. The Outcome records the local run on 8.30.1.
   - Alternative: install gitleaks in `.github/workflows/ci.yml` and make the test required, as the suite already requires `git`. That changes CI config and adds a tool that CI must download.
4. **Names and construction.**
   - Proposed: `ProcessGates(repo: Path)` in `adapters/process_gates.py`, with no executable parameters. `missing_tool` names `uv` and `gitleaks` as found on `PATH`; the tests put stand-ins first on `PATH`, as TASK-057 did for `claude`.
   - Alternative: `ProcessGates(repo, uv="uv", gitleaks="gitleaks")`, as `GitCli(repo, executable="git")` does. Easier for tests, but `missing_tool` would then check one name while `run` starts another.
5. **Test file split.**
   - Proposed: two files, one on stand-ins and one on the real tool. The skip then covers a whole file and the stand-in tests never need gitleaks.
   - Alternative: one file, with the skip on the AC6 tests only.

## Answers (2026-10-16, the human, following the advisor)
1. As proposed: `run("pytest", ...)` raises `NotImplementedError("pytest gate: outline item 2")`, with no test.
2. As proposed, with the advisor's addition: every command's text starts with its `$ <shlex.join(cmd)>` line; a "why" line (`timed out after <timeout_s> s`, or `<executable> could not be started: <OS error>`) follows it in place of standard output and standard error; no partial output on a timeout. Stand-ins that sleep use `exec sleep`.
3. As proposed: the real-gitleaks tests are skipped where `gitleaks` is not on `PATH`; the Outcome records the local run; the Later line is added at close.
4. As proposed: `ProcessGates(repo: Path)`, no executable parameters; tests replace `PATH` with a directory of `#!/bin/sh` stand-ins.
5. As proposed: two test files.

## Outcome
Built `ProcessGates(repo)` in `src/openfactory/adapters/process_gates.py`, implementing `GateRunner` with the `TYPE_CHECKING` assertion: `missing_tool()`, the `ruff` gate (two commands, both always run), the `gitleaks` gate (`--exit-code 3`; only exit 3 is a finding), the text layout and the "why" lines per the answers of 2026-10-16, and `NotImplementedError("pytest gate: outline item 2")` for `pytest`. New `tests/integration/test_process_gates.py` (stand-ins) and `tests/integration/test_process_gates_gitleaks.py` (real tools, skipped without `gitleaks`): 22 tests in the two files; full suite 1359 passed.

AC6, local run on gitleaks 8.30.1 (`/opt/homebrew/bin/gitleaks`):
- A staged token gives exit 3 through the adapter: `finding` true, `passed` false, the token not in `text`.
- A clean staged file gives exit 0 and passes.
- A scan error does not exit 3, so ADR-016's premise holds. Correction to the plan's wording: a plain non-git directory is not an error exit. Running `gitleaks git --pre-commit --staged --redact --no-banner --exit-code 3 .` in a fresh temp directory outside any git repo logged errors (`git diff --no-index` rejecting `--staged`) and still exited 0 ("no leaks found"). The test therefore uses a staged repo with an invalid `.gitleaks.toml`, which exits 1 (confirmed by hand): `passed` false, `finding` false.

Test edit (not mechanical): the AC5 timeout test in `tests/integration/test_process_gates.py` gained a warm-up run of the stand-in `uv` and deletes its record files before the timed run. The 1 s limit and the assertions are unchanged. Approved by the human following the advisor; `docs/decisions.md` row of 2026-10-19.

Deviation: the record was not committed at plan step 1; it goes in the task commit.

Follow-ups: two Later lines added to `docs/progress.md` (the caller's `VIRTUAL_ENV` passed to `uv`; the real-gitleaks tests skipped in CI), and the two "Spec wording" Later lines completed with the answers.
