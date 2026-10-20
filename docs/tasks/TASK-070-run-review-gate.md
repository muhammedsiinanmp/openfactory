# TASK-070: Run the `review` gate in `run`

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-015 (accepted), "How accepted ADRs are read from now on": "The reviewer is instead one `LLMProvider` call with no tools, set up as a planner call, replying `ReviewVerdict`. A failed reviewer process fails the `review` gate and `run` goes on". Also: "`GitProvider` gains the text of `git diff --cached <base>` in a worktree, for the reviewer" (built in TASK-063). The task adds no port, adapter, dependency, event type, payload, schema or convention.
- Spec impact: wording (see Spec gaps)
- Spec sections (spec v1.16; SC-105, SC-107, the rest of SC-87, SC-106, SC-119):
  - "Gates and remediation" › "Order": "`review` runs only when all three passed."
  - "Gates and remediation" › "The review gate": the whole paragraph. Key phrases: "one `LLMProvider` call, set up as a planner call"; "Its prompt is the task contract and the text of `git diff --cached <base>` in the worktree"; "recorded as an agent run: `AgentRunStarted` with `role: reviewer`, the task's id and the prompt's `context_hash`, then `AgentRunFinished`; a rejected reply is retried once"; "A failed reviewer process, or a second rejected reply, fails the gate and `run` goes on"; "The gate's output file holds the verdict and the comments; when there is no verdict, it holds the run's `error`"; "The `review` gate's `GateEvaluated.run_id` and its file's directory are those of the implementer run it judged."
  - "Execution" › "Events of one task": "When the reviewer runs, its `AgentRunStarted` and `AgentRunFinished` (a second pair when its reply is retried) come after the `gitleaks` `GateEvaluated`; they are events of the task for `causation_id`, as the implementer's are." Also: "a failed gate other than `path_check` is `gating` to `failed` with reason the name of the first failed gate in `required_gates` order", and "A git command that fails while a task is `running` or `gating` moves the task to `failed` with reason `git: <first line of the error>`".
  - "Gates and remediation", first paragraph: "A task passes only when every required gate passes".
  - "Gates and remediation", last paragraph: "The file is `.openfactory/runs/<run id>/<gate>.txt`, written through the `RunFiles` port ... the other gates write it on a pass and on a failure."

## Outline item
M4 outline item 8, slice 8b, whole. Slice 8a is TASK-069.

