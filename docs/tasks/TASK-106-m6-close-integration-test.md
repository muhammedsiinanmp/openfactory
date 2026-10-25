# TASK-106: M6 close integration test

- Milestone: M6
- Status: done
- Tests: integration-only. The deliverable is one integration test file over code that is already built and tested by use case and command (TASK-090 to TASK-105). No production code is expected to change. TASK-019, TASK-057, TASK-078 and TASK-089 are the precedents. See Open question 1.
- ADR: ADR-019 (accepted, with its 2026-10-24 amendment). Its "Invalidation at approval" and "One approved plan" bullets are what this test checks end to end. Other ADRs that apply:
  - ADR-002 and ADR-010: identical rebuild.
  - ADR-011: `cli.py` is driven through `CliRunner`.
  - ADR-005: no test starts `claude`.
  - ADR-015: the stand-in `uv` technique.

  The task adds no port, adapter, dependency, event type, payload, storage change or production convention. The answers to the Open questions get rows in `docs/decisions.md`.
- Spec impact: none (see Spec gaps: readings only)
- Spec sections (spec v1.19):
  - "Purpose and demo scenario", steps 6 to 9: "6. The human edits the requirement … Approves spec v2. 7. `openfactory impact` shows the impacted subgraph … 8. `openfactory replan` proposes new and revised tasks only for the impacted subgraph; the human runs `openfactory approve plan`, which invalidates the impacted tasks; untouched tasks stay `passed`. 9. `openfactory run` executes only those". Also the success criteria "Re-execution after the change touches only impacted tasks." and "Every state change can be reconstructed from the event log."
  - "Milestones and definition of done", item 6: "**Impact and replan.** Structural diff, classifier, traversal, `impact`, `replan`, partial re-execution."
  - "Spec diff and impact analysis":
    - Steps 1 to 5.
    - "Approving a replan": "… records `TaskStateChanged` to `invalidated`, with reason `spec change <to_version>` … Then it moves to `ready` every `pending` task whose dependencies have all passed … Untouched tasks keep their state and commits. Only the new tasks run, from the tip of the chain, which still holds the invalidated work; the new tasks change it (see Base and branches)."
  - "Execution":
    - "Base and branches": "`<base>` is the `sha` of the `commits` row with the highest run id, compared by number, among the tasks of the plan".
    - "`run`": "After a task passes, every `pending` task of the plan whose dependencies have all passed moves to `ready`".
  - "Traceability" › "Commit trailers": "`Spec-Version` is the plan's spec version."
  - "Task contract" › "Plan checks": the replan rules of `unknown-dependency` and `uncovered`, and `task-id-in-use`.
  - "CLI commands" › "Output": the `impact`, `replan`, `approve plan`, `run` and `status` bullets.
  - "Domain model and storage" › "Projection rules": the supersede-and-move rule of `PlanApproved` (SC-158), and identical rebuild.

## Outline item
M6 outline item 8 in `docs/progress.md`, the last one: "M6 close integration test: demo steps 6 to 9 on a sample repo, with only the new tasks re-executed; checks that untouched tasks keep their state and commits ("Approving a replan")". It depends on items 1a to 7b (TASK-092 to TASK-105), all done. TASK-105 Open question 2 (answered 2026-10-24) left the "keep their … commits" check to this item.

## Objective
Add `tests/integration/test_m6_close.py`. It drives the real Typer app and the real adapters on a sample git repo, with a stand-in `claude`, `uv` and `gitleaks` first on `PATH`. It runs:
- an initial build (approve spec, plan, approve plan, run);
- demo steps 6 to 9: approve `sv_02`, `impact`, `replan`, `approve plan`, `run`, `status`.

