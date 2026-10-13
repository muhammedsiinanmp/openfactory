# TASK-042: Read ports for `run`: the latest commit of a plan on `Plans`, the unfinished run of a task on `Runs`

- Milestone: M3
- Status: done
- Tests: acceptance
- ADR: ADR-014 (accepted). "Ports and adapters (SC-63, SC-68)": "`Plans` gains the latest commit of a plan with its task id; `Runs` gains the unfinished run of a task. Both stay read-only (ADR-012)." ADR-012 (accepted) covers the two ports, their adapters on their own connection and "Exact signatures are settled in the tasks that build them". ADR-006 covers the `TYPE_CHECKING` assertion. No new port, adapter, dependency, event type, payload or storage change. Names and return types are rows in `docs/decisions.md` (Open question 3).
- Spec impact: wording. One item, which does not stop the task (see "Spec gaps"): "the unfinished run of a task" does not say which run is given when a task has more than one. No criterion depends on it; it is Open question 2.
- Spec sections (spec v1.12, SC-56, SC-62, SC-68): "Domain model and storage" › "Ids" (the `Plans` and `Runs` sentences), "Projections" (the `commits` and `agent_runs` rows and their DDL); "Execution" › "Base and branches", "Restart"

## Outline item
M3 outline item 1, whole. Items 2 to 10 are left.

## Objective
Give `Plans` a read of the latest commit of a plan with its task id and `Runs` a read of the unfinished run of a task, with `SqlitePlans` and `SqliteRuns` behind them, so the `run` use case can find `<base>` and repair an interrupted task from the projections.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings and to SC-56, SC-62 and SC-68.

## Scope
In (names per Open question 3):
- `src/openfactory/domain/plans.py`: a frozen model `CommitRef` (`sha: CommitSha`, `task_id: TaskId`), unknown fields forbidden.
- `src/openfactory/ports/plans.py`: `latest_commit(plan_id: str) -> CommitRef | None`.
- `src/openfactory/ports/runs.py`: `unfinished_run(task_id: str) -> str | None`.
- `src/openfactory/adapters/sqlite_plans.py`: `latest_commit`, one `SELECT` over `commits` joined to `tasks` on the task id, the plan's rows ordered by the number in `run_id`.
- `src/openfactory/adapters/sqlite_runs.py`: `unfinished_run`, one `SELECT` over `agent_runs` for the task's rows with a null `exit`.
- New tests: one integration file for the two adapter reads.
- The two edits to fixed tests that the new methods force, approved by the human on 2026-10-13 (Open question 1): the exact sets in `tests/unit/test_plans_port.py` and `tests/unit/test_runs_port.py` gain the new method and stay exact; these two tests cover AC1's method sets.

Out (not this task):
- Every use case and command (outline items 7 to 9). Nothing calls the two methods yet.
- `GitProvider`, `WorkspaceManager`, `RunFiles`, `AgentExecutor` (items 2 to 5).
- Choosing `<base>` when the plan has no commit (`HEAD`): a `GitProvider` read (item 2) and the use case's rule (item 7).
- Deciding whether a `gating` task "has a `CommitRecorded`" (Restart step 1): the use case's rule, built from `latest_commit` and `tasks`.
- Recording `AgentRunFinished` for an unfinished run, and its order against the `TaskStateChanged` (audit F-2).
- Any change to `cli.py`, `sqlite_projector.py`, `sqlite_recorder.py`, `domain/payloads.py` or any module under `app/`.
- Any change to the existing fakes of `Plans` and `Runs` in `tests/unit/`. Pyright checks `src` only and no existing use case calls the new methods, so they keep working as they are.
- A commit whose `task_id` has no `tasks` row, a `commits` row with a `run_id` that has no `agent_runs` row, two commits with one run id, a plan with tasks in `invalidated` (M6).
- A task with two unfinished runs: no criterion and no test (Open question 2).
- A database without the tables: `sqlite3.OperationalError` is not handled, as for the existing reads.
- Hardening against exotic inputs.

## Acceptance criteria
"Ids" is the paragraph of that name under "Domain model and storage". Events are built through the payload models and recorded through `SqliteEventRecorder.record`; the adapters read on their own connection. `SHA_A`, `SHA_B` are any two different 40 lowercase hex strings. The plan used is `plan_01` with tasks `AUTH-001` and `AUTH-002`. An implementer run is an `AgentRunStarted` with role `implementer` and a task id.