## Objective
Once `ruff`, `pytest` and `gitleaks` all pass, `run_task` reads the staged diff and runs the reviewer through `LLMProvider`, retrying a rejected reply once. It records the reviewer's run events and the `review` `GateEvaluated` with the implementer's `run_id`, writes `review.txt`, and commits only on `approve`. `run_plan` passes `llm` through, and `cli.py` wires `ClaudeCodeLLM`.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/app/run.py`:
  - `run_task` gains a required keyword `llm: LLMProvider`, and `run_plan` gains one too and passes it through.
  - After the three gates, when none failed, `run_task` does the following:
    - `diff = git.staged_diff(worktree, base)`. A `GitError` gives `failed` with reason `git: <first line>`, with no reviewer event and no `review` `GateEvaluated`.
    - First attempt: `Runs.next_id()`; then `AgentRunStarted` (`role` `reviewer`, `task_id` the task, `runtime` `claude-code`, `context_hash` = `context_hash(build_review_prompt(contract, diff))`) on `run:<reviewer run id>`; then `llm.complete(prompt, ReviewVerdict.model_json_schema())`; then `parse_review_reply(reply.structured)`; then `AgentRunFinished`. All of this is built as in `plan._attempt`: an `LLMError` gives `exit` `timeout`/`error`, its `duration_s`, null metrics and `error` `str(error)`; a reply gives `exit` `ok`, the reply's metrics, and `error` the sorted rejection lines joined by `\n`, or null.
    - When the first reply is rejected, one more attempt with `build_review_prompt(contract, diff, rejections=<first rejections>)`. A failed process is not retried.
    - `run_files.write(<implementer run id>, "review.txt", review_file_text(verdict, error))`, where `error` is the last reviewer run's `error`. Then `GateEvaluated` with `gate` `review`, `run_id` the implementer's, `passed` = verdict is `approve`, and `output_path` the returned path.
    - `approve`: commit as today. Anything else: `gating` to `failed` with reason `review`, by the existing "first failed gate in `required_gates` order" rule.
  - Every reviewer event goes through the task's `_Chain`, actor `orchestrator`.
- `src/openfactory/cli.py`: `run` passes `llm=ClaudeCodeLLM()`.
- Tests: new tests in `tests/unit/test_run_task.py` with the prefix `test_task070_`, using a `FakeLLM` that returns set replies or raises `LLMError` and logs prompts and schemas; one new test in `tests/integration/test_cli_run.py` (the stubbed `run_plan` gets a `ClaudeCodeLLM`).
- Test edits that need approval:
  - `tests/unit/test_run_task.py`:
    - Mechanical: the `Run` harness passes `llm=` with a `FakeLLM` that approves by default, plus an optional keyword to set replies; `FakeGit` gains `staged_diff`; `FakeRuns` keeps giving new ids for the reviewer runs.
    - Not mechanical:
      - `PASSED_SHAPE` and `test_ac1_passed_run_records_seven_events_in_order` gain the reviewer's `AgentRunStarted`, `AgentRunFinished` and the `review` `GateEvaluated` before `CommitRecorded`.
      - `test_ac1_payloads_and_result` takes the commit at its new index, and its `run_files.calls` gain `review.txt`.
      - The `commit` case of `test_t053_ac3_gating_git_failure_fails_the_task` expects the reviewer events.
  - `tests/unit/test_run_plan.py`, mechanical: the `Run` harness and the two direct `run_plan(...)` calls gain `llm=FakeLLM()` (approves); `FakeGit` gains `staged_diff`.
  - `tests/integration/test_m3_close.py`, not mechanical:
    - The stand-in `claude` answers a reviewer prompt (stdin holding `## Staged diff`) with an envelope whose `structured_output` is `{"verdict": "approve", "comments": ...}`, and logs it with role `reviewer`. The planner branch stays for other `--json-schema` calls.
    - `task_group(passed=True)` gains the three reviewer events per passed task, and the event count and causation indices change to match.
    - The `agent_runs` and `gate_results` rows gain the reviewer runs and the `review` rows.
    - Reviewer runs take run numbers, so the implementer run ids the test names (for example `run_0004` and its run files) shift.
    - Item 13 still rewrites this test.

Out:
- The cost limit after each `AgentRunFinished` (item 9). Retry, `failed` to `ready`, `attempts exhausted` and the failure report (item 10). A failed task stays `failed`.
- Any change to `domain/`, `ports/`, `adapters/`, events, payloads or the schema.

