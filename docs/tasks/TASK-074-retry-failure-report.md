# TASK-074: Run use case, the failure report in a retry's context pack

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-015 (accepted). Its "Ports and adapters" section says "`RunFiles` gains a read of a run file by the path `write` returned, for the failure report" and "The failure report reads the task's last `failed` reason and its gate results from the task's stream through the existing `EventStore` port". `RunFiles.read` exists (TASK-063) and `EventStore` is already passed to `run_plan` (TASK-073). This task adds no port, adapter, dependency, event type, payload, schema or convention. It only passes `events: EventStore` on to `run_task`. The answers to Q1 and Q2 become rows in `docs/decisions.md`.
- Spec impact: wording
- Spec sections (spec v1.16; SC-89, SC-108):
  - "Execution" › "The context pack": "the failure report of the previous attempt if this is a retry (see Remediation)." and "It holds no contents of the repo's files; the agent reads them with its tools. A retry's failure report holds the text of the gates' output files, which may quote lines of code. `context_hash` is the SHA-256 of the text encoded as UTF-8, as for a planner run."
  - "Gates and remediation" › "Remediation": "The failure report of the previous attempt is the `reason` of the task's last `failed` event and, for each gate that failed in that attempt, its name and the text of its output file. The use case reads the reason and the gate results from the task's stream through the `EventStore` port, and the file text through `RunFiles`. The report may name code the new worktree no longer holds."
  - "Gates and remediation" › "Order": "... each recording its `GateEvaluated`, so the failure report holds every failure."
  - "Execution" › "Per-task sequence", steps 1 and 2: "Record `ready` to `running`. ..." then "Build the context pack and hash it; the hash is the run's `context_hash`."

## Outline item
M4 outline item 10, last slice (10c). When it is done, item 10 is done.

## Objective
When the task's stream holds a `failed` event, `run_task` builds a failure report and passes it to `build_context_pack`, which adds it as the last part of the pack. The report is the reason of that last `failed` event plus each failed gate of that attempt with the text of its output file, read through `EventStore` and `RunFiles`.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/app/context_pack.py`:
  - New frozen `FailedGate` (`gate: str`, `text: str`) and `FailureReport` (`reason: str`, `gates: list[FailedGate]`), both `extra="forbid"`.
  - `build_context_pack(contract, spec, tracked_files, failure: FailureReport | None = None)`. With `None` the text is byte for byte what it is today. Otherwise one more section follows the tracked-files section, in the form fixed by the answer to Q1.
  - The module still imports only `domain`, Pydantic and the standard library.
- `src/openfactory/app/run.py`:
  - `run_task` gains a required keyword `events: EventStore`.
  - After `ready` to `running`, and before the pack is built, the private `_failure_report(task_id, events, run_files) -> FailureReport | None` does the following:
    - reads `events.read(f"task:{task_id}")`;
    - returns `None` when no `TaskStateChanged` has `to` `failed` (under the answer to Q2);
    - otherwise takes `reason` from the last such event;
    - takes the `GateEvaluated` events with `passed` false that lie between the last `to running` before that `failed` event and that event, in stream order;
    - reads each gate's text with `run_files.read(Path(output_path))`.
  - `run_plan.take` passes its `events` to `run_task`.
  - `_last_move_index` is reused where it fits. Payloads are validated with the existing payload models, as in `_interrupted_reason`.
  - The module docstring mentions the report.
- Tests:
  - New tests with the prefix `test_task074_` in `tests/unit/test_context_pack.py`, `tests/unit/test_run_task.py` and `tests/unit/test_run_plan.py`.
  - A fake `EventStore` in `tests/unit/test_run_task.py`: seeded events plus the recorder's, `append` raising `AssertionError`, like TASK-073's `FakeEvents`.
  - A `FakeRunFiles.read` that returns set texts by path and logs its calls.
- Mechanical test edits that need approval:
  - `tests/unit/test_run_task.py`: the `Run` helper passes `events=` a fake `EventStore` over its recorder. `FakeRunFiles` gains `read`.
  - `tests/unit/test_run_plan.py`: `FakeRunFiles` gains `read` (returns `""` unless set). This is needed only if an existing test retries a task whose previous attempt has a failed gate.
  - No assertion changes are expected. Existing first attempts have no `failed` event, and the existing retries in `test_run_plan.py` fail on `run error` with no gate and do not inspect the pack. If an existing assertion fails, stop and report; do not edit it.
  - `tests/integration/test_m3_close.py`: no edit expected (its restarted task passes in Restart step 1, so there is no retry). If it fails, stop and report.

