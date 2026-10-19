# TASK-063: `GitProvider.staged_diff` and `RunFiles.read`

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-015 (accepted). Its "Ports and adapters" section says: "`GitProvider` gains the text of `git diff --cached <base>` in a worktree, for the reviewer." and "`RunFiles` gains a read of a run file by the path `write` returned, for the failure report." ADR-006 covers the layers and the `TYPE_CHECKING` assertion. The task adds no new port, adapter, dependency, event, payload or storage change, and no new convention. The answers to the open questions become rows in `docs/decisions.md`.
- Spec impact: wording. Three items, none of which blocks (see "Spec gaps").
- Spec sections (spec v1.16; SC-87, SC-89):
  - "Domain model and storage", the M4 paragraph after "Ids": "M4 adds what the gates and the retry need. `GitProvider` also gives the text of `git diff --cached <base>` in a worktree, for the reviewer. `RunFiles` also reads a run file by the path it returned."
  - "Gates and remediation" › "The review gate": "Its prompt is the task contract and the text of `git diff --cached <base>` in the worktree."
  - "Gates and remediation" › "Remediation": "The failure report of the previous attempt is ... for each gate that failed in that attempt, its name and the text of its output file. ... and the file text through `RunFiles`."

## Outline item
This is the first half of M4 outline item 4: the staged diff on `GitProvider` and `RunFiles.read`. The last gate result of a task on `Plans` (SC-92, for `status`) stays in item 4 as the next task. The first callers are item 8 (review gate) and item 10 (failure report).

## Objective
Give the run use case the text of `git diff --cached <base>` in a task's worktree, and a read of a run file by the path `RunFiles.write` returned.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/ports/git_provider.py`: add `staged_diff(worktree: Path, base: str) -> str`, the text of `git diff --cached <base>` in `worktree`. The path is required. A failed command raises `GitError`.
- `src/openfactory/adapters/git_cli.py`: `GitCli.staged_diff` runs exactly `git diff --cached <base>` through the existing `_run` and `_checked`, and returns standard output unchanged (not stripped). `_run` gains an `errors` keyword that defaults to `"strict"`; `staged_diff` passes `"replace"` (answer 2).
- `src/openfactory/ports/run_files.py`: add `read(path: Path) -> str`, the text of the run file at `path`, where `path` is relative to the repo as `write` returned it.
- `src/openfactory/adapters/filesystem_run_files.py`: `FilesystemRunFiles.read` reads `self._repo / path` as bytes and decodes it as UTF-8, so the text comes back exactly as written. An `OSError` is not caught, as in `write`.
- Tests:
  - New `tests/integration/test_git_cli_staged_diff.py` (real git with a linked worktree, plus a stand-in `git`).
  - New tests in `tests/integration/test_filesystem_run_files.py`.
  - Two approved test edits: the exact method-set assertions in `tests/unit/test_git_provider_port.py` (five names become six, adding `staged_diff`) and `tests/unit/test_run_files_port.py` (`{"write"}` becomes `{"write", "read"}`). Test names are kept, as in TASK-043 and TASK-044, and a Later line is added for the names.

Out:
- Any call from `app/run.py` or `cli.py`. The review gate is item 8 and the failure report is item 10.
- `Plans.last_gate_result` and `SqlitePlans`. These are the next task, still in item 4.
- Changing the existing fakes in `tests/unit/test_run_task.py` and `tests/unit/test_run_plan.py`. Pyright checks only `src`, and nothing calls the new methods.
- Changing `_run`'s default decoding (strict UTF-8) for the other methods, or the environment passed to `git` (decision of 2026-10-13).
- Handling a missing or unreadable run file in the use case. The spec names no outcome for it.

## Acceptance criteria
- [x] **AC1** ("Domain model and storage", the M4 paragraph: "`GitProvider` also gives the text of `git diff --cached <base>` in a worktree ... `RunFiles` also reads a run file by the path it returned").
  - `GitProvider` is a Protocol with exactly `tracked_files`, `head_commit`, `stage_changes`, `reset_soft`, `commit` and `staged_diff`.
  - `RunFiles` is a Protocol with exactly `write` and `read`.
  - Neither port module imports from `adapters` or `app`, and both adapters keep their `TYPE_CHECKING` assertions.
