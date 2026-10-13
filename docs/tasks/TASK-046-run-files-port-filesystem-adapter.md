# TASK-046: `RunFiles` port and the `filesystem_run_files` adapter

- Milestone: M3
- Status: done
- Tests: acceptance
- ADR: ADR-014 (accepted). "Ports and adapters (SC-63, SC-68)": "`RunFiles`, adapter `filesystem_run_files`: writes a file of a run under `.openfactory/runs/<run id>/` and returns its path relative to the repo. Gate output goes through it." ADR-001 and ADR-012 leave exact signatures to the task that builds them; ADR-006 covers the `TYPE_CHECKING` assertion. No new dependency, event type, payload or storage change. Names and signatures are rows in `docs/decisions.md` (Open questions 1 to 3).
- Spec impact: wording. One item, audit F-5; it does not stop the task as scoped (see "Spec gaps"). It becomes `gap (blocks)` if Open question 1 is answered with alternative (a).
- Spec sections (spec v1.12, SC-58, SC-63): "Domain model and storage" (the M3 paragraph after "Ids"; "Event payloads", the `GateEvaluated` line `output_path`); "Tech stack and repo layout"; "Execution" › "The path check", "Adapter interface"; "Gates and remediation" (the paragraph "Gate output is stored as a file")

## Outline item
M3 outline item 1. Items 2 to 7 are left.

## Objective
Give the run use case a `RunFiles` port, with the `filesystem_run_files` adapter behind it, that writes a text file of a run under `.openfactory/runs/<run id>/` and returns its path relative to the repo, so gate output can be stored without `app` touching the filesystem.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings and to SC-58 and SC-63.

## Scope
In (names and signatures per Open questions 1 to 3):
- `src/openfactory/ports/run_files.py` (new): Protocol `RunFiles` with one method.
  - `write(run_id: str, name: str, text: str) -> Path`: writes `text` to the file `name` of the run and returns the file's path relative to the repo, `.openfactory/runs/<run id>/<name>`.
- `src/openfactory/adapters/filesystem_run_files.py` (new): `FilesystemRunFiles(repo: Path)`.
  - `write` creates `repo/.openfactory/runs/<run id>/` when it is missing (parents included).
  - It writes the text as UTF-8 with `newline=""`, so the bytes are the text as given. This mirrors `FilesystemSpecFiles.read`.
  - It returns `Path(".openfactory/runs") / run_id / name`.
  - It resolves against its own repo, never the process's working directory.
  - It ends with the `TYPE_CHECKING` assertion against `RunFiles`.
- Tests: a new unit file for the port's shape, and a new integration file on a directory under `tmp_path`.

Out (not this task):
- Every caller. Building the name `<gate>.txt`, the line order of the violating paths, `output_path` in `GateEvaluated` and "when it passes, `output_path` is null" belong to outline item 4. Nothing calls the port yet.
- `output_dir`, `transcript.json` and who creates the run's directory for the executor (audit F-5; outline item 2).
- Any method that gives or creates the run's directory without writing a file (Open question 1).
- Wiring in `cli.py` (outline item 6).
- Reading a run file back. The "last failure report" of the context pack is "from M4".
- Hardening:
  - a `name` or `run_id` with `/` or `..`;
  - a run id not of the form `run_NNNN`;
  - a disk that cannot be written (an `OSError` propagates, not caught or wrapped);
  - atomic writes;
  - a missing `.openfactory/`.

## Acceptance criteria
"The M3 paragraph" is the paragraph after "Ids" under "Domain model and storage".

Terms:
- **A test repo** is a directory under `tmp_path` that holds `.openfactory/.gitignore` containing `*`, as `init` leaves it, and no `.openfactory/runs/`. No git is needed.

The criteria are written for the proposals under Open questions.

