# TASK-064: `Plans.last_gate_result`

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-015 (accepted). Its "Ports and adapters" section says: "`Plans` gains the last gate result of a task, for `status`. It stays read-only ([ADR-012])." ADR-012 covers the read ports and ADR-006 covers the `TYPE_CHECKING` assertion. The task adds no new port, adapter, dependency, event, payload or storage change. The answer to the open question becomes a row in `docs/decisions.md`.
- Spec impact: wording. Two items, neither blocks (see "Spec gaps").
- Spec sections (spec v1.16; SC-92):
  - "Domain model and storage" › "Ids": "They read the plan and task projections through the `Plans` port: ... the latest commit of a plan with its task id, and the last gate result of a task (for `status`). ... Both are read-only."
  - "CLI commands" › "Output", the `status` bullet: "`gate` is `<gate> passed` or `<gate> failed` for the last gate, in `required_gates` order, evaluated for the task's latest implementer run that has a gate result, or `-` when there is none".
  - "Domain model and storage" › "Projections": the `gate_results` DDL (`run_id`, `gate`, `passed`, `output_path`, `PRIMARY KEY (run_id, gate)`) and the `agent_runs` DDL (`task_id`, `role`).
  - "Domain model and storage" › "Event payloads", `GateEvaluated.run_id`: "the implementer run whose result the gate judged".

## Outline item
This is the second and last half of M4 outline item 4. The first half was TASK-063. The first caller is item 12 (`status`).

## Objective
Give `status` a task's last gate result: the last gate, in the contract's `required_gates` order, evaluated for the task's latest implementer run that has a gate result, read from the projections.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/domain/plans.py`: a new frozen model `GateResultRef` with `gate: GateName` and `passed: bool`, `extra="forbid"`, both fields required. The shape is proposed in Open question 1.
- `src/openfactory/ports/plans.py`: a new method `last_gate_result(task_id: str) -> GateResultRef | None`.
- `src/openfactory/adapters/sqlite_plans.py`: `SqlitePlans.last_gate_result` runs only `SELECT`s:
  1. Among the `gate_results` rows joined to `agent_runs` on `run_id`, keep those whose `agent_runs.task_id` is the task and whose `role` is `implementer`.
  2. Take the run with the highest run number (`CAST(substr(run_id, 5) AS INTEGER)`, as `latest_commit` does).
  3. Among that run's rows, return the one whose gate comes last in the task's `contract.required_gates`, read from `tasks.contract`.
  4. Return `None` when there is no such row or no `tasks` row.
- Tests:
  - A new `tests/integration/test_sqlite_plans_last_gate.py`. Events are recorded through `SqliteEventRecorder`, as in `tests/integration/test_sqlite_read_ports_m3.py`.
  - One test edit that needs approval: the exact method-set assertion in `tests/unit/test_plans_port.py::test_ac1_plans_is_a_protocol_with_exactly_the_five_reads` goes from six names to seven, adding `last_gate_result`. The name is kept, as in TASK-042 and TASK-063, and the existing Later line on that name is extended.

Out:
- The `status` use case and command, and the `<gate> passed` / `<gate> failed` / `-` text (outline item 12).
- Any change to `app/`, `cli.py`, the projector or the `gate_results` DDL. `task_id` stays unprojected.
- The test fakes of `Plans` in `tests/unit/test_run_task.py`, `test_run_plan.py` and `test_repair_plan.py`.
- Handling a gate row whose gate is not in the contract's `required_gates`. `complete_contract` always sets all five gates, so this cannot happen today; see Spec gaps item 2.

## Acceptance criteria
- [x] **AC1** ("Ids": "the last gate result of a task (for `status`) ... Both are read-only"):
  - `Plans` is a Protocol with exactly `current_draft`, `approved`, `next_id`, `tasks`, `live_tasks_referencing`, `latest_commit` and `last_gate_result`.
  - `GateResultRef` is frozen, rejects unknown fields, has exactly `gate` and `passed`, and rejects a `gate` outside the five gate names.
  - Neither `ports/plans.py` nor `domain/plans.py` imports from `adapters` or `app`.
  - `sqlite_plans.py` imports nothing from `app` and keeps its `TYPE_CHECKING` assertion.
- [x] **AC2** ("Output", `status`: "or `-` when there is none"). `last_gate_result` returns `None` in three cases:
  - a task with no implementer run;
  - a task whose only implementer runs have no `GateEvaluated` (for example a run that finished with `exit` `error`, or one with no `AgentRunFinished`);
  - a task id that has no row in `tasks`.
- [x] **AC3** ("Output", `status`: "the last gate, in `required_gates` order, evaluated for the task's latest implementer run"). For one run, the result is the evaluated gate that comes latest in `required_gates`, with its `passed`. Cases:
  - only `path_check` failed gives (`path_check`, false);
  - `path_check`, `ruff` and `pytest` passed and `gitleaks` failed, with no `review`, gives (`gitleaks`, false);
  - all five passed gives (`review`, true);
  - the same rows recorded in a different event order give the same answer.
