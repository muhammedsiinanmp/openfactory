# TASK-029: `LLMProvider` port and the Claude Code LLM adapter

- Milestone: M2
- Status: done
- Tests: acceptance
- ADR: ADR-005 (accepted, 2026-10-09, with its amendment of 2026-10-11). It decides the `LLMProvider` port, the call `claude -p --output-format json --json-schema`, "The Pydantic model's JSON Schema is passed in and the structured result is read from the envelope", tools disabled, the 300 second limit, the default model, the recorded model name, the removal of `ANTHROPIC_API_KEY` with one warning, "the envelope's field names are pinned by a captured fixture rather than by the spec" and "Adapter tests use a stand-in executable and a captured reply". The amendment says a failed process is not retried. ADR-006 covers the `TYPE_CHECKING` assertion. That is enough: no new ADR. The signature and the other answers under Open questions are rows in `docs/decisions.md`; two existing rows already bind (2026-10-08, G18: one method `complete(prompt, schema)`, `LLMError` on a process failure or timeout; 2026-10-11, SC-27: `LLMError` "carries the duration and whether it was a timeout").
- Spec impact: wording. Three items, none blocks (see "Spec gaps").
- Spec sections (spec v1.11): "Tech stack and repo layout" (the "Planner and diff LLM calls" row; the paragraph that starts "All model calls go through Claude Code"; the layout block's `ports/` and `adapters/` lines; the "Logging" row); "Domain model and storage" ("Event payloads": the `AgentRunFinished` block); "Metrics"; "CLI commands" ("Output": "log lines go to standard error")

## Objective
Add the `LLMProvider` port and its Claude Code adapter, which starts `claude -p --output-format json --json-schema` once with no tools and `ANTHROPIC_API_KEY` removed, and returns the structured result with the model, tokens, cost and duration, or raises `LLMError` with its duration for a failed process, so the plan use case can make a planner call without touching a process.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings.

## Scope
In (names and modules per Open questions 2 and 3):
- `src/openfactory/domain/llm.py` (new): frozen, `extra="forbid"` `LLMReply`.
  - `structured: object | None`, `model: str | None`, `tokens_in: int | None`, `tokens_out: int | None`, `cost_usd: float | None`, `duration_s: float`.
- `src/openfactory/ports/llm_provider.py` (new):
  - Protocol `LLMProvider` with one method, `complete(prompt: str, schema: dict[str, object]) -> LLMReply`.
  - `LLMError(Exception)` with `duration_s: float` and `timeout: bool`; its text is `str(error)`.
- `src/openfactory/adapters/claude_code_llm.py` (new; the module name is the spec's):
  - `ClaudeCodeLLM(executable: str = "claude", timeout_s: float = 300)` with `complete`.
  - One process per call, never a second, started in a new empty temporary directory.
  - The environment passed to the process has no `ANTHROPIC_API_KEY`; one structlog warning when it was present.
  - Ends with `if TYPE_CHECKING: _: type[LLMProvider] = ClaudeCodeLLM`.
- `tests/fixtures/claude_envelope.json` (new): one envelope captured from the installed Claude Code, saved as printed.
- Tests that start a stand-in executable written under `tmp_path`. No test starts `claude`.

Out (not this task):
- Every caller: the prompt, the JSON Schema of `PlannerReply`, `parse_reply` and `check_plan` on the reply, the single retry, `AgentRunStarted` and `AgentRunFinished`, `context_hash` (item 9); the `plan` command and its `planner call failed: <error>` line (item 10).
- Whether a reply with no structured result is retried (audit F-6). The adapter never retries.
- A structured result that is JSON `null`: no criterion asserts it (Open question 1).
- Configuring structlog (JSON lines, standard error). The adapter only gets a logger and logs; the configuration belongs to the composition root (Open question 10).
- `AgentExecutor`, `claude_code_executor` and any shared helper for the two Claude Code adapters (M3).
- `GitProvider` (item 8), `cli.py`, `app/`, the projector, `domain/payloads.py`, `domain/plan_checks.py`.
- Reading the envelope's `is_error` or `subtype`. The spec's three failed-process cases and "structured result is missing" decide the outcome.
- Hardening: output in an encoding other than UTF-8, an envelope whose metric fields have wrong types, a process that ignores termination, output size limits.

## Acceptance criteria
"Event payloads" is under "Domain model and storage"; "Output" is under "CLI commands". "The stand-in" is an executable script the test writes under `tmp_path`; it saves its arguments, its standard input and the names of its environment variables to files, then prints what the test tells it to and exits with the status the test gives. "The fixture" is `tests/fixtures/claude_envelope.json`. The expected numbers in AC3 are literals copied from the fixture by hand, not computed by the code under test. The criteria are written for the proposals under Open questions.

- [x] AC1 ("Tech stack and repo layout": "`ports/ # interfaces: ..., GitProvider, LLMProvider`" and "`adapters/ # ..., claude_code_executor, claude_code_llm, ...`"; "the domain never imports infrastructure"):
  - `openfactory.ports.llm_provider` defines a Protocol `LLMProvider` whose only public method is `complete`, and imports nothing from `openfactory.adapters` or `openfactory.app` (checked by parsing its imports with `ast`).
  - `openfactory.domain.llm` imports nothing from `openfactory.ports`, `openfactory.adapters` or `openfactory.app`; `openfactory.adapters.claude_code_llm` imports nothing from `openfactory.app` and does not import `anthropic`.
- [x] AC2 ("Tech stack and repo layout": "Claude Code headless (`claude -p --output-format json --json-schema`) behind `LLMProvider`" and "A planner or classifier call runs with no tools, a 300 second time limit and the default model"):
  - With the stand-in printing the fixture, `complete(prompt, schema)` starts it once with `-p`, `--output-format json` and `--json-schema` followed by a string that decodes as JSON to `schema`.
  - The arguments hold `--tools` followed by an empty string, and no `--model`.
  - The stand-in ran in a directory that was empty and is not the caller's working directory (the stand-in saves its working directory and that directory's listing).
  - The stand-in received `prompt` unchanged, a line break and a non-ASCII character included.
  - `ClaudeCodeLLM()` has a time limit of 300 seconds.
- [x] AC3 ("Tech stack and repo layout": "validated by Pydantic"; "Event payloads": "`model: "<model name>" | null`", "null when the runtime reported none" and "`duration_s` ... as the runtime reported it"; "Metrics": "`tokens_in` is every input token the runtime reports: uncached, written to the cache and read from it"):
  - With the stand-in printing the fixture, the returned `LLMReply` has `structured` equal to the fixture's structured result, and the fixture's model name, output tokens, cost and duration in seconds.
  - `tokens_in` is the sum of the fixture's three input counts.
  - With the token, cost and model fields removed from the envelope, those four values are `None` and the call still returns.
- [x] AC4 ("Tech stack and repo layout": "A non-zero exit, an envelope that cannot be parsed, or a timeout is a failed process: it is not retried, the run is recorded with `exit: error` or `timeout` and `error` set"; "Event payloads": "`duration_s` ... measured by the adapter when the process failed or timed out"):
  - The stand-in exits with status 3: `complete` raises `LLMError` with `timeout` false, a `duration_s` of zero or more and a text that is not empty.
  - The stand-in exits 0 and prints `not json`, or prints nothing: the same.
  - The stand-in sleeps longer than a small `timeout_s`: `LLMError` with `timeout` true and a `duration_s` of at least `timeout_s`.
  - In each case the stand-in was started exactly once.
- [x] AC5 ("Tech stack and repo layout": "An envelope that parses but whose structured result is missing or fails Pydantic validation is a rejected reply"):
  - With the fixture's `structured_output` key removed, `complete` raises nothing and returns an `LLMReply` with `structured` `None` and the fixture's model, tokens, cost and duration.
  - `parse_reply(reply.structured)` on that reply gives the one rejection `no structured result`.
  - With a structured result the caller's model would reject (an object with no `tasks`), `complete` returns it unchanged; the adapter does not validate it.
- [x] AC6 ("Tech stack and repo layout": "the adapters start `claude` with that variable removed from its environment, without reading its value, and log a warning if it was present"; the "Logging" row):
  - With `ANTHROPIC_API_KEY` set in the test's environment, the stand-in's environment has no such name and still has another variable the test set.
  - Exactly one log entry of level warning is captured (`structlog.testing.capture_logs`), and no captured entry holds the variable's value.
  - With the variable not set, no warning is captured.

## Architecture rules that apply
- Ports hold Protocols only and import from `openfactory.domain` only. `LLMError` sits beside its Protocol as `EventConflictError` does in `ports/event_store.py`.
- `domain/llm.py` is pure: no I/O, no import from `ports`, `adapters` or `app`.
- The adapter ends with its `TYPE_CHECKING` assertion against `LLMProvider` (ADR-006).
- "All LLM calls go through `claude -p`. Never add the Anthropic SDK or read `ANTHROPIC_API_KEY`": the adapter builds the child's environment without the name and never looks at the value.
- "All LLM output is validated by a Pydantic model before use": the adapter returns the structured result unvalidated; the caller validates it with `parse_reply` (ADR-005: the retry and the validation are in the app layer).
- No event is recorded and no projection is read or written.
- Tests from the test-writer are fixed. No existing test is changed.
- No hardening beyond the spec's rules.

## Plan
1. Create branch `task/TASK-029-llm-provider-claude-code-adapter` from an up-to-date main and commit this record.
2. Get the human's answers to the Open questions; record them here and as rows in `docs/decisions.md`.
3. Confirm the command line on the installed Claude Code, with the human's leave for one real call (Open question 4):
   - `claude --version` and `claude --help`: `--json-schema` is present, the flag that disables every tool, and that `-p` reads the prompt from standard input.
   - One call with a two-field schema and a one-line prompt; save its standard output unedited as `tests/fixtures/claude_envelope.json`.
   - Record in this record the field names the adapter reads (structured result, model, the three input counts, output tokens, cost, duration) and the Claude Code version.
4. Write failing tests:
   - `tests/unit/test_llm_provider_port.py` for AC1, in the style of `tests/unit/test_runs_port.py`.
   - `tests/integration/test_claude_code_llm.py` for AC2 to AC6, with one helper that writes the stand-in (shebang `sys.executable`, mode 0o755).
5. Add `domain/llm.py` and `ports/llm_provider.py`.
6. Add `adapters/claude_code_llm.py`:
   - Build the environment as every entry of `os.environ` whose name is not `ANTHROPIC_API_KEY`; log one warning when the name was in `os.environ`.
   - `subprocess.run` in a `tempfile.TemporaryDirectory()` with the argument list, `input=prompt`, `capture_output=True`, `text=True`, `encoding="utf-8"`, `timeout=timeout_s`, and `time.monotonic()` around it.
   - `TimeoutExpired`, a non-zero return code, an `OSError` on start, or standard output that is not a JSON object the envelope model accepts raises `LLMError` with the measured duration.
   - Otherwise read the envelope through a small private Pydantic model with every field optional, and build `LLMReply`.
7. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until green.
8. Update the living docs and the Outcome. Commit `feat(adapters): add the LLMProvider port and the Claude Code LLM adapter` with trailers `Task: TASK-029` and `Milestone: M2`.

## Files expected to change
- `src/openfactory/domain/llm.py` (new, about 25 lines)
- `src/openfactory/ports/llm_provider.py` (new, about 35 lines)
- `src/openfactory/adapters/claude_code_llm.py` (new, about 110 lines)
- `tests/fixtures/claude_envelope.json` (new, captured)
- `tests/unit/test_llm_provider_port.py` (new, about 45 lines)
- `tests/integration/test_claude_code_llm.py` (new, about 240 lines)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-029-llm-provider-claude-code-adapter.md`

About 170 lines of source and 285 of tests: over the 300-line aim, within six criteria (Open question 11).

Not expected to change: `cli.py`, everything under `app/`, the other modules under `domain/`, `ports/` and `adapters/`, `pyproject.toml` (structlog is already a dependency), `docs/adr/`, `docs/spec/`, and every existing test file.

## Living docs to update
- `docs/architecture.md`:
  - New sections "LLM reply" (`domain/llm.py`), "LLMProvider port" and "Claude Code LLM adapter", the last with the envelope fields read and the Claude Code version of the fixture.
  - "Data flow": the port exists for the plan use case and no use case calls it yet.
- `docs/progress.md`:
  - Current, then Done; remove outline item 7.
  - The "Spec gap (before outline item 9 is planned)" line: drop "settle before outline item 7 decides how the adapter reports a missing result" and say what the adapter does (a missing key gives `structured` `None`; a JSON `null` also arrives as `None`, with no test).
  - Outline item 9: it copies `str(LLMError)` unchanged into `AgentRunFinished.error` (audit Q4 of `docs/spec-audits/2026-10-11-proposal-v1.11.md`).
  - Outline item 10: structlog is configured there, JSON lines on standard error.
  - Later line for Spec gaps items 2 and 3.
- `docs/decisions.md`: rows for the answered questions.
- `CHANGELOG.md`, `README.md`: no change (no command or output is added).

## New dependencies
None. `structlog` is in `pyproject.toml` already and is used here for the first time.

## Spec gaps
Spec impact is "wording". None of the three blocks.

1. "Tech stack and repo layout": "An envelope that parses but whose structured result is missing or fails Pydantic validation is a rejected reply"; "Task contract" › "Plan checks": "A reply whose structured result is missing is one `schema` rejection with subject `reply` and the message `no structured result`".
   - Unclear: whether a structured result that is JSON `null` is "missing" or a Pydantic failure (TASK-028, reviewer; the "Later" line in `docs/progress.md`).
   - Does not block: under both readings the envelope parses, so the adapter returns a reply and raises nothing, which is all this task builds. The readings differ only in the message of one `schema` rejection with subject `reply`, which `parse_reply` produces. No criterion here asserts the `null` case. As built, a `null` arrives as `None`, the same as the TASK-028 row of 2026-10-11 in `docs/decisions.md`. The human confirms under Open question 1.
2. "Tech stack and repo layout": "A non-zero exit, an envelope that cannot be parsed, or a timeout is a failed process".
   - Missing: a `claude` executable that cannot be started (not installed, not executable) is none of the three.
   - Does not block: no criterion covers it; the proposal is under Open question 7.
3. The same sentence: "an envelope that cannot be parsed".
   - Unclear: whether it means output that is not JSON, or also JSON that lacks fields the adapter reads.
   - Does not block: AC4 asserts only output that is not JSON, which both readings call unparsable; AC3 follows "null when the runtime reported none" for absent metric fields. The proposal is under Open question 8.

Not this task's, recorded so it is not lost: the retry sentences ("If a reply fails Pydantic validation, the call is retried once"; "A reply rejected by Pydantic or by the plan checks is retried once") do not name a reply with no structured result (audit F-6). It concerns outline item 9 and is settled before that task is planned.

Readings, not gaps:
- "It is not retried" is met by the adapter starting one process per call; the retry of a rejected reply is the use case's (ADR-005).
- "Without reading its value" is met by building the child's environment from the names; the value is never compared, logged or stored.
- A non-zero exit is a failed process even when standard output holds an envelope; its tokens and cost are not returned.
- An envelope that reports an error but came with exit status 0 parses, so it is a reply; if it has no structured result it is a rejected reply.
- "The default model" is no `--model` argument.

## Open questions
Question 1 asks the human to confirm a scoping judgement. The others are not spec decisions; each has a proposal.

1. **The JSON `null` gap and this task.** Proposed: it does not block (Spec gaps item 1). `LLMReply.structured` is `object | None`; an absent key gives `None`, a JSON `null` also arrives as `None`, and no criterion asserts the `null` case. Alternative: settle it by `/spec-change` first; or carry a separate flag on the reply that says whether the key was present.
2. **The reply type.** The G18 row (2026-10-08) gives `LLMReply` a `text` field; the G19 row of the same day reads the structured result from the envelope, and `parse_reply` takes it. Proposed: `structured: object | None` and no `text`; `model`, `tokens_in`, `tokens_out` and `cost_usd` nullable (SC-27, SC-48); `duration_s` a float. Alternative: keep `text` as well.
3. **Where the types live.** Proposed: `LLMReply` in a new `domain/llm.py`, as `PlanRef` is in `domain/plans.py`; `LLMError` in `ports/llm_provider.py` beside the Protocol, as `EventConflictError` is. Alternative: both in the port module.
4. **Capturing the fixture.** It needs one real `claude -p` call on the subscription, outside pytest. Proposed: the session makes it once in plan step 3 with the human's leave, and saves the output unedited. Alternative: the human runs the command and commits the file.
5. **Which envelope fields.** Proposed, to be confirmed on the fixture: the duration is the envelope's wall-clock figure in milliseconds divided by 1000, not its API-only figure; the model name is the key of the envelope's per-model usage when there is exactly one, otherwise the one with the most output tokens. Alternative for the model: `None` when more than one model is reported.
6. **The text of `LLMError`.** It becomes `AgentRunFinished.error` and, by its first line, the `planner call failed: <error>` line (SC-50). Proposed: a non-zero exit gives standard error stripped, or `claude exited with status N` when that is empty; unparsable output gives `claude output is not a JSON envelope`; a timeout gives `timed out after 300 s` (with the adapter's limit). AC4 asserts only that the text is not empty. Alternative: fix the three texts in criteria.
7. **A `claude` that cannot be started.** Proposed: `LLMError` with `timeout` false and the text `claude not found`, as a decisions row with no criterion, plus a Later line for the spec. Alternative: let the `OSError` propagate until the spec names the case.
8. **"Cannot be parsed".** Proposed: standard output that is not a JSON object. A JSON object with metric fields absent parses, and those values are `None`; an absent duration takes the measured one. Alternative: an envelope without a duration is a failed process.
9. **How the process is started.** Proposed: the prompt on standard input, because the planner prompt holds the `git ls-files` list and may be long; constructor parameters `executable` and `timeout_s` so tests can point at the stand-in and use a short limit; the working directory is inherited. Note that Claude Code then loads the target repo's `CLAUDE.md` into the planner call, which the spec's list of what the planner receives does not mention. Alternative: the prompt as an argument; a fixed empty working directory.
10. **Logging.** This is the first code to use structlog. Proposed: the adapter calls `structlog.get_logger()` and logs one warning with an event name and no value; configuring structlog for JSON lines on standard error is left to the `plan` command (item 10); a decisions row, not an ADR. Alternative: configure it now in `cli.py`; or the human wants an ADR for the logging convention.
11. **Size.** Proposed: one task of about 455 lines with tests and six criteria; the port without its adapter is about 60 lines and tests nothing. Alternative: TASK-029 takes the port and `LLMReply` (AC1), TASK-030 the adapter (AC2 to AC6).

## Answers
The human answered the Open questions on 2026-10-11: "with the adviser", that is the advisor's recommendation for each. Rows are in `docs/decisions.md`.

1. The JSON `null` gap does not block. An absent `structured_output` key and a JSON `null` both give `structured` `None`; no criterion asserts the `null` case.
2. `LLMReply` has `structured: object | None` and no `text`; the row replaces the G18 row's field list.
3. `LLMReply` in `domain/llm.py`; `LLMError` in `ports/llm_provider.py`.
4. The session captured the fixture (see "Fixture").
5. Duration is `duration_ms` / 1000. The model is the key of `modelUsage` when there is one; with several, the one with the most `outputTokens`, the first in the envelope's order on a tie; `None` when `modelUsage` is absent or empty. Tokens and cost come from the envelope's totals (`usage`, `total_cost_usd`), not from one model's block.
6. Texts as proposed, the timeout's number written without a trailing `.0` for a whole number (`timed out after 300 s`). AC4 asserts only that the text is not empty.
7. A `claude` that cannot be started raises `LLMError` with `timeout` false and the text `claude could not be started: <the OS error's text>`. No criterion.
8. "Cannot be parsed" is standard output that is not a JSON object, or a JSON object the adapter's envelope model rejects (a wrong-typed field). Absent metric fields give `None`; an absent `duration_ms` takes the measured duration.
9. The prompt goes on standard input; constructor parameters `executable` and `timeout_s`; the process runs in a new empty temporary directory, not the inherited one (the advisor's recommendation, against the planner's proposal). AC2 gained a bullet for it. A Later line asks the spec to state the planner call's working directory.
10. The adapter logs one warning per call through `structlog.get_logger()`; structlog is configured in outline item 10. A decisions row, no ADR.
11. One task.

## Fixture
- Claude Code 2.1.287 (ADR-005 names 2.1.286).
- Captured on 2026-10-11 from a new empty directory, with `ANTHROPIC_API_KEY` not set and a two-line prompt on standard input: `claude -p --output-format json --json-schema '<schema with colour: string, letters: integer>' --tools ""`. Exit status 0, nothing on standard error. Saved unedited; it holds a session id and a uuid and nothing personal.
- Confirmed: `--json-schema` exists, `--tools ""` disables every tool, and `-p` reads the prompt from standard input.
- Fields the adapter reads: `structured_output`; the keys of `modelUsage` with each one's `outputTokens`; `usage.input_tokens`, `usage.cache_creation_input_tokens` and `usage.cache_read_input_tokens` (summed into `tokens_in`); `usage.output_tokens`; `total_cost_usd`; `duration_ms`.
- The fixture's values: `structured_output` `{"colour": "red", "letters": 3}`, model `claude-opus-5-5`, input counts 2 + 4379 + 0 = 4381, output tokens 74, cost 0.036520000000000004, `duration_ms` 2236 (2.236 s).
- Not checked: what `claude` prints when it exits non-zero (Answer 6's assumption that standard error explains it).

## Outcome
All of it is in the working tree; 913 tests pass, ruff, pyright and check_docs are clean.

Built:
- `src/openfactory/domain/llm.py`: frozen `LLMReply`.
- `src/openfactory/ports/llm_provider.py`: Protocol `LLMProvider` and `LLMError`.
- `src/openfactory/adapters/claude_code_llm.py`: `ClaudeCodeLLM`.
- `tests/fixtures/claude_envelope.json` (Claude Code 2.1.287), `tests/unit/test_llm_provider_port.py` (4 tests), `tests/integration/test_claude_code_llm.py` (14 tests).
- Living docs: `docs/architecture.md`, `docs/progress.md`; the seven rows in `docs/decisions.md`. `CHANGELOG.md` and `README.md` unchanged (no command or output added).

Deviations from the plan:
- The working directory is a new empty temporary directory per call (the advisor's recommendation), not the inherited one.
- A `claude` that cannot be started, and an envelope the private model rejects, also raise `LLMError`.
- The fixture was captured before the tests were written.

Test edit (approved by the human on 2026-10-11): in `test_ac4_timeout_raises_llm_error_with_timeout_true` the constants changed (`timeout_s` 0.5 to 2, `sleep` 3 to 10, bound `duration_s >= 0.5` to `>= 2`), because the first start of a freshly written script takes 0.19 to 0.59 s on macOS and the test failed about 1 run in 5. The four assertions are unchanged.

After the review (verdict: approve), the reviewer's four non-blocking notes were applied at the human's request: `tokens_in` is `None` when `usage` holds none of the three input counts (it was 0), and `"modelUsage": null` is read as no model and no longer fails the envelope; no test was added for either shape. The Later lines were adjusted as listed below.

Follow-ups (Later lines in `docs/progress.md`):
- Spec wording items: a `claude` that cannot be started, "cannot be parsed", the planner call's working directory, and which model name is recorded when several are reported. JSON `null` as a structured result stays in the "Spec gap (before outline item 9 is planned)" line.
- Spec gap before outline item 9: an envelope that reports an error with exit status 0 (`is_error`, `subtype` not read) is a rejected reply and is retried (reviewer).
- What `claude` prints on a non-zero exit in JSON output mode was not checked; the `LLMError` text may miss an explanation on standard output (advisor).
