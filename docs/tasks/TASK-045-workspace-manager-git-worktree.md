# TASK-045: `WorkspaceManager` port and the `git_worktree` adapter

- Milestone: M3
- Status: done
- Tests: acceptance
- ADR: ADR-014 (accepted). "Ports and adapters (SC-63, SC-68)": "`WorkspaceManager`, adapter `git_worktree`: creates and removes a task's worktree (`.openfactory/worktrees/<task id>`) and branch (`openfactory/<task id>`)." ADR-001 and ADR-012 (accepted) cover "Exact signatures ... are settled in the tasks that build them"; ADR-006 covers the `TYPE_CHECKING` assertion. The new port and adapter are the ones ADR-014 decides; no new dependency, event type, payload or storage change. Names, signatures and the commands the spec does not fix are rows in `docs/decisions.md` (Open questions 1 to 4).
- Spec impact: wording. Two items, neither stops the task (see "Spec gaps"): the M3 paragraph does not say where the use case gets the worktree's path (audit F-7), and it names one removal where the sequence needs two.
- Spec sections (spec v1.12, SC-56, SC-60, SC-62, SC-68): "Domain model and storage" (the M3 paragraph after "Ids"); "Execution" › "Per-task sequence" (steps 1 and 6), "Base and branches", "Events of one task" (the git failure bullet), "Restart"

## Outline item
M3 outline item 1. Items 2 to 8 are left.

## Objective
Give the run use case a `WorkspaceManager` port, with the `git_worktree` adapter behind it, that creates a task's worktree and branch from a commit and removes them, so the per-task sequence and the repair can do both without touching a process.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings and to SC-56, SC-60, SC-62 and SC-68.

## Scope
In (names, signatures and commands per Open questions 1 to 4):
- `src/openfactory/ports/workspace_manager.py` (new): Protocol `WorkspaceManager` with three methods.
  - `create(task_id: str, base: str) -> Path`: creates the worktree `.openfactory/worktrees/<task id>` on the new branch `openfactory/<task id>` at the commit `base`, and returns the worktree's path relative to the repo.
  - `remove(task_id: str) -> None`: removes the task's worktree and branch, each only if it exists.
  - `remove_worktree(task_id: str) -> None`: removes the task's worktree if it exists; the branch stays.
  - A failed git command raises `GitError`, imported from `ports/git_provider.py`.
- `src/openfactory/adapters/git_worktree.py` (new): `GitWorktree(repo: Path, executable: str = "git")`.
  - `create`: one process in `repo`, `git worktree add .openfactory/worktrees/<task id> -b openfactory/<task id> <base>`, the spec's command.
  - `remove` and `remove_worktree`: the commands of Open question 3.
  - Its own private process runner, with the same `GitError` texts as `GitCli`.
  - Ends with the `TYPE_CHECKING` assertion against `WorkspaceManager`.
- Tests:
  - a new unit file for the port's shape;
  - a new integration file on a real repository under `tmp_path`, with a stand-in executable for the command line of `create` and the failures.

Out (not this task):
- Every caller: "Remove ... if they exist, then `git worktree add`" as a sequence, `<base>`, the `git: <first line of the error>` reason, "no run event is recorded", the removal after a pass and in the repair (outline items 5 and 6). Nothing calls the port yet.
- Wiring in `cli.py` (outline item 7).
- Any change to `ports/git_provider.py`, `adapters/git_cli.py`, `app/`, `domain/` and existing tests.
- A process runner shared by `git_cli` and `git_worktree` (Open question 4, alternative).
- Audit F-5 (the `RunFiles` task) and F-1 (the run use case); this task only raises `GitError`.
- Hardening:
  - a worktree whose directory was deleted by hand but is still registered (Open question 3);
  - a locked worktree;
  - a directory at the path that is not a worktree;
  - a `post-checkout` hook of the target repo;
  - a task id that is not of the contract's form;
  - a time limit on `git` (decision of 2026-10-11: none).

## Acceptance criteria
"The M3 paragraph" is the paragraph after "Ids" under "Domain model and storage". The other headings are under "Execution".

