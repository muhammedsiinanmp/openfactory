# TASK-030: `GitProvider` port and the `git_cli` adapter

- Milestone: M2
- Status: done
- Tests: acceptance
- ADR: ADR-012 (accepted, 2026-10-11). It decides that "`GitProvider` gets its first method, the tracked files of the repo (`git ls-files`), implemented by a new adapter `git_cli`", that the port arrives in M2 with this one method and M3 adds the rest, and that "Exact signatures are settled in the tasks that build them". ADR-006 covers the `TYPE_CHECKING` assertion. That is enough: no new ADR. The signature and the other answers under Open questions are rows in `docs/decisions.md`; one existing row already binds (2026-10-11, SC-50: "The text of a failed `git ls-files` is left to the `GitProvider` task").
- Spec impact: wording. One item, which does not block (see "Spec gaps").
- Spec sections (spec v1.11): "Tech stack and repo layout" (the "Git" row; the layout block's `ports/` and `adapters/` lines); "Domain model and storage" ("Ids": "The list of tracked files comes from `GitProvider`, whose first adapter is `git_cli`"); "Task contract" ("Planning": the bullet that starts "The planner receives one prompt and no tools"); "CLI commands" ("Other commands"; "Output": the refusal `git ls-files failed: <error>`)

## Objective
Add the `GitProvider` port with one method that returns the tracked files of the repo, and its `git_cli` adapter, which runs `git ls-files` in the repo and raises `GitError` with a text that is not empty when the command fails, so the plan use case can put the file list in the planner prompt without touching a process.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings.

## Scope
In (names per Open questions 1 and 2):
- `src/openfactory/ports/git_provider.py` (new):
  - Protocol `GitProvider` with one method, `tracked_files() -> list[str]`.
  - `GitError(Exception)`; its text is `str(error)`.
- `src/openfactory/adapters/git_cli.py` (new; the module name is the spec's):
  - `GitCli(repo: Path, executable: str = "git")` with `tracked_files`.
  - One `git ls-files` process per call, started with `repo` as its working directory.
  - Paths are returned as git gives them: relative to `repo`, with `/` as the separator, in git's order.
  - Ends with `if TYPE_CHECKING: _: type[GitProvider] = GitCli`.
- Tests: the success path runs the real `git` on a repository made under `tmp_path`; the failure path and the command line use a stand-in executable written under `tmp_path`.

Out (not this task):
- Every caller: the prompt and where the file list sits in it, the `git ls-files failed: <error>` line, taking the first line of the text, the order of the warning and the refusals (items 9 and 10).
- Wiring `GitCli` in `cli.py` (item 10).
- Every other `GitProvider` method (branches, commits, `git status --porcelain`, `git diff --name-only`, trailers), `WorkspaceManager` and `git_worktree` (M3).
- Changing the `init` check: it starts no `git` process (spec, "`init`") and stays as it is.
- Filtering the list (for example removing `specs/**`): the spec says "the list of tracked files".
- A time limit on the `git` process (Open question 4).
- Hardening: submodules, sparse checkouts, a `repo` that is a sub-directory of a repository, path names that are not valid UTF-8, output size limits, the language of git's messages.

## Acceptance criteria
"Ids" is under "Domain model and storage"; "Planning" is under "Task contract"; "Output" and "Other commands" are under "CLI commands". "The stand-in" is an executable script the test writes under `tmp_path`; it saves its arguments and its working directory to files, then prints what the test tells it to on standard output and standard error and exits with the status the test gives. "A test repository" is a directory under `tmp_path` on which the test ran `git init`; files are added with `git add` and nothing is committed, so no git identity is needed. The criteria are written for the proposals under Open questions.

- [x] AC1 ("Tech stack and repo layout": "`ports/ # interfaces: ..., GitProvider, LLMProvider`" and "`adapters/ # ..., git_cli, git_worktree`"; "the domain never imports infrastructure"; "Ids": "The list of tracked files comes from `GitProvider`, whose first adapter is `git_cli`"):
  - `openfactory.ports.git_provider` defines a Protocol `GitProvider` whose only public method is `tracked_files`, and imports nothing from `openfactory.adapters` or `openfactory.app` (checked by parsing its imports with `ast`).
  - `openfactory.adapters.git_cli` imports nothing from `openfactory.app`.
- [x] AC2 ("Planning": "the list of tracked files from `git ls-files`"; "Other commands": "run against the current directory"):
  - In a test repository with `a.py` and `pkg/b.py` added and `notes.txt` written but not added, `GitCli(repo).tracked_files()` returns `["a.py", "pkg/b.py"]`: the tracked files only, relative to the repository, with `/` as the separator.
  - The result is the same when the test's working directory is another directory: the adapter reads `repo`, not the process's working directory.
  - In a test repository with nothing added, it returns `[]`.
- [x] AC3 ("Tech stack and repo layout": the "Git" row, "Git CLI via `subprocess`"; "Planning": "from `git ls-files`"):
  - With `GitCli(repo, executable=<the stand-in>)` and the stand-in printing two path names in the form the adapter reads, `tracked_files()` returns those two names in the order printed.
  - The stand-in was started exactly once, its first argument was `ls-files`, and its working directory was `repo`.
- [x] AC4 ("Output": "`git ls-files failed: <error>`" and "`<error>` is the first line of the failure's text"):
  - The stand-in exits with status 128 and writes two lines to standard error: `tracked_files()` raises `GitError`, and the first line of `str(error)` is not empty.
  - The stand-in exits with status 1 and writes nothing: `GitError` is raised and the first line of its text is not empty.
  - With the real `git` and a directory under `tmp_path` that is not a repository, `GitError` is raised.
  - In each stand-in case it was started exactly once.

## Architecture rules that apply
- Ports hold Protocols only and import from `openfactory.domain` only. `GitError` sits beside its Protocol, as `LLMError` does in `ports/llm_provider.py` and `EventConflictError` in `ports/event_store.py`.
- The adapter ends with its `TYPE_CHECKING` assertion against `GitProvider` (ADR-006).
- Git operations stay behind `GitProvider` (ADR-011, ADR-012); `cli.py` is not changed here.
- No event is recorded and no projection is read or written.
- No new dependency: `subprocess` and `pathlib` only.
- Tests from the test-writer are fixed. No existing test is changed.
- No hardening beyond the spec's rules.

## Plan
1. Create branch `task/TASK-030-git-provider-git-cli` from an up-to-date main and commit this record.
2. Get the human's answers to the Open questions; record them here and as rows in `docs/decisions.md`.
3. Write failing tests:
   - `tests/unit/test_git_provider_port.py` for AC1, in the style of `tests/unit/test_llm_provider_port.py`.
   - `tests/integration/test_git_cli.py` for AC2 to AC4, with one helper that makes a test repository (`git init`, `git add`) and one that writes the stand-in (shebang `sys.executable`, mode 0o755), as `tests/integration/test_claude_code_llm.py` does.
4. Add `ports/git_provider.py`.
5. Add `adapters/git_cli.py`:
   - `subprocess.run` with the argument list of Open question 2, `cwd=repo`, `capture_output=True`, `text=True`, `encoding="utf-8"`, `check=False`.
   - A non-zero return code or an `OSError` on start raises `GitError` with the text of Open question 3.
   - Otherwise split standard output into path names and return the list.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until green.
7. Update the living docs and the Outcome. Commit `feat(adapters): add the GitProvider port and the git CLI adapter` with trailers `Task: TASK-030` and `Milestone: M2`.

## Files expected to change
- `src/openfactory/ports/git_provider.py` (new, about 25 lines)
- `src/openfactory/adapters/git_cli.py` (new, about 45 lines)
- `tests/unit/test_git_provider_port.py` (new, about 40 lines)
- `tests/integration/test_git_cli.py` (new, about 130 lines)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-030-git-provider-git-cli.md`

About 70 lines of source and 170 of tests.

Not expected to change: `cli.py`, everything under `app/` and `domain/`, the other modules under `ports/` and `adapters/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, and every existing test file.

## Living docs to update
- `docs/architecture.md`:
  - New sections "GitProvider port" and "Git CLI adapter", the second with the command run and the error texts.
  - "Data flow": the port exists for the plan use case and no use case calls it yet.
- `docs/progress.md`:
  - Current, then Done; remove outline item 8.
  - A Later line for the Spec gaps item.
- `docs/decisions.md`: rows for the answered questions, the error text among them (SC-50 left it to this task).
- `CHANGELOG.md`, `README.md`: no change (no command or output is added).

## New dependencies
None.

## Spec gaps
Spec impact is "wording". The one item does not block.

1. "Task contract" › "Planning": "the list of tracked files from `git ls-files`".
   - Unclear: the form of a path name. Plain `git ls-files` prints a name with a non-ASCII character quoted and escaped (`"caf\303\251.py"`); `git ls-files -z` prints the name itself. The sentence names the command and not the form.
   - Does not block: the meaning, the names of the tracked files, is clear, and both forms give the same list for ASCII names, which is all the criteria assert. The proposal is under Open question 2, and a Later line asks the spec to say that the names are given as they are, unquoted.

Already decided, not a gap of this task: "CLI commands" › "Output", "`git ls-files failed: <error>`" does not define the text behind `<error>`. The human decided on 2026-10-11 that the spec is not changed and that this task records the text as a decisions row and makes it non-empty (SC-50 row; audit F-4 and Q4 of `docs/spec-audits/2026-10-11-proposal-v1.11.md`). AC4 asserts only that the first line is not empty; the proposal is under Open question 3.

Readings, not gaps:
- "Tracked" is what `git ls-files` lists: a file that was added and not yet committed is listed, an untracked or ignored file is not. `.openfactory/` ignores itself, so it does not appear.
- The order of the list is git's order; nothing sorts it again.
- "Other commands run against the current directory", and `init` refuses a sub-directory of a repository, so `repo` is the repository's root and the names are relative to it. The composition root passes the directory (item 10).
- A `git` that cannot be started is a failed `git ls-files`: the refusal line names the command that failed, not a kind of failure.
- "It receives no file contents" is the prompt's rule (item 9); this port returns names only.

## Open questions
None is a spec decision that blocks. Each has a proposal.

Answered 2026-10-11: the human approved the proposal for each of the six questions. From the advisor's note on question 5, the tests that run the real `git` remove `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` from the environment first, so a run under the pre-push hook cannot act on this repository; the adapter is not changed for it.

1. **Names and signature.** ADR-012 leaves the signature to this task. Proposed: `GitProvider.tracked_files() -> list[str]` (plain strings, no domain model); `GitError(Exception)` in `ports/git_provider.py` beside the Protocol, with no extra fields; `GitCli(repo: Path, executable: str = "git")`, the second parameter so tests can point at the stand-in, as `ClaudeCodeLLM` has. Alternative: `tuple[str, ...]`; the error in a `domain/` module.
2. **The command.** Proposed: `git ls-files -z`, split on the NUL character, so every name is returned as it is (Spec gaps item 1). No criterion asserts a non-ASCII name; AC3 asserts only that the first argument is `ls-files`. Alternative: plain `git ls-files` split on lines, which returns non-ASCII names quoted and escaped; or `git -c core.quotePath=false ls-files`. A further alternative: add one bullet to AC2 with a non-ASCII file name, which fixes the unquoted form in a test before the spec states it.
3. **The text of `GitError`.** It becomes, by its first line, the `git ls-files failed: <error>` line (SC-50). Proposed: a non-zero exit gives standard error stripped, or `git exited with status N` when that is empty; a `git` that cannot be started gives `git could not be started: <the OS error's text>`. AC4 asserts only that the first line is not empty; no criterion covers a `git` that cannot be started, as in TASK-029. Alternative: fix the texts in criteria.
4. **No time limit.** The spec gives a limit for planner and classifier calls only. Proposed: the `git` process has none. Alternative: a fixed limit and a `GitError` when it passes.
5. **Tests that run the real `git`.** AC2 and one bullet of AC4 need the `git` binary; they run `git init` and `git add` under `tmp_path` and never commit. The spec's stack is "Git CLI via `subprocess`", and M2's close test (item 13) needs a real repository anyway. Proposed: yes; the suite then requires `git` on the machine. Alternative: stand-in only, which leaves nothing to prove that real `git ls-files` output is read correctly.
6. **The wording item and this task.** Proposed: it does not block (Spec gaps item 1); a Later line carries it. Alternative: settle it by `/spec-change` first.

## Outcome
**Built.**
- `ports/git_provider.py`: Protocol `GitProvider` with `tracked_files() -> list[str]`, and `GitError(Exception)`.
- `adapters/git_cli.py`: `GitCli(repo, executable="git")`; one `git ls-files -z` process per call in `repo`, no time limit, output split on NUL with empty elements dropped; a non-zero exit raises `GitError` with standard error stripped, or `git exited with status N`; an `OSError` on start raises `GitError("git could not be started: <OS error text>")`. Ends with the `TYPE_CHECKING` assertion. `cli.py` unchanged; no use case calls it yet.
- Tests: `tests/unit/test_git_provider_port.py` (AC1), `tests/integration/test_git_cli.py` (AC2 to AC4). The suite now requires `git`.
- Decisions are rows in `docs/decisions.md`; architecture, progress updated. README already lists git as a prerequisite; CHANGELOG unchanged.

**Deviations from plan.**
- The record was not committed separately in plan step 1; there is one commit at the end, per the /next-task workflow.
- The tests remove `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` from the environment with an autouse fixture (from the advisor's note on Open question 5).
- No test edits after the test-writer; no existing test changed.

**Follow-ups.**
- Later line in `docs/progress.md` for the spec wording item on the form of a path name.
- Out of scope as recorded: a path name that is not valid UTF-8, and a `warning:` line before `fatal:` in standard error.
