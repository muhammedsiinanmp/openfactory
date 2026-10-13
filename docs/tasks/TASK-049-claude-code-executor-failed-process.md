# TASK-049: `claude_code_executor` adapter for a failed process

- Milestone: M3
- Status: done
- Tests: acceptance
- ADR: ADR-014 (accepted). "Ports and adapters (SC-63, SC-68)": "`AgentExecutor`, adapter `claude_code_executor`: `run(contract, context, workdir, output_dir) -> RunResult`. The adapter writes the runtime's result envelope to `<output_dir>/transcript.json`"; "How accepted ADRs are read from now on (SC-66, SC-71, SC-75)" covers the error envelope and the `claude` that cannot be started. ADR-005 (accepted) pins envelope field names "by a captured fixture rather than by the spec". No new port, adapter, dependency, event type, payload or storage change. The error texts, the field that marks an error envelope and the transcript rule are rows in `docs/decisions.md` (Open questions 1 to 5), as in TASK-029 and TASK-048.
- Spec impact: wording. Two items, neither stops the task (see "Spec gaps").
- Spec sections (spec v1.12, SC-63, SC-66, SC-71, SC-75): "Execution" › "The agent call", "Adapter interface", "Events of one task" (first bullet); "Tech stack and repo layout" (the paragraph after the stack table); "Domain model and storage" › "Event payloads" (the `AgentRunFinished` block)

## Outline item
M3 outline item 1(b), the whole of it. Item 1 is then done; items 2 to 6 are left.

## Objective
Make `ClaudeCodeExecutor.run` return, and never raise, a `RunResult` with `exit` `error` or `timeout` and `error` set for a non-zero exit, a `claude` that cannot be started, an envelope that cannot be parsed, an envelope that reports an error, and a timeout, and settle what `transcript.json` holds in each case.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings and to SC-63, SC-66, SC-71 and SC-75.

## Prerequisite
None. No real `claude` call: the error envelope used in tests is the captured fixture edited in the test (Open question 6).

## Scope
In (texts and rules per Open questions 1 to 5):
- `src/openfactory/adapters/claude_code_executor.py` (changed):
  - The `done.check_returncode()` line goes. Every failed process is returned as a `RunResult`, as the port's docstring says.
  - A timeout (`subprocess.TimeoutExpired`) gives `exit` `timeout`. The other four cases give `exit` `error`.
  - For every failed process: `error` is a non-empty text, `summary` is `""`, `duration_s` is the adapter's measured duration.
  - Standard error is decoded and used for the `error` text of a non-zero exit.
  - "Reports an error" is tested before the envelope model that requires `result` validates the output, so an error envelope without `result` keeps the runtime's error text. `is_error` and `subtype` are read through the all-optional model that also gives the metrics.
  - `model`, `tokens_in`, `tokens_out` and `cost_usd` on a failed process follow Open question 3.
  - `transcript.json` follows Open question 4.
  - The module docstring no longer says only a successful run is handled.
- Tests: a new integration file on a stand-in that can exit non-zero, write standard error and sleep. `tests/integration/test_claude_code_executor.py` is not changed.

Out (not this task):
- Any caller of the port, the events and the `run error` / `run timeout` reasons (the run use case, one task); wiring in `cli.py` (the `run` command).
- Any change to `ports/agent_executor.py`, `domain/agent_run.py`, `claude_code_llm.py`, the fixtures and every existing test.
- A shared module for the envelope models of the two Claude Code adapters.
- A real failing `claude` run, and capturing a real error envelope.
- Retrying a failed process. `max_cost_usd` (M4).
- Hardening: child processes of `claude` left alive after a timeout; an `output_dir` that cannot be written (`OSError` propagates); a `workdir` that does not exist (it reads as a `claude` that cannot be started); standard error that is not UTF-8 (decoded with replacement, no test).

## Acceptance criteria
"The agent call" and "Adapter interface" are under "Execution"; "Event payloads" is under "Domain model and storage".

Terms:
- **A test repo**, **the fixture**, `workdir` and `output_dir` are as in TASK-048.
- **The stand-in** here also takes an exit status, a text for standard error and a number of seconds to sleep before printing (as in `tests/integration/test_claude_code_llm.py`, copied, not shared).
- **A failed result** is a returned `RunResult` (no exception) with `error` a non-empty string and `summary` `""`.

The criteria are written for the proposals under Open questions.

