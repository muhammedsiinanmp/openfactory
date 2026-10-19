# TASK-061: `openfactory_req` pytest plugin and the `pytest` gate in `process_gates`

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-015 (accepted). Its section "The pytest plugin (SC-85, SC-86)" already covers the new convention: the plugin under `adapters/pytest_plugin/`, `PYTHONPATH`, `OPENFACTORY_REQ_OUT` and the two commands. ADR-016 and ADR-017 (accepted) cover `GateRunner` and `finding`. ADR-006 covers the layers. No new port, dependency (pytest is already a dev dependency of OpenFactory and of the target repo; `tempfile`, `os` and `json` are standard library), event type, payload or storage change. The detailed choices become rows in `docs/decisions.md`. The plugin implements no port, so like the projector (ADR-009) it needs no `TYPE_CHECKING` assertion.
- Spec impact: wording. Five items, none blocks (see "Spec gaps").
- Spec sections (spec v1.16; SC-84, SC-85, SC-86, SC-94, SC-95):
  - "Gates and remediation", the gate table: the `pytest` row (the command column only; the "Blocks on" tag rule is outline items 3 and 7).
  - "Gates and remediation" › "Running a gate that starts a process".
  - "Gates and remediation" › "The pytest gate and `req` markers", every sentence up to "The lines are read from the `--collect-only` command", plus "The gate fails when `pytest tests/` does not exit 0 (a run that collects no test included)".
  - "Tech stack and repo layout": the `adapters/` line (`process_gates, pytest_plugin/openfactory_req.py`) and "`pytest_plugin/openfactory_req.py` is the pytest plugin the `pytest` gate loads into the target repo's tests; it is not imported by OpenFactory's own code".
  - "Traceability", the "test → requirement" row: "pytest marker `@pytest.mark.req("REQ-AUTH-001")`, collected with `pytest --collect-only`".

## Outline item
M4 outline item 2. Depends on TASK-059 and TASK-060.

## Objective
Ship the `openfactory_req` plugin and make `ProcessGates.run("pytest", ...)` run the spec's two commands. The plugin goes on `PYTHONPATH` and `OPENFACTORY_REQ_OUT` names a temporary file. The gate returns `passed`, `text`, `finding` false and the marker lines collected by `--collect-only`.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In (details per the Open questions):

- `src/openfactory/adapters/pytest_plugin/openfactory_req.py` (new), one file with no `__init__.py`:
  - It registers the `req` marker through `pytest_configure` (`config.addinivalue_line("markers", ...)`).
  - When collection finishes, it writes one JSON line per collected test, in collection order, to the file named by `OPENFACTORY_REQ_OUT`. Each line is `{"file": <path relative to the repo, POSIX form>, "req": [<ids>]}`.
  - Imports per Open question 1.
- `src/openfactory/adapters/process_gates.py`. `run("pytest", worktree, timeout_s)`:
  - Starts `uv run pytest --collect-only -q -p openfactory_req tests/`, then `uv run pytest -p openfactory_req tests/`. Each runs with `cwd` set to `repo / worktree`, with its own `timeout_s`, and both always run.
  - The plugin's directory (resolved from the adapter module's own location) goes on `PYTHONPATH` (Open question 4).
  - `OPENFACTORY_REQ_OUT` names a temporary file created outside the worktree and removed before `run` returns (Open question 3).
  - `marker_lines` holds the lines read after the `--collect-only` command, each validated by `MarkerLine.model_validate_json` (Open question 5).
  - `passed` is true when both commands exit 0, and `finding` is false.
  - The text layout and the "why" lines are those of TASK-060, unchanged.
  - `_run_command` gains an environment parameter.
  - The `NotImplementedError` branch and the module docstring's "built by M4 outline item 2" go.