- [x] **AC4** ("Output", `status`: "the task's latest implementer run that has a gate result"):
  - With gate results on `run_0002` and `run_0003` of one task, the result comes from `run_0003`.
  - `run_0010` comes after `run_0009`: run numbers are compared as numbers.
  - A later implementer run of the task with no gate result does not hide the earlier run's result.
  - Gate results of another task's runs never count.
- [x] **AC5** ("Ids": "Both are read-only"):
  - `last_gate_result` changes no row of any projection table.
  - A `SqlitePlans` opened before the events are recorded on another connection sees them.

## Architecture rules that apply
- The domain stays pure. The port is a Protocol only. The adapter runs only `SELECT`, creates no table, and ends with its `TYPE_CHECKING` assertion.
- No event, payload, projection or schema change, and no new dependency.
- `app/` and `cli.py` are unchanged.

## Plan
1. Create branch `task/TASK-064-plans-last-gate-result` from an up-to-date main.
2. Record the answer to Open question 1 and add its row to `docs/decisions.md`.
3. Test-writer: write failing tests.
   - AC1: the approved edit in `tests/unit/test_plans_port.py`, and a new model test in the same file or in the new file.
   - AC2 to AC5: `tests/integration/test_sqlite_plans_last_gate.py`.
4. Add `GateResultRef`, the Protocol method and `SqlitePlans.last_gate_result`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the living docs and the Outcome.
7. Commit `feat(ports): add the last gate result of a task` with the trailers `Task: TASK-064` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/domain/plans.py` (about +8)
- `src/openfactory/ports/plans.py` (about +7)
- `src/openfactory/adapters/sqlite_plans.py` (about +25)
- `tests/integration/test_sqlite_plans_last_gate.py` (new, about 180)
- `tests/unit/test_plans_port.py` (one assertion, plus about 15 for the model test)
- `docs/architecture.md`:
  - the `GateResultRef` entry next to `CommitRef`;
  - "Plans port": seven methods;
  - "SQLite plans": the tables it reads now include `gate_results` and `agent_runs`, and the query;
  - data flow: nothing calls it yet.
- `docs/progress.md`: Current, Done, outline item 4 marked done, Later lines.
- `docs/decisions.md`: a row for the answer.
- `docs/tasks/TASK-064-plans-last-gate-result.md` (this record).

Not expected to change: the projector, `app/`, `cli.py`, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 240 lines with tests, about 40 of them in `src/`.

## Spec gaps
Spec impact is "wording". Neither item blocks, because neither changes which gate `status` shows. No answer is assumed.

1. **"Domain model and storage" › "Ids"**, "the last gate result of a task".
   - Unclear: the spec names no signature or return shape: a gate name and pass flag, `output_path` too, or text.
   - Why it does not block: `status` needs only the gate and whether it passed, and ADR-012 leaves signatures to the task, as TASK-042 did for `CommitRef`. → Open question 1.
2. **"CLI commands" › "Output"**, "the last gate, in `required_gates` order".
   - Unclear: the spec does not say what a gate row outside the contract's `required_gates` gives.
   - Why it does not block: `complete_contract` always sets all five gates in `REQUIRED_GATES` order, so no such row can exist. This goes to a Later line, with no test and no handling.

Existing Later line, not taken: `latest_commit` already notes that a task id reused by re-planning would mix two plans' rows. `last_gate_result`, which reads by task id through `agent_runs.task_id`, has the same exposure. Extend that line for M6.

## Open questions
1. **Shape of the read.**
   - Proposed: `last_gate_result(task_id: str) -> GateResultRef | None`, where `GateResultRef` is frozen with `gate: GateName` and `passed: bool`, next to `CommitRef` in `domain/plans.py`. The adapter applies the `required_gates` order from the task's stored contract, filters on `role = 'implementer'`, and compares run ids by number. `None` covers no result and no `tasks` row.
   - Alternative (a): return every gate result of the latest run with a result, and let the `status` use case pick the last one. This departs from the spec's "the last gate result of a task".
   - Alternative (b): add `output_path` to `GateResultRef`. `status` does not use it.
   - Alternative (c): order by the `REQUIRED_GATES` constant instead of the contract's `required_gates`. Today the result is the same, but it reads the spec less literally.

## Later lines in `docs/progress.md`
- Taken: none.
- Added or extended:
  - the "Spec wording" line for item 1 of Spec gaps, with the answer;
  - the unreachable gate outside `required_gates`;
  - the `test_ac1_plans_is_a_protocol_with_exactly_the_five_reads` name line (now seven names);
  - the task-id reuse line for `latest_commit`, extended to `last_gate_result`.

## Outcome
- Status: done.
- Tests: 15 new or changed tests failed first, then passed. Full suite: 1415 passed.
- Approved test edit: the method-set assertion in `tests/unit/test_plans_port.py` goes from six names to seven (adds `last_gate_result`); the test name is kept.
- Mechanical test fixes: none.
- Implementation note: the first draft of the query joined on a non-existent `agent_runs.run_id` column; corrected to `agent_runs.id`.
- Living docs: `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`.