## Acceptance criteria
- [ ] **AC1** ("Order": "`review` runs only when all three passed"; "The review gate": "Its prompt is the task contract and the text of `git diff --cached <base>`", "`AgentRunStarted` with `role: reviewer`, the task's id and the prompt's `context_hash`, then `AgentRunFinished`"; "Events of one task": "come after the `gitleaks` `GateEvaluated`; they are events of the task for `causation_id`"):
  - With the three gates passing, `GitProvider.staged_diff` is called once with the worktree and `<base>`. `LLMProvider.complete` gets `build_review_prompt(contract, diff)` and `ReviewVerdict.model_json_schema()`.
  - `AgentRunStarted` (role `reviewer`, the task id, a new run id, `context_hash` of that prompt) and `AgentRunFinished` (exit `ok`, the reply's metrics, `error` null) are recorded on `run:<reviewer run id>`, after the `gitleaks` `GateEvaluated`, in the task's causation chain.
  - When any of the three gates failed, or `path_check` failed, `staged_diff` and `complete` are not called.
- [ ] **AC2** ("The review gate": "The gate's output file holds the verdict and the comments", "The `review` gate's `GateEvaluated.run_id` and its file's directory are those of the implementer run it judged"; "Per-task sequence" step 6):
  - On `approve`, `review.txt` is written through `RunFiles.write` under the implementer's run id with `review_file_text(verdict, None)`.
  - Then `GateEvaluated` (`gate` `review`, `passed` true, `run_id` the implementer's, `output_path` the returned path), then `CommitRecorded` and `gating` to `passed` as today. `CommitRecorded.run_id` stays the implementer's.
- [ ] **AC3** ("Gates and remediation": "A task passes only when every required gate passes"; "Events of one task": "a failed gate other than `path_check` is `gating` to `failed` with reason the name of the first failed gate in `required_gates` order"):
  - On `reject`, `review.txt` holds the verdict and comments, and its `GateEvaluated` has `passed` false.
  - The task goes `gating` to `failed` with reason `review`. Nothing is committed and the worktree is not removed.
- [ ] **AC4** ("The review gate": "a rejected reply is retried once, as for a planner call. A rejected reviewer reply has `exit: ok` and `error` set to its rejection lines ... sorted and joined by newlines", "a second rejected reply, fails the gate"; "when there is no verdict, it holds the run's `error`"):
  - For a first reply that `parse_review_reply` rejects, the first `AgentRunFinished` has `exit` `ok` and `error` the sorted rejection lines joined by `\n`.
  - A second run follows: a new run id, the prompt `build_review_prompt(contract, diff, rejections=<the first's>)` and its own `context_hash`.
  - An accepted second reply then acts as AC2 or AC3.
  - A rejected second reply fails the gate: `review.txt` is the second run's `error`, and the reason is `review`.
- [ ] **AC5** ("The review gate": "A failed reviewer process ... fails the gate and `run` goes on"; "Events of one task": "A git command that fails while a task is ... `gating` moves the task to `failed` with reason `git: <first line of the error>`"):
  - An `LLMError` gives `AgentRunFinished` with `exit` `timeout` or `error` (from `LLMError.timeout`), its `duration_s`, null metrics and `error` `str(error)`.
  - There is no second run. `review.txt` holds that error, `GateEvaluated` has `passed` false, and the reason is `review`.
  - A `GitError` from `staged_diff` gives `failed` with reason `git: <first line>`, with no reviewer run event and no `review` `GateEvaluated`.
- [ ] **AC6** (ADR-011; ADR-015; "The review gate": "one `LLMProvider` call, set up as a planner call"):
  - `run_plan` passes its `llm` to `run_task`.
  - `openfactory run` passes a `ClaudeCodeLLM` as `llm` (the stubbed `run_plan` receives it).
  - `app/run.py` imports `LLMProvider` from `ports` and nothing from `adapters` or `cli`.
  - The suite passes with only the approved test edits listed in Scope.

## Architecture rules that apply
- `app` depends on `domain` and `ports` only. `cli.py` is the composition root (ADR-011).
- All LLM output is validated by a Pydantic model before use: `parse_review_reply` / `ReviewVerdict`.
- All LLM calls go through `claude -p`, here `ClaudeCodeLLM` (300 s, no tools, a new empty directory).
- Every event goes through `_Chain`; no event, payload, schema or dependency change.

## Plan
1. Create branch `task/TASK-070-run-review-gate` from an up-to-date main.
2. Test-writer:
   - make the approved edits in `test_run_task.py`, `test_run_plan.py` and `test_m3_close.py`;
   - write failing tests for AC1 to AC5 in `test_run_task.py`;
   - write the AC6 wiring test in `test_cli_run.py`. AC6 also rests on the existing import tests.
3. Implement a private reviewer-attempt helper in `run.py`, modelled on `plan._attempt` but recording through `_Chain`, and call it once or twice after the three gates. Pass `llm` from `run_plan` and wire `ClaudeCodeLLM()` in `cli.py`.
4. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
5. Update the living docs and the Outcome.
6. Commit `feat(app): run the review gate in run` with the trailers `Task: TASK-070` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/app/run.py` (about +60)
- `src/openfactory/cli.py` (about +2)
- `tests/unit/test_run_task.py` (approved edits about +30, new tests about +200)
- `tests/unit/test_run_plan.py` (approved edits, about +10)
- `tests/integration/test_m3_close.py` (approved edits, about +40)
- `tests/integration/test_cli_run.py` (one new test, about +10)
- `docs/architecture.md`:
  - the `run_task` and `run_plan` paragraphs and the data flow (the reviewer is now called; `staged_diff` is now used);
  - `domain/review.py` and `app/review_prompt.py` no longer "nothing calls it yet".
- `docs/progress.md`:
  - Current: TASK-070. Done: add the line. Outline: item 8 removed.
  - Later: remove "Until item 8, `run_task` commits ... without running `review`" and settle the three item-8 points in the TASK-069 Later line (see design choices 2 and 3). Add the G1 wording item.
- `docs/decisions.md`: a row for the reading of G1, if approved.
- `docs/tasks/TASK-070-run-review-gate.md` (this record).

Not expected to change: `domain/`, `ports/`, `adapters/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 380 lines with tests, about 65 of them in `src/`.

## Spec gaps
- **G1 (wording, does not block). "Gates and remediation" › "The review gate", "when there is no verdict, it holds the run's `error`".**
  - Unclear: after a retry the gate has two reviewer runs, and "the run's" doesn't say which one.
  - Proposed reading: the last reviewer run, so the second run's rejection lines after a second rejected reply, or the failed process's error.
  - Why it does not block: only the last run ended without a verdict and decided the gate. This is a fix to the text, not a new decision.

## Design choices to confirm at planning
1. Item 8b is not split. `cli.py` must change in the same commit that makes `llm` required on `run_plan`.
2. The diff goes into the prompt unchanged, as TASK-069 AC4 requires. The doubled blank line before the retry section (TASK-069 Later line) is left as is.
3. The empty-diff point in the same Later line is unreachable: the reviewer runs only after `path_check` passed on a non-empty list of changed paths, and such a staged diff is never empty. No guard is added. Every no-verdict path passes a non-empty `error` to `review_file_text`.
4. The stand-in `claude` in `test_m3_close.py` recognises a reviewer call by `## Staged diff` in its stdin and logs role `reviewer`, so `Claude.starts()` for `planner` and `implementer` is unchanged.

## Outcome
Test edits approved after the test-writer ran (not in Scope at planning, approved 2026-10-20):
- `tests/unit/test_run_task.py::test_task068_ac1_gates_run_in_order_with_worktree_and_timeout`: the gate list gains `("review", True)` (not mechanical; all gates pass in that run, so `review` runs).
- `tests/unit/test_run_task.py`: `test_ac1_passed_run_records_seven_events_in_order` renamed to `test_ac1_passed_run_records_the_events_in_order`; the count in the name was no longer true.
- `tests/integration/test_m3_close.py::test_ac1_run_takes_the_tasks_in_order_through_the_stand_in`: the `AgentRunStarted` events are filtered to `role == "implementer"` before the comparison with `claude.starts()` (not mechanical; the reviewer starts are checked by the other edited tests).
- `test_task068_ac2_text_is_written_unchanged_and_path_is_recorded` is not edited: ruff fails in it, so `review` does not run, and it passes unchanged.
- `run_task` and `run_plan` take a required `llm: LLMProvider`; `run_task` reads `staged_diff` after the three gates pass and records the reviewer run(s) through a private `_review_attempt` (a `_Review` holds verdict, rejections and error). One retry on a rejected reply, none on an `LLMError`. `review.txt` is written under the implementer's run id and the `review` `GateEvaluated` follows; `approve` commits, anything else fails the task with reason `review`. `cli.py` passes `ClaudeCodeLLM()`. No port, adapter, dependency, event, payload or schema change; ADR field unchanged.
- G1 answered and decided 2026-10-20: the last reviewer run's `error`; recorded in `docs/decisions.md`. The diff goes in unchanged (doubled blank line stays); no empty-diff guard.
- Living docs: `docs/architecture.md`, `docs/progress.md` (item 8 removed, Later lines settled), `docs/decisions.md`.