- [x] AC1 ("The agent call": "A non-zero exit, a `claude` that cannot be started ... is a failed process: the run has `exit: error` or `timeout` and `error` set"; "Adapter interface": "`summary` is ... empty when `exit` is `error` or `timeout`"; "Event payloads": "`duration_s` ... measured by the adapter when the process failed or timed out"; SC-63, SC-75):
  - With the stand-in printing nothing, writing `boom` to standard error and exiting 3: a failed result with `exit` `error` and `error` `boom`; `model`, `tokens_in`, `tokens_out` and `cost_usd` are `None`.
  - With the same and nothing on standard error: `error` is `claude exited with status 3`.
  - With the stand-in printing the fixture and exiting 3: `exit` is `error` and `summary` is `""`; `duration_s` is not the fixture's 5.735.
  - With an executable path that does not exist: a failed result with `exit` `error`, and `error` starts with `claude could not be started: `; the four nullable metrics are `None`.
- [x] AC2 ("The agent call": "an envelope that cannot be parsed ... is a failed process"; "Tech stack and repo layout": "An envelope that cannot be parsed is output that is not JSON, or JSON without the fields the adapter reads"; `docs/decisions.md` row of 2026-10-14: `result` is a required string):
  - With exit status 0 and standard output `not json`: a failed result with `exit` `error` and `error` `claude output is not a JSON envelope`.
  - The same result for the fixture with `result` removed (and `is_error` still `false`, `subtype` still `success`).
- [x] AC3 ("The agent call": "an envelope that reports an error ... is a failed process"; `docs/decisions.md` row of 2026-10-13, SC-71: "For an agent run, an envelope that reports an error is a failed process (`exit: error`)"; SC-71):
  - With exit status 0 and the fixture edited to `is_error` `true`, `subtype` `error_during_execution` and `result` `Usage limit reached`: a failed result with `exit` `error` and `error` `Usage limit reached`. `summary` is `""`, not the envelope's `result`.
  - With the same envelope and `result` removed: `exit` is `error` and `error` names the subtype, not `claude output is not a JSON envelope`.
  - With the fixture edited only to `subtype` `error_max_turns` (`is_error` `false`): `exit` is `error`.
  - In the first case `cost_usd`, `tokens_in`, `tokens_out` and `model` are the fixture's values, and `duration_s` is not 5.735.
- [x] AC4 ("The agent call": "a time limit of the contract's `max_runtime_s`" and "or a timeout is a failed process: the run has `exit: error` or `timeout`"; "Event payloads": `duration_s` "measured by the adapter when the process failed or timed out"; SC-66):
  - With a contract whose `max_runtime_s` is 1 and the stand-in sleeping 10 seconds: a failed result with `exit` `timeout` and `error` `timed out after 1 s`.
  - `duration_s` is at least 1 and less than 10. The four nullable metrics are `None`.
- [x] AC5 ("Adapter interface": "The adapter writes the runtime's result envelope to `<output_dir>/transcript.json`"; `docs/decisions.md` row of 2026-10-14: the file holds standard output as `claude` printed it; the answer to Open question 4; SC-63):
  - After the `not json` run of AC2 and after the exit-3 run of AC1 that prints the fixture, `repo/.openfactory/runs/run_0002/transcript.json` holds exactly the bytes the stand-in printed.
  - After the timeout of AC4 and after the run with a missing executable, the file exists and is empty.
- [x] AC6 ("The agent call": "exactly the tools `Read`, `Glob`, `Grep`, `Edit`, `Write` and `Bash`, all approved in advance and no others available, the default model" and "The exact command-line flags are fixed by the task that builds the adapter"; `docs/decisions.md` row of 2026-10-14: "with no `--model` and no permission-bypass flag"; SC-66):
  - For a run that succeeds, the stand-in's argument list equals exactly `["-p", "--output-format", "json", "--tools", "Read,Glob,Grep,Edit,Write,Bash", "--allowedTools", "Read,Glob,Grep,Edit,Write,Bash"]`.
  - This test passes before the change; it pins the list and is not a failing-first test.

## Architecture rules that apply
- The adapter keeps its `TYPE_CHECKING` assertion as its last statement (ADR-006).
- `ANTHROPIC_API_KEY` is never read. No Anthropic SDK.
- LLM output is validated by a Pydantic model before use. `is_error`, `subtype` and the metrics are read through a model whose fields are all optional; `summary` comes only through the model that requires `result`.
- No event is recorded. `cli.py`, `app/`, `domain/` and `ports/` are not changed.
- No new dependency. No `req` markers. No hardening beyond what the spec asks.
- Existing tests are fixed: none is edited, weakened or deleted.

