# TASK-079: `TestsCollected` event and the plugin's `node_id`

- Milestone: M5
- Status: done
- Tests: acceptance
- ADR: ADR-018 (accepted). It defines the new event `TestsCollected` `{run_id, task_id, tests: [{node_id, file, req}]}`: stream `task:<task id>`, actor `orchestrator`, recorded "after the git commit is made, just before `CommitRecorded`". It also gives the plugin line `{"node_id", "file", "req"}`, and its Consequences say "The plugin, `MarkerLine` and every `GateRunner` fake gain `node_id`". `EventType.TestsCollected` already exists (SC-157, commit 5a804e4). No new port, adapter, dependency or schema.
- Spec impact: none
- Spec sections (spec v1.17; SC-128):
  - "Domain model and storage" › "Event payloads": the `TestsCollected` block, with `tests: [ { node_id, file, req } ]  # every test the pytest gate collected, untagged ones with req [], sorted by node_id`; and "Each event type has one payload model in the domain, and the models forbid unknown fields. Every field of a payload model is required".
  - "Domain model and storage" › "Streams and actors": "`GateEvaluated`, `TestsCollected`, `CommitRecorded` | `task:<task id>` | `orchestrator`".
  - "Execution" › "Per-task sequence", step 6: "the orchestrator itself commits with trailers (see Traceability), records `TestsCollected` and `CommitRecorded`, moves the task to `passed`".
  - "Execution" › "Events of one task": "either `TestsCollected`, `CommitRecorded` and `gating` to `passed`, or `gating` to `failed`. `TestsCollected` holds the collection of the `pytest` gate and is recorded after the git commit is made, just before `CommitRecorded`, so a commit that fails leaves no collection"; and the `causation_id` rule (the event recorded just before it for the same task).
  - "Gates and remediation" › "Running a gate that starts a process": "`marker_lines`, the parsed marker lines of `pytest` (`node_id`, `file`, `req`)".
  - "Gates and remediation" › "The pytest gate and `req` markers": "writes one JSON line per collected test, `{"node_id": "<pytest node id>", "file": "<path>", "req": ["<id>", ...]}`"; "imports only `pytest`, `json` and `os`".

## Outline item
This is M5 outline item 1, the whole item. Item 2 (the `trace_links` table and its projector rules, `TestsCollected` included) comes next. Until then the projector checks a `TestsCollected` payload against its model and writes nothing for it.

## Objective
The `openfactory_req` plugin and `MarkerLine` carry the pytest node id. After the git commit of a passing attempt, `run` records `TestsCollected`, which holds that attempt's whole `pytest` collection sorted by `node_id`, just before `CommitRecorded`.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `adapters/pytest_plugin/openfactory_req.py`:
  - The line becomes `{"node_id": item.nodeid, "file": ..., "req": ...}`.
  - Imports are unchanged (`pytest`, `json`, `os`).
- `domain/gates.py`:
  - `MarkerLine` gains `node_id: str`, required, first field.
  - It stays frozen with `extra="forbid"`.
- `domain/payloads.py`:
  - New frozen `CollectedTest` (`node_id`, `file`, `req: list[str]`, `extra="forbid"`). See Design choice 1.
  - New frozen `TestsCollectedPayload` (`run_id: RunId`, `task_id: TaskId`, `tests: list[CollectedTest]`, every field required, `extra="forbid"`). The model checks no order; sorting is the use case's job, as for `CommitRecordedPayload.files`.
  - Registered in `PAYLOAD_MODELS`, giving twelve entries. Only `ImpactComputed` has none.
- `app/run.py`, `run_task`:
  - Keep the `pytest` gate's `GateOutput.marker_lines` of the attempt.
  - After `git.commit` returns the sha, record `TestsCollected` through the task's `_Chain`, then `CommitRecorded` as now.
  - `tests` is built from those lines, sorted by `node_id`.
  - A `GitError` from `commit` keeps today's `failed` path and records no `TestsCollected`.
- Tests: new tests for AC1 to AC6, and the approved edits to existing tests (Open question 1).

Out:
- The `trace_links` table, its projector rules and `M5_TABLES` (item 2).
- Any change to the tag rule, `process_gates` command lines, Restart, `CommitRecorded` or the commit itself.
- Any check of duplicate `node_id`s, or of the link between `file` and `node_id`.

