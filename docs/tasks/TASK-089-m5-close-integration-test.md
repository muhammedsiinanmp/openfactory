# TASK-089: M5 close integration test

- Milestone: M5
- Status: done
- Tests: integration-only. The deliverable is one integration test file over code that is already built and tested by command, use case and adapter (TASK-079 to TASK-088). No production code is expected to change. TASK-019, TASK-038, TASK-057 and TASK-078 are the precedents. See Open question 2.
- ADR: ADR-018 (accepted). Its "Rebuild from git" bullet states the check this test makes: "M5 is met when that set equals those rows for the tasks that have a `CommitRecorded`, apart from a commit made without its `CommitRecorded` that is still on its task's branch because the task was not retried." Other ADRs that apply:
  - ADR-002 and ADR-010: identical rebuild, and `rebuild()` lives on the adapter.
  - ADR-011: `cli.py` is driven through `CliRunner`.
  - ADR-005: no test starts `claude`.
  - ADR-015: gates and the stand-in `uv` technique.

  The task adds no port, adapter, dependency, event type, payload, storage change or production convention. The policy and kill choices get rows in `docs/decisions.md`.
- Spec impact: wording. See "Spec gaps"; it does not block the task.
- Spec sections (spec v1.17):
  - "Milestones and definition of done", item 5: "**Traceability.** `trace`, `why`, `coverage`; `TestsCollected` and the `trace_links` projection; rebuild the links of platform commits from git trailers alone."
  - "Milestones and definition of done", "Phase 1 is done when": "Every platform commit has trailers, and every file it changed resolves in `openfactory why` to that commit's task and requirements."
  - "Traceability": the link table; "Commit trailers"; the rebuild paragraph (SC-132): "The rebuild holds when that set equals the rows of those links in `trace_links` for the tasks that have a `CommitRecorded`, apart from the commit of a task that was made without its `CommitRecorded` and is still on the task's branch because the task was not retried."; "Queries".
  - "Domain model and storage" › "Projection rules": the `trace_links` bullets (SC-126, SC-127), rebuilding, identical rebuild, "M5 `trace_links`".
  - "Execution" › "Events of one task": "`TestsCollected` … is recorded after the git commit is made, just before `CommitRecorded`".
  - "Execution" › "Restart", steps 2 and 3, and "a commit made without its `CommitRecorded` becomes unreachable".
  - "CLI commands" › "Output": the `trace`, `why`, `coverage` and `run` bullets (SC-130, SC-131).

## Outline item
This is M5 outline item 3, the last one: "M5 close integration test, the rebuild check included". It depends on items 1 and 2 (TASK-079 to TASK-088), all done. TASK-088 Open question 2 (answered 2026-10-23) gave the comparison with `trace_links` to this item.

## Objective
Add `tests/integration/test_m5_close.py`. Through the real Typer app and the real adapters, on a sample git repo with a stand-in `claude`, `uv` and `gitleaks` first on `PATH`, it covers:
- a `run` killed with a real `SIGKILL` after a task's git commit and before its `TestsCollected`, then a restarting `run`;
- `coverage`, `trace` and `why` on the result;
- the rebuild check: `rebuild_links(git=GitCli(repo))` against the `trace_links` rows, with the orphan-commit exception;
- the ten projection tables, found identical after `SqliteEventRecorder.rebuild()`.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- **New test file.** `tests/integration/test_m5_close.py` holds its own helpers, spec texts and stand-ins, as `test_m4_close.py` does. It reuses `tests/fixtures/claude_envelope.json` and `tests/fixtures/claude_agent_envelope.json`.
- **The sample repo.** Built as in `test_m4_close.py`:
  - real `git init`, `app/main.py` and the SC-116 `.gitignore` committed;
  - local identity and `commit.gpgsign false`;
  - `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `PYTEST_ADDOPTS`, `PYTHONPATH` and `VIRTUAL_ENV` removed.
  - Then: `init`, specs, `specs/policies.yaml` set to `max_attempts: 1` (Open question 1), `approve spec`, `plan` and `approve plan`.
- **Stand-ins.**
  - `claude`: planner when `--json-schema` is given, reviewer (always `approve`) when standard input holds `## Staged diff`, implementer otherwise, the task taken from its working directory's name.
  - `uv`: exec `sys.executable -m "$@"` after dropping `run`, as in TASK-078, so the real `ruff`, `pytest`, `openfactory_req` plugin and tag rule run.
  - `gitleaks`: exits 0.
- **The killed run.** As in `test_m3_close.py`, a child process runs `openfactory.cli.app` with `SqliteEventRecorder.record` patched to `SIGKILL` itself when the event is `TestsCollected` for `AUTH-003`.
- **The rebuild.** The test imports `openfactory.app.rebuild_links.rebuild_links` and `openfactory.adapters.git_cli.GitCli` directly, since the spec makes the rebuild "a function, not a command". It also imports `SqliteEventRecorder` for `rebuild()`.

