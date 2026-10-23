# TASK-088: Rebuild of trace links from git

- Milestone: M5
- Status: done
- Tests: acceptance
- ADR: ADR-018 (accepted). Its "Rebuild from git" bullet covers this. It says a function, not a command, returns requirement → task, task → run, run → commit and commit → file from the trailers and the `--no-renames` diffs, and never writes `trace_links`. Its "Ports" bullet covers `GitProvider.branch_commits` (TASK-087), which this task only calls. The task adds no port, adapter, event, payload, storage schema, dependency or convention. Design choices go in `docs/decisions.md`, one row each.
- Spec impact: none. The readings are under "Spec gaps"; none of them is a gap.
- Spec sections (spec v1.17; SC-132, SC-133):
  - "Traceability", the paragraph after "Commit trailers": "The rebuild is a function, not a command, and it never writes `trace_links`. It reads, through `GitProvider`, the commits reachable from the `openfactory/*` branches that have a `Task` trailer, with their trailers read by `git log --format=%(trailers:only,unfold)`, and returns these links: requirement → task (`contract`) for each id in `Requirements`; task → run and run → commit (`trailer`) from `Task`, `Agent-Run` and the commit's sha; and commit → file (`diff`) for each path the commit changed against its parent, listed with `--no-renames`."
  - "Traceability", link table: "A link is stored in `trace_links` in the direction shown, with that `source`". These are the rows `requirement → task | … | contract`, `task → agent run | … | trailer`, `agent run → commit | … | trailer` and `commit → file | … | diff`.
  - "Traceability" › "Commit trailers": "`Requirements` and `Acceptance-Criteria` list the contract's ids in contract order, joined by `, `."
  - "Domain model and storage" › "Ids", M5 paragraph: "`GitProvider` also lists the commits reachable from the `openfactory/*` branches … for the rebuild of links from git (see Traceability)."
  - "Milestones and definition of done", item 5: "rebuild the links of platform commits from git trailers alone."

## Outline item
This is part (b) of M5 outline item 2 in `docs/progress.md`. It depends on TASK-087 (`GitProvider.branch_commits`, done). Item 3, the M5 close integration test, comes next. That test runs the rebuild check against `trace_links` after a real `run` ("the rebuild check included").

