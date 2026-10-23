# TASK-087: `GitProvider` listing of the commits on `openfactory/*` branches

- Milestone: M5
- Status: done
- Tests: acceptance
- ADR: ADR-018 (accepted). Its "Ports" bullet ("`GitProvider` also lists the commits reachable from `openfactory/*`, with their trailers and changed paths") covers the new method and its `GitCli` implementation. ADR-012 and ADR-014 cover `GitProvider` and `GitCli`, and ADR-006 the `TYPE_CHECKING` assertion, which is already in place. The task adds no port, adapter, event, payload, storage schema or dependency. Design choices go in `docs/decisions.md`, one row each.
- Spec impact: none (readings listed under "Spec gaps"; none is a gap)
- Spec sections (spec v1.17; SC-132, SC-133):
  - "Domain model and storage" › "Ids", M5 paragraph: "`GitProvider` also lists the commits reachable from the `openfactory/*` branches, each with its trailers and its changed paths, for the rebuild of links from git (see Traceability)."
  - "Traceability": "It reads, through `GitProvider`, the commits reachable from the `openfactory/*` branches that have a `Task` trailer, with their trailers read by `git log --format=%(trailers:only,unfold)`, and returns these links: … commit → file (`diff`) for each path the commit changed against its parent, listed with `--no-renames`."
  - "Traceability" › "Commit trailers": "The trailers are the last paragraph of the message".
  - "Milestones and definition of done", item 5: "rebuild the links of platform commits from git trailers alone."

## Outline item
This is part (a) of M5 outline item 2 in `docs/progress.md`. Part (b) is the rebuild function that returns links from git; it follows as TASK-088 and depends on this task. Item 3 (the M5 close test) comes after that.