Terms used in the criteria:
- **A test repository** is a directory under `tmp_path` made with `git init`, with `user.name`, `user.email` and `commit.gpgsign false` in its own config, and `.openfactory/.gitignore` containing `*`, as `init` writes it.
- **`BASE`** is the sha of its first commit, which holds `app/a.py`. **`TIP`** is the sha of a second commit on the checkout's branch, so `BASE` is not `HEAD`.
- **The stand-in** is an executable script under `tmp_path` that appends its arguments and working directory to a file on each start, writes what the test gives it and exits with the status given, as in `tests/integration/test_git_cli_m3.py`.

Every test removes `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` from the environment. The criteria are written for the proposals under Open questions.

- [x] AC1 (the M3 paragraph: "`WorkspaceManager`, whose adapter is `git_worktree`, creates and removes a task's worktree and branch"; "Tech stack and repo layout": `WorkspaceManager` under `ports/`, `git_worktree` under `adapters/`):
  - `WorkspaceManager` is a Protocol whose public methods are exactly `create`, `remove` and `remove_worktree`.
  - `ports/workspace_manager.py` imports nothing from `openfactory.adapters` or `openfactory.app`; `adapters/git_worktree.py` imports nothing from `openfactory.app`.
  - `uv run pyright` passes with the `TYPE_CHECKING` assertion as the last statement of `git_worktree.py`.
- [x] AC2 ("Per-task sequence" step 1: "`git worktree add .openfactory/worktrees/AUTH-002 -b openfactory/AUTH-002 <base>`"; "Base and branches": "The human's checkout and branches never change. A worktree is created from a commit, so uncommitted work in the checkout is not in it"; the M3 paragraph: "these operations take the worktree's path"):
  - With an uncommitted `app/draft.py` in the checkout, `create("AUTH-002", BASE)` returns `Path(".openfactory/worktrees/AUTH-002")`, and `repo / <returned>` is a directory that holds `app/a.py` and no `app/draft.py`.
  - In that directory `git rev-parse HEAD` is `BASE` (not `TIP`) and `git branch --show-current` is `openfactory/AUTH-002`.
  - With the test's working directory outside the repo, `GitCli(repo).head_commit(<returned>)` is `BASE`.
  - `git status --porcelain`, `git rev-parse HEAD` and `git branch --show-current` in the checkout give the same output before and after.
- [x] AC3 ("Per-task sequence" step 1: "Remove the task's worktree and branch if they exist"; "Restart": "Because a task's worktree and branch are removed and created again before each attempt, a commit made without its `CommitRecorded` becomes unreachable"; "Base and branches": "it removes and creates branches and worktrees there freely"):
  - After `create("AUTH-002", BASE)`, the test commits a file in the worktree (sha `AGENT`), changes `app/a.py` and writes an untracked file there. `remove("AUTH-002")` then raises nothing.
  - Afterwards the directory is gone, `git worktree list --porcelain` in the repo lists one worktree, `refs/heads/openfactory/AUTH-002` does not exist, and `git branch --contains AGENT` prints nothing.
  - A following `create("AUTH-002", TIP)` succeeds and `HEAD` in the new worktree is `TIP`.
  - `remove("AUTH-002")` raises nothing when neither the worktree nor the branch exists. When only the branch exists it removes the branch.
  - The checkout's three outputs of AC2 are unchanged.
- [x] AC4 ("Per-task sequence" step 6: "removes the worktree; the branch stays"; "Restart" step 1: "its worktree is removed"; "Base and branches": "Each task branch therefore contains every earlier passed task"):
  - After `create("AUTH-002", BASE)` and a commit made by the test in the worktree (sha `DONE`), `remove_worktree("AUTH-002")` removes the directory, and `git rev-parse openfactory/AUTH-002` in the repo is still `DONE`.
  - A second `remove_worktree("AUTH-002")` raises nothing.
  - `create("AUTH-003", DONE)` then gives a worktree whose `HEAD` is `DONE`.