- Tests:
  - A new integration file on a stand-in `uv` placed first on `PATH`. It records its arguments, working directory, `PYTHONPATH` and `OPENFACTORY_REQ_OUT`.
  - For the real plugin, a stand-in `uv` that drops `run` and execs the test interpreter's `-m pytest` with the rest of the arguments. It runs on a sample project under `tmp_path`, so the real pytest loads the real plugin through `PYTHONPATH` with no network and no `uv sync`.

Out:
- The tag rule and its `no tagged test in a changed file: <id>` lines (outline item 3).
- Any caller: the gate order, `RunFiles` writes and the `<tool> not found` refusal in `run_plan` (item 7).
- The prompts' text about tests under `tests/` (item 6).
- Any change to `domain/gates.py`, `ports/gate_runner.py`, `app/`, `cli.py`, the other adapters, `pyproject.toml` or CI.
- Changing the environment passed to `uv` beyond `PYTHONPATH` and `OPENFACTORY_REQ_OUT`. `VIRTUAL_ENV` stays as in TASK-060, and its Later line stays.
- Killing the whole process group on a timeout (Open question 6).

## Acceptance criteria
- [ ] **AC1** ("The pytest gate and `req` markers": "The plugin registers the `req` marker and, during collection, writes one JSON line per collected test, `{"file": "<path relative to the repo>", "req": ["<id>", ...]}`, to the file named by the environment variable `OPENFACTORY_REQ_OUT`"; "Traceability", test → requirement). Real pytest, through the exec stand-in, on a sample project with `tests/test_a.py` (one test with `@pytest.mark.req("REQ-A-001")`, one with none) and `tests/sub/test_b.py` (one test with two `req` ids):
  - `run("pytest", ...)` gives `marker_lines` equal to one `MarkerLine` per collected test, in collection order: `file` `tests/test_a.py` or `tests/sub/test_b.py`, and `req` the test's ids, `[]` for the unmarked test (id order per Open question 2).
  - The sample project does not register `req` itself. Both commands run with `--strict-markers` added through the sample's own pytest config, and still exit 0. This shows the plugin registers the marker.
- [ ] **AC2** ("Tech stack and repo layout": "it is not imported by OpenFactory's own code"; "The pytest gate and `req` markers": "a single file under `adapters/pytest_plugin/` that imports only pytest"; ADR-015). Checked with `ast`:
  - `src/openfactory/adapters/pytest_plugin/` holds exactly one `.py` file, `openfactory_req.py`.
  - Its imports are only `pytest`, `json` and `os` (Answer 1), and nothing from `openfactory`.
  - No module under `src/openfactory/` other than the plugin itself imports `openfactory_req`.
- [ ] **AC3** (gate table, `pytest` row: "`uv run pytest --collect-only -q -p openfactory_req tests/` and `uv run pytest -p openfactory_req tests/`"; "Each command runs in the worktree: `ruff` and `pytest` through `uv run`"; "the adapter puts its directory on `PYTHONPATH`"; "a temporary file outside the worktree"). Recording stand-in `uv`:
  - `run("pytest", Path(".openfactory/worktrees/T-1"), 30)` starts `uv` twice, with arguments `run pytest --collect-only -q -p openfactory_req tests/`, then `run pytest -p openfactory_req tests/`. Both run with working directory `<repo>/.openfactory/worktrees/T-1`, also when the test's working directory is elsewhere.
  - In each, the first `PYTHONPATH` entry is the directory that holds `openfactory_req.py`, and an existing `PYTHONPATH` is kept after it (per Open question 4).
  - `OPENFACTORY_REQ_OUT` names a path that is not inside the repo, and it is set for the commands named by Open question 3.
  - After `run` returns, that file no longer exists.
- [ ] **AC4** ("A gate's commands all run; `passed` is true when every one exits 0"; "`finding` is true only when `gitleaks` exits 3, and false for every other gate and outcome"; "The gate fails when `pytest tests/` does not exit 0 (a run that collects no test included)"):
  - With the recording stand-in, the second command runs when the first exits non-zero. `passed` is true only when both exit 0, and `finding` is false in every case.
  - With real pytest: a sample whose one test fails gives `passed` false, with `marker_lines` still read from the `--collect-only` command. A sample with an empty `tests/` (exit 5) gives `passed` false.
