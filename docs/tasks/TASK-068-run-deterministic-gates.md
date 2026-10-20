# TASK-068: Run the `ruff`, `pytest` and `gitleaks` gates and the pytest tag rule after `path_check`

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-015, ADR-016, ADR-017 (all accepted). ADR-015 "Gates and retry": "A `path_check` failure ends the gating; otherwise `ruff`, `pytest` and `gitleaks` all run, and `review` only when all three passed." ADR-017: "The use case chooses `secret found` from `finding`." The task adds no port, adapter, dependency, event type, payload, schema or convention.
- Spec impact: none
- Spec sections (spec v1.16; SC-84, SC-88, SC-123):
  - "Execution" › "Per-task sequence", step 5: "Run the other required gates in the worktree, in the order given under Gates and remediation."
  - "Gates and remediation" › "Order": "`path_check` runs first (see Execution); when it fails, no other gate runs. Otherwise `ruff`, `pytest` and `gitleaks` all run, in that order, each recording its `GateEvaluated`, so the failure report holds every failure."
  - "Gates and remediation" › "Running a gate that starts a process": "the `GateRunner` port ... has `run(gate, worktree, timeout_s) -> GateOutput`"; "`timeout_s` is the contract's `max_runtime_s`"; "the use case chooses `secret found` from it [`finding`]"; "The use case writes `text` through `RunFiles` on a pass and on a failure."
  - "Gates and remediation", last paragraph: "The file is `.openfactory/runs/<run id>/<gate>.txt`, written through the `RunFiles` port. `path_check` writes it only on a failure; the other gates write it on a pass and on a failure."
  - "Gates and remediation" › "The pytest gate and `req` markers": "The gate fails when `pytest tests/` does not exit 0 (...), or when, for a requirement in the contract, no collected test that carries its `req` marker is in a file among the path check's changed paths. When the tag rule fails, also when `pytest tests/` itself failed, the use case adds one line per uncovered requirement, `no tagged test in a changed file: <requirement id>`, to the gate's text before writing it."
  - "Execution" › "Events of one task": "When `gitleaks` reported a finding, the task goes `gating` to `failed`, then `failed` to `escalated`, both with reason `secret found`, whichever other gates failed. Otherwise a failed gate other than `path_check` is `gating` to `failed` with reason the name of the first failed gate in `required_gates` order."

## Outline item
M4 outline item 7, whole (the human chose not to split it, following the advisor).