- [x] AC1 ("Ids": "They read the plan and task projections through the `Plans` port: the current draft plan, the approved plan if there is one, the next plan id, the tasks of a plan with their dependencies, the live tasks that reference a requirement, and the latest commit of a plan with its task id. The `Runs` port gives the next run id and the unfinished run of a task. Both are read-only."):
  - `Plans` is a Protocol whose public methods are exactly `current_draft`, `approved`, `next_id`, `tasks`, `live_tasks_referencing` and `latest_commit`.
  - `Runs` is a Protocol whose public methods are exactly `next_id` and `unfinished_run`.
  - `openfactory.ports.plans` and `openfactory.ports.runs` import nothing from `openfactory.adapters` or `openfactory.app`; `openfactory.domain.plans` imports nothing from `ports`, `adapters` or `app`.
  - `uv run pyright` passes with the `TYPE_CHECKING` assertions at the end of `sqlite_plans.py` and `sqlite_runs.py` unchanged.
- [x] AC2 ("Execution" › "Base and branches": "when the plan has no commit, it is the commit `HEAD` of the repo points at when the task starts"):
  - With `plan_01` created and approved and no `CommitRecorded`, `latest_commit("plan_01")` is `None`.
  - For a plan id with no row, and on an empty log, it is `None`.
- [x] AC3 ("Base and branches": "`<base>` is the `sha` of the `commits` row with the highest run id, compared by number, among the tasks of the plan"; "Ids": "the latest commit of a plan with its task id"):
  - After `CommitRecorded` (`SHA_A`, `AUTH-001`, `run_0002`), `latest_commit("plan_01")` equals `CommitRef(sha=SHA_A, task_id="AUTH-001")`.
  - After a second `CommitRecorded` (`SHA_B`, `AUTH-002`, `run_0003`), it equals `CommitRef(sha=SHA_B, task_id="AUTH-002")`.
  - Run ids are compared by number: with commits of `run_9999` (`AUTH-001`) and `run_10000` (`AUTH-002`), the result is the commit of `run_10000`.
  - Only the tasks of the plan count: with a draft `plan_02` holding the task `API-001` and the one commit above for `AUTH-001`, `latest_commit("plan_02")` is `None` and `latest_commit("plan_01")` still gives `SHA_A`.
- [x] AC4 ("Ids": "The `Runs` port gives the next run id and the unfinished run of a task"; "Execution" › "Restart": "If it has an unfinished run, that run gets `AgentRunFinished`"; "Projections", the DDL comment on `agent_runs.exit`: "null until AgentRunFinished"):
  - With no run recorded, `unfinished_run("AUTH-001")` is `None`.
  - After `AgentRunStarted` for `run_0002`, task `AUTH-001`, it is `"run_0002"`.
  - After the `AgentRunFinished` of `run_0002` it is `None`.
  - Runs of others are not given: with an unfinished planner run (`task_id` null) and an unfinished implementer run of `AUTH-002`, `unfinished_run("AUTH-001")` is `None`.
  - `next_id()` is unchanged by the new method: after those events it is still one more than the highest run number.
- [x] AC5 ("Ids": "Both are read-only"; "Projection rules": "Projection tables are never written in any other way"):
  - An adapter opened before the events were recorded gives the new answers after them: `latest_commit` goes from `None` to the commit, and `unfinished_run` from `None` to the run id and back to `None`.
  - Calling `latest_commit` and `unfinished_run` changes no row of `events`, `plans`, `tasks`, `task_deps`, `commits`, `agent_runs` or `projection_state`.

## Architecture rules that apply
- `ports` holds Protocols only and imports from `openfactory.domain` only; `CommitRef` lives in the domain, beside `PlanRef` and `Task`.
- The adapters run only `SELECT`, create no table, cache nothing and keep their own connection (ADR-010, ADR-012). Each still ends with its `TYPE_CHECKING` assertion (ADR-006).
- Run ids are compared as integers (`CAST(substr(run_id, 5) AS INTEGER)`), the form `sqlite_runs.py` already uses.
- "All state changes go through the events table": tests fill the projections by recording events, never by writing rows.
- Tests from the test-writer are fixed. The two edits under Open question 1 are not mechanical; the human approved them on 2026-10-13, and each is reported in the Outcome.
- OpenFactory's own tests carry no `req` markers.
- No hardening beyond what the spec asks.

## Plan
1. Create branch `task/TASK-042-read-ports-latest-commit-and-unfinished-run` from an up-to-date main.
2. Get the human's answers to Open questions 1 to 3. Record them here and as rows in `docs/decisions.md`.
3. Write failing tests:
   - AC1: the approved edits of step 4; no new unit file.
   - `tests/integration/test_sqlite_read_ports_m3.py` (new) for AC2 to AC5, with the event builders and the `db`, `recorder`, `plans` and `runs` fixtures in the style of `tests/integration/test_sqlite_plans.py` and `test_sqlite_runs.py`.
