# TASK-067: `run` refuses with `<tool> not found`

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-016 (accepted). Its Decision says: "`GateRunner` gains `missing_tool() -> str | None` ... `run_plan` calls it after the `git failed` check and turns a name into the `<tool> not found` refusal, before any event." ADR-015 ("`run` refuses before any event with `<tool> not found`") and ADR-011 (`cli.py` wires adapters, prints and sets exit codes) also apply. The task adds no new port, adapter, dependency, event type, payload, schema or convention.
- Spec impact: none
- Spec sections (spec v1.16; SC-115):
  - "Execution" › "`run`": "It refuses with one line on standard error and exits 1, before any event. The refusals, checked in this order: `no approved plan`; `repository has no commit`, ...; `git failed: <error>`, ...; `<tool> not found`, when `uv` or `gitleaks` is not on `PATH`, with `<tool>` the first of the two that is missing, as `GateRunner.missing_tool()` gives it."
  - "Execution" › "`run`": "It then repairs the plan (see Restart)." and "`--task ID` ... After the repair it refuses with `unknown task <ID>` ... these two refusals come after the repair".
  - "Gates and remediation" › "Running a gate that starts a process": "`GateRunner` also gives `missing_tool() -> str | None`, the first of `uv` and `gitleaks` that is not on `PATH`, for the refusal of `run`."
  - "CLI commands" › "Output": "Failure messages (... the refusals of ... `run` ...) ... go to standard error." and "A command that fails exits 1".

## Outline item
M4 outline item 7, first half. The second half wires `ruff`, `pytest` and `gitleaks` after `path_check` in `run_task`: the gate files, the reasons, `secret found` and the tag rule lines (SC-84, SC-88, SC-123). That second half stays as item 7 in the outline.