- [x] AC5 ("Per-task sequence" step 1, the command as quoted in AC2; "Events of one task": "A git command that fails while a task is `running` or `gating` moves the task to `failed` with reason `git: <first line of the error>` ... When the worktree cannot be created, no run event is recorded"):
  - With `GitWorktree(repo, executable=<the stand-in>)`, `create("AUTH-002", BASE)` starts the stand-in once, with exactly the arguments `worktree add .openfactory/worktrees/AUTH-002 -b openfactory/AUTH-002 <BASE>` and the repo as its working directory.
  - With the stand-in exiting 128 and writing two lines to standard error, `create` raises `GitError` whose text is those lines stripped; with empty standard error the text is `git exited with status 128`.
  - With an executable that does not exist, `create` raises `GitError` whose text starts with `git could not be started: `.
  - On the real `git`, `create("AUTH-002", <a sha that is no commit>)` raises `GitError` with a text that is not empty.

## Architecture rules that apply
- `ports` holds Protocols only. The port uses `pathlib.Path` and plain strings and imports `GitError` from `ports/git_provider.py`, as `EventRecorder` uses `EventConflictError` from `ports/event_store.py`.
- The adapter ends with its `TYPE_CHECKING` assertion against `WorkspaceManager` (ADR-006).
- Every git command stays behind a port (ADR-011, ADR-014). `cli.py` and `app/` are not changed.
- No event is recorded and no projection is read or written.
- No new dependency.
- The working directory is given with `cwd=`, not `git -C <path>`, as TASK-043 fixed.
- OpenFactory's own tests carry no `req` markers.
- No hardening beyond what the spec asks.

## Plan
1. Create branch `task/TASK-045-workspace-manager-git-worktree` from an up-to-date main.
2. Get the human's answers to Open questions 1 to 4. Record them here and as rows in `docs/decisions.md`. If an answer differs from a proposal, adjust the criteria before any test is written.
3. Write failing tests:
   - `tests/unit/test_workspace_manager_port.py` (new) for AC1;
   - `tests/integration/test_git_worktree.py` (new) for AC2 to AC5, with its own autouse fixture for the git variables, helpers for the test repository and the stand-in.
4. Add `ports/workspace_manager.py` with the Protocol and docstrings.
5. Add `adapters/git_worktree.py`. Confirm against the real `git` what the planner did not run:
   - `git worktree add` creates the missing `.openfactory/worktrees/` directory;
   - `git worktree remove --force` removes a worktree with changed and untracked files;
   - `git branch -D` works once the worktree is gone;
   - the exit status of the branch existence check.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green. The three `tests/integration/test_git_cli*.py` files must pass unchanged.
7. Update the living docs and the Outcome. Commit `feat(adapters): create and remove a task's worktree and branch` with trailers `Task: TASK-045` and `Milestone: M3`.