## Objective
A function in `app` reads `GitProvider.branch_commits()` and keeps the commits that have a `Task` trailer. It returns the set of requirement → task (`contract`), task → run and run → commit (`trailer`) and commit → file (`diff`) links that their trailers and changed paths give. The links have the same kinds, ids, direction and `source` that the projector writes into `trace_links`. The function writes nothing.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/domain/traces.py`:
  - add a frozen `TraceLink(from_kind, from_id, to_kind, to_id, source)` with `extra="forbid"` (Design choice 1);
  - `from_kind` and `to_kind` are a `LinkKind` Literal of the seven kinds (`requirement`, `adr`, `task`, `run`, `commit`, `file`, `test`);
  - `source` is a `LinkSource` Literal of the five sources (`spec`, `contract`, `trailer`, `diff`, `test_tag`).
- New `src/openfactory/app/rebuild_links.py`. It imports only `domain`, `ports` and the standard library.
  - `rebuild_links(*, git: GitProvider) -> set[TraceLink]` calls `git.branch_commits()` once.
  - It keeps the commits with a `Task` trailer, matched exactly (Design choice 3).
  - For each kept commit it returns:
    - one `requirement → task` `contract` link per id in `Requirements`, the value split on `,` with whitespace stripped (Design choice 2);
    - `task → run` and `run → commit` `trailer` links from `Task`, `Agent-Run` and the sha;
    - one `commit → file` `diff` link per entry of `files`.
  - `Acceptance-Criteria` and `Spec-Version` give no link.
  - A `GitError` propagates unchanged (Design choice 4).
- Tests:
  - New `tests/unit/test_rebuild_links.py`, with a fake `GitProvider` that returns given `BranchCommit`s.
  - New `tests/integration/test_rebuild_links_git.py`, on real `git` under `tmp_path` with `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` removed, as `test_git_cli_branch_commits.py` does. It makes base commits, then `openfactory/<id>` commits in linked worktrees with `build_commit_message` messages, and runs `rebuild_links(git=GitCli(repo))`.
  - A model test that `TraceLink` is frozen, forbids extra fields and is hashable, added to `tests/unit/test_traces_models.py`.

Out:
- Comparing the rebuilt set with the `trace_links` rows, including the "tasks that have a `CommitRecorded`" filter and the exception for a commit made without its `CommitRecorded`. This is M5 outline item 3, the close test (Open question 2).
- Any CLI command (the spec says "a function, not a command"), and any change to `cli.py`, `Traces`, `SqliteTraces`, the projector, payloads, `GitProvider` or `GitCli`.
- The TASK-087 review items in "Later": non-UTF-8 paths and `log.showSignature`.
- `spec` (requirement → ADR), task → task `contract` and `test_tag` links. Trailers do not carry them, and the spec does not list them for the rebuild.

## Acceptance criteria
- [x] **AC1** ("Traceability": "It reads, through `GitProvider`, the commits reachable from the `openfactory/*` branches that have a `Task` trailer"):
  - Only commits with a `Task` trailer give links. A commit with no trailers gives no link. So does a commit that has `Requirements` and `Agent-Run` but no `Task`, such as the base history the branches share.
  - `branch_commits()` returning `[]` gives an empty set.
  - The function calls `branch_commits` once and no other `GitProvider` method (fake records calls).
- [x] **AC2** ("requirement → task (`contract`) for each id in `Requirements`"; "Commit trailers": ids "joined by `, `"):
  - `Task: AUTH-002` and `Requirements: REQ-A-1, REQ-A-2` give exactly the two links `TraceLink("requirement", "REQ-A-1", "task", "AUTH-002", "contract")` and the same for `REQ-A-2`.
  - `Acceptance-Criteria` and `Spec-Version` give no link.
- [x] **AC3** ("task → run and run → commit (`trailer`) from `Task`, `Agent-Run` and the commit's sha"):
  - A commit with sha `S`, `Task: T` and `Agent-Run: run_0091` gives `("task", T, "run", "run_0091", "trailer")` and `("run", "run_0091", "commit", S, "trailer")`.
  - Two tasks' commits give their own links, and each link appears once in the set.
- [x] **AC4** ("commit → file (`diff`) for each path the commit changed against its parent, listed with `--no-renames`"):
  - Each entry of the commit's `files` gives `("commit", S, "file", path, "diff")`, with the path unchanged.
  - With real git (`GitCli`), the set is exactly the AC2 to AC4 links for two `openfactory/*` branches. One branch holds two task commits, and one commit renames a file. This means:
    - each commit's files are those it changed against its parent;
    - a rename gives both names;
    - the base commits and a commit only on `main` give nothing.
- [x] **AC5** ("The rebuild is a function, not a command, and it never writes `trace_links`"):
  - `app/rebuild_links.py` imports nothing from `adapters`, `cli` or `sqlite3`, and its function takes only `git` (AST check).
  - `cli.py` defines no command that calls it.
  - In the integration test, the database's `events` and `trace_links` row counts are unchanged after a call on an initialised repo.
- [x] **AC6** ("A link is stored in `trace_links` in the direction shown, with that `source`"):
  - `TraceLink` is frozen with `extra="forbid"`, is hashable, and rejects a kind or source outside the seven kinds and five sources.
  - A conformance test checks that the rebuild's links for a commit equal, field for field, the rows that `SqliteProjector` writes for a matching `CommitRecorded` and `PlanApproved`. The `requirement → task` `contract` rows and the `trailer` and `diff` rows are read in primary-key order. This keeps the two writers' shapes from drifting before the close test.

## Architecture rules that apply
- `app/rebuild_links.py` depends on `domain` and `ports` only, does no I/O of its own and returns data.
- `TraceLink` lives in `domain/traces.py`, which stays pure.
- Nothing writes `trace_links` outside the projector (ADR-002, ADR-018).

## Plan
1. Create branch `task/TASK-088-rebuild-links-from-git` from an up-to-date main.
2. Record the human's answers to Design choices 1 to 5 and the Open questions.
3. Test-writer: write failing tests for AC1 to AC6 (`test_task088_...`).
4. Implement `TraceLink`, `LinkKind` and `LinkSource` in `domain/traces.py`, then `app/rebuild_links.py`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`: a "Rebuild of links from git" section, the `TraceLink` line, the test file list, and `branch_commits`'s caller;
   - `docs/progress.md`: Current, a Done line, and outline item 2(b) marked done;
   - `docs/decisions.md`: one row per Design choice;
   - fill in the Outcome.
7. Commit `feat(app): rebuild trace links from git` with the trailers `Task: TASK-088` and `Milestone: M5`. Do not push.

## Files expected to change
- `src/openfactory/domain/traces.py` (about +20)
- `src/openfactory/app/rebuild_links.py` (new, about +40)
- `tests/unit/test_rebuild_links.py` (new, about +100)
- `tests/unit/test_traces_models.py` (about +20)
- `tests/integration/test_rebuild_links_git.py` (new, about +110, the AC4 to AC6 git and projector cases)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, this record

Not expected to change: `ports/`, `adapters/`, `cli.py`, payloads, any existing test except the additions to `test_traces_models.py`, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 290 lines, about 60 of them in `src/`.

## Design choices to confirm at planning
1. **Shape of a link.**
   - Proposed: a frozen Pydantic `TraceLink` in `domain/traces.py`, with Literal kinds and sources. This matches every other domain value, and frozen models are hashable, so a `set` works.
   - Alternative: a `NamedTuple`. It compares equal to the `sqlite3` row tuples directly, but it is the only non-Pydantic domain value and it validates nothing.
2. **Splitting `Requirements`.**
   - Proposed: split on `,`, strip whitespace from each id and drop empty pieces. This gives the same result as splitting on `, ` for every message `build_commit_message` writes.
   - Alternative: split on exactly `", "`, the spec's join string, and nothing else.
3. **Matching trailer keys.**
   - Proposed: exact, case-sensitive keys (`Task`, `Requirements`, `Agent-Run`), as `build_commit_message` writes them. With a repeated key, the first value is used (TASK-087 kept duplicates in git's order).
   - Alternative: case-insensitive, as git itself treats trailer keys.
4. **A failed listing.**
   - Proposed: `GitError` from `branch_commits` propagates unchanged. There is no caller yet, and the close test wants the failure visible.
   - Alternative: catch it and return a result type with an error. The spec names no handling.
5. **Module and name.**
   - Proposed: `app/rebuild_links.py`, `rebuild_links(*, git) -> set[TraceLink]`, one module that takes the port.
   - Alternative: a pure `links_from_commits(commits)` in `domain/git_history.py` plus a thin app wrapper. That is easier to unit-test, but it adds one more function for no caller.

## Open questions
1. **A commit with a `Task` trailer but no `Agent-Run` (or no `Requirements`).** The orchestrator always writes all five trailers, so this only happens with a commit someone else made on an `openfactory/*` branch. The spec does not say what such a commit gives.
   - Proposed: emit the links whose inputs are present. No `Agent-Run` gives no `trailer` links; no `Requirements` gives no `contract` links. The `diff` links stay. One unit test for each case.
   - Alternative: skip the commit entirely.
2. **Where the comparison with `trace_links` is tested.** Proposed: only in M5 outline item 3, the close test after a real `run`, which can produce the orphan-commit exception. This task's AC6 pins only the link shape against the projector. Confirm that item 3 owns the "rebuild holds" check.

## Answers (human, 2026-10-23)
Plan approved. Design choices 1 to 5 and Open questions 1 and 2: all as proposed.

## Spec gaps
None. These are readings, not gaps:
1. "Returns these links" means a set with no order and no duplicates. The spec compares it for equality with rows, so order does not matter.
2. "requirement → task (`contract`)" from the rebuild has the same `source` as the projector's `PlanApproved` row. This is the same node, the same link and the same table row, which is what lets the comparison work.
3. The rebuild does not filter by spec version or `deprecated`. Trailers carry the ids as committed, and `trace_links` stores them without a version (ADR-018, "Versions (G14)").
4. The Later line on the milestone wording ("from git history alone", F-5) does not change what this task builds.

## Outcome
Built as planned.
- `domain/traces.py`: `LinkKind`, `LinkSource` and a frozen `TraceLink` with `extra="forbid"`.
- `app/rebuild_links.py`: `rebuild_links(*, git) -> set[TraceLink]`, one `branch_commits` call, `Task` filter, `contract`, `trailer` and `diff` links, missing `Agent-Run` or `Requirements` gives no links of its own, `GitError` propagates.
- Tests: `tests/unit/test_rebuild_links.py`, `tests/integration/test_rebuild_links_git.py` (real git and the projector conformance), additions to `tests/unit/test_traces_models.py`.
- Test edits: none were made to the test-writer's tests.
- Deviation: `TraceLink` declares its config as class arguments (`class TraceLink(BaseModel, frozen=True, extra="forbid")`) instead of `model_config`, because pyright's `reportUnhashable` does not see `model_config` frozen and the rebuild puts links in a set. Recorded in `docs/decisions.md`.
- Follow-ups: M5 item 3, the close test, compares the rebuild with `trace_links`. The TASK-087 review items (non-UTF-8 paths, `log.showSignature`) stay in "Later". The review's spec-gap note (Open question 1 settles a point the spec leaves open) and its coverage notes are lines under "Later".
