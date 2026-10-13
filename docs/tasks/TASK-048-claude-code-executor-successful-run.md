# TASK-048: `claude_code_executor` adapter for a run that succeeds

- Milestone: M3
- Status: done
- Tests: acceptance
- ADR: ADR-014 (accepted). "Ports and adapters (SC-63, SC-68)": "`AgentExecutor`, adapter `claude_code_executor`: `run(contract, context, workdir, output_dir) -> RunResult`. The adapter writes the runtime's result envelope to `<output_dir>/transcript.json`." ADR-005 (accepted) puts agent runs behind the port, removes `ANTHROPIC_API_KEY`, and pins envelope field names "by a captured fixture rather than by the spec". ADR-006 covers the `TYPE_CHECKING` assertion. No new port, dependency, event type, payload or storage change. The command-line flags, the envelope fields and the constructor are rows in `docs/decisions.md` (Open questions 2 to 5), as in TASK-029. If Open question 2 is answered with a permission-bypass flag, that is a choice with lasting consequences and needs your word on whether ADR-014's "`Bash` approved in advance" reading covers it.
- Spec impact: wording. Three items, none stops the task (see "Spec gaps").
- Spec sections (spec v1.12, SC-63, SC-66, SC-69, SC-76): "Execution" › "The agent call", "Adapter interface", "Per-task sequence" (step 3); "Tech stack and repo layout" (the paragraph after the stack table; the layout block); "Domain model and storage" › "Event payloads" (the `AgentRunFinished` block and the `model` sentence after the payload block); "Metrics" (`tokens_in`)

## Outline item
M3 outline item 1(a). Item 1(b) and items 2 to 6 are left.

## Objective
Add `ClaudeCodeExecutor`, the `AgentExecutor` adapter that starts `claude -p --output-format json` in a task's worktree with the six tools and the contract's time limit, and for a run that succeeds returns a `RunResult` read from the envelope and writes the envelope to `<output_dir>/transcript.json`.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings and to SC-63, SC-66, SC-69 and SC-76.

## Prerequisite
One real `claude -p` call with tools, on your subscription, outside pytest, in a scratch repository outside this project. It runs an agent with `Bash` approved in advance on your machine. The session makes it only with your leave, or you run it and hand over the output (Open question 1). Without the captured envelope the criteria AC5 and AC6 have no fixture and the flags of AC1 are unconfirmed: the task is then blocked.

## Scope
In (names and flags per Open questions 2 to 5):
- `tests/fixtures/claude_agent_envelope.json` (new): the standard output of one real implementer-style run, saved unedited. `tests/fixtures/claude_envelope.json` is unchanged.
- `src/openfactory/adapters/claude_code_executor.py` (new): `ClaudeCodeExecutor(repo: Path, executable: str = "claude")`.
  - One process per `run`: `claude -p --output-format json`, the six tools `Read`, `Glob`, `Grep`, `Edit`, `Write`, `Bash` made the only ones available and approved in advance by the flags confirmed in plan step 3, no `--model`, no `--json-schema`.
  - The context pack goes on standard input as UTF-8.
  - The working directory is `repo / workdir`, so a relative `workdir` is resolved against the adapter's repo and an absolute one is used as it is (the `GitCli` rule, row of 2026-10-13).
  - The time limit is `contract.limits.max_runtime_s`. The constructor has no time-limit parameter.
  - The environment is every variable except `ANTHROPIC_API_KEY`, built from the names; one structlog warning `anthropic_api_key_removed` when the name was present.
  - For exit status 0 and an envelope that parses: `RunResult` with `exit` `ok`, `error` `None`, `summary` the agent's final message, and `model`, `tokens_in`, `tokens_out`, `cost_usd`, `duration_s` read as `ClaudeCodeLLM` reads them (row of 2026-10-11, TASK-029).
  - It creates `repo / output_dir` when missing (parents included) and writes the envelope to `transcript.json` there (audit F-5, answer b).
  - It ends with `if TYPE_CHECKING: _: type[AgentExecutor] = ClaudeCodeExecutor`.
  - Private envelope models and helpers of its own; `claude_code_llm.py` is not changed (the `GitWorktree` precedent).
- Tests: a new integration file on a stand-in executable written under `tmp_path`. No test starts `claude`.