## Acceptance criteria
- [x] **AC1** ("The pytest gate and `req` markers": "writes one JSON line per collected test, `{"node_id": "<pytest node id>", "file": "<path>", "req": [...]}`"; "imports only `pytest`, `json` and `os`"):
  - `ProcessGates.run("pytest", ...)` runs the real plugin on a sample worktree with tagged and untagged tests, one of them in a subdirectory.
  - Each returned `MarkerLine` has `node_id` equal to pytest's node id (for example `tests/sub/test_b.py::test_x`), with `file` and `req` as before.
  - The plugin module still imports only `pytest`, `json` and `os`.
- [x] **AC2** ("Running a gate that starts a process": "`marker_lines`, the parsed marker lines of `pytest` (`node_id`, `file`, `req`)"; "a line that does not validate fails the gate with no lines and the text line `invalid marker line: <line>`"):
  - `MarkerLine` has the required fields `node_id`, `file` and `req`.
  - It is frozen and rejects unknown keys.
  - It round-trips the spec's JSON line.
  - A plugin line without `node_id` fails the `pytest` gate with `marker_lines` `[]` and the `invalid marker line: <line>` text.
- [x] **AC3** ("Event payloads": the `TestsCollected` block; "Each event type has one payload model ... forbid unknown fields. Every field ... is required"):
  - `TestsCollectedPayload` has exactly `run_id`, `task_id` and `tests`, each item exactly `node_id`, `file` and `req`. It is frozen and rejects a missing or unknown field.
  - `PAYLOAD_MODELS[EventType.TestsCollected]` is that model.
  - The spec-conformance payload-field test runs for `TestsCollected` and no longer skips it.
  - Recording a `TestsCollected` through `SqliteEventRecorder` validates it and changes no projection row. A payload the model rejects raises.
- [x] **AC4** ("Per-task sequence" step 6; "Events of one task": "`TestsCollected` ... is recorded after the git commit is made, just before `CommitRecorded`"; "Streams and actors"; the `causation_id` rule):
  - A passing `run_task` records, after the `review` `GateEvaluated`: `TestsCollected`, `CommitRecorded`, then `gating` to `passed`.
  - `TestsCollected` has stream `task:<task id>`, actor `orchestrator`, `causation_id` the `review` `GateEvaluated` event, `run_id` the implementer run and `task_id` the task.
  - `CommitRecorded`'s `causation_id` is the `TestsCollected` event.
  - `git.commit` was called before `TestsCollected` was recorded.
- [x] **AC5** ("Event payloads": "every test the pytest gate collected, untagged ones with req [], sorted by node_id"):
  - Given `pytest` marker lines in unsorted order, including an untagged test (`req` `[]`), a test with two `req` ids and a test in a file the task did not change, `TestsCollected.tests` holds every one of them, sorted by `node_id`.
  - Each item's `file` and `req` are as the gate gave them (`req` order and duplicates kept).
- [x] **AC6** ("Events of one task": "so a commit that fails leaves no collection"; "either `TestsCollected`, `CommitRecorded` and `gating` to `passed`, or `gating` to `failed`"):
  - A `GitError` from `git.commit` moves the task to `failed` with reason `git: <first line>` and records no `TestsCollected`.
  - An attempt failed by a gate (`pytest` or `review`) records no `TestsCollected`.
  - The full suite passes, with only the edits approved under Open question 1. `test_m4_close.py`'s rebuild check stays identical.

## Architecture rules that apply
- `domain/gates.py` and `domain/payloads.py` stay pure. If Design choice 1 is answered "reuse", `payloads.py` imports `MarkerLine` from `domain/gates.py` (domain to domain).
- `app/run.py` records through the `EventRecorder` and the existing `_Chain`. No new port.
- The plugin imports nothing from `openfactory`.

## Plan
1. Create branch `task/TASK-079-tests-collected` from an up-to-date main.
2. Get the human's answers to the Open questions and record them here.
3. Test-writer: write failing tests.
   - AC1: `tests/integration/test_process_gates_pytest.py`.
   - AC2: `tests/unit/test_gate_runner_port.py`.
   - AC3: new `tests/unit/test_m5_payloads.py`, plus the projector check in a new `tests/integration/test_sqlite_projector_m5.py` or the existing M3 projector file.
   - AC4 to AC6: `tests/unit/test_run_task.py`.
   - Make the approved edits to existing tests.
