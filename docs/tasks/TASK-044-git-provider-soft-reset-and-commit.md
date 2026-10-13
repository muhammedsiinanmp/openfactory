# TASK-044: `GitProvider` for `run`, the rest: the soft reset and the commit

- Milestone: M3
- Status: done
- Tests: acceptance
- ADR: ADR-014 (accepted). "Ports and adapters (SC-63, SC-68)": "`GitProvider`, adapter `git_cli`, gains: ... a soft reset of a branch, and making a commit. These take the worktree's path." "How accepted ADRs are read from now on": "the orchestrator resets the branch to `<base>` with the changes kept, and every commit on a task branch is its own." ADR-012 (accepted) covers "Exact signatures are settled in the tasks that build them"; ADR-006 covers the `TYPE_CHECKING` assertion. No new port, adapter, dependency, event type, payload or storage change. Names, signatures and the commands not fixed by the spec are rows in `docs/decisions.md` (Open questions 1 to 4).
- Spec impact: wording. One item, which does not stop the task (see "Spec gaps"): whether the stored commit message must equal the built message exactly, given git's message clean-up.
- Spec sections (spec v1.12, SC-63, SC-65, SC-66): "Domain model and storage" (the M3 paragraph after "Ids"); "Execution" › "Per-task sequence" (step 6), "Base and branches", "The commit", "Events of one task" (the git failure bullet); "Traceability" › "Commit trailers"

## Outline item
M3 outline item 1, the second half, which finishes the item. TASK-043 built the three operations used before the commit. Items 2 to 9 are left.

## Objective
Give `GitProvider` and `GitCli` a soft reset of a worktree's branch to a commit and an operation that commits what is staged in a worktree with a given message and returns the new commit's sha, so the run use case can discard an agent's commits, make its own and record `CommitRecorded` without touching a process.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings and to SC-63, SC-65 and SC-66.

## Scope
In (names, signatures and commands per Open questions 1 to 4):
- `src/openfactory/ports/git_provider.py`:
  - `reset_soft(worktree: Path, base: str) -> None`: moves the branch checked out in the worktree to `base` and keeps the changes staged.
  - `commit(worktree: Path, message: str) -> str`: commits what is staged in the worktree with `message` and returns the sha of the new commit.
  - Both paths are required: neither operation is ever made on the checkout ("The human's checkout and branches never change").
- `src/openfactory/adapters/git_cli.py`:
  - `reset_soft`: one process, `git reset --soft <base>`.
  - `commit`: `git commit --no-verify -m <message>`, then `git rev-parse --verify HEAD` for the sha. The second process is not started after a failed commit.
  - Both use the existing `_run` and `_checked`; the `GitError` texts are unchanged.
  - No identity, author, signing or `--allow-empty` option is passed.
  - The `TYPE_CHECKING` assertion stays the last statement.
- Tests: a new integration file, on a real repository with a linked worktree made by the test, and a stand-in executable for the command lines and the failures.
- The one edit to a fixed test that the new methods force: the exact method set in `tests/unit/test_git_provider_port.py` gains the two names. It is approved in advance (TASK-043, answer 1 of 2026-10-13, `docs/decisions.md`), reported in the Outcome and checked by the reviewer.

Out (not this task):
- Building the message: subject cut to 72 characters, body, trailers (item 5). The tests pass a literal message.
- Every caller: the condition "if the branch tip is not `<base>`", the order of the reset against the path check, `CommitRecorded`, the `git: <first line of the error>` reason (item 6). Nothing calls the new methods yet.
- `WorkspaceManager` and `git_worktree` (item 2). The tests make their worktree with `git worktree add`.
- Any change to `cli.py`, `app/`, `domain/`, and the `FakeGit` in `tests/unit/test_plan_entry.py`.
- The environment given to `git` (the Later line from TASK-030): it stays for item 2. The tests remove the variables themselves.
- Audit F-7, F-5 and F-1: none touches this task (see "Spec gaps", readings).
- Hardening: a commit with nothing staged beyond "the command fails", a `base` that is not a commit beyond "the command fails", a repo with no configured identity beyond "the command fails", `prepare-commit-msg` and `post-commit` hooks, commit signing set in the repo's config, a message too long for one argument, a time limit on `git` (decision of 2026-10-11: none).