Out (not this task):
- Outline item 1(b): a non-zero exit, a `claude` that cannot be started, output that is not JSON or lacks the fields read, a timeout that passes, an envelope that reports an error (`is_error`, `subtype`), the `error` texts, and what `transcript.json` holds when there is no envelope (SC-63, SC-66, SC-71). Until 1(b), these paths are not handled and not tested here: an exception propagates, and an error envelope with exit status 0 is read as a success. The adapter is therefore not wired until 1(b) is done.
- Building the context pack and its hash (item 2); every caller of the port (item 3); wiring in `cli.py` (item 5).
- Any flag that stops Claude Code loading the target repo's own files. "The agent call" says the run loads them from the worktree (SC-69).
- Any check of `contract` beyond reading `limits.max_runtime_s`. `allowed_paths` is not turned into permission rules: "the path check stays the enforcement".
- `max_cost_usd` (M4). The Docker stretch goal.
- Hardening: a `workdir` that does not exist, an `output_dir` that cannot be written (`OSError` propagates), an existing `transcript.json` (replaced, no test), a `workdir` outside the repo.
- Any change to `ports/agent_executor.py`, `domain/agent_run.py`, `claude_code_llm.py` and existing tests.

## Acceptance criteria
"The agent call" and "Adapter interface" are under "Execution"; "the stack paragraph" is the paragraph after the stack table under "Tech stack and repo layout".

Terms:
- **A test repo** is a directory under `tmp_path` holding `.openfactory/worktrees/AUTH-002/` (made by the test) and no `.openfactory/runs/`. No git is needed.
- **The stand-in** is an executable script that records its arguments, standard input, environment names and working directory, then prints given text and exits with a given status (as in `tests/integration/test_claude_code_llm.py`, copied, not shared).
- **The fixture** is `tests/fixtures/claude_agent_envelope.json`.
- Unless said otherwise, `run` is called with `workdir` `Path(".openfactory/worktrees/AUTH-002")`, `output_dir` `Path(".openfactory/runs/run_0002")`, the stand-in printing the fixture with exit status 0, and the test's working directory set to another directory under `tmp_path`.

The criteria are written for the proposals under Open questions.

- [x] AC1 ("The agent call": "an implementer run starts `claude -p --output-format json` in the worktree with exactly the tools `Read`, `Glob`, `Grep`, `Edit`, `Write` and `Bash`, all approved in advance and no others available, the default model" and "The adapter passes the tool list on the command line"; "Tech stack and repo layout": `claude_code_executor` under `adapters/`; SC-66, SC-68):
  - The stand-in is started exactly once. Its arguments hold `-p`, and `--output-format` followed by `json`.
  - The arguments hold the availability flag and the approval flag confirmed in plan step 3, each followed by exactly the six tool names. They hold no `--model` and no `--json-schema`.
  - Standard input, decoded as UTF-8, equals the context pack, for a pack of two lines with a non-ASCII character.
  - `adapters/claude_code_executor.py` imports nothing from `openfactory.app`, and `uv run pyright` passes with the `TYPE_CHECKING` assertion as its last statement.
- [x] AC2 ("The agent call": "in the worktree"; "Per-task sequence" step 3: "the worktree as its working directory"; `docs/decisions.md` rows of 2026-10-13, audit F-7 and TASK-043: an adapter resolves a relative path against its own repo):
  - The stand-in's working directory, resolved, equals `(repo / ".openfactory/worktrees/AUTH-002")` resolved, although the test's working directory is elsewhere.
- [x] AC3 ("The agent call": "a time limit of the contract's `max_runtime_s`"):
  - With a spy that wraps `subprocess.run` in the adapter's module and delegates to the real one, the `timeout` passed is 1200 for a contract with `max_runtime_s` 1200 and 7 for one with 7.
- [x] AC4 (the stack paragraph: "the adapters start `claude` with that variable removed from its environment, without reading its value, and log a warning if it was present"):
  - With `ANTHROPIC_API_KEY` set in the test's environment, the stand-in's environment names do not hold it and do hold another variable the test set.
  - Exactly one log entry of level warning is captured (`structlog.testing.capture_logs`), and no captured entry holds the variable's value.
  - With the variable not set, no warning is captured.