## Objective
After a passing `path_check`, make `run_task` run `ruff`, `pytest` and `gitleaks` through `GateRunner` in that order. The pytest tag rule runs on the gate's marker lines and the path check's changed paths; when it fails, the `pytest` gate fails and its lines are added to the text. Each gate's text is written to `<gate>.txt` and recorded as a `GateEvaluated`. The task fails with `secret found` (then escalates) or with the first failed gate's name, and is committed only when all three pass.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/app/run.py`:
  - `run_task` gains a required keyword `gates: GateRunner`, and `run_plan` passes its `gates` through.
  - After a passing `path_check`, for each of `ruff`, `pytest`, `gitleaks` in that order:
    - call `gates.run(gate, worktree, task.contract.limits.max_runtime_s)`;
    - for `pytest`: `uncovered = uncovered_requirements(output.marker_lines, changed, task.contract)`; when it is not empty, the gate fails and `tag_rule_lines(uncovered)` are appended to the text, also when `output.passed` was already false. Appending: a `\n` is added first when the text is not empty and does not end in one, then each line followed by `\n` (a row in docs/decisions.md);
    - `run_files.write(run_id, f"{gate}.txt", text)`;
    - record `GateEvaluated` with `passed` and `output_path` (the returned path, POSIX form).
  - Then:
    - when `gitleaks` gave `finding`: `gating` to `failed`, then `failed` to `escalated`, both with reason `secret found`;
    - else, when a gate failed: `gating` to `failed` with reason the first failed gate in `task.contract.required_gates` order;
    - else: commit as today.
  - A failed task stays `failed` (retry is item 10).
- Tests: new tests in `tests/unit/test_run_task.py` with the prefix `test_task068_`, using a `FakeGates` that returns a set `GateOutput` per gate and logs its calls.
- Test edits that need approval:
  - `tests/unit/test_run_task.py`, mechanical:
    - the `Run` harness passes `gates=` with a `FakeGates` whose default makes all three gates pass, plus an optional keyword to set outputs per gate.
  - `tests/unit/test_run_task.py`, not mechanical (the spec changes the pass sequence):
    - `PASSED_SHAPE` and `test_ac1_passed_run_records_seven_events_in_order` gain three `GateEvaluated` before `CommitRecorded`;
    - `test_ac1_payloads_and_result` takes the commit at its new index, and its `run_files.calls == []` becomes the three gate writes;
    - in `test_t053_ac3_gating_git_failure_fails_the_task`, the `commit` case expects the four `GateEvaluated`.
  - `tests/unit/test_run_plan.py`:
    - `FakeGates.run` returns a passing `GateOutput` and appends to a new `run_calls`, where today it raises `AssertionError`;
    - the `test_task067_` refusal tests gain `assert r.gates.run_calls == []`, which keeps their intent.
  - `tests/integration/test_m3_close.py`:
    - the autouse fixture writes a stand-in `uv` into `claude-bin`, because the sample repo is not a uv project: it exits 0 and, when `OPENFACTORY_REQ_OUT` is set, writes a marker line `{"file": <a file the task changed>, "req": ["REQ-AUTH-001"]}` so the tag rule passes for the passed tasks;
    - `task_group(passed=True)` gains the `ruff`, `pytest` and `gitleaks` `GateEvaluated`;
    - `len(events) == 22` becomes 28, and the causation index `15` becomes `21`;
    - the `gate_results` rows gain the six passing rows with their `output_path`.
    - Outline item 13 still rewrites this test.

Out:
- The review gate (item 8): until then, a task whose three gates pass is committed without `review`, as M3 committed on `path_check` alone.
- The cost limit (item 9), retry, `attempts exhausted` and the failure report (item 10).
- Any change to `domain/`, `ports/`, `adapters/`, `cli.py`, events or the schema.

## Acceptance criteria
- [ ] **AC1** ("Order": "Otherwise `ruff`, `pytest` and `gitleaks` all run, in that order, each recording its `GateEvaluated`"; "Running a gate that starts a process": "`timeout_s` is the contract's `max_runtime_s`"):
  - After a passing `path_check`, `GateRunner.run` is called three times: `ruff`, `pytest`, `gitleaks`, each with the worktree from `WorkspaceManager.create` and the contract's `max_runtime_s`.
  - Each call is followed by its `GateEvaluated` (`run_id`, `task_id`, `gate`, `passed`), in the same order and in the task's chain.
  - All three run when an earlier one fails.
- [ ] **AC2** (last paragraph of "Gates and remediation": "the other gates write it on a pass and on a failure"; "The use case writes `text` through `RunFiles`"):
  - Each of the three gates writes `<gate>.txt` with `GateOutput.text` unchanged, through `RunFiles.write`, on a pass and on a failure.
  - Its `GateEvaluated.output_path` is the path `write` returned.
- [ ] **AC3** ("Order": "when it fails, no other gate runs"; "Per-task sequence" step 6):
  - A `path_check` violation calls no `GateRunner.run`, and its events stay as today.
  - With all three gates passing, the task goes on to `CommitRecorded` and `gating` to `passed` as today, with the three `GateEvaluated` between the `path_check` one and `CommitRecorded`.
- [ ] **AC4** ("Events of one task": "Otherwise a failed gate other than `path_check` is `gating` to `failed` with reason the name of the first failed gate in `required_gates` order"):
  - When any of the three fails with `finding` false, the task goes `gating` to `failed` with reason the first failed gate's name (for example `pytest` when `pytest` and `gitleaks` failed).
  - Nothing is committed, the worktree is not removed, and the result is `failed` with `last_event_id` the `failed` event.
- [ ] **AC5** ("Events of one task": "When `gitleaks` reported a finding, the task goes `gating` to `failed`, then `failed` to `escalated`, both with reason `secret found`, whichever other gates failed"; ADR-017):
  - When `gitleaks` gives `finding` true, the task goes `gating` to `failed`, then `failed` to `escalated`, both with reason `secret found`, also when `ruff` failed too.
  - Nothing is committed, and the result is `escalated`.
- [ ] **AC6** ("The pytest gate and `req` markers"; SC-123; decisions 2026-10-15 and 2026-10-16):
  - With `pytest` passing but a contract requirement with no marker line in a changed file (a marker in an unchanged file does not count), the `pytest` gate fails, its `GateEvaluated.passed` is false, and `pytest.txt` is the gate text followed by one line `no tagged test in a changed file: <id>` per uncovered requirement, in contract order; the task fails with reason `pytest`.
  - With `pytest` itself failing and a requirement uncovered, the lines are added too.
  - With every requirement covered, the text is written unchanged and the gate keeps `GateOutput.passed`.
- [ ] **AC7** (ADR-011; "Running a gate that starts a process"):
  - `run_plan` passes its `gates` to `run_task`.
  - `app/run.py` imports nothing from `adapters` or `cli`.
  - The suite passes with only the approved test edits listed in Scope.

## Architecture rules that apply
- `app` depends on `domain` and `ports` only; the use case has no I/O of its own (ADR-015 Consequences).
- Every event goes through `_Chain`, so each transition is checked against `TRANSITIONS` (`failed` to `escalated` is allowed).
- No event, payload, schema or dependency change.

## Plan
1. Create branch `task/TASK-068-run-deterministic-gates` from an up-to-date main.
2. Test-writer:
   - make the approved edits in `test_run_task.py`, `test_run_plan.py` and `test_m3_close.py`;
   - write failing tests for AC1 to AC6 in `test_run_task.py`;
   - AC7 rests on the existing import test and a `run_plan` test that a gate is called during the loop.
3. Implement in `run_task`, using the existing `_Chain` and the `path_check` code as the model, and pass `gates` from `run_plan`.
4. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
5. Update the living docs and the Outcome.
6. Commit `feat(app): run the ruff, pytest and gitleaks gates and the tag rule in run` with the trailers `Task: TASK-068` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/app/run.py` (about +50)
- `tests/unit/test_run_task.py` (approved edits about +25, new tests about +220)
- `tests/unit/test_run_plan.py` (approved edits, about +8)
- `tests/integration/test_m3_close.py` (approved edits, about +30)
- `docs/architecture.md`: the `run_task` paragraph and data flow (gates now run after `path_check`; `GateRunner.run` is now used; `review` not yet).
- `docs/progress.md`:
  - Current: TASK-068; Done: add the line; Outline: item 7 removed;
  - Later: the stand-in `gitleaks` line now also names the stand-in `uv`, both to be revisited at item 13; the test names that no longer match (`test_ac1_passed_run_records_seven_events_in_order`).