## Acceptance criteria
"The M3 paragraph" is the paragraph after "Ids" under "Domain model and storage". The other headings are under "Execution" unless "Traceability" is named.

Terms used in the criteria:
- **A test repository** is a directory under `tmp_path` made with `git init`, with `user.name` `Test`, `user.email` `test@example.com` and `commit.gpgsign false` in its own config.
- **`BASE`** is the sha of the test repository's first commit, which holds `app/a.py`.
- **The worktree** is made by the test with `git worktree add <path> -b openfactory/AUTH-002 BASE`, at an absolute path.
- **The agent's work** is made by the test in the worktree: `docs/c.md` is added and committed (the agent's commit, sha `AGENT`), `app/a.py` is changed and `app/new.py` is written, neither added.
- **`MESSAGE`** is the spec's example: the subject `AUTH-002: Implement login endpoint using membership number`, a blank line, a one-line body, a blank line, and the five trailer lines of "Commit trailers", ending with one newline.
- **The stand-in** is an executable script under `tmp_path` that appends its arguments and working directory to a file on each start, prints what the test gives it and exits with the status given.

Every test removes `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE` and the `GIT_AUTHOR_*` and `GIT_COMMITTER_*` variables from the environment. The criteria are written for the proposals under Open questions.

- [x] AC1 (the M3 paragraph: "`GitProvider` also gives the commit `HEAD` points at and the tracked files of a worktree, stages the changes of a worktree and lists the paths that differ from a commit, resets a branch softly, and makes a commit; these operations take the worktree's path"):
  - `GitProvider` is a Protocol whose public methods are exactly `tracked_files`, `head_commit`, `stage_changes`, `reset_soft` and `commit`.
  - The two import tests in `tests/unit/test_git_provider_port.py` pass unchanged.
  - `uv run pyright` passes with the `TYPE_CHECKING` assertion at the end of `git_cli.py` unchanged.
- [x] AC2 ("The commit": "if the branch tip is not `<base>` when the agent exits, the orchestrator resets the branch to `<base>` with `git reset --soft`, which keeps the changes staged"; "Base and branches": "The human's checkout and branches never change"):
  - With the agent's work in the worktree, the test calls `stage_changes(worktree, BASE)` and keeps the result, then `reset_soft(worktree, BASE)`.
  - `head_commit(worktree)` is `BASE`, and `git rev-parse openfactory/AUTH-002` in the repo is `BASE`.
  - `git diff --cached --name-only BASE` in the worktree lists `app/a.py`, `app/new.py` and `docs/c.md`, and a second `stage_changes(worktree, BASE)` gives the same paths as the first.
  - `git status --porcelain` and `git rev-parse HEAD` in the checkout give the same output before and after.
- [x] AC3 ("The commit": "so every commit on the branch is the orchestrator's. "The agent never commits" means that no commit of the agent survives. The orchestrator commits what the path check staged"; "Per-task sequence" step 6: "the orchestrator itself commits with trailers"; "Traceability" › "Commit trailers": "The trailers are the last paragraph of the message"):
  - After the steps of AC2, `commit(worktree, MESSAGE)` returns a string of 40 lowercase hex characters that equals `git rev-parse HEAD` in the worktree and is not `AGENT`.
  - The new commit's only parent is `BASE`: `git rev-list BASE..HEAD` in the worktree has one line.
  - `git diff --name-only BASE HEAD` in the worktree lists `app/a.py`, `app/new.py` and `docs/c.md`, and `git status --porcelain` there is empty.
  - `git log -1 --format=%B` in the worktree, with trailing newlines removed, equals `MESSAGE` with trailing newlines removed.
  - `git log -1 --format='%(trailers:key=Task,valueonly)'` gives `AUTH-002`, and the same with `key=Agent-Run` gives `run_0091`.
  - `git status --porcelain` and `git rev-parse HEAD` in the checkout give the same output before and after.