- [x] AC1 (the M3 paragraph: "`RunFiles`, whose adapter is `filesystem_run_files`, writes a file of a run under `.openfactory/runs/<run id>/` and returns its path relative to the repo"; "Tech stack and repo layout": `RunFiles` under `ports/`, `filesystem_run_files` under `adapters/`):
  - `RunFiles` is a Protocol whose public methods are exactly `write`.
  - `ports/run_files.py` imports nothing from `openfactory.adapters` or `openfactory.app`; `adapters/filesystem_run_files.py` imports nothing from `openfactory.app`.
  - `uv run pyright` passes with the `TYPE_CHECKING` assertion as the last statement of `filesystem_run_files.py`.
- [x] AC2 ("Gates and remediation": "The file is `.openfactory/runs/<run id>/<gate>.txt`, written through the `RunFiles` port"; "Execution" › "The path check": "the gate's output file lists the violating paths, one per line"):
  - On a test repo, `FilesystemRunFiles(repo).write("run_0007", "path_check.txt", TEXT)` returns `Path(".openfactory/runs/run_0007/path_check.txt")`.
  - `TEXT` is two lines ending in `\n`, one of them a path with a non-ASCII character.
  - The bytes of `repo / <returned>` equal `TEXT.encode("utf-8")`.
- [x] AC3 (the M3 paragraph: "returns its path relative to the repo"; "Event payloads", `GateEvaluated`: "`output_path: null | "<path>"` # relative to the repo"):
  - With the test's working directory set to another directory under `tmp_path`, `write("run_0007", "path_check.txt", TEXT)` returns the same relative path as in AC2 (`is_absolute()` is false).
  - The file is at `repo / <returned>`, and the working directory holds no `.openfactory` entry afterwards.
- [x] AC4 ("Execution" › "Adapter interface": "`output_dir` is the run's directory, `.openfactory/runs/<run id>/`. The adapter writes the runtime's result envelope to `<output_dir>/transcript.json`"; "Gates and remediation": "Gate output is stored as a file ... so the audit trail keeps the evidence"):
  - On a test repo where the test has already written `.openfactory/runs/run_0007/transcript.json`, `write("run_0007", "path_check.txt", A)` succeeds and leaves `transcript.json` with its bytes unchanged.
  - A following `write("run_0007", "ruff.txt", B)` and `write("run_0008", "path_check.txt", C)` leave the first file holding `A`.
  - The directories `run_0007` and `run_0008` then hold exactly `{transcript.json, path_check.txt, ruff.txt}` and `{path_check.txt}`.

## Architecture rules that apply
- `ports` holds Protocols only. The port uses `pathlib.Path` and plain strings.
- The adapter ends with its `TYPE_CHECKING` assertion against `RunFiles` (ADR-006).
- `app` writes no file; every file `run` writes goes through a port (ADR-006, ADR-014). `cli.py`, `app/` and `domain/` are not changed.
- No event is recorded and no projection is read or written.
- No new dependency.
- OpenFactory's own tests carry no `req` markers.
- No hardening beyond what the spec asks.

## Plan
1. Create branch `task/TASK-046-run-files-port-filesystem-adapter` from an up-to-date main.
2. Get the human's answers to Open questions 1 to 3. Record them here and as rows in `docs/decisions.md`.
   - If question 1 is answered with alternative (a), stop: set Status to blocked and Spec impact to `gap (blocks)` until the `/spec-change` is applied.
   - If another answer differs from a proposal, adjust the criteria before any test is written.
3. Write failing tests:
   - `tests/unit/test_run_files_port.py` (new) for AC1, after `tests/unit/test_workspace_manager_port.py`;
   - `tests/integration/test_filesystem_run_files.py` (new) for AC2 to AC4, with a fixture for the test repo.
4. Add `ports/run_files.py` with the Protocol and its docstring.
5. Add `adapters/filesystem_run_files.py`.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
7. Update the living docs and the Outcome. Commit `feat(adapters): write a file of a run and return its path` with trailers `Task: TASK-046` and `Milestone: M3`.