- [ ] **AC5** ("The text holds, for each command, its command line, then its standard output, then its standard error"; "A command that cannot be started or runs past `timeout_s` fails its gate, and the text says why"):
  - With the recording stand-in printing distinct markers to standard output and standard error, `text` holds, in order: `$ uv run pytest --collect-only -q -p openfactory_req tests/`, its output, its error, `$ uv run pytest -p openfactory_req tests/`, its output, its error. The layout is TASK-060's.
  - With no `uv` on `PATH`, `run("pytest", ...)` returns `passed` false, `finding` false, `marker_lines` `[]` and a text saying `uv` could not be started, and raises nothing.
  - A stand-in that sleeps past a 1 s limit on the `--collect-only` command gives `passed` false and a `timed out after 1 s` line, the second command still runs, and `marker_lines` is `[]` (Answer 5).
  - A stand-in whose `--collect-only` command exits 0 after writing a line to `OPENFACTORY_REQ_OUT` that `MarkerLine` rejects (for example `{"file": "tests/test_a.py", "req": [123]}`), and whose second command exits 0, gives `passed` false, `finding` false, `marker_lines` `[]`, and a text that ends with the line `invalid marker line: <the line>`; `run` raises nothing (Answer 5).

## Architecture rules that apply
- `adapters/process_gates.py` keeps its `TYPE_CHECKING` assertion and imports from `openfactory` only `domain` and `ports`.
- `adapters/pytest_plugin/openfactory_req.py` implements no port, so it has no assertion. No OpenFactory module imports it; the adapter only names its directory.
- No event, projection, `RunFiles`, `app/` or `cli.py` change.
- No new dependency. No hardening beyond the spec: the plugin does not check `req` argument types; a line that does not validate is caught by the adapter (Answer 5).