## Objective
`GitProvider` gains a read-only listing of every commit reachable from the `refs/heads/openfactory/*` branches. Each commit comes with its sha, its trailers as `git log --format=%(trailers:only,unfold)` gives them, and the paths it changed against its parent, listed with `--no-renames`.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/domain/git_history.py` (new, pure):
  - frozen `BranchCommit(sha: str, trailers: list[tuple[str, str]], files: list[str])`, `extra="forbid"`;
  - `trailers` holds (key, value) pairs in git's order, with duplicates kept (Design choice 2).
- `src/openfactory/ports/git_provider.py`:
  - `GitProvider` gains `branch_commits() -> list[BranchCommit]`. It reads the repo the provider was made for and takes no worktree.
  - The docstring says that a failed command raises `GitError` and that no order is promised (Design choice 4).
- `src/openfactory/adapters/git_cli.py`:
  - `GitCli.branch_commits` runs `git log --branches=openfactory/*` with `--format` built on `%H` and `%(trailers:only,unfold)`, and `--no-renames`.
  - It uses one process if the output format can be pinned (Design choice 3).
  - Names are read NUL-separated, so they come back unquoted, as `tracked_files` does.
  - Strict UTF-8, as the other methods except `staged_diff`.
- Tests:
  - New `tests/integration/test_git_cli_branch_commits.py`, on real `git` under `tmp_path` with `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` removed. Commits on `openfactory/<id>` branches are made in linked worktrees with messages from `build_commit_message`. A stand-in executable covers the command line and the failures.
  - `tests/unit/test_git_provider_port.py`: the exact method-set test gains `branch_commits`. The test name is kept. This is an approved edit of an existing test, of the same kind as in TASK-043, TASK-044 and TASK-063; list it in the Outcome.
  - A model test that `BranchCommit` is frozen and forbids extra fields.

Out:
- The rebuild function, parsing `Requirements` into ids, filtering on `Task`, and the comparison with `trace_links` (TASK-088).
- The M5 close test (item 3).
- Any change to `app/`, `cli.py`, `Traces`, the projector or the payloads. Nothing calls the new method yet.
- Merge commits, signatures and the user's `log.*` or `diff.*` configuration beyond what `--no-renames` overrides. The spec names none of them.

## Acceptance criteria
- [ ] **AC1** ("Ids", M5 paragraph):
  - `GitProvider` has `branch_commits`, and `BranchCommit` is frozen with `extra="forbid"`.
  - `domain/git_history.py` imports nothing from `ports`, `adapters` or `app`, and the port imports nothing from `adapters` or `app`.
  - `git_cli.py` still ends with the `TYPE_CHECKING` assertion.
  - The listing leaves HEAD, every ref and the index unchanged.
- [ ] **AC2** ("the commits reachable from the `openfactory/*` branches"):
  - Commits on `openfactory/A` and `openfactory/B` are listed, each exactly once. This includes the base history the branches share, and two task commits on one branch.
  - These are not listed:
    - a commit reachable only from `main`;
    - a commit reachable only from a branch outside `openfactory/` (e.g. `feature/x`);
    - a commit whose `openfactory/` branch was deleted (`git branch -D`).
  - A repo with no `openfactory/*` branch gives `[]`, not HEAD's history. Confirm this on git 2.54.0 and record it.
- [ ] **AC3** ("trailers read by `git log --format=%(trailers:only,unfold)`"; "Commit trailers"):
  - A commit made with a `build_commit_message` message gives `Task`, `Requirements`, `Acceptance-Criteria`, `Agent-Run` and `Spec-Version`, in that order, with their values as written (`Requirements: REQ-A-1, REQ-A-2` stays one value).
  - A trailer folded over two lines comes back unfolded.
  - A `Key: value` line in the body that is not in the last paragraph is not a trailer.
  - A commit with no trailers gives `[]`.
- [ ] **AC4** ("each path the commit changed against its parent, listed with `--no-renames`"):
  - `files` holds the commit's added, modified and deleted paths, relative to the repo with `/`.
  - A rename gives both the old and the new path.
  - A path with a space comes back unquoted.
  - A commit's files are those against its parent, not against the branch's base: with two commits on one branch, the second lists only its own paths.
- [ ] **AC5** (`GitError`, as for the other `GitProvider` methods):
  - A non-zero exit raises `GitError` with standard error stripped, or `git exited with status N` when standard error is empty.
  - A `git` that cannot be started raises `git could not be started: <OS error>`.
  - Both are checked with a stand-in.

## Architecture rules that apply
- `domain/git_history.py` is pure.
- The port imports only from `openfactory.domain`, `pathlib` and `typing`.
- `GitCli` starts `git` through its existing `_run` and `_checked` in the repo (`worktree=None`) and keeps its `TYPE_CHECKING` assertion.

## Plan
1. Create branch `task/TASK-087-git-branch-commits` from an up-to-date main.
2. Record the human's answers to Design choices 1 to 4.
3. Test-writer: write failing tests for AC1 to AC5 (`test_task087_...`). Make the approved edit to the method-set test in `tests/unit/test_git_provider_port.py`.
4. Implement `BranchCommit`, the port method and `GitCli.branch_commits`. Confirm on git 2.54.0:
   - that `--branches=openfactory/*` with no matching branch prints nothing;
   - that the output format chosen in Design choice 3 can be split reliably;
   - that a root commit's paths are listed.
5. Run `uv run pytest -q`, ruff, pyright and check_docs until all pass.
6. Update the docs:
   - `docs/architecture.md`: GitProvider port (seven methods), Git CLI adapter bullet, test file list, a `BranchCommit` line;
   - `docs/progress.md`: Current, a Done line, outline item 2 split into (a) done and (b) the rebuild;
   - `docs/decisions.md`: one row per Design choice;
   - fill in the Outcome.
7. Commit `feat(adapters): list the commits of openfactory branches` with the trailers `Task: TASK-087` and `Milestone: M5`. Do not push.

## Files expected to change
- `src/openfactory/domain/git_history.py` (new, about +15)
- `src/openfactory/ports/git_provider.py` (about +12)
- `src/openfactory/adapters/git_cli.py` (about +35)
- `tests/integration/test_git_cli_branch_commits.py` (new, about +200)
- `tests/unit/test_git_provider_port.py` (+1, approved edit)
- a `BranchCommit` model test (about +15)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, this record

Expected size: about 280 lines, about 60 of them in `src/`.

## Design choices to confirm at planning
1. **Where the `Task` filter lives.**
   - Proposed: the adapter lists every reachable commit, and the rebuild (TASK-088) keeps those with a `Task` trailer. The port stays word for word with the M5 paragraph and knows nothing about trailer keys.
   - Alternative: the adapter keeps only commits with a `Task` trailer, following the Traceability sentence. That puts a trailer key in the adapter, but it avoids listing the target repo's whole earlier history.
2. **Shape of the trailers.**
   - Proposed: `list[tuple[str, str]]` in git's order, duplicates kept, split at the first `: `. It loses nothing, and the rebuild decides what to do with them.
   - Alternative: `dict[str, str]`, which needs a rule for repeated keys that the spec does not give.
3. **Number of git processes.**
   - Proposed: one `git log --branches=openfactory/* --no-renames --name-only -z --format=<separator>%H<separator>%(trailers:only,unfold)<separator>`, with the separators fixed at implementation and pinned by AC2 to AC4.
   - Alternative: one `git log` for sha and trailers, then one `git diff-tree -r --name-only -z --no-renames <sha>` per commit. That is simpler to parse but costs a process per commit, and the whole history if choice 1 lists everything.
4. **Order.**
   - Proposed: no order is promised for commits or files. The rebuild returns a set and tests compare sets.
   - Alternative: sort commits by sha and files as strings, matching `CommitRecorded.files`.

## Open questions
- Design choices 1 to 4.
- A root commit or a merge commit reachable from an `openfactory/*` branch: neither ever has a `Task` trailer, since the orchestrator makes neither. Proposed: whatever `git log --name-only` gives (a root commit lists its files, a merge lists none), with no test beyond the root commit check in step 4. If the answer to choice 1 is to filter in the adapter, the question goes away.

## Answers (2026-10-23)
The human approved the plan with every open question as proposed:
1. The adapter lists every reachable commit; TASK-088's rebuild keeps those with a `Task` trailer.
2. Trailers are `list[tuple[str, str]]` in git's order, duplicates kept, split at the first `": "`.
3. One `git log` process; separators are not NUL, the parser finds records by their start marker, and one test covers a commit that lists no files.
4. No order is promised for commits or files.
5. Root and merge commits: whatever `git log --name-only` gives; no test beyond the root-commit check in step 4.

## Spec gaps
None. These are readings, not gaps:
1. "Reachable from the `openfactory/*` branches" means local branches `refs/heads/openfactory/*` (`--branches`), not remote-tracking refs. `WorkspaceManager` makes local branches only.
2. "Changed against its parent": orchestrator commits always have exactly one parent (the `<base>` chain), so first parent and only parent are the same.
3. "With a `Task` trailer": whether the listing or the rebuild applies this filter is Design choice 1, not a gap. Both readings meet the spec.

## Outcome
Built:
- `domain/git_history.py`: frozen `BranchCommit(sha, trailers, files)`, `extra="forbid"`.
- `GitProvider.branch_commits()` (seven methods) and `GitCli.branch_commits`: one `git log --branches=openfactory/* --no-renames --name-only -z --format=%x1e%H%x1f%(trailers:only,unfold)%x1f` process; records split on RS, names after NUL and newline. All five Answers followed.
- Confirmed on git 2.54.0: no matching `openfactory/*` branch prints nothing (no HEAD fallback), and a root commit lists its files.
- New `tests/integration/test_git_cli_branch_commits.py`. The test-writer added a non-ASCII path (`café.py`) to the AC4 path test, beyond the record's wording.
- Docs: `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md` (one row per Answer plus the git finding).

Test edits:
- Approved, planned (not a fix): `tests/unit/test_git_provider_port.py` method-set assertion gains `"branch_commits"`.
- No mechanical test fixes.