## Files expected to change
- `src/openfactory/ports/run_files.py` (new, about 25 lines)
- `src/openfactory/adapters/filesystem_run_files.py` (new, about 30 lines)
- `tests/unit/test_run_files_port.py` (new, about 40 lines)
- `tests/integration/test_filesystem_run_files.py` (new, about 90 lines)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-046-run-files-port-filesystem-adapter.md` (this record; Outcome at close)

Not expected to change: `cli.py`, every module under `app/` and `domain/`, every existing port and adapter, `pyproject.toml`, `docs/adr/`, `docs/spec/` and every existing test file.

Expected size: about 190 lines with tests, about 55 of them in `src/`.

## Living docs to update
- `docs/architecture.md`:
  - new sections "RunFiles port" and "Filesystem run files";
  - "Data flow": the port exists for the run use case and nothing calls it yet.
- `docs/progress.md`: Current, Done, outline item 1 removed, and the Later lines listed below.
- `docs/decisions.md`: rows for the answered open questions.
- `CHANGELOG.md` and `README.md`: no change (nothing a user sees).

## New dependencies
None.

## Spec gaps
Spec impact is "wording": one item, which does not stop the task as scoped.

1. "Execution" › "Adapter interface" ("`output_dir` is the run's directory, `.openfactory/runs/<run id>/`. The adapter writes the runtime's result envelope to `<output_dir>/transcript.json`"), with "Gates and remediation" ("written through the `RunFiles` port") and "Domain model and storage", the M3 paragraph after "Ids" ("`RunFiles` ... writes a file of a run under `.openfactory/runs/<run id>/`"). This is audit F-5 of `docs/spec-audits/2026-10-13-proposal-v1.12.md`.
   - Missing: there are two writers under one directory, and no text says who creates it or which component hands `output_dir` to the use case. Spec v1.12 and ADR-014 (accepted) do not hold the audit's proposed sentence ("`RunFiles` gives the directory of a run, creating it; the use case passes it to the executor as `output_dir`").
   - Does not block this task:
     - the one operation the spec gives `RunFiles` is fully stated, and AC1 to AC4 trace to it;
     - the value of `output_dir` is stated ("`.openfactory/runs/<run id>/`", "the path follows from the run id");
     - `write` creates the directory when it is missing and leaves what is in it, so it is correct under every answer (AC4 fixes both cases).
   - Not assumed: this task adds no directory operation and does not decide who creates the directory for `transcript.json`.
   - Blocks later: outline item 2 (`AgentExecutor`) cannot be planned without the answer. It decides whether the executor adapter creates `output_dir` and whether the use case builds the path or gets it from `RunFiles`.
   - Would block now: Open question 1, alternative (a). A criterion for a directory operation has no spec text to trace to.

Readings, not gaps (each follows from the text as written):
- "writes a file of a run" is general, so the port takes a file name and the use case builds `<gate>.txt`. The port does not know gate names.
- `init` creates `.openfactory/` but not `.openfactory/runs/`, and the port has one operation, so that operation must be able to write the first file of a run.
- `.openfactory/.gitignore` holds `*`, so run files never show in the checkout's status and are never a changed path of a worktree.
- "relative to the repo" with `output_path` stored in an event: the returned path does not depend on the process's working directory (AC3).

## Later lines in `docs/progress.md`: taken or left
- "Spec gap ... F-5 who creates the directory of a run and where `output_dir` comes from (before the `RunFiles` task is planned ...)": not taken, unless Open question 1 is answered with (a) or (b). At close the F-5 part is reworded to "before the `AgentExecutor` task (outline item 2) is planned; `RunFiles.write` creates the run's directory when missing and works under either answer (TASK-046, planner)". F-1 to F-4 and F-8 are left.
- Every other Later line: left.
- To add at close:
  - "`FilesystemRunFiles.write` does not catch `OSError`; the spec does not say what `run` does when a gate's output file cannot be written (TASK-046, planner)".
  - "`RunFiles.write` replaces an existing file of the same run and name; no test, since a gate is evaluated once per run (TASK-046, planner)", per Open question 3.
  - "`RunFiles.write` does not check `run_id` or `name` (a `/` or `..` would write outside the run's directory); the only caller passes a run id from `Runs.next_id` and a gate name (TASK-046, planner)".

## Open questions
Answered by the human on 2026-10-13: the proposal of each of the three questions is taken (advisor: 3 AGREE). Rows are in `docs/decisions.md`.

1. **Method set and audit F-5 (Spec gaps, item 1).**
   - Proposed: one method, `write`, as spec v1.12 and ADR-014 word the port. F-5 stays open and moves to "before outline item 2 is planned". If it is later answered as the audit proposed, a method is added then by `/spec-change`, and the exact method-set test of AC1 gains the name (the TASK-043 and TASK-044 precedent).
   - Alternative (a): decide F-5 now as the audit and advisor proposed, so `RunFiles` also gives the directory of a run, creating it (for example `run_dir(run_id: str) -> Path`), and the use case passes it as `output_dir`. This needs a `/spec-change` to the M3 paragraph and "Adapter interface", and an amendment of ADR-014's `RunFiles` bullet by the human, before this task starts. The task is then blocked until that is applied, and gains one criterion.
   - Alternative (b): decide F-5 now the other way: the use case builds `Path(".openfactory/runs") / run_id` itself ("the path follows from the run id") and each writer creates the directory when missing. This task is unchanged; item 2's adapter creates `output_dir` and resolves a relative one against its repo. It is a `docs/decisions.md` row plus a "Spec wording" Later line, as F-7 was handled.
2. **Signature and constructor.**
   - Proposed: `write(run_id: str, name: str, text: str) -> Path`, with the returned `Path` relative to the repo, as `WorkspaceManager.create` returns one; the use case stores `path.as_posix()` in `output_path`. `FilesystemRunFiles(repo: Path)`, as `GitWorktree(repo)`. Module names `ports/run_files.py` and `adapters/filesystem_run_files.py`.
   - Alternative (a): return `str` in POSIX form, as `SpecFiles` uses string paths, so the use case passes it to the payload unchanged.
   - Alternative (b): `write(run_id, gate, text)`, with the port appending `.txt`. This is narrower than the spec's "a file of a run".
   - Alternative (c): `text: bytes`. No M3 or M4 writer has bytes.
3. **Encoding, line endings and a repeated write.** The spec gives none of them for a run file.
   - Proposed: UTF-8, `newline=""` (the bytes are the text as given, so the file does not depend on the platform), and a second write of the same run and name replaces the file. AC2 fixes the first two; no test fixes the third.
   - Alternative: refuse to overwrite (open with `"x"`), which turns an orchestrator bug into an error at the cost of one more failure mode for the run use case.

## Outcome
Built as planned.
- `src/openfactory/ports/run_files.py`: Protocol `RunFiles` with `write(run_id: str, name: str, text: str) -> Path`.
- `src/openfactory/adapters/filesystem_run_files.py`: `FilesystemRunFiles(repo: Path)`. `write` creates `repo/.openfactory/runs/<run id>/` when missing (parents included), writes `text.encode("utf-8")` with `write_bytes`, and returns `Path(".openfactory/runs") / run_id / name`. It ends with the `TYPE_CHECKING` assertion.
- Tests: `tests/unit/test_run_files_port.py` (3) and `tests/integration/test_filesystem_run_files.py` (3). Full suite 1149 passed; ruff, pyright and check_docs clean.
- Deviation: the plan said to write with `newline=""`; the adapter uses `write_bytes(text.encode("utf-8"))`. The bytes are the same (an implementation detail, noted by the advisor).
- Test edits after the test-writer: none.
- Nothing calls the port yet; no `cli.py` wiring.
- Follow-ups (Later lines in `docs/progress.md`): audit F-5 reworded to be decided before the `AgentExecutor` task; `OSError` not caught; a repeated write replaces the file, no test; `run_id` and `name` not checked.