Out:
- `resolve` (item 11), `status` (item 12), the M4 close test (item 13).
- Any change to the implementer instructions (`_INSTRUCTIONS`), which the spec's bullet and a conformance test fix. Nothing is added there about the report.
- Catching an `OSError` from `RunFiles.read` (a deleted run file). The spec names no handling. It propagates, and a Later line records it.
- Changes to ports, adapters, domain, events, payloads, schema, projector and `cli.py` (`run` already opens `SqliteEventStore`, TASK-073).

## Acceptance criteria
- [x] **AC1** ("The context pack": "the failure report of the previous attempt if this is a retry"):
  - On a task whose stream holds no `failed` event, `run_task` passes no report.
  - The pack and its `context_hash` are the same as before this task, so every existing `test_run_task.py` and `test_context_pack.py` assertion holds unchanged.
- [x] **AC2** ("Remediation": "the `reason` of the task's last `failed` event"):
  - On a retry the pack's last section holds the reason of the task's last `TaskStateChanged` whose `to` is `failed`.
  - With several `failed` events in the stream, only the last one's reason appears.
  - A previous attempt with no gate (`run error`, `run timeout`, `no changes`, `interrupted`, `git: ...`) gives a report with the reason alone.
- [x] **AC3** ("Remediation": "for each gate that failed in that attempt, its name and the text of its output file"; "Order": "so the failure report holds every failure"):
  - Each `GateEvaluated` with `passed` false that was recorded between the previous attempt's `ready` to `running` and its `failed` event appears with its gate name and the text `RunFiles.read` returns for its `output_path`.
  - Gates appear in the order they were recorded (for example `ruff` then `pytest`, or `review`).
  - Gates that passed and failed gates of earlier attempts are left out.
- [x] **AC4** ("Remediation": "reads the reason and the gate results from the task's stream through the `EventStore` port, and the file text through `RunFiles`"; "The context pack": `context_hash`):
  - `run_task` reads `events.read("task:<id>")` after recording `ready` to `running` and before `AgentRunStarted`, and never calls `EventStore.append`.
  - `RunFiles.read` is called once per failed gate of the previous attempt.
  - The `AgentRunStarted.context_hash` is `context_hash` of the pack the executor received, report included.
- [x] **AC5** ("`run`": "A task that a failure moved back to `ready` ... is taken again in the same invocation"):
  - Through `run_plan`, a task whose first attempt fails and is moved back to `ready` gets, on its second attempt in the same invocation, a pack whose report holds the first attempt's reason (and failed gates, if any).
  - Its first pack has no report.
  - `run_plan` passes its own `events` to `run_task`.
- [x] **AC6** (ADR-011, ADR-006 layering):
  - `app/context_pack.py` imports nothing from `ports`, `adapters`, `app` or `cli`.
  - `app/run.py` imports nothing from `adapters` or `cli`.
  - The suite passes with only the approved test edits listed in Scope.

## Architecture rules that apply
- `app` depends on `domain` and `ports` only. `build_context_pack` stays pure. The I/O (stream read, file read) is in `run_task` through ports.
- `EventStore` is only read here (ADR-001, ADR-010). The stream read is the ADR-015 exception to ADR-012.
- All LLM output is unaffected. The report is input to the implementer, not model output.

## Plan
1. Create branch `task/TASK-074-retry-failure-report` from an up-to-date main.
2. Test-writer:
   - make the approved mechanical edits;
   - write failing `test_task074_` tests:
     - the rendering for AC1 to AC3 in `test_context_pack.py`, in the form fixed by Q1;
     - AC1 to AC4 in `test_run_task.py`, seeding streams that hold an earlier attempt's failed and passed gates, two `failed` events, and a gate-less failure;
     - AC5 in `test_run_plan.py`, with an executor that keeps the context it receives and fails the first attempt.