- [x] AC4 ("The commit": "with `--no-verify`, under the repo's configured git identity"):
  - The test repository has executable `pre-commit` and `commit-msg` hooks in `.git/hooks` that exit 1. `commit(worktree, MESSAGE)` on staged changes still returns a sha.
  - The new commit's author and committer are both `Test <test@example.com>` (`git log -1 --format='%an <%ae>|%cn <%ce>'`).
- [x] AC5 (the M3 paragraph: "these operations take the worktree's path"; "The commit": the two commands as quoted in AC2 and AC4; "Events of one task": "A git command that fails while a task is `running` or `gating` moves the task to `failed` with reason `git: <first line of the error>`"):
  - With `GitCli(repo, executable=<the stand-in>)`: `reset_soft(worktree, BASE)` starts the stand-in once, with the arguments `reset --soft <BASE>` and the worktree as its working directory.
  - With the stand-in printing a 40-character sha and a newline: `commit(worktree, MESSAGE)` returns that sha without the newline. The stand-in was started exactly twice, both times in the worktree: first with `commit --no-verify -m <MESSAGE>` (the message one argument, unchanged), then with `rev-parse --verify HEAD`.
  - With the stand-in exiting 128 and writing two lines to standard error: `reset_soft` and `commit` each raise `GitError` whose first line is not empty, and for `commit` the stand-in was started once.
  - In a real worktree with nothing staged, `commit(worktree, MESSAGE)` raises `GitError` with a text that is not empty, and `head_commit(worktree)` is still `BASE`.

## Architecture rules that apply
- `ports` holds Protocols only and imports from `openfactory.domain` only. The new methods use `pathlib.Path` and plain strings; no domain model is added.
- The adapter ends with its `TYPE_CHECKING` assertion against `GitProvider` (ADR-006).
- Every git command stays behind `GitProvider` (ADR-011, ADR-014). `cli.py` and `app/` are not changed.
- No event is recorded and no projection is read or written.
- No new dependency.
- The working directory is given with `cwd=`, not `git -C <path>`, as TASK-043 fixed.
- Tests from the test-writer are fixed. The one edit to `tests/unit/test_git_provider_port.py` is covered by the approval of 2026-10-13 and is reported in the Outcome.
- OpenFactory's own tests carry no `req` markers.
- No hardening beyond what the spec asks.

## Plan
1. Create branch `task/TASK-044-git-provider-soft-reset-and-commit` from an up-to-date main.
2. Get the human's answers to Open questions 1 to 4. Record them here and as rows in `docs/decisions.md`.
3. Write failing tests in `tests/integration/test_git_cli_commit.py` (new) for AC2 to AC5: its own autouse fixture for the git variables, helpers for the test repository, the worktree and the agent's work, and a stand-in that appends each start's arguments and working directory to a JSON-lines file.
4. Add `reset_soft` and `commit` to the exact set in `tests/unit/test_git_provider_port.py` and change nothing else in that file.
5. Add the two Protocol methods to `ports/git_provider.py`, with docstrings.
6. Add `reset_soft` and `commit` to `adapters/git_cli.py` on `_run` and `_checked`. Confirm against the real `git` the three behaviours the planner did not run: the default clean-up for `-m`, that `--no-verify` skips the two hooks of AC4, and the exit status and output of a commit with nothing staged.
7. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green. `tests/integration/test_git_cli.py` and `tests/integration/test_git_cli_m3.py` must pass unchanged.
8. Update the living docs and the Outcome. Commit `feat(adapters): reset a task branch softly and make the commit` with trailers `Task: TASK-044` and `Milestone: M3`.

## Files expected to change
- `src/openfactory/ports/git_provider.py` (about 20 lines)
- `src/openfactory/adapters/git_cli.py` (about 15 lines)
- `tests/integration/test_git_cli_commit.py` (new, about 200 lines)
- `tests/unit/test_git_provider_port.py` (the exact method set, two names added)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-044-git-provider-soft-reset-and-commit.md` (this record; Outcome at close)

Not expected to change: `cli.py`, every module under `app/` and `domain/`, the other modules under `ports/` and `adapters/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, `tests/integration/test_git_cli.py`, `tests/integration/test_git_cli_m3.py`, `tests/unit/test_plan_entry.py` and every other test file.