## Objective
Make `run_plan` ask `GateRunner.missing_tool()` after the `git failed` check, and refuse before any event when `uv` or `gitleaks` is missing. Make `cli.py` wire `ProcessGates` and print `<tool> not found`.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/app/run.py`:
  - `RunRefusal` gains `tool_not_found`.
  - `run_plan` gains a required keyword `gates: GateRunner`. After the `head is None` check and before `repair_plan`, it calls `gates.missing_tool()`. A name gives `RunReport(refusal=RunRefusal.tool_not_found, detail=<name>)`.
  - `run_task` is not changed.
- `src/openfactory/cli.py`:
  - `run` passes `gates=ProcessGates(repo)`.
  - `_run_refusal_line` maps `tool_not_found` to `f"{detail} not found"`.
- Tests:
  - New tests in `tests/unit/test_run_plan.py` with the prefix `test_task067_`, using a `FakeGates` whose `missing_tool` returns a set value and counts its calls, and whose `run` raises `AssertionError`.
  - New tests in `tests/integration/test_cli_run.py`.
- Test edits that need approval, all mechanical:
  - `tests/unit/test_run_plan.py`: the three `run_plan(...)` calls (the `Run` harness, `test_ac2_repair_warnings_are_returned` and the helper near line 490) gain `gates=FakeGates(None)`; the `Run` harness also gains an optional `missing` keyword (default `None`, the old behaviour) that sets what its `FakeGates` reports. No assertion changes.
  - `tests/integration/test_m3_close.py`: the autouse `claude` fixture also writes a stand-in `gitleaks` (exits 0) into `claude-bin`. `run` would otherwise refuse wherever `gitleaks` is not installed, CI included. No assertion changes. This task never invokes the stand-in, because no gate runs yet.

Out:
- Running any gate in `run_task`, gate files, failure reasons, `secret found` and the tag rule (item 7, second half).
- The review gate, the cost limit, retry, `resolve` and `status` (items 8 to 12).
- Any change to `domain/`, `ports/`, `adapters/`, events or the schema.

## Acceptance criteria
- [ ] **AC1** ("`run`": "`<tool> not found`, when `uv` or `gitleaks` is not on `PATH`, with `<tool>` the first of the two that is missing, as `GateRunner.missing_tool()` gives it"; "before any event"):
  - When `missing_tool()` returns `"uv"` or `"gitleaks"`, `run_plan` returns `refusal` `tool_not_found` with `detail` that name, and `warnings` and `tasks` empty.
  - No event is recorded, no `WorkspaceManager` or `AgentExecutor` call is made, and `GateRunner.run` is not called.
- [ ] **AC2** ("`run`": "The refusals, checked in this order"; "It then repairs the plan"):
  - With no approved plan, with `HEAD` at no commit, and with a failing `head_commit`, the earlier refusal is returned and `missing_tool()` is not called. This holds even when the fake would report a missing tool.
  - With `missing_tool()` returning `None`, `run_plan` goes on to the repair and the loop as before. The existing tests in `test_run_plan.py` pass with only the `gates=` edit.
- [ ] **AC3** ("`run`": "`--task ID` ... After the repair it refuses with `unknown task <ID>` ..."):
  - With `task_id` set and a tool missing, the result is `tool_not_found`, not `unknown_task` or `not_ready`.
  - The repair records no event, even when the plan holds a `running` task the repair would fail.
- [ ] **AC4** ("CLI commands" › "Output": refusals to standard error, exit 1):
  - `openfactory run`, with `run_plan` returning `tool_not_found` and `detail` `gitleaks`, writes exactly `gitleaks not found` to standard error, nothing to standard output, and exits 1.
  - With the real wiring, an approved plan, a repo with a commit and a `PATH` that has `git` but neither `uv` nor `gitleaks`, it writes `uv not found` and records no event. A `PATH` with `uv` but no `gitleaks` gives `gitleaks not found`.
- [ ] **AC5** (ADR-011; "Gates and remediation" › "Running a gate that starts a process"):
  - `run` passes a `ProcessGates` as `gates` (the stubbed `run_plan` receives it).
  - `cli.py` stays the only module that imports both `adapters` and `app`.
  - `app/run.py` imports `GateRunner` from `ports` and nothing from `adapters`.

## Architecture rules that apply
- `app` depends on `domain` and `ports` only; `cli.py` is the composition root (ADR-011).
- The refusal is data on `RunReport`; `cli.py` turns it into the line.
- No event, payload, schema or dependency change.

## Plan
1. Create branch `task/TASK-067-run-missing-tool-refusal` from an up-to-date main.
2. Test-writer: make the approved `gates=` edits in `test_run_plan.py` and the stand-in `gitleaks` in `test_m3_close.py`. Then write failing tests for AC1 to AC3 in `test_run_plan.py` and for AC4 and AC5 in `test_cli_run.py`. For the real-wiring AC4 test, build a `PATH` from a directory holding links to `git` (and to `uv` for the second case), so `shutil.which` finds only those.
3. Add `RunRefusal.tool_not_found`, the `gates` parameter and the check to `run_plan`. Wire `ProcessGates` and add the refusal line in `cli.py`.
4. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
5. Update the living docs and the Outcome.
6. Commit `feat(app): refuse run when uv or gitleaks is missing` with the trailers `Task: TASK-067` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/app/run.py` (about +10)
- `src/openfactory/cli.py` (about +5)
- `tests/unit/test_run_plan.py` (3 approved one-line edits, `FakeGates`, about +70)
- `tests/integration/test_cli_run.py` (about +70)
- `tests/integration/test_m3_close.py` (approved edit, about +4)
- `docs/architecture.md`: the `run_plan` signature and refusal list; "GateRunner port" and the data-flow paragraph (`run_plan` now calls `missing_tool()`; `run` is still unused).
- `docs/progress.md`: Current: TASK-067; Done: add the line; Outline: item 7 loses the refusal; Later: the stand-in `gitleaks` in `test_m3_close.py`, to be revisited by item 13.
- `docs/tasks/TASK-067-run-missing-tool-refusal.md` (this record).

Not expected to change: `domain/`, `ports/`, `adapters/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, `docs/decisions.md`.

Expected size: about 160 lines with tests, about 15 of them in `src/`.

## Decisions (human, 2026-10-20, following the advisor)
1. Item 7 is split: this task covers the refusal only; the gates in `run_task` come next.
2. `test_m3_close.py` gets a stand-in `gitleaks` (exits 0) in `claude-bin`. `uv` gets no stand-in, because it is on the inherited `PATH`.
3. The enum member is `RunRefusal.tool_not_found`, named after its refusal line like the other members.

## Outcome

- `run_plan` takes `gates: GateRunner` and, after the `git failed` check and before any event, returns `RunRefusal.tool_not_found` with `detail` the name `missing_tool()` gives. `cli.py` wires `ProcessGates(repo)` and prints `<tool> not found`. No port, adapter, event or dependency changed; `GateRunner.run` is still unused.
- No test-writer test was edited during implementation. The approved mechanical edits (3 one-line edits in `tests/unit/test_run_plan.py`, the stand-in `gitleaks` in `tests/integration/test_m3_close.py`) were made by the test-writer.
- Follow-up: the stand-in `gitleaks` always exits 0; recorded under Later in progress.md.