- [x] **AC2** ("The review gate": "the text of `git diff --cached <base>` in the worktree"). On real git, in a linked worktree branched from `<base>`, after `stage_changes(worktree, base)`, `GitCli.staged_diff(worktree, base)` returns the same string as `git diff --cached <base>` run in that worktree.
  - The text holds a modified tracked file and a new file.
  - A file created in the worktree after staging (as a gate's cache would be) is not in the text.
  - With nothing staged against `<base>`, the text is `""`.
- [x] **AC3** (same sentence; the `git: <first line>` reason of "Events of one task" needs a `GitError`). With a stand-in `git`:
  - `staged_diff` starts exactly one process, with the arguments `diff --cached <base>`, in `repo / worktree`.
  - Standard output that is not valid UTF-8 comes back with replacement characters, not an exception.
  - A non-zero exit raises `GitError` with standard error stripped, or `git exited with status N` when standard error is empty.
  - A `git` that cannot be started raises `GitError` with `git could not be started: <OS error>`.
- [x] **AC4** ("Remediation": "the text of its output file ... the file text through `RunFiles`"; the M4 paragraph: "by the path it returned"). For the path `FilesystemRunFiles.write(run_id, name, text)` returned, `read(path)` gives back `text` exactly, including non-ASCII characters, `\r\n` and a missing final line break. The path is resolved against the adapter's `repo`, whatever the process's working directory.

## Architecture rules that apply
- Ports are Protocols only. Adapters implement them and end with their `TYPE_CHECKING` assertion.
- No event, projection, payload or schema change, and no new dependency.
- `app/` and `cli.py` are unchanged.
- No hardening beyond the spec. Paths are not checked, as for `write`.

## Plan
1. Create branch `task/TASK-063-git-staged-diff-and-run-files-read` from an up-to-date main.
2. Answers recorded (see "Answers"); rows added to `docs/decisions.md`.
3. Test-writer: write failing tests for AC1 (the two approved method-set edits), AC2 and AC3 (`tests/integration/test_git_cli_staged_diff.py`, new) and AC4 (`tests/integration/test_filesystem_run_files.py`).
4. Add the two Protocol methods and the two adapter methods.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
6. Update the living docs and the Outcome. Commit `feat(ports): add the staged diff and the run file read` with the trailers `Task: TASK-063` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/ports/git_provider.py` (about +8)
- `src/openfactory/adapters/git_cli.py` (about +3)
- `src/openfactory/ports/run_files.py` (about +7)
- `src/openfactory/adapters/filesystem_run_files.py` (about +3)
- `tests/integration/test_git_cli_staged_diff.py` (new, about 130)
- `tests/integration/test_filesystem_run_files.py` (about +40)
- `tests/unit/test_git_provider_port.py` and `tests/unit/test_run_files_port.py` (one assertion each)
- `docs/architecture.md`:
  - "GitProvider port" and "Git CLI adapter": six methods, the `staged_diff` command line.
  - "RunFiles port" and "Filesystem run files": `read`.
  - Data flow: nothing calls them yet.
- `docs/progress.md`: Current, Done, outline item 4 narrowed to the `Plans` read, Later lines.
- `docs/decisions.md`: rows for the answers.
- `docs/tasks/TASK-063-git-staged-diff-and-run-files-read.md` (this record, with the Outcome at close).

Not expected to change: `domain/`, `ports/plans.py`, `adapters/sqlite_plans.py`, `app/`, `cli.py`, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 230 lines with tests, about 20 of them in `src/`.

## Spec gaps
Spec impact is "wording". None of the three items blocks, because none of them changes what the reviewer or the failure report is given. Each has an Open question below, and no answer is assumed.

1. **"Gates and remediation" › "The review gate"** and the M4 paragraph, "the text of `git diff --cached <base>`".
   - Unclear: the spec writes the bare command. It does not say whether the user's or repo's git configuration (`color.diff=always`, `diff.external`, `diff.noprefix`, rename detection) may shape the text, or whether flags such as `--no-color --no-ext-diff` are added.
   - Why it does not block: the default configuration gives plain text either way, and the reviewer reads text. → Open question 1.
2. **Same sentence.** The spec gives no decoding for the diff text. `GitCli._run` decodes standard output as strict UTF-8, so a staged text file that is not valid UTF-8 would raise `UnicodeDecodeError`, not `GitError`. This matches the existing Later line on `tracked_files` and `stage_changes`. Binary files show as "Binary files ... differ" by default.
   - Why it does not block: an exotic input that the spec does not ask us to handle. → Open question 2.
3. **"Domain model and storage"**, "`RunFiles` also reads a run file by the path it returned".
   - Unclear: the spec names no signature or argument type (`GateEvaluated.output_path` is stored as a POSIX string, and `write` returns a `Path`), no decoding, and no outcome for a missing file.
   - Why it does not block: the only caller reads paths that `write` produced in the same repo. → Open question 3.

## Open questions
1. **Command line of `staged_diff`.**
   - Proposed: exactly `git diff --cached <base>`, as the spec writes it, with no added flag. The repo's and the user's configuration apply, as for `commit` (decision of 2026-10-13).
   - Alternative: `git diff --cached --no-color --no-ext-diff <base>`, so that configuration cannot add colour codes or call an external diff tool.
2. **Decoding of the diff text.**
   - Proposed: the existing `_run` (strict UTF-8). A file that is not valid UTF-8 extends the existing Later line on `UnicodeDecodeError`.
   - Alternative: decode this one command with `errors="replace"`, as `process_gates` does for gate text (decision of 2026-10-16).
3. **Shape of `RunFiles.read`.**
   - Proposed: `read(path: Path) -> str`, with `path` relative to the repo as `write` returned it. The caller passes `Path(output_path)`. Bytes are decoded as strict UTF-8, matching `write`'s encoding. A missing file raises the `OSError` (not caught), as `write` does.
   - Alternative (a): `read(run_id, name) -> str`, mirroring `write`. This departs from the spec's "by the path it returned".
   - Alternative (b): a missing file gives `None`.

## Answers (human, 2026-10-19: "do as the advisor says")
1. Exactly `git diff --cached <base>`, no added flag; config applies. A Later line records the `diff.external` hang risk (no timeout in `_run`).
2. `errors="replace"` for `staged_diff` only, through an `errors` keyword on `_run` defaulting to `"strict"`.
3. `read(path: Path) -> str`, repo-relative as `write` returned it, strict UTF-8 from bytes, a missing file raises `OSError`.

## Later lines in `docs/progress.md`
- Taken: none.
- Added:
  - The three "Spec wording" lines, with the answers.
  - The kept names of the two edited method-set tests.
  - The `diff.external` hang risk of `staged_diff`.

## Outcome
Added `GitProvider.staged_diff` and `GitCli.staged_diff` (exactly `git diff --cached <base>`, standard output unstripped, decoded with `errors="replace"` through a new `errors` keyword on `_run` that defaults to `"strict"`) and `RunFiles.read` and `FilesystemRunFiles.read` (repo-relative path, bytes decoded strict UTF-8, `OSError` not caught). Behaviour follows the answers of 2026-10-19. Tests: new `tests/integration/test_git_cli_staged_diff.py`, new tests in `tests/integration/test_filesystem_run_files.py`, and the two approved method-set edits in `tests/unit/test_git_provider_port.py` and `tests/unit/test_run_files_port.py`, names kept. The implementer made no test edits; on the reviewer's non-blocking note, with the human's go-ahead, it added one test, `test_task063_ac4_read_of_a_missing_file_raises_os_error`, which pins the decided `OSError` on a missing file. Nothing calls the new methods yet; the review gate (outline item 8) and the failure report (item 10) are the first callers.

Living docs: `docs/architecture.md` (GitProvider port, Git CLI adapter, RunFiles port, Filesystem run files, data flow), `docs/progress.md` (Current, Done, outline item 4 narrowed to the `Plans` read, Later lines), `docs/decisions.md` (three rows), all in this task's commit.