Expected size: about 240 lines with tests.

## Living docs to update
- `docs/architecture.md`:
  - "GitProvider port": five methods, the two new signatures, the required path.
  - "Git CLI adapter": the two commands, that `commit` starts two processes and stops after a failed commit, the new test file.
  - "Data flow": the two operations exist for the run use case and nothing calls them yet.
- `docs/progress.md`:
  - Current, then Done.
  - Outline item 1 removed; the numbering and the "depends on" references of the remaining items adjusted, or kept with item 1 struck, as the human prefers.
  - The Later lines listed below.
- `docs/decisions.md`: rows for the answered open questions.
- `CHANGELOG.md` and `README.md`: no change (nothing a user sees).

## New dependencies
None.

## Spec gaps
Spec impact is "wording". The one item does not stop the task.

1. "Traceability" › "Commit trailers": "The body is the run's `summary`", with "Execution" › "The commit": "The orchestrator commits what the path check staged, with `--no-verify`".
   - Unclear: whether the stored message must equal the built message exactly. Git cleans a message given on the command line: by default it removes trailing whitespace and collapses runs of blank lines, and a target repo that sets `commit.cleanup = strip` would also drop lines that start with `#`, which a summary written as Markdown can have.
   - Does not block: the meaning is clear (commit that message, trailers last), and the trailers survive every clean-up mode, so the graph stays rebuildable. Whether the adapter passes a `--cleanup` flag is Open question 4 for the human, not an assumption of the task. `MESSAGE` in the criteria is one that the default clean-up leaves unchanged.