## Files expected to change
- `src/openfactory/ports/workspace_manager.py` (new, about 40 lines)
- `src/openfactory/adapters/git_worktree.py` (new, about 60 lines)
- `tests/unit/test_workspace_manager_port.py` (new, about 40 lines)
- `tests/integration/test_git_worktree.py` (new, about 200 lines)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-045-workspace-manager-git-worktree.md` (this record; Outcome at close)

Not expected to change: `cli.py`, every module under `app/` and `domain/`, `ports/git_provider.py`, `adapters/git_cli.py`, `pyproject.toml`, `docs/adr/`, `docs/spec/` and every existing test file.

Expected size: about 340 lines with tests, about 100 of them in `src/`.

## Living docs to update
- `docs/architecture.md`:
  - new sections "WorkspaceManager port" and "Git worktree adapter";
  - "Data flow": the port exists for the run use case and nothing calls it yet.
- `docs/progress.md`: Current, Done, outline item 1 removed or struck, and the Later lines listed below.
- `docs/decisions.md`: rows for the answered open questions.
- `CHANGELOG.md` and `README.md`: no change (nothing a user sees).

## New dependencies
None.

## Spec gaps
Spec impact is "wording". Neither item stops the task.

1. "Domain model and storage", the M3 paragraph after "Ids": "`WorkspaceManager`, whose adapter is `git_worktree`, creates and removes a task's worktree and branch", with "these operations take the worktree's path" and "Execution" › "Per-task sequence" step 3, "`AgentExecutor.run(contract, context, workdir, output_dir)`".
   - Missing: where the use case gets the path it passes as `workdir` and to the `GitProvider` operations (audit F-7 of `docs/spec-audits/2026-10-13-proposal-v1.12.md`, proposed text "creating it returns the worktree's path").
   - Does not block: the location is fixed by "Per-task sequence" step 1 (`.openfactory/worktrees/AUTH-002`) and by "Base and branches"; ADR-014 repeats it. Who hands the path to the use case is a port signature, which ADR-001 and ADR-012 leave to the task. It is Open question 1 for the human, not an assumption of the task. The spec text is left to a later `/spec-change`.
2. The same paragraph, "creates and removes a task's worktree and branch", against "Per-task sequence" step 6, "removes the worktree; the branch stays", and "Restart" step 1, "its worktree is removed".
   - Unclear: the paragraph names one removal, of worktree and branch; the sequence needs a second that keeps the branch.
   - Does not block: the meaning is clear from step 6. How the port offers the two is a signature (Open question 2).

Readings, not gaps (each follows from the text as written):
- "Remove the task's worktree and branch if they exist, then `git worktree add`" is a sequence of the use case; the port gives the two operations and `create` does not remove first (Open question 2 holds the alternative).
- A failure of worktree creation or removal is "a git command that fails", so the port raises `GitError`, the type the use case already turns into `git: <first line of the error>`.
- The spec's command has a relative path, so it runs with the repo as working directory.
- `.openfactory/.gitignore` holds `*`, so a worktree under `.openfactory/worktrees/` does not show in the checkout's status; AC2 asserts it.
- Audit F-1 (a git failure during the repair or when a worktree is removed after a pass) is the run use case's; this task only raises. Audit F-5 is the `RunFiles` task's.

## Later lines in `docs/progress.md`: taken or left
- "Spec gap ... F-7 ... F-5 ... F-1": the F-7 part is taken by Open question 1. At close it is cut from that line and replaced by a "Spec wording" line with the answer given. F-5 and F-1 are left.
- "`GitCli` passes the caller's environment to `git` ... settle it in M3 with `git_worktree`": taken by Open question 4. At close the line is reworded to the answer given, and it names `git_worktree` too.
- "a `warning:` line before `fatal:`": left. At close it gains that the same holds for `GitWorktree`.
- Every other Later line: left.
- To add at close:
  - "Spec wording: "Domain model and storage", the M3 paragraph, "creates and removes a task's worktree and branch" names one removal; step 6 needs one that keeps the branch (TASK-045, planner)".
  - "`git worktree add` runs a `post-checkout` hook of the target repo; not checked, no test (TASK-045, planner)".
  - "A worktree whose directory was deleted by hand stays registered, and `git worktree add` on its path may fail until `git worktree prune`; not checked (TASK-045, planner)", unless Open question 3 is answered otherwise.

## Open questions
Answered by the human on 2026-10-13: all four as proposed (advisor: 4 AGREE). Rows are in `docs/decisions.md`. With the answers: an adapter resolves the relative worktree path against its own repo, never the use case (1); any non-zero exit of the branch check counts as "no branch" (3); the decision on the environment covers `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` only, the identity variables stay a Later line (4).

1. **Where the use case gets the worktree's path (audit F-7; Spec gaps, item 1).**
   - Proposed: `create(task_id, base) -> Path` returns the path relative to the repo, `.openfactory/worktrees/<task id>`, as the spec writes it and as `RunFiles` "returns its path relative to the repo". `GitCli` already takes a relative path against its repo (decision of 2026-10-13, TASK-043), and AC2 adds the test of the relative form that row asks for.
   - Alternative (a): `create` returns the absolute path `repo / ...`, which the executor adapter can use as a working directory without knowing the repo.
   - Alternative (b): `create` returns `None` and a method `path(task_id) -> Path`, or a domain function, gives the path. That also serves a caller that has not created the worktree, which no M3 step needs.
   - Consequence for outline item 3: with the proposal, `claude_code_executor` must resolve `workdir` against the repo, or the use case must.
2. **Method set, names and the error type (Spec gaps, item 2).**
   - Proposed: three methods, `create(task_id: str, base: str) -> Path`, `remove(task_id: str) -> None` (worktree and branch, each if it exists) and `remove_worktree(task_id: str) -> None` (worktree if it exists, branch stays). Both removals do nothing when there is nothing to remove. Module `ports/workspace_manager.py`, class `GitWorktree(repo, executable="git")` in `adapters/git_worktree.py`. Failures raise `GitError` from `ports/git_provider.py`.
   - Alternative (a): two methods, where `create` removes the task's worktree and branch first, so the use case cannot skip it; `remove_worktree` stays.
   - Alternative (b): a `WorkspaceError` of the port's own, which the use case would have to catch beside `GitError` for the same `git:` reason.
3. **The commands of the removals.** The spec gives the command of creation only.
   - Proposed for the worktree: `git worktree remove --force .openfactory/worktrees/<task id>`, run only when that directory exists.
   - Proposed for the branch: `git branch -D openfactory/<task id>`, run only when `git rev-parse --verify --quiet refs/heads/openfactory/<task id>` exits 0, and after the worktree is removed (git refuses to delete a branch a worktree has checked out).
   - Proposed: no `git worktree prune`. A worktree deleted by hand and still registered is out of scope, with a Later line.
   - Alternative: `git worktree prune` before every `create` or inside `remove`, one more process and one more test.
   - Unchecked: the planner did not run git. The implementer confirms the four behaviours listed in plan step 5.
4. **The environment given to `git` (the Later line from TASK-030, "settle it in M3 with `git_worktree`").**
   - Proposed: decide it now as "left as it is in Phase 1". Both adapters pass the caller's environment; it matters only when `openfactory` is started from a git hook or with `GIT_*` variables set by hand. `GitWorktree` gets its own private runner with the same `GitError` texts as `GitCli`; `git_cli.py` is not touched. The Later line is reworded to record the decision.
   - Alternative: both adapters remove `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` (and whether `GIT_AUTHOR_*` and `GIT_COMMITTER_*` go too, given "under the repo's configured git identity"), through a shared helper module `adapters/git_process.py` with no port. That changes `git_cli.py` and would be a separate small task right after this one, before the run use case.

## Outcome
- Built: Protocol `WorkspaceManager` (`create`, `remove`, `remove_worktree`) in `ports/workspace_manager.py`, and `GitWorktree(repo, executable="git")` in `adapters/git_worktree.py` with its own private `_run` and `_checked` (same `GitError` texts as `GitCli`; `git_cli.py` unchanged) and the `TYPE_CHECKING` assertion last. New `tests/unit/test_workspace_manager_port.py` (3 tests, AC1) and `tests/integration/test_git_worktree.py` (7 tests, AC2 to AC5) on real git and a stand-in. Nothing calls the port yet; no `cli.py` wiring.
- Deviations from the plan: none. The implementation passed on its first run.
- Test edits: none; no existing test changed and no test from the test-writer was edited.
- Outline numbers: "outline item 1", "items 2 to 8" and "outline items 3, 5, 6, 7" in this record are the numbers before item 1 was removed from the M3 outline; old items 2 to 8 are now items 1 to 7, so the cited 3, 5, 6 and 7 are now 2, 4, 5 and 6.
- Confirmed against git 2.54.0 (Apple Git-157) by the real-git tests: `git worktree add` creates the missing `.openfactory/worktrees/` directory; `git worktree remove --force` removes a worktree with changed and untracked files; `git branch -D` works once the worktree is gone. The exit status of the branch check for a missing branch is not asserted on its own; the adapter treats any non-zero status as no branch.
- Checks: 1143 tests pass, ruff clean, pyright clean, `check_docs.py` passes.
- Follow-ups (Later lines in `docs/progress.md`): the F-7 "Spec wording" line with the answer given; the "one removal" spec-wording line; the `GitCli`/`GitWorktree` environment line (decision) and the identity-variables "Spec wording" line; the `warning:` before `fatal:` line, now also for `GitWorktree`; the `post-checkout` hook not checked; a worktree deleted by hand and still registered (`git worktree prune`); `create` returns the path but not the branch name.