## Plan
1. Create branch `task/TASK-049-claude-code-executor-failed-process` from an up-to-date main and commit this record.
2. Get the human's answers to Open questions 1 to 6; record them here and as rows in `docs/decisions.md`. If an answer differs from a proposal, adjust the criteria before any test is written.
3. Write failing tests in `tests/integration/test_claude_code_executor_failures.py` (new) for AC1 to AC5, and the pin test of AC6.
4. Change `adapters/claude_code_executor.py`:
   - Catch `subprocess.TimeoutExpired` and `OSError` around `subprocess.run` only, so an `OSError` from writing the transcript still propagates.
   - Write the transcript on every path (Open question 4).
   - Load standard output as JSON; when it is an object, read `is_error`, `subtype` and the metrics through a model whose fields are all optional (Open questions 1 and 3). When that model rejects the object, the metrics are `None` and the outcome is decided as otherwise.
   - Decide in this order: error envelope, non-zero exit, envelope that does not validate, success (Open question 2).
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
6. Update the living docs and the Outcome. Commit `feat(adapters): return a failed implementer run as a result` with trailers `Task: TASK-049` and `Milestone: M3`.

## Files expected to change
- `src/openfactory/adapters/claude_code_executor.py` (about 60 lines added or changed)
- `tests/integration/test_claude_code_executor_failures.py` (new, about 230 lines)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-049-claude-code-executor-failed-process.md` (this record; Outcome at close)

Not expected to change: `cli.py`, everything under `app/`, `domain/` and `ports/`, `adapters/claude_code_llm.py`, `tests/integration/test_claude_code_executor.py`, both fixtures, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 290 lines with tests. If the answers to Open questions 1 and 3 add cases, AC3 (the error envelope) is split into its own task.

## Living docs to update
- `docs/architecture.md`, section "Claude Code executor adapter": replace the "Only a run that succeeds is handled" bullet with the five failed-process cases, their order, the `error` texts, the metric rule and the transcript rule; "Data flow": the adapter is complete, nothing calls it yet.
- `docs/progress.md`: Current, Done, outline item 1 removed, and the Later lines listed below.
- `docs/decisions.md`: rows for the answered open questions.
- `CHANGELOG.md` and `README.md`: no change (nothing a user sees).

## New dependencies
None.

## Spec gaps
Spec impact is "wording": two items, neither stops the task.

1. "Execution" › "Adapter interface" ("The adapter writes the runtime's result envelope to `<output_dir>/transcript.json`").
   - Missing: what is written when there is no envelope: a timeout, a `claude` that cannot be started, or output that is not JSON.
   - Does not block: for a process that ran to its end, the row of 2026-10-14 already says the file holds standard output as printed, whatever it is, and the code already does so. Only the timeout and the `claude` that cannot be started are open; that is Open question 4, and AC5's second bullet traces to its answer. Nothing reads the file in M3.
   - Not assumed: AC5's second bullet is written for the proposal and changes with the answer.
2. "Domain model and storage" › "Event payloads", the `AgentRunFinished` block ("`tokens_in` ... null when the runtime reported none", the same for `tokens_out` and `cost_usd`; "`duration_s` ... measured by the adapter when the process failed or timed out").
   - Unclear: whether model, tokens and cost are read from an envelope that a failed process printed (an error envelope, or a non-zero exit with an envelope on standard output). The text says null "when the runtime reported none" and is silent on a failed process that did report them. `duration_s` is clear: measured.
   - Does not block: either reading gives a valid `RunResult`. It is Open question 3; the metric bullets of AC1 and AC3 change with the answer. It matters from M4, where `max_cost_usd` sums `cost_usd`.

Readings, not gaps (each follows from the text as written):
- "an envelope that reports an error": the spec does not name the field, and ADR-005 pins field names by fixture. Open question 1.
- "`error` set": the spec fixes that it is set, not its text. Open question 2, as the TASK-029 row of 2026-10-11 did for `LLMError`.
- "`exit: error` or `timeout`": `timeout` for a time limit that passes, `error` for the other four.
- A failed process is returned, not raised: the port's docstring and the TASK-047 row of 2026-10-14.

## Later lines in `docs/progress.md`: taken or left
- **"`ClaudeCodeExecutor` handles only a run that succeeds ... must not be wired before outline item 1(b)" (TASK-048, planner).** Taken: AC1 to AC4. Removed at close.
- **"For outline item 1(b): the `done.check_returncode()` line ... standard error is captured and dropped ... exact-argv assertion" (TASK-048, reviewer).** All three taken: AC1 (returned result, standard error in `error`) and AC6 (exact argument list). Removed at close.
- **"The AC3 test of `ClaudeCodeExecutor` is tied to `subprocess.run` ..." (TASK-048, advisor).** Half taken: AC4 fixes the limit by behaviour. The spy test stays unchanged, since existing tests are fixed (Open question 5). The line is reworded to say the timeout outcome is now also tested by behaviour; the spy test stays, since it checks two contract values and AC4 checks one.
- **"Outline item 1(b): an error envelope may carry no `result` ..." (TASK-048, advisor).** Taken: AC3, second bullet. Removed at close.
- **"`transcript.json` when the process gave no envelope ..." (TASK-047, planner).** Taken: AC5. Replaced at close by a "Spec wording ... Answer given" line (Spec gaps item 1).
- **"`RunResult` checks no link between `exit`, `error` and `summary` ..." (TASK-047, planner).** Taken for the adapter: every failed result has `error` set and `summary` empty. Reworded: the model still checks nothing, the adapter's tests do.
- **"What `claude` prints when it exits non-zero in JSON output mode was not checked ..." and "The adapter does not read the envelope's `is_error` or `subtype` ..." (TASK-029).** Left. Both are about `ClaudeCodeLLM`; "(TASK-049: the executor reads `is_error` and `subtype`, still unobserved on a real failing run)" is added to the second.
- **"`ClaudeCodeExecutor` and `ClaudeCodeLLM` each hold their own envelope models ..." (TASK-048, planner).** Left; the error texts are now duplicated too, which is added to the line.
- **"No others available" (TASK-048), the `duration_ms` wording line (TASK-048, advisor), the F-5 and transcript byte-form wording lines, `.openfactory/runs` as a literal in two places.** Left.
- **Every other Later line:** left.
- **To add at close:**
  - "Spec wording: 'Event payloads', `AgentRunFinished`: model, tokens and cost of a failed process that printed an envelope. Answer given: <Open question 3> (TASK-049, planner)".
  - "No real error envelope was captured: the `is_error` and `subtype` rule and the test envelopes are edited by hand from the fixture; check at the first real implementer run that fails (TASK-049, planner)".
  - "After a timeout only the `claude` process is killed; processes it started through `Bash` may live on and may hold the output pipe open; not checked (TASK-049, planner)".
  - "A `workdir` that does not exist gives `claude could not be started: ...`, the same text as a missing executable (TASK-049, planner)".

## Open questions
1. **Which envelope field says "reports an error".** The fixture holds `is_error` (`false`), `subtype` (`success`) and `api_error_status` (`null`). No error envelope has been observed.
   - Proposed: an envelope reports an error when `is_error` is `true`, or `subtype` is a string other than `success`. Either signal is enough, so an error subtype with `is_error` `false` does not go on to the gates. `api_error_status` is not read.
   - Alternative: `is_error` `true` only. An error subtype with `is_error` `false` and a `result` string would then read as a success.
2. **The `error` texts and the order of the checks.**
   - Proposed texts, those of `ClaudeCodeLLM` (row of 2026-10-11) where the case is the same:
     - timeout: `timed out after <max_runtime_s> s`;
     - cannot be started: `claude could not be started: <OS error>`;
     - error envelope: the envelope's `result` when it is a non-empty string, otherwise `claude reported an error: <subtype>`, or `claude reported an error` with no subtype;
     - non-zero exit: standard error stripped, or `claude exited with status N` when it is empty;
     - unparsable: `claude output is not a JSON envelope`.
   - Proposed order after the process ends: error envelope, then non-zero exit, then an envelope that does not validate. An error envelope printed with a non-zero exit then keeps the runtime's own text and not `claude exited with status 1`.
   - Alternative: non-zero exit first, as `ClaudeCodeLLM` does. Simpler, but the likely real case (error envelope, exit 1, empty standard error) gets the status text only.
3. **Model, tokens and cost of a failed process (Spec gaps item 2).**
   - Proposed: when standard output is a JSON object, `model`, `tokens_in`, `tokens_out` and `cost_usd` are read from it as for a success, each `None` when absent, whatever the outcome. For a timeout, a `claude` that cannot be started and output that is not a JSON object they are `None`. `duration_s` is always the measured duration for a failed process.
   - Alternative: all four `None` for every failed process, as for a failed planner call. Simpler, but the cost of a run that ended in an error envelope is then missing from the M4 cost limit and the M7 figures.
4. **`transcript.json` when there is no envelope (Spec gaps item 1).**
   - Proposed: the file is always written, so it exists after every `run`. A process that ran to its end: standard output as printed (the existing rule, also for empty or non-JSON output). A timeout and a `claude` that cannot be started: an empty file. Partial output from a timed-out process is not kept.
   - Alternative (a): no file for a timeout and a `claude` that cannot be started; the directory is still created.
   - Alternative (b): for a timeout, the bytes captured before the process was killed.
5. **The TASK-048 spy test of the time limit.**
   - Proposed: it stays unchanged, and AC4 adds the behaviour test. The spy still passes, since the adapter keeps `subprocess.run`.
   - Alternative: the human approves deleting `test_ac3_time_limit_is_the_contracts_max_runtime`, since AC4 covers the limit by behaviour. This is a deletion of a fixed test, so it needs that approval.
   - Note: the AC4 test takes about 1 second of wall time, because `max_runtime_s` is an integer greater than 0.
6. **The error envelope used in tests.**
   - Proposed: the captured fixture edited inside the test (`is_error`, `subtype`, `result`), with no new fixture file and no real call.
   - Alternative: one real call that ends in an error, with the human's leave, saved as a second fixture. An error is hard to provoke with the adapter's own flags, so the capture would use a flag the adapter does not pass.

## Answers
Given by the human on 2026-10-14, after the advisor's review (6 AGREE of 6). Each is a row in `docs/decisions.md`.

1. As proposed: an envelope reports an error when `is_error` is `true`, or `subtype` is a string other than `success`. The two keys are read through the all-optional model, not from the raw parsed object.
2. As proposed: the texts and the order (error envelope, non-zero exit, envelope that does not validate, success).
3. As proposed. When the all-optional model rejects the JSON object (a metric field of the wrong type), the four metrics are `None` and the outcome is decided as otherwise.
4. As proposed: the file is always written; empty for a timeout and a `claude` that cannot be started. Spec impact stays wording; the spec text is left to a later `/spec-change`.
5. As proposed: the spy test stays unchanged. The AC4 test asserts nothing the stand-in records.
6. As proposed: the fixture edited in the test, no real call.

## Outcome
Built (only `src/openfactory/adapters/claude_code_executor.py` changed in `src/`):
- `ClaudeCodeExecutor.run` returns and never raises for a failed process; `done.check_returncode()` is gone. `subprocess.TimeoutExpired` gives `exit` `timeout` and `timed out after <max_runtime_s> s`; an `OSError` from starting the process gives `exit` `error` and `claude could not be started: <OS error>`. In both, `transcript.json` is written empty and the four nullable metrics are `None`.
- After a process that ran to its end, standard output is written to `transcript.json` as printed and checked in this order: error envelope (`is_error` true, or `subtype` a string other than `success`), non-zero exit (standard error stripped, else `claude exited with status N`), envelope that does not validate or is not JSON (`claude output is not a JSON envelope`), success.
- Models: `_Metrics` is the base of `_Envelope` (adds required `result`, `duration_ms`) and of the new all-optional `_Reported` (adds `is_error`, `subtype`, `result`). For a failed process whose standard output is a JSON object that `_Reported` accepts, `model`, `tokens_in`, `tokens_out` and `cost_usd` are read from it, else `None`. `duration_s` is measured and `summary` is `""` for every failed process. One private helper `_result` builds every `RunResult`; `_write_transcript` creates the directory and writes the file.
- New `tests/integration/test_claude_code_executor_failures.py`: 15 tests (14 for AC1 to AC5, one AC6 pin of the exact argument list, which passed before the change). 1196 tests pass; ruff, pyright and check_docs clean.

Deviations from plan: none, apart from the three advisor refinements recorded under Answers (the two keys read through the all-optional model; the metrics `None` when that model rejects the object; the AC4 test asserts nothing the stand-in records).

Test edits: none. No existing test, fixture, port, domain or app file changed; no test from the test-writer was edited.

Follow-ups (Later lines in `docs/progress.md`): no real error envelope captured; after a timeout only `claude` is killed; a missing `workdir` reads as a `claude` that cannot be started; the two "Spec wording ... Answer given" lines (transcript when there is no envelope; metrics of a failed process); the lines for TASK-029, the duplicated envelope models and error texts, and the spy test were reworded. Nothing calls the adapter yet; no `cli.py` wiring.