4. Implement the plugin line, `MarkerLine.node_id`, `CollectedTest` and `TestsCollectedPayload` with the `PAYLOAD_MODELS` entry, then the `run_task` change.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`: `PAYLOAD_MODELS` line (twelve entries), the payload model bullets, the `MarkerLine` bullet, the `openfactory_req` plugin section, and the run use case's event list.
   - `docs/progress.md`: Current, a Done line, item 1 removed from the M5 outline, and the Later line "M5: the `TestsCollected` payload model ..." reworded to what is left (the table and `M5_TABLES`).
   - `docs/decisions.md`: a row for Design choice 1.
   - Fill in the Outcome, listing every test edit.
7. Commit `feat(app): record TestsCollected before CommitRecorded` with the trailers `Task: TASK-079` and `Milestone: M5`. Do not push.

## Files expected to change
- `src/openfactory/adapters/pytest_plugin/openfactory_req.py` (about +1)
- `src/openfactory/domain/gates.py` (about +3)
- `src/openfactory/domain/payloads.py` (about +20)
- `src/openfactory/app/run.py` (about +20)
- `tests/unit/test_m5_payloads.py` (new, about +80)
- `tests/unit/test_run_task.py` (new AC4 to AC6 tests, about +80; approved edits)
- `tests/unit/test_gate_runner_port.py`, `tests/integration/test_process_gates_pytest.py` (new tests and approved edits)
- `tests/integration/test_sqlite_projector_m5.py` (new, about +30) or an addition to the M3 projector test file
- Approved edits only: `tests/unit/test_tag_rule.py`, `tests/unit/test_run_plan.py`, `tests/unit/test_m4_payloads.py`, `tests/integration/test_m3_close.py`
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-079-tests-collected.md` (this record)

Not expected to change: `ports/`, `adapters/process_gates.py`, `adapters/sqlite_projector.py` (its existing "model, no rule" path applies), `domain/tag_rule.py`, `cli.py`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, `tests/integration/test_m4_close.py`.

Expected size: about 300 lines, about 45 of them in `src/`.

## Design choices to confirm at planning
1. **The payload's item model.**
   - Proposed: a separate frozen `CollectedTest` in `domain/payloads.py`. A stored payload's shape is then independent of the adapter's parse model, following the `RecordedViolation` / `Violation` precedent (TASK-005).
   - Alternative: reuse `MarkerLine` as the item type. It's one less model, but a later change to `MarkerLine` would change a stored payload.
2. **Sort key.** `sorted(..., key=lambda t: t.node_id)`, Python string order, as "sorted as strings" elsewhere in the spec. The use case sorts; the model does not check the order.
3. **Source of the collection.** The `GateOutput.marker_lines` of the same attempt's `pytest` gate, unchanged by the tag rule. It is not re-collected after the commit.

## Open questions
1. **Approval of edits to existing (fixed) tests.** ADR-018 Consequences anticipates the `node_id` edits. The others insert one `TestsCollected` event into fixed expected sequences. All are needed to keep the suite green:
   - `tests/unit/test_gate_runner_port.py`: `LINE_JSON`, `MarkerLine(...)` constructions and the `accepts_empty_req` JSON gain `node_id`.
   - `tests/unit/test_tag_rule.py`: the `marker()` helper gains a `node_id`.
   - `tests/unit/test_run_task.py`:
     - the `_gate_output` and inline `MarkerLine(...)` sites gain `node_id`;
     - the shape lists (`test_ac1_passed_run_records_the_events_in_order`, `PASSED_SHAPE`) and the stream list gain `("TestsCollected", None, None)` / `task:AUTH-002` before `CommitRecorded`;
     - `r.events[11]` and `r.events[13]` become `[12]` and `[14]`.
   - `tests/unit/test_run_plan.py`: the fake gate's `MarkerLine` gains `node_id`.
   - `tests/integration/test_process_gates_pytest.py`: the expected `MarkerLine` at line 238 gains its `node_id`.
   - `tests/integration/test_m3_close.py`:
     - the stand-in `uv`'s `UV_BODY` marker gains `node_id`. Without it the line no longer validates and the `pytest` gate fails;
     - the expected sequence gains `(stream, "TestsCollected")` before `CommitRecorded`;
     - `len(events) == 34` rises by one per passed task.
   - `tests/unit/test_m4_payloads.py`: `test_ac2_payload_models_has_exactly_the_eleven_keys` now expects `TestsCollected` among the keys (twelve). Its name will no longer match, which gets a Later line.
   - Proposed: approve all as listed.
   - Alternative: split the task so the reviewer sees fewer edits at once:
     - TASK-079 is the plugin and `MarkerLine` `node_id` (AC1, AC2; the `node_id` edits only);
     - TASK-080 is the payload and the `run` recording (AC3 to AC6; the sequence edits).

