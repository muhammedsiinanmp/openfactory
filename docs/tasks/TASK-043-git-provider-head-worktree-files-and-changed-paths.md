# TASK-043: `GitProvider` for `run`, first half: the commit `HEAD` points at, the tracked files of a worktree, staging and the changed paths

- Milestone: M3
- Status: done
- Tests: acceptance
- ADR: ADR-014 (accepted). "Ports and adapters (SC-63, SC-68)": "`GitProvider`, adapter `git_cli`, gains: the commit `HEAD` points at, the tracked files of a worktree, staging the changes of a worktree and listing the paths that differ from a commit, a soft reset of a branch, and making a commit. These take the worktree's path." "Execution": "The path check is `git add -A` followed by `git diff --cached --name-only -z --no-renames <base>`." ADR-012 (accepted) covers "Exact signatures are settled in the tasks that build them"; ADR-006 covers the `TYPE_CHECKING` assertion. No new port, adapter, dependency, event type, payload or storage change. Names, signatures and the commands not fixed by the spec are rows in `docs/decisions.md` (Open questions 2 to 4).
- Spec impact: wording. One item, which does not stop the task (see "Spec gaps"): "these operations take the worktree's path" against the `HEAD` of the repo, which is read before any worktree exists.
- Spec sections (spec v1.12, SC-56, SC-58, SC-63, SC-64, SC-72): "Tech stack and repo layout" (the "Git" row); "Domain model and storage" (the M3 paragraph after "Ids"); "Execution" › "`run`" (the refusals), "Base and branches", "The context pack", "The path check", "The commit", "Events of one task" (the git failure bullet)

## Outline item
M3 outline item 1, first half. Item 1 is split because the whole of it is about 440 lines with tests. This task takes the three operations used before the commit. Left for the next task, as item 1: the soft reset and the commit. Items 2 to 9 are left.

## Objective
Give `GitProvider` and `GitCli` the commit `HEAD` points at (or none), the tracked files of a worktree, and one operation that stages a worktree's changes and returns the paths that differ from a commit, so the run use case can choose `<base>`, refuse a repo with no commit, build the context pack and run the path check without touching a process.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings and to SC-56, SC-58, SC-63, SC-64 and SC-72.

## Scope
In (names and signatures per Open questions 2 to 4):
- `src/openfactory/ports/git_provider.py`:
  - `head_commit(worktree: Path | None = None) -> str | None`: the sha of the commit `HEAD` points at; `None` when it points at no commit.
  - `tracked_files(worktree: Path | None = None) -> list[str]`: the existing method gains the optional path.
  - `stage_changes(worktree: Path, base: str) -> list[str]`: stages every change in the worktree, then returns the paths that differ from `base`, in git's order.
  - For the two optional paths, `None` is the repo the adapter was made for.
- `src/openfactory/adapters/git_cli.py`:
  - One private helper that starts one `git` process in a directory and raises `GitError` with the texts of the TASK-030 row; `tracked_files` is moved onto it.
  - `head_commit`: one process (Open question 3).
  - `stage_changes`: `git add -A`, then `git diff --cached --name-only -z --no-renames <base>`, output split on NUL.
  - The `TYPE_CHECKING` assertion stays the last statement.
- Tests: a new integration file for the three operations, on a real repository with a linked worktree made by the test (`git worktree add`), and a stand-in executable for the command lines and the failures.
- The one edit to a fixed test that the new methods force (Open question 1): the exact method set in `tests/unit/test_git_provider_port.py`.