## Plan
1. Create branch `task/TASK-061-pytest-plugin-and-pytest-gate` from an up-to-date main and commit this record.
2. Get the human's answers to Open questions 1 to 6. Record them here and as rows in `docs/decisions.md`, replacing the 2026-10-16 `NotImplementedError` row. Adjust the criteria before any test is written.
3. Test-writer: write failing tests for AC1 to AC5 in `tests/integration/test_process_gates_pytest.py` (new). Stand-ins are `#!/bin/sh` scripts in a directory that replaces `PATH`, as in TASK-060. The exec stand-in carries the absolute `sys.executable`. No existing test is changed.
4. Add `adapters/pytest_plugin/openfactory_req.py`.
5. Extend `adapters/process_gates.py`: the pytest commands, the environment, the temporary file, reading the marker lines, and `_run_command(args, cwd, timeout_s, env)`.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
7. Update the living docs and the Outcome. Commit `feat(adapters): add the openfactory_req plugin and the pytest gate` with the trailers `Task: TASK-061` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/adapters/pytest_plugin/openfactory_req.py` (new, about 35 lines)
- `src/openfactory/adapters/process_gates.py` (about +45 lines)
- `tests/integration/test_process_gates_pytest.py` (new, about 220 lines)
- `docs/architecture.md`:
  - "process_gates adapter" gains the `pytest` gate.
  - A new short section, "openfactory_req pytest plugin".
  - The Data flow line becomes "`ProcessGates` is the adapter for `ruff`, `pytest` and `gitleaks`; nothing calls it yet".
- `docs/progress.md`: Current, Done, outline item 2 removed, and the Later lines below.
- `docs/decisions.md`: rows for the answers. The 2026-10-16 `NotImplementedError` row is marked superseded.
- `docs/tasks/TASK-061-pytest-plugin-and-pytest-gate.md` (this record; Outcome at close).

Not expected to change: `domain/`, `ports/`, `app/`, `cli.py`, other adapters, `pyproject.toml`, `.github/`, `docs/adr/`, `docs/spec/`, and every existing test (TASK-060 left the `pytest` branch untested).

Expected size: about 300 lines with tests, about 80 of them in `src/`.

## Spec gaps
Spec impact is "wording". Five items. None blocks, because each concerns how the adapter and plugin carry out an intent the spec fixes. Each has an Open question below, and no answer is assumed.

1. **"The pytest gate and `req` markers"**: "a single file ... that imports only pytest".
   - Unclear: read literally, the plugin cannot import `os` (to read `OPENFACTORY_REQ_OUT`) or `json`.
   - Why it does not block: ADR-015 gives the intent, "so it loads in the target repo's environment". → Open question 1.
2. **Same section**: `"file": "<path relative to the repo>"`.
   - Unclear: no base is named for the path inside the plugin (pytest's `rootpath` or the invocation directory). The spec gives no separator form, and does not say how `req` is built for a test with several `req` markers or one marker with several ids (order, duplicates).
   - Why it does not block: the tag rule (item 3) compares `file` with the path check's changed paths, which git gives relative to the worktree root and in POSIX form. → Open question 2.
3. **Same section**: "writes ... to the file named by ... `OPENFACTORY_REQ_OUT`, a temporary file outside the worktree. The lines are read from the `--collect-only` command."
   - Unclear: whether the variable is also set for `pytest tests/`, which collects too. What the plugin does when the variable is unset. Who creates and removes the file.
   - Why it does not block: only the `--collect-only` lines are read, as the spec says. → Open question 3.
4. **Same section**: "the adapter puts its directory on `PYTHONPATH`".
   - Unclear: whether it is added in front of the caller's `PYTHONPATH` or replaces it.
   - Why it does not block: either way the plugin loads. → Open question 4.
5. **Same section**: what `marker_lines` holds when the `--collect-only` command fails, times out or cannot start, or a line does not validate.
   - Why it does not block: the gate fails anyway, since a command did not exit 0. → Open question 5.

Readings, not gaps:
- "a run that collects no test included": pytest exits 5 when it collects nothing, so the "every command exits 0" rule already fails the gate. No extra code.
- `finding` is false for `pytest` in every case (SC-121).
- The plugin is found through the adapter module's own location, `Path(__file__).parent / "pytest_plugin"`, made absolute. Whether `uv_build` packages a directory with no `__init__.py` into a wheel is not checked; OpenFactory runs from its source tree in Phase 1. This goes in a Later line.

## Later lines in `docs/progress.md`
Taken: none. The TASK-060 process-group line is answered by Open question 6.

To add at close:
- "Whether `uv_build` puts `adapters/pytest_plugin/openfactory_req.py` (no `__init__.py`) in a built wheel was not checked; Phase 1 runs from the source tree (TASK-061, planner)."
- The five "Spec wording" lines, completed with the answers.

## Answers
Decided by the human on 2026-10-19, following the advisor (5 AGREE, 1 DISAGREE on question 5, whose alternative (b) was taken).

1. `pytest` and the standard library modules the plugin actually uses: `json` and `os`. Nothing from `openfactory`, no other third-party package. AC2 checks exactly this list.
2. As proposed: `file` relative to `config.invocation_params.dir`, POSIX form; `req` from `item.iter_markers("req")`, closest first, arguments in order, duplicates kept.
3. As proposed, and the descriptor `mkstemp` returns is closed at once.
4. As proposed: plugin directory, then the caller's `PYTHONPATH` when set and not empty.
5. Alternative (b). The file is read after the `--collect-only` command whatever its outcome; a missing or empty file gives `[]`. A line that `MarkerLine` rejects (bad JSON included) gives `passed` false and `marker_lines` `[]`, and the text gains the line `invalid marker line: <the line>`; nothing is raised. The `req` values come from tests an agent writes, and the port's rule is "a failure is returned, not raised".
6. As proposed: no process-group kill; the TASK-060 Later line stays and now also names `pytest`.

## Open questions (as planned)

1. **What the plugin may import.**
   - Proposed: `pytest` and the standard library (`json`, `os`, `pathlib`), nothing from `openfactory` and no other third-party package. AC2 checks this list.
   - Alternative: a `/spec-change` first, to reword "imports only pytest".
2. **The base of `file`, and how `req` is built.**
   - Proposed:
     - `file` is `item.path` relative to `config.invocation_params.dir`, in POSIX form. That directory is the adapter's `cwd`, the worktree root.
     - `req` is the arguments of every `req` marker from `item.iter_markers("req")`, in that order (closest marker first), each marker's arguments in order. Duplicates are kept.
   - Alternative (a): `file` relative to `config.rootpath`. That base depends on the target repo's pytest config and may differ from the worktree root.
   - Alternative (b): `req` without duplicates, or sorted.
3. **`OPENFACTORY_REQ_OUT` and the temporary file.**
   - Proposed:
     - The adapter creates the file with `tempfile.mkstemp()` in the system temp directory and sets the variable only for the `--collect-only` command.
     - The plugin writes nothing when the variable is unset. When it is set, it writes the file in `"w"` mode, as UTF-8, at `pytest_collection_finish`.
     - The adapter deletes the file in a `finally` before returning.
   - Alternative: set the variable for both commands. The second run then rewrites the file after it has been read.
4. **`PYTHONPATH`.**
   - Proposed: the plugin directory, then `os.pathsep` and the caller's `PYTHONPATH` when it is set and not empty. The value is the same for both commands.
   - Alternative: replace `PYTHONPATH` with the plugin directory alone.
5. **`marker_lines` when collection did not finish cleanly.**
   - Proposed:
     - The file is read after the `--collect-only` command whatever its outcome: one `MarkerLine.model_validate_json` per non-empty line. A missing or empty file gives `[]`, so a timeout or a command that cannot start gives `[]`.
     - A line that does not validate raises `ValidationError`. The plugin is OpenFactory's own, so no hardening.
   - Alternative (a): `[]` whenever the `--collect-only` command did not exit 0.
   - Alternative (b): a line that does not validate is returned as a failed gate with a line in the text, keeping the port's "returned, not raised" rule.
6. **The TASK-060 Later line on killing the process group on a timeout.**
   - Proposed: leave it out. The spec asks only that the gate fails and the text says why. The Later line stays, now also naming `pytest`.
   - Alternative: start each command with `start_new_session=True` and kill the group on a timeout, with a test that the grandchild is gone. This adds about 30 lines.

## Outcome
- Added `src/openfactory/adapters/pytest_plugin/openfactory_req.py` and the `pytest` gate in `src/openfactory/adapters/process_gates.py` (the `NotImplementedError` is gone). Details are in `docs/architecture.md` ("process_gates adapter", "openfactory_req pytest plugin") and the 2026-10-19 rows of `docs/decisions.md`.
- Tests: `tests/integration/test_process_gates_pytest.py` (16 tests). 1375 tests pass; ruff, pyright and check_docs are clean. The new file passed 6 repeated runs, so the timeout test is stable.
- Test edit (one, mechanical): the test-writer's exec stand-in `uv` in `tests/integration/test_process_gates_pytest.py` (`make_exec_uv`) used `shift`, which dropped only `run` and passed `pytest` to `python -m pytest` as a path argument. Changed to `shift 2` and its docstring to "drops `run pytest`". Assertions unchanged.
- Docs: `docs/architecture.md`, `docs/progress.md` (Current, Done, outline item 2 removed, Later line on the built wheel).

Reviewer notes (approve, no blocking issues), applied at the human's request:
- `_run_pytest` drops a caller's `OPENFACTORY_REQ_OUT` from the environment, so the variable reaches the `--collect-only` command only, whatever the caller's environment holds.
- The five TASK-061 "Spec wording" lines in `docs/progress.md` now carry the answers given.
- Not applied: comparing the whole `marker_lines` list in the AC1 test. The order between files is left unchecked because pytest versions differ on directories before files, and the test is the test-writer's.