Readings, not gaps (each follows from the text as written):
- "Resets a branch softly" with "take the worktree's path": the reset runs in the worktree and moves the branch checked out there, which is `openfactory/<task id>`.
- "If the branch tip is not `<base>`" is the caller's condition; the use case has `head_commit(worktree)` for it. The adapter resets whenever it is called.
- The order of the reset against the path check is the run use case's (item 6). A soft reset does not touch the index, so AC2 holds for either order.
- "Under the repo's configured git identity": the adapter passes no identity option. A repo with none configured makes the commit fail, which is a `GitError` and so the `git: <first line of the error>` reason.
- "A run that changed no path ... nothing is committed": the use case never calls `commit` with nothing staged, so the adapter passes no `--allow-empty`, and such a call fails.
- `CommitRecorded` needs the sha, so making a commit yields it. Whether `commit` returns it or the caller reads `HEAD` is a signature (Open question 1).
- Audit F-7 (where the use case gets the worktree's path) is settled before the `WorkspaceManager` task; whatever the answer, the use case hands a path to these methods. Audit F-5 is the `RunFiles` task's. Audit F-1 is the run use case's; this task only raises `GitError`.

## Later lines in `docs/progress.md`: taken or left
- "Spec gap ... F-7 ... F-5 ... F-1": left, unchanged.
- "`GitCli` passes the caller's environment to `git` ...": left for item 2. At close it gains: "since TASK-044 `git_cli` also runs `git reset --soft` and `git commit`, and `GIT_AUTHOR_*` or `GIT_COMMITTER_*` set in the environment override the repo's configured identity".
- "a `warning:` line before `fatal:`": left. At close it gains that the same holds for `reset_soft` and `commit`.
- "`test_ac1_git_provider_is_a_protocol_with_only_tracked_files` keeps a name its assertion no longer matches": left; at close "three names" becomes "five names".
- Every other Later line: left.
- To add at close:
  - "Spec wording: "Traceability" › "Commit trailers", "The body is the run's `summary`" does not say whether the stored message must equal the built one; git's clean-up applies to it (TASK-044, planner)", with the answer to Open question 4.
  - "`--no-verify` skips the `pre-commit` and `commit-msg` hooks only; a `prepare-commit-msg` hook of the target repo can still change the message and a `post-commit` hook still runs. Not checked by the planner; no test (TASK-044, planner)".
  - "A target repo with `commit.gpgsign true` signs the orchestrator's commits, and a signing failure fails the task with a `git:` reason; the spec does not mention signing (TASK-044, planner)".

## Open questions
None is a spec decision that blocks. Each has a proposal.

Answered by the human on 2026-10-13: the proposal is taken for all four (advisor: 4 AGREE). Rows are in `docs/decisions.md`.

1. **Names and signatures.** ADR-012 leaves them to the task. Proposed:
   - `reset_soft(worktree: Path, base: str) -> None`.
   - `commit(worktree: Path, message: str) -> str`, returning the new commit's sha.
   - Both paths required, with no `None` for the checkout.
   - Alternative: `commit` returns `None` and the use case calls `head_commit(worktree)` afterwards, which leaves the use case to treat a `None` there.
2. **How `commit` gets the sha.**
   - Proposed: a second process, `git rev-parse --verify HEAD` in the worktree, started only after a successful commit.
   - Alternative: parse the `[branch sha] subject` line `git commit` prints, which is abbreviated and meant for people.
3. **How the message reaches git.**
   - Proposed: `git commit --no-verify -m <message>`, the message as one argument.
   - Alternative: `git commit --no-verify -F -` with the message on standard input. It has no argument-length limit, and needs an `input` parameter on `_run` and a stand-in that records standard input.
4. **Message clean-up** (Spec gaps, item 1).
   - Proposed: no `--cleanup` flag. Git's default and the repo's config apply, with a Later line.
   - Alternative: `--cleanup=verbatim`, which stores the message byte for byte and adds a flag the spec does not name.
   - Unchecked: the planner did not run git. The implementer confirms the default mode for `-m` in step 6.

## Outcome
- Built: `GitProvider` gains `reset_soft(worktree: Path, base: str) -> None` and `commit(worktree: Path, message: str) -> str`, both paths required. `GitCli.reset_soft` runs `git reset --soft <base>`; `commit` runs `git commit --no-verify -m <message>` and then `git rev-parse --verify HEAD`, the second not started after a failed commit. Both use `_run` and `_checked`; no `--cleanup`, identity, signing or `--allow-empty` option. New `tests/integration/test_git_cli_commit.py` (8 tests, AC2 to AC5) on real git with a linked worktree and a stand-in executable. Nothing calls the new methods yet.
- Deviations from the plan: none.
- Outline numbers: "item 2", "item 5" and "item 6" in this record are the numbers before item 1 was removed from the M3 outline; they are now items 1, 4 and 5.
- Reviewer: approve on the first pass, no blocking issue. Its three non-blocking notes: the outline numbers (the line above), the "Spec wording" prefix on two Later lines (applied), and the AC4 hook test, which is a fixed test and is left as a Later line.
- Fixed-test edit (approved in advance, `docs/decisions.md`, TASK-043 row of 2026-10-13): the exact method set in `test_ac1_git_provider_is_a_protocol_with_only_tracked_files` (`tests/unit/test_git_provider_port.py`) gained `reset_soft` and `commit`, now five names; the name is kept. No other test edit.
- Confirmed against git 2.54.0 (Apple Git-157) by the test-writer: the default clean-up for `git commit -m` is `whitespace` (a `#` line is kept, a run of blank lines collapses to one); `--no-verify` skips failing `pre-commit` and `commit-msg` hooks, read for a linked worktree from the main repository's `.git/hooks`; `git commit` with nothing staged exits 1 with its text on standard output and empty standard error, so the `GitError` text is `git exited with status 1`.
- Checks: 1133 tests pass, ruff clean, pyright clean, `check_docs.py` passes.
- Follow-ups (Later lines in `docs/progress.md`): the "Commit trailers" spec-wording line with the answer to Open question 4; `prepare-commit-msg` and `post-commit` hooks not checked; `commit.gpgsign`; the `git exited with status 1` text for an empty commit; the `GitCli` environment line, the `warning:` line and the renamed-test line extended for TASK-044.