Out:
- Any change under `src/`. If an assertion that traces to spec text fails, that is a defect: stop and report it with the spec text it breaks.
- Any edit to an existing test, `test_m3_close.py` and `test_m4_close.py` included.
- A deprecated requirement in `coverage`, `trace` refusals and `why` refusals. Their own command tests cover them (TASK-082, TASK-084, TASK-086).
- `why` on the orphan commit's files (see Spec gaps).
- The TASK-087 review items in "Later" (non-UTF-8 paths, `log.showSignature`).
- A test that starts the real `claude`, `uv` or `gitleaks`.

## Sample plan and flow
The ids, dependencies, paths, test names and kill point are fixed, because the criteria depend on them. Objectives, statements and summaries are the test's choice.

Spec: `components: [auth]`. `REQ-AUTH-001` has criteria `AC-AUTH-001-1` and `AC-AUTH-001-2` and is constrained by `ADR-001` (accepted). `REQ-AUTH-002` has `AC-AUTH-002-1`.

Every task has `components: [auth]`, `role: implementer` and `allowed_paths: [app/, tests/]`.

| Task | Requirement / criterion | Depends on | Implementer writes |
| --- | --- | --- | --- |
| `AUTH-001` | `REQ-AUTH-001` / `AC-AUTH-001-1` | none | `app/login.py`; `tests/test_login.py` with `test_login` tagged `REQ-AUTH-001` |
| `AUTH-002` | `REQ-AUTH-001` / `AC-AUTH-001-2` | `AUTH-001` | edits `app/login.py`; adds `app/otp.py` and `tests/test_otp.py` with `test_otp_tagged` (tagged `REQ-AUTH-001`) and `test_otp_untagged` (no marker) |
| `AUTH-003` | `REQ-AUTH-002` / `AC-AUTH-002-1` | none | `app/config.py`; `tests/test_config.py` with one test tagged `REQ-AUTH-002` |

Run ids: planner `run_0001`; `AUTH-001` `run_0002` (reviewer `run_0003`); `AUTH-002` `run_0004` (`run_0005`); `AUTH-003` `run_0006` (`run_0007`).

**First `run` (child process).** `AUTH-001` passes, then `AUTH-002` (lowest ready id first), then `AUTH-003` passes all five gates and is committed on `openfactory/AUTH-003` above `AUTH-002`'s tip. The process is killed when `TestsCollected` for `AUTH-003` is about to be recorded.

**Second `run`.** The repair:
- step 2: `AUTH-003` `gating` to `failed`, reason `interrupted`;
- step 3: `failed` to `escalated`, reason `attempts exhausted` (attempt 1 of 1).

No task is ready, and the branch stays.

**Then** `coverage`, `trace REQ-AUTH-001`, `trace REQ-AUTH-002`, `why app/login.py`, and `why` on every file of every `commits` row.

## Acceptance criteria
A snapshot is every row of the ten projection tables, read in primary-key order. `S1` and `S2` are the tips of `openfactory/AUTH-001` and `openfactory/AUTH-002`, and `S3` is the tip of `openfactory/AUTH-003`.

- [x] **AC1** ("Execution" › "Events of one task": "`TestsCollected` … is recorded after the git commit is made, just before `CommitRecorded`"; "Restart" steps 2 and 3; "Projection rules", the `TestsCollected` bullet; "CLI commands" › "Output", the `run` bullet):
  - The child exits with `-9`. `S3`'s parent is `S2`, and `S3` carries `Task: AUTH-003` and `Agent-Run: run_0006`. The log holds no `TestsCollected` and no `CommitRecorded` for `AUTH-003`.
  - The second `run` prints nothing on either stream and exits 0. It records exactly two events for `AUTH-003`: `gating` to `failed` (reason `interrupted`), then `failed` to `escalated` (reason `attempts exhausted`). Both have actor `orchestrator` and no `causation_id`.
  - Afterwards `openfactory/AUTH-003` still points at `S3`.
  - `commits` holds exactly (`S1`, `AUTH-001`, `run_0002`) and (`S2`, `AUTH-002`, `run_0004`).
  - The `test_tag` rows of `trace_links` are exactly the five that `AUTH-002`'s `TestsCollected` gives: three test → file and two test → requirement.