### Answers (2026-10-22, the human: "do as the advisor says")
1. Approved, one task, with the advisor's corrections added to the list:
   - `tests/unit/test_run_task.py:442`: index `11` becomes `12` in `(1, 2, 4, 11)`.
   - `tests/integration/test_m3_close.py:475`: `(0, 27)` becomes `(0, 29)`; `len(events) == 34` becomes `36`.
   - `tests/unit/test_gate_runner_port.py:103`: the `no-req`, `no-file` and `unknown-key` inputs gain `node_id`, so each still fails for its own reason.
   - `tests/integration/test_process_gates_pytest.py:295`: the `bad` line (`"req": [123]`) gains `node_id`, for the same reason.
2. Design choice 1: a separate frozen `CollectedTest` (ADR-007).
3. Design choice 2: Python string order of `node_id`, sorted by the use case; the model checks no order.
4. Design choice 3: the passing attempt's `pytest` `marker_lines`; no second collection.

## Spec gaps
None. Readings, not gaps:
- "sorted by node_id" is read as string order (Design choice 2).
- Between this task and item 2, a recorded `TestsCollected` is checked against its model and writes nothing. This is the same interim state as `GateEvaluated` and `CommitRecorded` in TASK-040 and `TaskResolved` in TASK-058.
- Restart step 1 passes a `gating` task that has a `CommitRecorded` and records no `TestsCollected`. The collection was already recorded before `CommitRecorded`, so nothing is lost. The "crash between the two" case is the spec's stated consequence and needs no handling here.

## Outcome
Built:
- `openfactory_req.py` writes `{"node_id": item.nodeid, "file", "req"}`; imports unchanged.
- `MarkerLine` gains `node_id` as its first field.
- `domain/payloads.py` gains frozen `CollectedTest` and `TestsCollectedPayload`, registered in `PAYLOAD_MODELS` (twelve entries; only `ImpactComputed` has none).
- `run_task` keeps the `pytest` gate's `marker_lines` of the attempt and, after `git.commit` returns, records `TestsCollected` (sorted by `node_id`) through the `_Chain`, then `CommitRecorded`. A `GitError` or a failed gate records none.
- The projector is unchanged: it validates the payload and writes nothing.
- New tests: `tests/unit/test_m5_payloads.py`, `tests/integration/test_sqlite_projector_m5.py`, and new cases in `test_process_gates_pytest.py`, `test_gate_runner_port.py` and `test_run_task.py`.
- Design choices 1 to 3 are in `docs/decisions.md` (2026-10-22, TASK-079).

Test edits to existing tests: the list approved under Open question 1 Answers (the `node_id` additions in `test_gate_runner_port.py`, `test_tag_rule.py`, `test_run_task.py`, `test_run_plan.py`, `test_process_gates_pytest.py` and `test_m3_close.py`; the `TestsCollected` event inserted into the expected sequences of `test_run_task.py` and `test_m3_close.py` with their index and count changes; `test_m4_payloads.py` now expecting twelve keys), plus one mechanical fix not in that list: in `tests/integration/test_sqlite_projector_m5.py`, `all_rows` now leaves out the bookkeeping tables `projection_state` and `sqlite_sequence`, which every recorded event changes. The assertion's intent, that no projection row changed, is unchanged.

Later: `test_ac2_payload_models_has_exactly_the_eleven_keys` now checks twelve keys, so its name no longer matches (in `progress.md` Later).