Out (not this task):
- The soft reset and the commit (`git reset --soft`, `git commit --no-verify`): the next task, the rest of outline item 1.
- `WorkspaceManager` and `git_worktree` (item 2). The tests make their worktree with `git worktree add` themselves.
- Every caller: the `repository has no commit` and `git failed: <error>` refusals, the choice of `<base>`, matching tracked files against `allowed_paths`, `violating_paths`, sorting the paths for `CommitRecorded.files`, the `git: <first line of the error>` reason (items 5 to 8). Nothing calls the new methods yet.
- Any change to `cli.py`, `app/`, `domain/`, and the `FakeGit` in `tests/unit/test_plan_entry.py`. Pyright checks `src` only, and `create_plan` still calls `tracked_files()` with no argument.
- Removing `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` from the environment the adapter gives to `git` (the Later line from TASK-030). It stays for item 2, where one decision covers `git_cli` and `git_worktree`. The tests of this task remove the three variables, as `tests/integration/test_git_cli.py` does.
- Audit F-7 (where the use case gets the worktree's path), F-5 and F-1: see "Spec gaps", readings.
- Hardening: path names that are not valid UTF-8 (Later line of TASK-030), a `warning:` line before `fatal:`, repositories with SHA-256 object names, submodules, sparse checkouts, a `base` that is not a commit beyond "the command fails", a time limit on `git` (decision of 2026-10-11: none).

## Acceptance criteria
"The M3 paragraph" is the paragraph after "Ids" under "Domain model and storage". The other headings are under "Execution".

Terms used in the criteria:
- **A test repository** is a directory under `tmp_path` made with `git init`. It has `user.name`, `user.email` and `commit.gpgsign false` set in its own config, so the test can commit.
- **`BASE`** is the sha of the test repository's first commit, read by the test with `git rev-parse HEAD`.
- **The worktree** is made by the test with `git worktree add <path> -b openfactory/AUTH-002 BASE`, at an absolute path.
- **The stand-in** is an executable script under `tmp_path`. It appends its arguments and working directory to a file on each start, prints what the test gives it and exits with the status given.

Every test removes `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` from the environment. The criteria are written for the proposals under Open questions.

- [x] AC1 (the M3 paragraph: "`GitProvider` also gives the commit `HEAD` points at and the tracked files of a worktree, stages the changes of a worktree and lists the paths that differ from a commit"; "Tech stack and repo layout": "the domain never imports infrastructure"):
  - `GitProvider` is a Protocol whose public methods are exactly `tracked_files`, `head_commit` and `stage_changes`.
  - `openfactory.ports.git_provider` imports nothing from `openfactory.adapters` or `openfactory.app`; `openfactory.adapters.git_cli` imports nothing from `openfactory.app` (the two existing tests, unchanged).
  - `uv run pyright` passes with the `TYPE_CHECKING` assertion at the end of `git_cli.py` unchanged.
- [x] AC2 ("`run`": "`repository has no commit`, when `HEAD` points at no commit; `git failed: <error>`, when a git command fails before any task is taken"; "Base and branches": "when the plan has no commit, it is the commit `HEAD` of the repo points at when the task starts"; "The commit": "if the branch tip is not `<base>` when the agent exits"):
  - In a test repository with one commit, `GitCli(repo).head_commit()` equals `BASE`, 40 lowercase hex characters.
  - In a test repository with no commit, `head_commit()` is `None`.
  - In a directory that is not a repository, `head_commit()` raises `GitError`; it does not return `None`.
  - After the test makes a second commit in the worktree, `head_commit(worktree)` is that commit's sha and `head_commit()` is still `BASE`.
- [x] AC3 ("The context pack": "the names of the tracked files in the worktree that match `allowed_paths`"; "Base and branches": "A worktree is created from a commit, so uncommitted work in the checkout is not in it"):
  - `BASE` holds `app/a.py` and `README.md`. In the checkout, `extra.py` is added with `git add` and not committed. In the worktree, `scratch.txt` is written and not added.
  - `tracked_files(worktree)` returns `["README.md", "app/a.py"]`.
  - `tracked_files()` still lists `extra.py`.
- [x] AC4 ("The path check": "the orchestrator runs `git add -A` in the worktree, then `git diff --cached --name-only -z --no-renames <base>`. The paths this prints are the changed paths: they cover untracked files, both names of a rename, and anything the agent committed. A path the repo ignores is outside the check"; "A run that changed no path"; "The commit": "The orchestrator commits what the path check staged"; "Base and branches": "The human's checkout and branches never change"):
  - `BASE` holds `app/a.py`, `app/old.py` and a `.gitignore` with the line `__pycache__/`.
  - In the worktree the test changes `app/a.py`, writes the new file `app/new.py`, renames `app/old.py` to `app/renamed.py`, writes `app/__pycache__/a.pyc`, and adds and commits `docs/c.md`.
  - `stage_changes(worktree, BASE)`, sorted, is `["app/a.py", "app/new.py", "app/old.py", "app/renamed.py", "docs/c.md"]`, each path once.
  - After the call every change is staged: `git status --porcelain` in the worktree has no line with an unstaged or untracked entry.
  - In a worktree where nothing was changed, `stage_changes(worktree, BASE)` is `[]`.
  - `git status --porcelain` and `git rev-parse HEAD` in the checkout give the same output before and after the calls.
- [x] AC5 ("The path check": the two commands as quoted in AC4; the M3 paragraph: "these operations take the worktree's path"; "Events of one task": "A git command that fails while a task is `running` or `gating` moves the task to `failed` with reason `git: <first line of the error>`"; "`run`": "`<error>` the first line of the failure's text"):
  - With `GitCli(repo, executable=<the stand-in>)` and the stand-in printing `b.py`, NUL, `a dir/c.py`, NUL: `stage_changes(worktree, BASE)` returns `["b.py", "a dir/c.py"]`.
  - The stand-in was started exactly twice: first with the arguments `add -A`, then with `diff --cached --name-only -z --no-renames <BASE>`. Both times its working directory was the worktree.
  - With the stand-in exiting 128 and writing two lines to standard error, `stage_changes` raises `GitError`, the first line of `str(error)` is not empty, and the stand-in was started once: the diff does not run after a failed `add`.
  - With the same failing stand-in, `head_commit()` and `tracked_files(worktree)` each raise `GitError` whose first line is not empty.

## Architecture rules that apply
- `ports` holds Protocols only and imports from `openfactory.domain` only. The new methods use `pathlib.Path` and plain strings; no domain model is added.
- The adapter ends with its `TYPE_CHECKING` assertion against `GitProvider` (ADR-006).
- Every git command stays behind `GitProvider` (ADR-011, ADR-014). `cli.py` and `app/` are not changed.
- No event is recorded and no projection is read or written.
- No new dependency: `subprocess` and `pathlib` only.
- A fixed test binds the argument list: `tests/integration/test_git_cli.py::test_ac3_reads_names_the_stand_in_prints_in_order` asserts the first argument is `ls-files` and the working directory is `repo`. So the directory is given with `cwd=`, not with `git -C <path>` or a leading `-c` option.
- Tests from the test-writer are fixed. The edit under Open question 1 is not mechanical and needs the human's approval; it is reported in the Outcome.
- OpenFactory's own tests carry no `req` markers.
- No hardening beyond what the spec asks.

## Plan
1. Create branch `task/TASK-043-git-provider-head-worktree-files-and-changed-paths` from an up-to-date main.
2. Get the human's answers to Open questions 1 to 4. Record them here and as rows in `docs/decisions.md`.
3. Write failing tests:
   - AC1: the approved edit of step 4; no new unit file.
   - `tests/integration/test_git_cli_m3.py` (new) for AC2 to AC5. It has the autouse fixture that removes the three git variables, a helper that makes a test repository with a first commit, a helper that adds the worktree, and a stand-in that appends each start's arguments and working directory to a JSON-lines file.
4. Make the approved edit to `tests/unit/test_git_provider_port.py` (Open question 1) and nothing else in that file.
5. Add the two new Protocol methods and the optional parameter of `tracked_files` to `ports/git_provider.py`, with docstrings.
6. In `adapters/git_cli.py`:
   - add the private helper (one `subprocess.run` with `cwd`, `capture_output=True`, `text=True`, `encoding="utf-8"`, `check=False`; the `GitError` texts unchanged) and move `tracked_files` onto it;
   - add `head_commit` and `stage_changes`.
7. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green. The whole of `tests/integration/test_git_cli.py` must pass unchanged.
8. Update the living docs and the Outcome. Commit `feat(adapters): read HEAD and worktree files and stage the changed paths` with trailers `Task: TASK-043` and `Milestone: M3`.

## Files expected to change
- `src/openfactory/ports/git_provider.py` (about 25 lines)
- `src/openfactory/adapters/git_cli.py` (about 45 lines)
- `tests/integration/test_git_cli_m3.py` (new, about 190 lines)
- `tests/unit/test_git_provider_port.py` (the exact method set, per Open question 1)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-043-git-provider-head-worktree-files-and-changed-paths.md` (this record; Outcome at close)

Not expected to change: `cli.py`, every module under `app/` and `domain/`, the other modules under `ports/` and `adapters/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, `tests/integration/test_git_cli.py`, `tests/unit/test_plan_entry.py` and every other test file.

Expected size: about 270 lines with tests.

## Living docs to update
- `docs/architecture.md`:
  - "GitProvider port": three methods, the optional path and what `None` means, `head_commit` returning `None` for no commit.
  - "Git CLI adapter": the helper, the commands, that `stage_changes` starts two processes and stops after a failed `add`, the tests' linked worktree.
  - "Data flow": the two new operations exist for the run use case and nothing calls them yet.
- `docs/progress.md`:
  - Current, then Done.
  - Outline item 1 reworded to what is left: "`GitProvider` in `git_cli`, the rest: the soft reset and the commit (ADR-014)". The numbering and the "depends on" references are unchanged.
  - The Later lines listed below.
- `docs/decisions.md`: rows for the answered open questions.
- `CHANGELOG.md` and `README.md`: no change (nothing a user sees).

## New dependencies
None.

## Spec gaps
Spec impact is "wording". The one item does not stop the task.

1. "Domain model and storage", the M3 paragraph after "Ids": "`GitProvider` also gives the commit `HEAD` points at and the tracked files of a worktree, stages the changes of a worktree and lists the paths that differ from a commit, resets a branch softly, and makes a commit; these operations take the worktree's path."
   - Unclear: "these operations" covers the `HEAD` read, but two other sentences need `HEAD` of the repo when no worktree exists yet. "Execution" › "`run`": "`repository has no commit`, when `HEAD` points at no commit", checked "before any event". "Base and branches": "it is the commit `HEAD` of the repo points at when the task starts", which is the `<base>` the worktree is then created from.
   - Does not block: the meaning is clear from those two sentences. The `HEAD` read must work on the repo itself, and "take the worktree's path" is true of the operations that run after a worktree exists. How the method takes its path is a signature, which ADR-012 leaves to the task; it is Open question 2 for the human, not an assumption of the task. A Later line asks the spec to say that the `HEAD` read is also made on the repo.

Readings, not gaps (each follows from the text as written):
- "`HEAD` points at no commit" and a git command that fails are two different refusals of `run`, so the read returns "none" for the first and raises `GitError` for the second.
- "Stages the changes of a worktree and lists the paths that differ from a commit" is the pair of commands "The path check" quotes. Whether the port has one method or two for the pair is a signature (Open question 2).
- The changed paths are returned in the order git prints them. "sorted as strings" is said of `CommitRecorded.files`, which the use case builds (item 6). The order of the gate's output file is an existing Later line (TASK-039).
- A sha is returned as git prints it, a plain string. The `CommitSha` pattern is applied by the `CommitRecorded` payload model when the use case builds the event.
- Audit F-7 (where the use case gets the worktree's path) does not touch this task. Whatever the answer, the use case hands a path to these methods. Whether that path is absolute or relative to the repo is the `WorkspaceManager` task's; Open question 4 proposes an adapter that works for both.
- Audit F-5 (the directory of a run) is the `RunFiles` task's. Audit F-1 (a git failure in the repair or on worktree removal) is the run use case's; this task only raises `GitError`.

## Later lines in `docs/progress.md`: taken or left
- "Spec gap ... F-7 ... F-5 ... F-1": left, unchanged. None is needed here (see the readings).
- "`GitCli` passes the caller's environment to `git` ... settle it in M3 with `git_worktree` (TASK-030, reviewer)": left for item 2. At close it gains: "since TASK-043 `git_cli` also runs `git add -A`, so a `GIT_DIR` set in the environment would stage in another repository".
- "`GitCli.tracked_files`: a `warning:` line before `fatal:`" and "a tracked name that is not valid UTF-8": left. At close each gains that the same holds for `head_commit` and `stage_changes`.
- Every other Later line: left; none concerns `GitProvider`.
- To add at close:
  - "Spec wording: "Domain model and storage", the M3 paragraph after "Ids", "these operations take the worktree's path": the `HEAD` read is also made on the repo before a worktree exists ("`run`", "Base and branches"); the spec text is left to a later `/spec-change` (TASK-043, planner)".
  - If Open question 1 keeps the name: "`tests/unit/test_git_provider_port.py::test_ac1_git_provider_is_a_protocol_with_only_tracked_files` keeps a name its assertion no longer matches (TASK-043)".

## Open questions
None is a spec decision that blocks. Question 1 is an edit to a fixed test and needs the human's approval. Each of the others has a proposal.

1. **One edit to a fixed test that the new methods force.** `tests/unit/test_git_provider_port.py::test_ac1_git_provider_is_a_protocol_with_only_tracked_files` asserts `public == {"tracked_files"}` and fails once a method is added.
   - Proposed: update the set in place to the three names and keep it exact; keep the test's name, with a Later line. This is the TASK-042 precedent (answer of 2026-10-13).
   - Also proposed: the approval covers the same edit in the next task, when the soft reset and the commit are added, so it is asked once.
   - Alternative: change `==` to `>=` and assert the exact set in the new test file.
2. **Names and signatures.** ADR-012 leaves them to the task. Proposed:
   - `head_commit(worktree: Path | None = None) -> str | None`.
   - `tracked_files(worktree: Path | None = None) -> list[str]`. The existing method gains an optional path, so `create_plan` and its fake are unchanged.
   - `stage_changes(worktree: Path, base: str) -> list[str]`: one method for the pair `git add -A` and `git diff --cached ...`. The spec defines the changed paths as the output of the pair, and a diff without the `add` would miss untracked files.
   - `None` means the repo the adapter was made for (Spec gaps, item 1).
   - Alternatives: a required path everywhere, with `cli.py` handing the repo's path to the use case; a separate `tracked_files_in(worktree)`; two methods `stage_all(worktree)` and `changed_paths(worktree, base)`.
3. **How "points at no commit" is read.**
   - Proposed: `git rev-parse --verify --quiet HEAD`. Exit 0 gives the sha (standard output stripped). A non-zero exit with empty standard error gives `None`. Any other non-zero exit raises `GitError`.
   - Unchecked: the planner did not run this command. The implementer confirms the exit status and the empty standard error against the real `git` on a repository with no commit. AC2 fixes the behaviour (`None` for no commit, `GitError` for a directory that is not a repository), whichever command gives it.
   - Alternative: `git rev-list -n 1 HEAD`, or `git symbolic-ref` with `git show-ref`.
4. **The working directory for a path.**
   - Proposed: `cwd` is `repo` when the path is `None`, otherwise `repo / worktree`. An absolute path is used as it is and a relative one is taken against the repo, not against the process's working directory, so the adapter works whichever form the `WorkspaceManager` task gives (audit F-7).
   - The criteria use absolute paths only; no test fixes the relative form.
   - Alternative: use the path as given.

### Answers (human, 2026-10-13: "do as the advisor says")
1. The proposed edit: the set becomes the three names, stays exact, the test's name is kept with a Later line. The advance approval is narrow: in the next task it covers only adding that task's new method names to this one set, still reported in that task's Outcome and checked by the reviewer.
2. The proposed names and signatures. Carried forward: a caller that forgets the path to `tracked_files` reads the checkout, so the context-pack task asserts the path it passes.
3. The advisor's rule, not the planner's: `git rev-parse --verify --quiet HEAD`; exit 0 gives the sha; `None` only when the exit status is exactly 1 and standard error is empty; every other non-zero exit raises `GitError`. The statuses (1 for no commit, 128 for a directory that is not a repository) are confirmed against the real `git` by the AC2 tests; if the real status for no commit is not 1, that status is used, not standard error alone. This overrides, for this one command, the TASK-030 rule that a silent non-zero exit is an error.
4. The proposed answer: `repo / worktree`. No test fixes the relative form; the `WorkspaceManager` task adds one if it chooses relative paths.

## Outcome
Built:
- `ports/git_provider.py`: `tracked_files(worktree: Path | None = None)`, `head_commit(worktree: Path | None = None) -> str | None` and `stage_changes(worktree: Path, base: str) -> list[str]`; `None` is the repo the provider was made for.
- `adapters/git_cli.py`: private `_run(worktree, *args)` (one `git` process, `cwd` = `repo` for `None`, else `repo / worktree`; `git could not be started: <OS error>`), `_checked(done)` (the TASK-030 error texts) and module function `_names` (split on NUL). `head_commit` runs `git rev-parse --verify --quiet HEAD` and returns `None` only for exit status 1 with empty standard error; every other non-zero exit raises `GitError`. `stage_changes` runs `git add -A`, then `git diff --cached --name-only -z --no-renames <base>`, and does not start the diff after a failed `add`. The `TYPE_CHECKING` assertion is still last.
- `tests/integration/test_git_cli_m3.py` (new, 13 tests, one parametrized over three cases): real git with a linked worktree, and a stand-in executable.

Real-git statuses confirmed (git 2.54.0): a repository with no commit gives exit 1 with empty output; a directory that is not a repository gives 128 with a `fatal:` line.

Test edits: one approved edit to a fixed test (Open question 1, answer of 2026-10-13): the exact set in `tests/unit/test_git_provider_port.py::test_ac1_git_provider_is_a_protocol_with_only_tracked_files` is now the three names; the name is kept. No mechanical fixes were made to the test-writer's tests.

Deviations from plan: none. Nothing calls the new methods yet.

Follow-ups (Later lines in `docs/progress.md`): the test name that no longer matches its assertion; the advisor's risk that a caller omitting the path to `tracked_files` reads the checkout (the context-pack task asserts the path); the TASK-030 lines on the environment, a `warning:` line before `fatal:` and non-UTF-8 names, each extended to the new methods; the spec-wording line on the `HEAD` read of the repo (already in Later).