It then checks:
- only the new tasks are executed, from the chain tip;
- the untouched task keeps its state, commit and branch;
- the projections rebuild identically.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- **New test file.** `tests/integration/test_m6_close.py` holds its own helpers, spec texts and stand-ins, as `test_m5_close.py` does, copied, not imported. It reuses `tests/fixtures/claude_envelope.json` and `tests/fixtures/claude_agent_envelope.json`.
- **The sample repo.** Built as in `test_m5_close.py`:
  - real `git init`, `app/main.py` and the SC-116 `.gitignore` committed;
  - local identity and `commit.gpgsign false`;
  - `GIT_*`, `ANTHROPIC_API_KEY`, `PYTEST_ADDOPTS`, `PYTHONPATH` and `VIRTUAL_ENV` removed;
  - `max_attempts: 2` in `specs/policies.yaml`.
- **Stand-ins.** `claude` picks its role from its arguments and standard input, in this order:
  - reviewer (always `approve`) when standard input holds `## Staged diff`;
  - classifier when standard input holds `You are the change classifier`;
  - replanner when standard input holds `## Replan instructions`;
  - planner when `--json-schema` is given;
  - implementer otherwise, the task taken from its working directory's name, writing that task's files.

  `uv` is `shift` then `exec <sys.executable> -m "$@"`, so the real `ruff`, `pytest`, `openfactory_req` plugin and tag rule run (decision of 2026-10-21, TASK-078). `gitleaks` exits 0.
- **One module-scoped flow fixture.** It runs the sequence once and keeps the outputs and snapshots each AC needs. Everything runs in-process through `CliRunner`; no kill and no child process.