3. Add `FailedGate`, `FailureReport` and the `failure` parameter to `build_context_pack`.
4. Add `_failure_report` and the `events` keyword to `run_task`, and pass `events` from `run_plan.take`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the living docs, add the `decisions.md` rows for Q1 and Q2, and fill in the Outcome.
7. Commit `feat(app): add the failure report to a retry's context pack` with the trailers `Task: TASK-074` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/app/context_pack.py` (about +30)
- `src/openfactory/app/run.py` (about +35)
- `tests/unit/test_context_pack.py` (new tests about +60)
- `tests/unit/test_run_task.py` (mechanical edits about +20, new tests about +100)
- `tests/unit/test_run_plan.py` (mechanical edit about +3, new test about +35)
- `docs/architecture.md`:
  - the `context_pack.py` paragraph: `FailureReport` and the new parameter;
  - the `run_task` signature, with `events`;
  - the `RunFiles` line: `read` is now called by `run_task`;
  - the `EventStore` callers line.
- `docs/decisions.md`: two rows, the answers to Q1 and Q2.
- `docs/progress.md`:
  - Current is TASK-074, with a Done line;
  - item 10 is done and removed from the outline;
  - the TASK-072 Later line "A retry's context pack is the same as the first attempt's" is removed;
  - add a Later line for an `OSError` from `RunFiles.read`.
- `docs/tasks/TASK-074-retry-failure-report.md` (this record).

Not expected to change: `ports/`, `adapters/`, `domain/`, `cli.py`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, `tests/integration/test_m3_close.py`.

Expected size: about 285 lines with tests, about 65 of them in `src/`.

## Design choices to confirm at planning
1. **The previous attempt's gates are those recorded between its `ready` to `running` and its `failed` event.** The stream is read after the current attempt's `ready` to `running`, so the bound is the last `to running` *before* the last `failed`. This matches how SC-120 bounds Restart step 2 by stream position, and the same span holds the `review` gate, whose `run_id` is the implementer's.
2. **`events: EventStore` is a required keyword of `run_task`,** as `gates` and `llm` were added. The read comes after `ready` to `running`, as the per-task sequence orders step 1 before step 2.
3. **A failed gate always has an `output_path`** (path_check writes on failure; the others always write). A null one is a programming error and is asserted, not handled.
4. **The report's data is built in `run.py` and rendered in `context_pack.py`,** so the pack stays a pure function of its arguments and equal inputs still give one `context_hash`.

## Open questions
**Q1. "Execution" › "The context pack" / "Gates and remediation" › "Remediation".** The spec says what the report holds (the reason; each failed gate's name and its file's text) but gives no form for it in the pack: no heading, no layout, no wording for a report with no failed gate.
- Proposed answer: a section headed `## Failure report of the previous attempt`; then the line `reason: <reason>`; then, for each failed gate in recorded order, a `### <gate>` heading followed by the file's text as written; with no failed gate, the line `failed gates: (none)`, matching the pack's existing `(none)` convention.
- Does not block: only the text form is open. The answer becomes a `decisions.md` row.
- **Answer (2026-10-21):** the advisor's form. `## Failure report of the previous attempt`, then `reason: <reason>`, then for each failed gate in recorded order its file's text inside `<gate name="<gate>">\n<text>\n</gate>`, mirroring the pack's `<adr id>` delimiter; with no failed gate, the line `failed gates: (none)`.

**Q2. "Execution" › "The context pack", "if this is a retry".** The spec does not say whether the first attempt after `resolve --retry` (which sets `attempt` to 0) is "a retry", nor so whether its pack carries the report of the attempt that escalated. "Command line" › "Output" says "A task escalated on a path violation or a secret can be retried", which points to yes.
- Proposed answer: an attempt is a retry when its task's stream holds an earlier `failed` event, after `resolve` too; the previous attempt is the one that ended in the last `failed` event.
- Does not block: `resolve` (item 11) does not exist yet, so both readings behave the same today. The answer becomes a `decisions.md` row.
- **Answer (2026-10-21):** as proposed.

## Later (to add to progress.md at close)
- `RunFiles.read` raising `OSError` for a deleted run file is not caught. The spec names no handling, so `run` stops with the task in `running`. The next repair fails it as `interrupted`, and its retry's report then has no gate to read (TASK-074, planner).

## Outcome
All six acceptance criteria are met. `FailedGate`, `FailureReport` and the `failure` parameter are in `app/context_pack.py`; `run_task` has the required keyword `events` and the private `_failure_report`; `run_plan` passes its `events`. No port, adapter, domain, event, schema or `cli.py` change. The answers to Q1 and Q2 and the trailing-newline choice are rows in `docs/decisions.md`.

- Trailing newlines: a gate file's trailing newlines are dropped (`rstrip("\n")`) so each block ends `<text>\n</gate>`; the test-writer raised that real gate files end in `\n`.
- Approved mechanical test edits, all in `tests/unit/test_run_task.py`: `FakeEvents` (seeded events plus the recorder's, `append` raises `AssertionError`), `FakeRunFiles.read`, `texts` and `read_calls`, the `Run` helper's `seeded=`, `file_texts=` and `events=`, and the `EventType` import. No existing assertion changed.
- `tests/unit/test_run_plan.py`: `FakeRunFiles` was not edited.
- After review (non-blocking notes 1 and 2, applied at the human's request): added `test_task074_gate_text_trailing_newlines_are_dropped` in `tests/unit/test_context_pack.py`, which pins the `rstrip`, and named the dropped trailing line breaks in the Q1 Spec wording line in `docs/progress.md`. Note 3 (a `run_plan` retry with failed gates) was not applied; `run_task` tests cover it.