- [x] **AC2** ("CLI commands" › "Output", the `coverage` bullet; "Traceability" › "Queries": "requirements with no passing tagged test"). `coverage` prints exactly `REQ-AUTH-002`, writes nothing to standard error and exits 0.
- [x] **AC3** ("CLI commands" › "Output", the `trace` bullet). `trace REQ-AUTH-001` prints exactly these lines, with standard error empty and exit 0:
  ```
  task  AUTH-001  passed
  task  AUTH-002  passed
  commit  S1  AUTH-001
  commit  S2  AUTH-002
  file  app/login.py
  file  app/otp.py
  file  tests/test_login.py
  file  tests/test_otp.py
  test  tests/test_login.py::test_login  tagged
  test  tests/test_otp.py::test_otp_tagged  tagged
  test  tests/test_otp.py::test_otp_untagged  file
  ```
  `trace REQ-AUTH-002` prints exactly `task  AUTH-003  escalated` and exits 0, with no commit line for `S3`.
- [x] **AC4** ("CLI commands" › "Output", the `why` bullet; "Phase 1 is done when": "every file it changed resolves in `openfactory why` to that commit's task and requirements"):
  - `why app/login.py` prints exactly `commit  S1  AUTH-001`, `commit  S2  AUTH-002`, `task  AUTH-001  passed`, `task  AUTH-002  passed`, `requirement  REQ-AUTH-001`, `adr  ADR-001`, and exits 0.
  - For each `commits` row, the paths `git diff-tree -r --no-renames --name-only <sha>^ <sha>` lists are the files of its `CommitRecorded`. `why <path>` for each of them exits 0 and prints a `commit  <sha>  <task>` line and a `task  <task>  passed` line, plus a `requirement` line for each id in the commit's `Requirements` trailer.
- [x] **AC5** ("Traceability", the rebuild paragraph; ADR-018 "Rebuild from git"). Let:
  - `R` be `rebuild_links(git=GitCli(repo))`;
  - `O` be exactly the five links of `S3`: `REQ-AUTH-002` → `AUTH-003` (`contract`), `AUTH-003` → `run_0006` and `run_0006` → `S3` (`trailer`), and `S3` → `app/config.py` and `S3` → `tests/test_config.py` (`diff`);
  - `T` be the `trace_links` rows, read as `TraceLink`s, of the four link kinds the rebuild gives, for the tasks that have a `CommitRecorded` (`AUTH-001`, `AUTH-002`). These are: requirement → task `contract` rows to those tasks; their task → run `trailer` rows; run → commit `trailer` rows from those runs; and commit → file `diff` rows from those commits.

  Then:
  - `O` ⊆ `R`, and `R − O == T`.
  - `trace_links` holds the `contract` row `REQ-AUTH-002` → `AUTH-003`, which is not in `T`.
  - No `trailer` or `diff` row of `trace_links` names `S3`.
  - `REQ-AUTH-001` → `AUTH-001` and → `AUTH-002` are both in `R` and `T`. `app/login.py` has two `diff` links, one from `S1` and one from `S2`, in both. (This covers the TASK-088 Later line on links shared across commits.)
- [x] **AC6** ("Projection rules": rebuilding, identical rebuild, "M5 `trace_links`"; "CLI commands" › "Output": "`trace`, `why` and `coverage` record no events and do not repair the plan"):
  - The highest `seq` and the event count are the same before and after all the AC2 to AC4 commands.
  - After the last command, the snapshot of the ten tables is non-empty (`trace_links` included), and emptying the tables gives a different snapshot.
  - After `rebuild()` the snapshot equals the first, `projection_state` is (`1`, highest `seq`) and `events` is unchanged.
  - The full suite passes with no existing test edited.

## Architecture rules that apply
- No module under `src/` changes. The test imports only `openfactory.cli.app`, `SqliteEventRecorder`, `GitCli`, `rebuild_links` and `TraceLink`.
- The `DELETE` in AC6 is the test damaging disposable tables (decisions row of 2026-10-10). The test never writes `events` or `trace_links` through anything but the app.
- All LLM calls go through `claude -p`, here a stand-in. `ANTHROPIC_API_KEY` is removed, not read.

## Plan
1. Create branch `task/TASK-089-m5-close-integration-test` from an up-to-date main.
2. Record the human's answers to the Open questions here, and the rows in `docs/decisions.md`.
3. Write `tests/integration/test_m5_close.py`:
   - spec texts, the plan reply, the stand-ins and the child script;
   - helpers `query`, `snapshot`, `empty_projections`, `rebuild`, `tip`, `trailers` and `trace_rows`;
   - one module-scoped flow fixture that runs the sequence once and keeps the outputs.