4. Make the approved edits to `tests/unit/test_plans_port.py` and `tests/unit/test_runs_port.py` (Open question 1) and nothing else in those files.
5. Add `CommitRef` to `domain/plans.py`, then the two Protocol methods with their docstrings.
6. Add `SqlitePlans.latest_commit` and `SqliteRuns.unfinished_run`.
7. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
8. Update the living docs and the Outcome. Commit `feat(ports): read the latest commit of a plan and the unfinished run of a task` with trailers `Task: TASK-042` and `Milestone: M3`.

## Files expected to change
- `src/openfactory/domain/plans.py` (about 8 lines)
- `src/openfactory/ports/plans.py`, `src/openfactory/ports/runs.py` (about 8 lines each)
- `src/openfactory/adapters/sqlite_plans.py`, `src/openfactory/adapters/sqlite_runs.py` (about 15 lines each)
- `tests/integration/test_sqlite_read_ports_m3.py` (new, about 200 lines)
- `tests/unit/test_plans_port.py`, `tests/unit/test_runs_port.py` (the exact method set of each, per Open question 1)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-042-read-ports-latest-commit-and-unfinished-run.md` (this record; Outcome at close)

Not expected to change: `cli.py` (it opens `SqlitePlans` and `SqliteRuns` already), every module under `app/`, `sqlite_projector.py`, `sqlite_recorder.py`, `domain/payloads.py`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, and every other test file, the fakes of `Plans` and `Runs` included.

Expected size: about 250 lines with tests.

## Living docs to update
- `docs/architecture.md`:
  - "Plan and task references": `CommitRef`.
  - "Plans port": six methods, with `latest_commit`.
  - "SQLite plans": the query, and that it also reads `commits`.
  - "Runs port": two methods, with `unfinished_run`.
  - "SQLite runs": the query.
  - "Data flow": the two reads exist for the run use case and nothing calls them yet.
- `docs/progress.md`: Current, then Done; remove outline item 1, renumber and keep the "depends on" references correct; add the Later lines listed below.
- `docs/decisions.md`: rows for the answered open questions.
- `CHANGELOG.md` and `README.md`: no change (nothing a user sees).

## New dependencies
None.

## Spec gaps
Spec impact is "wording". The one item does not stop the task.

1. "Domain model and storage" › "Ids", "The `Runs` port gives the next run id and the unfinished run of a task", with "Execution" › "Restart", step 2: "If it has an unfinished run, that run gets `AgentRunFinished`". The text speaks of one unfinished run and does not say which is given if a task has two. The sequence as written produces at most one, because the repair finishes it before the task can run again. Two can arise only if a `run` is interrupted inside the repair itself, between the two events of step 2, whose order the spec does not give (audit F-2). It does not block: no criterion uses a task with two unfinished runs. The query still has to return something in that case, so it is Open question 2 for the human, not an assumption of the task.

Readings, not gaps (each follows from the text as written):
- "Unfinished" is an `agent_runs` row whose `exit` is null: the DDL comment says "null until AgentRunFinished".
- "Among the tasks of the plan" is the `tasks` rows whose `plan_id` is the plan's; `commits` has no plan column, so the read joins on the task id.
- "Highest run id, compared by number" needs no tie rule: a run gets at most one `CommitRecorded`.
- "With its task id" means the read returns the commit's `task_id` beside its `sha`. `run_id` and `branch` are not asked for, and the branch follows from the task id (`openfactory/<task id>`).
- `latest_commit` takes the plan id and does not look at the plan's status; `run` passes the approved plan's id ("`run` works on the approved plan").
- The audit findings F-1, F-5 and F-7 do not touch this task. F-1 is a git failure in the repair or on worktree removal (items 7 and 8). F-5 is the `RunFiles` port (item 4). F-7 is the `WorkspaceManager` port (item 3).

## Later lines in `docs/progress.md`: taken or left
- "Spec gap (before the M3 run use case is planned) ... F-1 ... F-5 ... F-7": left. Proposed rewording at close: F-7 is needed before item 3 (`WorkspaceManager`) is planned and F-5 before item 4 (`RunFiles`), because both decide a port signature; only F-1 waits for the run use case.
- "Wording, same report: F-2 order of the two events for an interrupted task": left; it is the source of the wording item above.
- "Spec gap (before M7 is planned): a started run can lack a finish ... a planner run is not covered (TASK-032)": left. `unfinished_run` takes a task id, so it never returns a planner run.
- "`test_ac1_spec_versions_is_a_protocol_with_the_three_methods` keeps a name its assertion no longer matches (TASK-024)": left; the same kind of line is added for the two tests of Open question 1 if their names are kept.
- Every other Later line: left; none concerns the read ports.
- To add at close:
  - Open question 1 keeps the names: "`tests/unit/test_plans_port.py::test_ac1_plans_is_a_protocol_with_exactly_the_five_reads` and `tests/unit/test_runs_port.py::test_ac1_runs_is_a_protocol_with_only_next_id` keep names their assertions no longer match (TASK-042)".
  - The "Spec wording" line for Open question 2 was added when the record was saved; at close it gains the answer given (the highest run number).

## Open questions
Question 2 is a spec wording item and is the human's to answer. The others are not spec decisions; each has a proposal.

1. **Two edits to fixed tests that the new methods force.** Both assert an exact method set and fail once a method is added.
   - `tests/unit/test_plans_port.py::test_ac1_plans_is_a_protocol_with_exactly_the_five_reads`: `public == {five names}`.
   - `tests/unit/test_runs_port.py::test_ac1_runs_is_a_protocol_with_only_next_id`: `public == {"next_id"}`.

   Proposed: change each `==` to `>=` (the earlier methods are present), keep the names with a Later line, and assert the exact sets of six and two in the new `tests/unit/test_m3_read_ports.py` (the TASK-024 and TASK-040 precedent). Alternative: update the sets and rename the tests in place, with no new unit file.
2. **Which run when a task has two unfinished runs?** (Spec gaps, item 1.) Proposed: the one with the highest run number; a row in `docs/decisions.md`; no test either way; the spec text left to a later `/spec-change`, together with F-2. Alternative: return every unfinished run of the task (`list[str]`, ascending), so the repair can finish all of them; this changes the port's signature and the wording "the unfinished run".
3. **Names and types.** Proposed:
   - `CommitRef` in `domain/plans.py` with `sha: CommitSha` and `task_id: TaskId`, frozen, unknown fields forbidden;
   - `Plans.latest_commit(plan_id: str) -> CommitRef | None`;
   - `Runs.unfinished_run(task_id: str) -> str | None`, a plain run id, as `next_id` returns a plain string.

   Alternative for the return of `latest_commit`: also carry `run_id` and `branch`, the whole `commits` row; the spec asks only for the task id.

### Answers (human, 2026-10-13: "do as the advisor says")
1. Update the two exact sets in place and keep them exact (six names for `Plans`, two for `Runs`); keep the test names, with a Later line; no `tests/unit/test_m3_read_ports.py`. This is the TASK-024 precedent (`docs/decisions.md`, 2026-10-11), not the subset form.
2. The run with the highest run number; a row in `docs/decisions.md` that also says the older unfinished run then keeps a null `exit`; no test; the spec text left to a later `/spec-change` with F-2.
3. As proposed: `CommitRef` (`sha: CommitSha`, `task_id: TaskId`), `latest_commit(plan_id: str) -> CommitRef | None`, `unfinished_run(task_id: str) -> str | None`.

## Outcome
Built:
- `CommitRef` (frozen, `sha: CommitSha`, `task_id: TaskId`, unknown fields forbidden) in `src/openfactory/domain/plans.py`.
- `Plans.latest_commit(plan_id: str) -> CommitRef | None` in `src/openfactory/ports/plans.py`; `SqlitePlans.latest_commit` is one `SELECT` over `commits` joined to `tasks` on the task id, for the plan's tasks, ordered by `CAST(substr(commits.run_id, 5) AS INTEGER) DESC LIMIT 1`.
- `Runs.unfinished_run(task_id: str) -> str | None` in `src/openfactory/ports/runs.py`; `SqliteRuns.unfinished_run` is one `SELECT` over `agent_runs` where `task_id = ?` and `exit IS NULL`, highest run number first, `LIMIT 1`.
- New `tests/integration/test_sqlite_read_ports_m3.py` (ten tests, AC2 to AC5).
- 1112 tests pass; ruff, pyright and check_docs are clean. Nothing calls the two methods yet.

Edits to fixed tests (approved by the human, 2026-10-13; not mechanical; names kept):
- `tests/unit/test_plans_port.py::test_ac1_plans_is_a_protocol_with_exactly_the_five_reads`: the expected set gained `latest_commit` and is now six names; the assertion is still an exact set (`==`).
- `tests/unit/test_runs_port.py::test_ac1_runs_is_a_protocol_with_only_next_id`: the expected set changed from `{"next_id"}` to `{"next_id", "unfinished_run"}`; the assertion is still an exact set (`==`).
- No `tests/unit/test_m3_read_ports.py` was created.

Deviations from the plan: none besides those the Answers section records (the in-place exact sets instead of the proposed subset form and new unit file).

Follow-ups (Later lines in `docs/progress.md`):
- The "Spec wording" line on a task with two unfinished runs gained the answer (highest run number; `docs/decisions.md`; no test; spec text for a later `/spec-change` with audit F-2).
- The "Spec gap" line on audit F-1, F-5 and F-7 is reworded: F-7 before the `WorkspaceManager` task is planned, F-5 before the `RunFiles` task is planned, F-1 before the run use case.
- New line: the two tests above keep names their assertions no longer match.