Out:
- Any change under `src/`. If an assertion that traces to spec text fails, that is a defect: stop and report it with the spec text it breaks.
- Any edit to an existing test.
- `report` (demo step 9's second half) and `stats`: M7.
- A second replan, a deprecated or removed requirement, a cosmetic change, a refused `impact`, `replan` or `approve plan`. Their own command tests cover these (TASK-096, TASK-103, TASK-105). The Later lines on the second-replan and deletion-only gaps stay open.
- A test that starts the real `claude`, `uv` or `gitleaks`.

## Sample plan and flow
The ids, dependencies, paths, test names and replies are fixed, because the criteria depend on them. Objectives, titles and summaries are the test's choice.

**Spec `sv_01`** (`components: [auth]`):
- `REQ-AUTH-001` "users log in with a membership number", constrained by `ADR-001` (accepted). Criteria `AC-AUTH-001-1` and `AC-AUTH-001-2`.
- `REQ-AUTH-002` (config). Criteria `AC-AUTH-002-1` and `AC-AUTH-002-2`.

**Spec `sv_02`** (demo step 6). Only `REQ-AUTH-001` changes, and `ADR-001` is unchanged:
- its statement becomes "users log in with a one-time code";
- `AC-AUTH-001-1`'s text changes;
- `AC-AUTH-001-2` is removed;
- `AC-AUTH-001-3` is added.

**Plan `plan_01`.** Every task has `components: [auth]`, `role: implementer` and `allowed_paths: [app/, tests/]`.

| Task | Requirement / criteria | Depends on | Implementer writes |
| --- | --- | --- | --- |
| `AUTH-001` | `REQ-AUTH-002` / `AC-AUTH-002-1` | none | `app/config.py`; `tests/test_config.py` with `test_config` tagged `REQ-AUTH-002` |
| `AUTH-002` | `REQ-AUTH-001` / `AC-AUTH-001-1`, `AC-AUTH-001-2` | `AUTH-001` | `app/login.py`; `tests/test_login.py` with `test_login` tagged `REQ-AUTH-001` |
| `AUTH-003` | `REQ-AUTH-002` / `AC-AUTH-002-2` | `AUTH-002` | `app/token.py`; `tests/test_token.py` with `test_token` tagged `REQ-AUTH-002` |

**Classifier reply:**
```json
{"changes": [{"req_id": "REQ-AUTH-001", "kind": "replacement", "rationale": "…", "obsolete_criteria": ["AC-AUTH-001-1"], "new_work": ["OTP verify endpoint"]}]}
```
The lost `AC-AUTH-001-2` is added to `obsolete_criteria` by rule.

**Replan reply** (`plan_02`, on `sv_02`):

| Task | Requirement / criteria | Depends on | Implementer writes |
| --- | --- | --- | --- |
| `AUTH-004` | `REQ-AUTH-001` / `AC-AUTH-001-1`, `AC-AUTH-001-3` | `AUTH-001` (untouched) | rewrites `app/login.py`; rewrites `tests/test_login.py` to hold only `test_otp_login` tagged `REQ-AUTH-001` |
| `AUTH-005` | `REQ-AUTH-002` / `AC-AUTH-002-2` | `AUTH-004` | rewrites `app/token.py`; rewrites `tests/test_token.py` to hold only `test_otp_lifetime` tagged `REQ-AUTH-002` |

This reply passes the replan rules:
- `uncovered`: untouched `AUTH-001` covers `AC-AUTH-002-1`;
- `unknown-dependency`: `AUTH-004` depends on untouched `AUTH-001`;
- `task-id-in-use`: `AUTH-004` and `AUTH-005` are new ids.

**Run ids:**
- planner `run_0001`;
- `AUTH-001` `run_0002` (reviewer `run_0003`), `AUTH-002` `run_0004` (`run_0005`), `AUTH-003` `run_0006` (`run_0007`);
- classifier `run_0008`, replanner `run_0009`;
- `AUTH-004` `run_0010` (`run_0011`), `AUTH-005` `run_0012` (`run_0013`).

`S1` to `S5` are the tips of `openfactory/AUTH-001` to `openfactory/AUTH-005`.

**Flow:** `init`, `approve spec`, `plan`, `approve plan`, `run` (all three pass). Then a snapshot "before change": the `commits` rows, the three branch tips, the `tasks` rows and the highest `seq`. Then edit `requirements.yaml`, `approve spec`, `impact`, `replan`, `approve plan`, `run`, `status`, and the rebuild.

## Acceptance criteria
A snapshot is every row of the ten projection tables, read in primary-key order, as in `test_m5_close.py`.

- [x] **AC1** (demo steps 6 and 7; "Spec diff and impact analysis" steps 1 to 4; "CLI commands" › "Output", the `impact` bullet):
  - `approve spec` exits 0 and its last line is `approved sv_02`.
  - `impact` exits 0, writes nothing to standard error and prints exactly:
    ```
    requirement  REQ-AUTH-001  modified  replacement
    task  AUTH-002
    downstream  AUTH-003
    file  app/login.py
    file  app/token.py
    file  tests/test_login.py
    file  tests/test_token.py
    test  tests/test_login.py::test_login
    test  tests/test_token.py::test_token
    obsolete  AC-AUTH-001-1
    obsolete  AC-AUTH-001-2
    new-work  REQ-AUTH-001  OTP verify endpoint
    impact sv_01..sv_02
    ```
  - It records, in order:
    - `AgentRunStarted` for `run_0008`, role `classifier`, no task;
    - its `AgentRunFinished`;
    - `ImpactComputed` on `spec:sv_02`, with `from_version` `sv_01`, `to_version` `sv_02` and `run_id` `run_0008`.
- [x] **AC2** (demo step 8, first half; "Step 5: replan": "records … `PlanCreated` of a draft plan for the latest approved version that holds only the new tasks. It invalidates nothing."; "Output", the `replan` bullet):
  - `replan` exits 0 with standard error empty. It prints exactly the `AUTH-004  <objective>` line, the `AUTH-005  <objective>` line, then `created plan_02`.
  - The planner run is `run_0009`.
  - The draft `PlanCreated` for `plan_02` has `spec_version` `sv_02` and holds exactly `AUTH-004` and `AUTH-005`.
  - No `TaskStateChanged` is recorded from the "before change" `seq` through the end of `replan`.
  - `plan_01` is still `approved`, and `AUTH-001` to `AUTH-003` are still `passed`.
- [x] **AC3** (demo step 8, second half; "Approving a replan"; "Projection rules", SC-158; "Output", the `approve plan` bullet):
  - `approve plan` exits 0 and prints exactly:
    ```
    AUTH-002  invalidated
    AUTH-003  invalidated
    AUTH-004  ready
    approved plan_02
    ```
  - The two invalidations have reason `spec change sv_02`.
  - In the projections:
    - `plan_01` is `superseded` and `plan_02` is `approved`;
    - all five tasks have `plan_id` `plan_02`;
    - `AUTH-005` is `pending`.
- [x] **AC4** (demo step 9, first half; "Approving a replan": "Only the new tasks run, from the tip of the chain"; "Base and branches"; "Commit trailers": "`Spec-Version` is the plan's spec version"; "Output", the `run` bullet):
  - `run` exits 0 and prints exactly `AUTH-004  passed` then `AUTH-005  passed`.
  - Its events name no task other than `AUTH-004` and `AUTH-005`.
  - The only implementer `AgentRunStarted` events are `run_0010` (`AUTH-004`) and `run_0012` (`AUTH-005`).
  - `S4`'s parent is `S3`, and `S5`'s parent is `S4`.
  - `S4` and `S5` carry `Task: AUTH-004` and `Task: AUTH-005`, and both carry `Spec-Version: sv_02`.
  - `commits` gains exactly (`S4`, `AUTH-004`, `run_0010`) and (`S5`, `AUTH-005`, `run_0012`).
- [x] **AC5** ("Approving a replan": "Untouched tasks keep their state and commits"; demo step 8: "untouched tasks stay `passed`"; "Output", the `status` bullet):
  - After the last `run`, the `commits` rows of `AUTH-001` to `AUTH-003` equal the "before change" rows, and `openfactory/AUTH-001` to `AUTH-003` still point at `S1` to `S3`.
  - No event on `task:AUTH-001` has a `seq` above the "before change" `seq`. `task:AUTH-002` and `task:AUTH-003` each have exactly one: the invalidation.
  - `status` exits 0 and prints exactly:
    ```
    AUTH-001  passed  1/2  review passed
    AUTH-002  invalidated  1/2  review passed
    AUTH-003  invalidated  1/2  review passed
    AUTH-004  passed  1/2  review passed
    AUTH-005  passed  1/2  review passed
    ```
- [x] **AC6** ("Projection rules": identical rebuild; success criterion "Every state change can be reconstructed from the event log"):
  - After `status`, the ten-table snapshot is not empty, and emptying the tables gives a different snapshot.
  - After `SqliteEventRecorder.rebuild()` the snapshot equals the first one, `projection_state` is (`1`, highest `seq`), and `events` is unchanged.
  - The full suite passes with no existing test edited, and nothing under `src/` changes (a review check on the diff).

## Architecture rules that apply
- No module under `src/` changes. The test imports only `openfactory.cli.app` and `SqliteEventRecorder`.
- The `DELETE` in AC6 is the test damaging disposable tables (decisions row of 2026-10-10). The test never writes `events` through anything but the app.
- All LLM calls go through `claude -p`, here a stand-in. `ANTHROPIC_API_KEY` is removed, not read.

## Plan
1. Create branch `task/TASK-106-m6-close-integration-test` from an up-to-date main.
2. Record the human's answers to the Open questions here, and the rows in `docs/decisions.md`.
3. Write `tests/integration/test_m6_close.py`:
   - the spec texts for `sv_01` and `sv_02`, the plan, classifier and replan replies, and the stand-ins;
   - helpers `query`, `events_between`, `snapshot`, `empty_projections`, `rebuild`, `tip`, `trailer` and `parent`;
   - one module-scoped flow fixture.
4. Run the file. It is expected to pass with no `src/` change. Hand check: in the working tree only, comment out the supersede-and-move statements of `SqliteProjector.apply`'s `PlanApproved` branch, and watch AC3 and AC4 fail. Then restore it and say so in the Outcome.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/progress.md`: Current, a Done line, item 8 marked done, and the M6 box per Open question 2;
   - `docs/decisions.md`: rows for the answers;
   - `docs/architecture.md`: only where a section names the close tests;
   - fill in the Outcome.
7. Commit `test(cli): add the M6 close integration test` with the trailers `Task: TASK-106` and `Milestone: M6`. Do not push.

## Files expected to change
- `tests/integration/test_m6_close.py` (new, about 500 lines; see Open question 1)
- `docs/progress.md`, `docs/decisions.md`, possibly `docs/architecture.md`
- `docs/tasks/TASK-106-m6-close-integration-test.md` (this record)

Not expected to change: anything under `src/`, every existing test file, the fixtures, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

## Open questions
None of these is a spec decision. Each has a proposal and an alternative.

1. **Size and Tests field.** About 500 lines, against the ~300 aim. TASK-057 (548), TASK-078 (607) and TASK-089 were each approved as one task, the last "for this task only".
   - Proposed: one task, `integration-only`. The failing check comes from AC6's emptied snapshot and the hand check in Plan step 4.
   - Alternative: split. TASK-106 would be the initial build through `approve plan` (AC1 to AC3). TASK-107 would be the re-run, untouched tasks and rebuild (AC4 to AC6), with the fixture copied over.
2. **Ticking M6.** M4 and M5 are unticked, pending the human's real `run` (Blockers).
   - Proposed: leave M6 unticked as well. Extend the Blockers line: after the real build, the human edits a requirement on the scratch repo and runs `approve spec`, `impact`, `replan`, `approve plan` and `run`, and M6 is ticked with M4 and M5.
   - Alternative: tick M6 on the green suite alone.
3. **`trace` after the re-run.**
   - Proposed: leave it out. "Approving a replan" and outline item 8 do not name it, and `test_m5_close.py` covers `trace`.
   - Alternative: add to AC5 a `trace REQ-AUTH-001` check after the run, showing `AUTH-002  invalidated` and `AUTH-004  passed` with both commits. That adds about 20 lines.

### Answers (human, 2026-10-24)
1. One `integration-only` task, for this task only; not a general rule.
2. M6 stays unticked. The Blockers line is extended: after the real build, the human edits a requirement on the scratch repo and runs `approve spec`, `impact`, `replan`, `approve plan` and `run`. The M6 part passes when only the new tasks run and pass and the untouched tasks stay `passed`. M6 is ticked with M4 and M5.
3. No `trace` check. A "Later" line notes that `trace` after a supersede has no end-to-end check yet, for M7's `report` task.

## Spec gaps
None blocking; Spec impact is none. These are readings:
1. **"Untouched tasks keep their … commits"** is read as: their `commits` rows are unchanged, and their `openfactory/<task id>` branch tips are unchanged.
2. **"Only the new tasks run, from the tip of the chain".** After the move every task is in `plan_02`, so by "Base and branches" `<base>` for `AUTH-004` is `S3`, the commit with the highest run id, and an invalidated task's. AC4 asserts `S4`'s parent is `S3`.
3. **Demo step 9's `openfactory report`** belongs to M7 and is out of this milestone.
4. **Demo step 8's "new and revised tasks".** A revised task gets a new id ("Task contract": "`invalidated` is a terminal state, so a revised task in a later plan always gets a new id"). `AUTH-004` and `AUTH-005` stand for the revised `AUTH-002` and `AUTH-003`.
5. **The `impact` tests line.** The `test_tag` rows are the latest collection (`AUTH-003`'s, holding all three test files). `tests/test_config.py::test_config` is neither tagged with the seed nor in an impacted file, so it is not listed.

## Outcome
- Added `tests/integration/test_m6_close.py`: 7 tests, 595 lines (the estimate was about 500), covering AC1 to AC6. `test_first_build_passes_all_three_tasks` guards the initial build. No file under `src/` changed and no existing test was edited.
- Full suite: 2078 passed. ruff, pyright and `check_docs` are clean.
- Deviation from the planned wording: AC2's "`AUTH-001` to `AUTH-003` are still `passed`" is asserted on those three rows only, because the draft `plan_02`'s tasks are projected as `pending` too. The spec expects this; it is not a defect.
- Hand check: removing the supersede-and-move UPDATEs (the `tasks` `plan_id` move and the `plans` `superseded` update) in `SqliteProjector.apply`'s `PlanApproved` branch made AC3, AC4 and AC5 fail. The file was restored with `git checkout`.
- Answers 1 to 3 are rows in `docs/decisions.md`. M6 stays unticked and the Blockers line in `docs/progress.md` is extended (answer 2). The `trace` Later line is added (answer 3).