4. Run the file. It is expected to pass with no `src/` change. Hand check: change the kill point to `CommitRecorded` (so `TestsCollected` is applied for `AUTH-003`) and watch AC1 and AC2 fail, then restore the file. Say so in the Outcome.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`: the `rebuild_links` section ("No command calls it yet; the M5 close test will compare …") and the test file list;
   - `docs/progress.md`: Current, a Done line, the M5 outline emptied, the M5 box per Open question 3, and the Later line from TASK-088 on shared commits marked taken;
   - `docs/decisions.md`: rows for the answers;
   - fill in the Outcome.
7. Commit `test(cli): add the M5 close integration test` with the trailers `Task: TASK-089` and `Milestone: M5`. Do not push.

## Files expected to change
- `tests/integration/test_m5_close.py` (new, about 450 to 500 lines; see Open question 2)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-089-m5-close-integration-test.md` (this record)

Not expected to change: anything under `src/`, every existing test file, the fixtures, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

## Open questions
None of these is a spec decision. Each has a proposal and an alternative.

1. **How to reach the orphan-commit exception.**
   - Proposed: `max_attempts: 1` in the sample policy, and a kill just before `AUTH-003`'s `TestsCollected`. The restart then escalates with `attempts exhausted`, and `S3` stays on the branch. Killing before `TestsCollected`, not `CommitRecorded`, keeps a stale collection out of `trace_links` (Events of one task: "a crash between the two leaves that collection …"), so `coverage` stays exact.
   - Alternative: keep `max_attempts: 2`, make `AUTH-003`'s first attempt fail `ruff`, and kill on the second. That costs one more round of gate processes and about 30 more lines.
   - A second alternative: drop the exception case and test only the plain equality. Then the half of the spec's rebuild sentence starting "apart from …" goes untested.
2. **Size and Tests field.** About 450 to 500 lines, against the ~300 aim. TASK-057 (548 lines) and TASK-078 (607 lines) were approved as one task.
   - Proposed: one task, `integration-only`. The failing check is covered by AC6's emptied-snapshot check and the hand check in Plan step 4.
   - Alternative: split. TASK-089 would be the flow, AC1 to AC4 and AC6. TASK-090 would be the rebuild check, AC5, about 150 lines, with the fixture copied over.
3. **Ticking M5.** M4 is still unticked, pending the human's real `run` (Blockers).
   - Proposed: leave M5 unticked as well. Extend the Blockers line: after the real `run` passes, the human runs `openfactory why <changed file>`, `trace <its requirement>` and `coverage` on the scratch repo, and M5 is ticked with M4.
   - Alternative: tick M5 on the green suite alone.

## Answers (human, 2026-10-23, following the advisor: 3 AGREE)
1. `max_attempts: 1` in the sample policy, kill just before AUTH-003's `TestsCollected`.
2. One task, `integration-only`, for this task only.
3. M5 stays unticked; it is ticked with M4 after the human's real `run` and `why`, `trace` and `coverage` on the scratch repo.

## Spec gaps
1. **Wording, not blocking.**
   - Spec heading: "Milestones and definition of done" › "Phase 1 is done when", item "Every platform commit has trailers, and every file it changed resolves in `openfactory why` to that commit's task and requirements."
   - The problem: this item conflicts with the rebuild paragraph's own exception. A commit the orchestrator made without its `CommitRecorded`, still on a task's branch because the task was not retried (`S3` here), is a platform commit with trailers. But its files have no `diff` row, so by the `why` bullet `why app/config.py` refuses with `no commit changed app/config.py`. The item does not say whether such a commit counts as a "platform commit".
   - Why it does not block: this task asserts the item only for commits that have a `CommitRecorded` (AC4), and leaves `why` on `S3`'s files unasserted rather than fixing either reading. The item is a Phase 1 gate, not an M5 criterion. Proposed for `/spec-change`: "every platform commit that has a `CommitRecorded`", or name the exception.

Readings, not gaps:
- "The rows of those links … for the tasks that have a `CommitRecorded`" is read as the four link kinds the rebuild returns, reached from those tasks: requirement → task to them, task → run from them, then run → commit and commit → file along those links. It excludes task → task `contract` rows, which the rebuild does not give.
- "apart from the commit …" is read as taking that commit's links (its `contract`, `trailer` and `diff` links) out of the rebuilt set before comparing.
- The `trace` test lines: whether the tagged and file lines are one group sorted by node id, or two groups, the chosen node ids give the same order either way.
- The second `run` prints nothing and exits 0: no task is `ready` after the repair ("with no `ready` task it prints nothing on standard output … and exits 0").

## Outcome
- `tests/integration/test_m5_close.py` (6 tests) passed first time with no `src/` change.
- Hand check: moving the kill point to `CommitRecorded` failed AC1, AC2 and AC3 (AC3 too, as AUTH-003's collection replaced the `test_tag` links). The file was restored.
- Full suite 1761 passed; ruff, pyright and check_docs clean.
- No test-writer tests (integration-only); no existing test edited.
- M5 stays unticked until the human's real `run` and `why`, `trace`, `coverage` (Blockers).