- `docs/tasks/TASK-068-run-deterministic-gates.md` (this record).

- `docs/decisions.md`: one row for how the tag-rule lines are appended to the text.

Not expected to change: `domain/`, `ports/`, `adapters/`, `cli.py`, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 340 lines with tests, about 50 of them in `src/`.

## Decisions at planning (human, following the advisor)
1. The non-mechanical test edits listed in Scope are approved. progress.md "Later" names the stand-in `uv` next to the stand-in `gitleaks`.
2. Item 7 is not split: the tag rule is in this task.
3. Until item 8, a task whose three gates pass is committed without `review`; the gap stays in Out and in progress.md until item 8.
4. The three gates run in the fixed order ruff, pytest, gitleaks, not filtered by `required_gates`; the reason uses `required_gates` order.

## Outcome
- `src/openfactory/app/run.py`: `run_task` takes a required `gates: GateRunner`; after a passing `path_check` it runs `ruff`, `pytest`, `gitleaks` in that order (all three always), writes each `<gate>.txt` and records each `GateEvaluated` with the returned path; `_apply_tag_rule` applies the tag rule to `pytest`; `finding` gives `failed` then `escalated` with `secret found`, else the first failed gate in `required_gates` order gives `failed`, else the commit as before. `run_plan` passes `gates` through. No change to `domain/`, `ports/`, `adapters/`, `cli.py`, events or schema.
- Tests: new `test_task068_` tests in `tests/unit/test_run_task.py` (AC1 to AC6).
- Approved test edits (made by the test-writer, as listed in Scope): `test_run_task.py` harness `FakeGates`, `PASSED_SHAPE`, `test_ac1_passed_run_records_seven_events_in_order`, `test_ac1_payloads_and_result`, `test_t053_ac3_gating_git_failure_fails_the_task`; `test_run_plan.py` `FakeGates.run` and `run_calls` asserts in the `test_task067_` tests; `test_m3_close.py` stand-in `uv`, `task_group(passed=True)`, 28 events, causation index 21, six `gate_results` rows. The implementer needed no mechanical test fixes.
- Decisions recorded in `docs/decisions.md` (2026-10-20): how the tag-rule lines are appended; fixed gate order with the reason in `required_gates` order; commit without `review` until item 8.
- Left: the stale test name `test_ac1_passed_run_records_seven_events_in_order` and the stand-in `uv` and `gitleaks`, in progress.md "Later".