- [x] AC5 ("Adapter interface": the `RunResult` block, "`summary` is the agent's final message" and "The other fields of `RunResult` become the fields of `AgentRunFinished`"; "Event payloads": "`duration_s` ... as the runtime reported it" and "When the runtime reports several models, `model` is the one with the most output tokens, the first on a tie"; "Metrics": "`tokens_in` is every input token the runtime reports: uncached, written to the cache and read from it"; SC-63, SC-76):
  - The returned `RunResult` has `exit` `ok` and `error` `None`.
  - `summary` equals the fixture's final message; `model` is the fixture's model name; `tokens_in` is the sum of the fixture's three input counts; `tokens_out`, `cost_usd` and `duration_s` (milliseconds divided by 1000) are the fixture's. The expected values are written as literals in the test, taken from the fixture at capture.
  - With the fixture edited to report two models, `model` is the one with more output tokens.
- [x] AC6 ("Adapter interface": "`output_dir` is the run's directory, `.openfactory/runs/<run id>/`. The adapter writes the runtime's result envelope to `<output_dir>/transcript.json`"; `docs/decisions.md` row of 2026-10-14, audit F-5 answer (b): the adapter creates the directory when missing and resolves a relative `output_dir` against its own repo; SC-63):
  - On a test repo with no `.openfactory/runs/`, after `run` the file `repo/.openfactory/runs/run_0002/transcript.json` exists and its bytes equal the bytes the stand-in printed.
  - The test's working directory holds no `.openfactory` entry afterwards.

## Architecture rules that apply
- The adapter implements a port and ends with its `TYPE_CHECKING` assertion (ADR-006, `CLAUDE.md`).
- All LLM calls go through `claude -p`; no Anthropic SDK; `ANTHROPIC_API_KEY` is never read (the environment is built from the names).
- LLM output is validated by a Pydantic model before use: the envelope goes through a private Pydantic model.
- No event is recorded and no projection is read or written. `cli.py`, `app/`, `domain/` and `ports/` are not changed.
- No new dependency. OpenFactory's own tests carry no `req` markers.
- No hardening beyond what the spec asks.

## Plan
1. Create branch `task/TASK-048-claude-code-executor-successful-run` from an up-to-date main and commit this record.
2. Get the human's answers to Open questions 1 to 6; record them here and as rows in `docs/decisions.md`. If an answer differs from a proposal, adjust the criteria before any test is written.
3. With the human's leave, confirm the command line and capture the fixture:
   - Read `claude --version` and `claude --help` for the flags that set the available tools and the pre-approved tools, and their value form.
   - In a new scratch git repository outside this project, with `ANTHROPIC_API_KEY` not set, make one call with the proposed flags and a short prompt on standard input that needs `Write` and `Bash` (for example: create `hello.txt` holding `hi`, then run `ls`).
   - Check: exit status 0, the file exists, `permission_denials` is empty, standard output is one JSON object.
   - Save standard output unedited as `tests/fixtures/claude_agent_envelope.json`, after checking it holds nothing personal (a path of the machine, an email).
   - Record the version, the command and the fields read under a "Fixture" heading here.
4. Write failing tests in `tests/integration/test_claude_code_executor.py` (new) for AC1 to AC6. No existing test is changed.
5. Add `adapters/claude_code_executor.py`.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
7. Update the living docs and the Outcome. Commit `feat(adapters): run the implementer through claude -p and read its envelope` with trailers `Task: TASK-048` and `Milestone: M3`.

## Files expected to change
- `src/openfactory/adapters/claude_code_executor.py` (new, about 110 lines)
- `tests/integration/test_claude_code_executor.py` (new, about 220 lines)
- `tests/fixtures/claude_agent_envelope.json` (new, captured)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-048-claude-code-executor-successful-run.md` (this record; Fixture and Outcome at close)

Not expected to change: `cli.py`, everything under `app/`, `domain/` and `ports/`, `adapters/claude_code_llm.py` and every other adapter, `tests/fixtures/claude_envelope.json`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, every existing test file.

Expected size: about 330 lines with tests, about 110 of them in `src/`. This is a little over the 300-line aim; the six criteria share one stand-in and one fixture.

## Living docs to update
- `docs/architecture.md`:
  - new section "Claude Code executor adapter": the command line, the fields read, the fixture's Claude Code version, the two path rules, and that the failed-process cases are not built yet;
  - "Data flow": the adapter exists, nothing calls it, `cli.py` does not wire it.
- `docs/progress.md`: Current, Done, outline item 1 reduced to (b), and the Later lines listed below.
- `docs/decisions.md`: rows for the answered open questions.
- `CHANGELOG.md` and `README.md`: no change (nothing a user sees).

## New dependencies
None.

## Spec gaps
Spec impact is "wording": three items, none stops the task.

1. "Execution" › "Adapter interface" ("`output_dir` is the run's directory, `.openfactory/runs/<run id>/`. The adapter writes the runtime's result envelope to `<output_dir>/transcript.json`"). Audit F-5.
   - Missing: the text does not say who creates the directory or that `output_dir` is passed relative to the repo.
   - Does not block: answered (b) on 2026-10-14, a `docs/decisions.md` row, and the port's docstring states the rule. AC6 traces to that row. The spec text is left to a later `/spec-change`.
2. "Execution" › "The agent call" ("in the worktree") and "Per-task sequence" step 3 ("the worktree as its working directory"). Audit F-7.
   - Missing: the text does not say that `workdir` arrives relative to the repo and is resolved by the adapter.
   - Does not block: decided on 2026-10-13 (`WorkspaceManager.create` returns a relative path; "an adapter resolves the path against its own repo"). AC2 traces to that row. The port's docstring states the rule for `output_dir` only; this task states and tests it for `workdir` in the adapter and in `docs/architecture.md`, and does not edit the port.
3. "Execution" › "Adapter interface" ("writes the runtime's result envelope to `<output_dir>/transcript.json`").
   - Unclear: whether the file holds the bytes `claude` printed or the envelope serialised again by the adapter.
   - Does not block: the meaning (the envelope is kept as evidence) is clear; the byte form is Open question 5, to be a `docs/decisions.md` row and a "Spec wording" Later line. AC6 is written for the proposal and changes if the answer differs.

Readings, not gaps (each follows from the text as written):
- "The exact command-line flags are fixed by the task that builds the adapter": the spec hands the flags to this task. They are Open question 2, not a gap.
- "`summary` is the agent's final message": the spec does not name the envelope field, and ADR-005 pins field names by fixture. Open question 4.
- "the default model": no `--model` flag, as for `ClaudeCodeLLM`.
- "`duration_s` ... as the runtime reported it": `duration_ms` divided by 1000, the TASK-029 row.
- "The agent run loads the target repo's own Claude Code files from the worktree": the process starts in the worktree with no flag against it; unlike a planner call there is no empty directory.
- "all approved in advance": no permission prompt can be answered in a `-p` run, so the approval is a command-line flag.

## Later lines in `docs/progress.md`: taken or left
- **"The `AgentExecutor` docstring gives the relative-path rule for `output_dir` only; the first `claude_code_executor` task states and tests that a relative `workdir` is resolved against the adapter's repo too" (TASK-047, reviewer).** Taken: AC2. Removed at close.
- **"Spec wording: ... `output_dir` ... (audit F-5). Answer given: (b) ..." (TASK-046; TASK-047).** The adapter half is taken: AC6. The line stays, since the spec text and the use-case half are left; "(TASK-048)" is added to it.
- **"`RunResult` checks no link between `exit`, `error` and `summary` ..." (TASK-047, planner).** Half taken: `error` `None` and `summary` set for `exit` `ok` (AC5). The failed-process half is 1(b). Left.
- **"`transcript.json` when the process gave no envelope ..." (TASK-047, planner).** Left for 1(b).
- **"The adapter does not read the envelope's `is_error` or `subtype` ..." and "What `claude` prints when it exits non-zero in JSON output mode was not checked ..." (TASK-029).** Left; 1(b) needs both for the executor.
- **"`.openfactory/runs` is a literal in two places ..." (TASK-047, advisor).** Left; this adapter holds no such literal.
- **Every other Later line:** left.
- **To add at close:**
  - "`ClaudeCodeExecutor` handles only a run that succeeds: a failed process raises, and an error envelope with exit status 0 is returned as `exit: ok`; it must not be wired before outline item 1(b) (TASK-048, planner)".
  - "'no others available' rests on the meaning of the availability flag in `claude --help`; no run observed a seventh tool being refused, and the target repo's own Claude Code files may widen the list (SC-69) (TASK-048, planner)".
  - "`ClaudeCodeExecutor` and `ClaudeCodeLLM` each hold their own envelope models, environment code and model rule; a change to one rule must be made in both (TASK-048, planner)".
  - "Spec wording: 'Adapter interface', 'writes the runtime's result envelope' does not give the bytes of `transcript.json`. Answer given: <Open question 5> (TASK-048, planner)".

## Open questions
1. **Capturing the fixture (prerequisite).** It needs one real `claude -p` call with `Read`, `Glob`, `Grep`, `Edit`, `Write` and `Bash` approved in advance, on the subscription, outside pytest.
   - Proposed: the session makes it once in plan step 3 with the human's leave, in a new scratch git repository outside this project, with a prompt that only writes one small file and runs `ls`, and saves the output unedited.
   - Alternative: the human runs the command and hands over or commits the file.
   - Without either, the task is blocked.
2. **The command-line flags.** The spec leaves them to this task. Flag names are proposals to be confirmed on `claude --help` in plan step 3, not checked yet.
   - Proposed: `claude -p --output-format json --tools "Read,Glob,Grep,Edit,Write,Bash" --allowedTools "Read,Glob,Grep,Edit,Write,Bash"`, with no `--model`. `--tools` limits what is available (`ClaudeCodeLLM` passes `--tools ""`), and `--allowedTools` approves them in advance.
   - Alternative (a): `--tools` with a permission-bypass flag (`--permission-mode bypassPermissions` or `--dangerously-skip-permissions`). Wider than "all approved in advance" needs, and it also bypasses the target repo's own deny rules; the ADR field says what that would need.
   - Alternative (b): `--allowedTools` only. The other built-in tools would then be present but unapproved, against "no others available".
3. **Constructor and prompt transport.**
   - Proposed: `ClaudeCodeExecutor(repo: Path, executable: str = "claude")`, as `GitCli(repo, executable)`; the context pack on standard input as UTF-8, as `ClaudeCodeLLM` does; no time-limit parameter, since the limit is the contract's.
   - Alternative: the prompt as a command-line argument. A long context pack can pass the argument limit.
4. **Which envelope fields.** To be confirmed on the new fixture.
   - Proposed: `summary` is the envelope's `result` string. The other fields are read as the row of 2026-10-11 (TASK-029) says: `duration_ms` / 1000, the three `usage` input counts summed, `usage.output_tokens`, `total_cost_usd`, the key of `modelUsage` with the most `outputTokens`.
   - To settle with it: whether `result` is a field the adapter requires. Proposed: yes, a string is required, so an envelope without it is "JSON without the fields the adapter reads" and becomes a failed process in 1(b). In this task such an envelope is not handled and not tested. Alternative: an absent `result` gives `summary` `""`, which would let a run with no final message reach the commit with an empty body.
5. **The bytes of `transcript.json`.**
   - Proposed: standard output as `claude` printed it, encoded as UTF-8 and written with `write_bytes`, with no parsing in between, so the file is the evidence unedited (the rule chosen for run files, row of 2026-10-13).
   - Alternative: the parsed envelope dumped again as JSON. It loses the fields the adapter does not read unless the raw dict is kept, and changes the formatting.
6. **How AC3 tests the time limit without the timeout case.** The timeout result belongs to 1(b), and a test that asserts an exception here would have to change there.
   - Proposed: a spy that wraps `subprocess.run` in the adapter's module and asserts the `timeout` argument. It ties the test to `subprocess.run`.
   - Alternative: no test of the limit in this task; 1(b) fixes it by behaviour with a stand-in that sleeps past a 1-second limit. AC3 is then dropped here and the adapter still passes the limit.

## Answers
The human approved the plan and the six proposed answers on 2026-10-14 (advisor: 6 AGREE). Each is a row in `docs/decisions.md`.
1. The session captured the fixture, once, in a new scratch git repository outside this project (see "Fixture").
2. `--tools "Read,Glob,Grep,Edit,Write,Bash" --allowedTools "Read,Glob,Grep,Edit,Write,Bash"`, each value one comma-joined argument, no `--model`, no permission-bypass flag.
3. `ClaudeCodeExecutor(repo: Path, executable: str = "claude")`; the context pack on standard input as UTF-8; no time-limit parameter.
4. `summary` is the envelope's `result`, a required string; the other fields as the TASK-029 row of 2026-10-11.
5. `transcript.json` holds standard output as `claude` printed it. Standard output is captured as bytes and written with `write_bytes` before it is parsed (the advisor's refinement), so no decoding or line-ending translation comes between.
6. AC3 uses a spy that wraps `subprocess.run` in the adapter's module and asserts the `timeout` argument.

## Fixture
- Claude Code 2.1.287.
- Captured on 2026-10-14 in a new empty git repository outside this project, with `ANTHROPIC_API_KEY` not set and a two-line prompt on standard input (create `hello.txt` holding `hi`, run `ls`, name files by relative path): `claude -p --output-format json --tools "Read,Glob,Grep,Edit,Write,Bash" --allowedTools "Read,Glob,Grep,Edit,Write,Bash"`. Exit status 0, nothing on standard error, `hello.txt` written, `permission_denials` empty, `num_turns` 3. Saved unedited as `tests/fixtures/claude_agent_envelope.json`; it holds a session id and a uuid and nothing personal.
- Confirmed on `claude --help`: `--tools <tools...>` ("the list of available tools from the built-in set") and `--allowedTools <tools...>` ("Comma or space-separated list of tool names to allow"). Confirmed by the run: `-p` reads the prompt from standard input with tools enabled, and `Write` and `Bash` ran with no prompt.
- Fields the adapter reads: `result`; the keys of `modelUsage` with each one's `outputTokens`; `usage.input_tokens`, `usage.cache_creation_input_tokens` and `usage.cache_read_input_tokens` (summed into `tokens_in`); `usage.output_tokens`; `total_cost_usd`; `duration_ms`.
- The fixture's values: `result` ``I created `hello.txt` containing `hi`, and `ls` shows it as the only file in the directory.``, model `claude-opus-5-5`, input counts 6 + 4061 + 22041 = 26108, output tokens 251, cost 0.0419402, `duration_ms` 5735 (5.735 s).
- Not checked: that a seventh tool is refused; `--tools` speaks of the built-in set, so MCP tools from user-level configuration or the target repo's `.mcp.json` may stay present, unapproved. The run was not isolated from the user-level Claude Code configuration.

## Outcome
- Built `ClaudeCodeExecutor(repo, executable="claude")` in `src/openfactory/adapters/claude_code_executor.py`, as the Objective and Answers say: one `claude -p --output-format json --tools ... --allowedTools ...` process per run with the six tools, context pack on standard input, `cwd` `repo / workdir`, `timeout` the contract's `max_runtime_s`, `ANTHROPIC_API_KEY` removed with one warning, standard output written as bytes to `repo / output_dir / transcript.json` before parsing, `RunResult` `ok` with `summary` the envelope's `result`. Only a run that succeeds is handled; nothing calls the adapter and `cli.py` does not wire it.
- Tests: `tests/integration/test_claude_code_executor.py` (11 tests, AC1 to AC6) on a stand-in executable, and the fixture `tests/fixtures/claude_agent_envelope.json`. 1181 tests pass; ruff, pyright and check_docs clean.
- Deviations from the plan: none. No test from the test-writer was edited.
- After the first review (changes required): the adapter did not read the exit status, so a non-zero exit with a parseable envelope came back as `exit` `ok`, against the Scope ("For exit status 0") and the docs ("a failed process raises"). Fixed with `done.check_returncode()` after the transcript is written, so a non-zero exit raises `subprocess.CalledProcessError`; no test covers it (the failed-process cases are outline item 1(b)).
- Living docs: `docs/architecture.md` (new section and Data flow), `docs/progress.md`, `docs/decisions.md` (six rows). `CHANGELOG.md` and `README.md` unchanged.
- Follow-ups (now in Later in `docs/progress.md`): the adapter must not be wired before outline item 1(b); "no others available" rests on the flag's meaning (MCP tools and user-level configuration not checked); duplicated envelope models with `ClaudeCodeLLM`; the AC3 test is tied to `subprocess.run`; error envelopes may carry no `result`; `duration_ms` fallback for a successful envelope; the `transcript.json` byte-form spec wording.
