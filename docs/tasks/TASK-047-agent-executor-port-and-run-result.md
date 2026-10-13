# TASK-047: `AgentExecutor` port, `RunResult` and `ContextPack`

- Milestone: M3
- Status: done
- Tests: acceptance
- ADR: ADR-014 (accepted). "Ports and adapters (SC-63, SC-68)": "`AgentExecutor`, adapter `claude_code_executor`: `run(contract, context, workdir, output_dir) -> RunResult`." ADR-005 (accepted) puts agent runs "behind the `AgentExecutor` port"; ADR-006 covers the layers. No adapter, dependency, event type, payload or storage change in this task. Module names and the model's config are rows in `docs/decisions.md` (Open questions 2 and 3).
- Spec impact: wording. One item, audit F-5; it does not stop this task (see "Spec gaps").
- Spec sections (spec v1.12, SC-63, SC-64, SC-68): "Execution" › "Adapter interface", "The context pack" (first sentence), "Per-task sequence" (step 3); "Domain model and storage" (the M3 paragraph after "Ids"; "Event payloads", the `AgentRunFinished` block); "Tech stack and repo layout" (the layout block)

## Outline item
M3 outline item 1, first of three pieces (Open question 1). The adapter `claude_code_executor` is left in item 1; items 2 to 6 are left.

## Objective
Give the run use case the `AgentExecutor` port with its result model `RunResult` and the type `ContextPack`, as the spec's "Adapter interface" block states them, so the context pack and the run use case can be built and tested against the port before the Claude Code adapter exists.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings and to SC-63, SC-64 and SC-68.

## Scope
In (names and modules per Open questions 2 and 3):
- `src/openfactory/domain/agent_run.py` (new):
  - `ContextPack = str`.
  - `RunResult`, frozen and `extra="forbid"`, with the eight fields of the spec's block in its order, all required: `exit` (`RunExit` from `domain/payloads.py`, the same three values), `model: str | None`, `tokens_in: int | None`, `tokens_out: int | None`, `cost_usd: float | None`, `duration_s: float`, `error: str | None`, `summary: str`.
- `src/openfactory/ports/agent_executor.py` (new): Protocol `AgentExecutor` with one method, `run(self, contract: TaskContract, context: ContextPack, workdir: Path, output_dir: Path) -> RunResult`.
  - Its docstring says a failed process is returned as a `RunResult` with `exit` `error` or `timeout`, not raised, and that `output_dir` is the run's directory.
  - It states the rule of Open question 4, answer (b): the caller passes `output_dir` relative to the repo (`.openfactory/runs/<run id>`), and the adapter resolves a relative `output_dir` against its own repo and creates the directory when missing.
- Tests: a new unit file for the port and the model, and one added conformance test that reads the spec's class block.

Out (not this task):
- The adapter `claude_code_executor` and everything it does: the command line, the six tools, the time limit, `ANTHROPIC_API_KEY`, reading an envelope, `summary` from the final message, the failed-process cases, an envelope that reports an error, `transcript.json`, a new fixture (the rest of outline item 1).
- Any code that builds `output_dir`, creates the directory or resolves it (audit F-5 is answered under Open question 4; the use case and the adapter that follow it are later tasks). No test of the docstring's text.
- Building the context pack and its hash (outline item 2); every caller of the port (outline item 3); wiring in `cli.py` (outline item 5).
- An exception type on the port. The spec's result carries `exit` and `error`.
- Any check across fields of `RunResult` (for example `summary` empty when `exit` is not `ok`, or `error` set). That is the adapter's behaviour, and `AgentRunFinishedPayload` checks no such link either.
- Any change to `domain/payloads.py`, `domain/llm.py`, existing ports, adapters and tests.

## Acceptance criteria
"Adapter interface" and "The context pack" are under "Execution"; "Event payloads" is under "Domain model and storage". The criteria are written for the proposals under Open questions.

- [x] AC1 ("Adapter interface": "`class AgentExecutor(Protocol): def run(self, contract: TaskContract, context: ContextPack, workdir: Path, output_dir: Path) -> RunResult`"; "Tech stack and repo layout": "`ports/ # interfaces: ..., AgentExecutor, ...`" and "the domain never imports infrastructure"; SC-63, SC-68):
  - `AgentExecutor` is a Protocol whose public methods are exactly `run`.
  - The parameters of `run` after `self` are `contract`, `context`, `workdir`, `output_dir`, in that order, annotated `TaskContract`, `ContextPack`, `Path`, `Path`, and it returns `RunResult` (read with `inspect.signature` and `typing.get_type_hints`).
  - `ports/agent_executor.py` imports nothing from `openfactory.adapters` or `openfactory.app`; `domain/agent_run.py` imports nothing from `openfactory.ports`, `openfactory.adapters` or `openfactory.app` (checked by parsing imports with `ast`, as in `tests/unit/test_llm_provider_port.py`).
- [x] AC2 ("Adapter interface": the `class RunResult(BaseModel)` block; "The context pack": "one prompt text (`ContextPack` is a `str`)"; SC-63, SC-64):
  - A conformance test reads the `RunResult` class block from `docs/spec/phase1-spec.md`. The names of `RunResult.model_fields`, in order, equal the block's eight field names.
  - Every field is required. The values `exit` accepts are exactly `ok`, `error` and `timeout`. `model`, `tokens_in`, `tokens_out`, `cost_usd` and `error` accept `None`; `duration_s` and `summary` do not.
  - `ContextPack` is `str`.
- [x] AC3 ("Adapter interface": "The other fields of `RunResult` become the fields of `AgentRunFinished`"; "Event payloads": the `AgentRunFinished` block; "Per-task sequence" step 3):
  - The field names of `RunResult` without `summary` equal the field names of `AgentRunFinishedPayload` without `run_id`.
  - For a result with `exit` `ok` and every value set, and for one with `exit` `timeout`, an `error` text, null `model`, tokens and cost, and `summary` `""`: `AgentRunFinishedPayload(run_id="run_0002", **result.model_dump(exclude={"summary"}))` validates and holds the same seven values.

## Architecture rules that apply
- `ports` holds Protocols only and imports from `openfactory.domain` only; `RunResult` and `ContextPack` are in `domain`, as `LLMReply` is in `domain/llm.py`.
- `domain/agent_run.py` is pure: no I/O, no import from `ports`, `adapters` or `app`.
- No adapter is added, so there is no `TYPE_CHECKING` assertion in this task.
- No event is recorded and no projection is read or written. `cli.py` and `app/` are not changed.
- No new dependency. OpenFactory's own tests carry no `req` markers.
- No hardening beyond what the spec asks.

## Plan
1. Create branch `task/TASK-047-agent-executor-port-and-run-result` from an up-to-date main and commit this record.
2. Get the human's answers to Open questions 1 to 4; record them here and as rows in `docs/decisions.md`. If an answer differs from a proposal, adjust the criteria before any test is written.
3. Write failing tests:
   - `tests/unit/test_agent_executor_port.py` (new) for AC1, AC3 and the value bullets of AC2;
   - one new test in `tests/unit/test_spec_conformance.py` for the field names of AC2, using its `code_block` helper. No existing test is changed.
4. Add `domain/agent_run.py`.
5. Add `ports/agent_executor.py` with the Protocol and its docstring.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
7. Update the living docs and the Outcome. Commit `feat(ports): add the AgentExecutor port and RunResult` with trailers `Task: TASK-047` and `Milestone: M3`.

## Files expected to change
- `src/openfactory/domain/agent_run.py` (new, about 30 lines)
- `src/openfactory/ports/agent_executor.py` (new, about 30 lines)
- `tests/unit/test_agent_executor_port.py` (new, about 110 lines)
- `tests/unit/test_spec_conformance.py` (one test added, about 15 lines)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-047-agent-executor-port-and-run-result.md` (this record; Outcome at close)

Not expected to change: `cli.py`, everything under `app/` and `adapters/`, the other modules under `domain/` and `ports/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, every other existing test file.

Expected size: about 185 lines with tests, about 60 of them in `src/`.

## Living docs to update
- `docs/architecture.md`:
  - new sections "Agent run result" (`domain/agent_run.py`) and "AgentExecutor port";
  - "Data flow": the port exists for the run use case, has no adapter yet and nothing calls it.
- `docs/progress.md`:
  - Current and Done.
  - Outline item 1 reworded to the two adapter pieces that are left (per the answer to Open question 1).
  - The F-5 Later line reworded to "before the `claude_code_executor` task that writes `transcript.json` is planned".
- `docs/decisions.md`: rows for the answered open questions.
- `CHANGELOG.md` and `README.md`: no change (nothing a user sees).

## New dependencies
None.

## Spec gaps
Spec impact is "wording": one item, which does not stop the task.

1. "Execution" › "Adapter interface" ("`output_dir` is the run's directory, `.openfactory/runs/<run id>/`. The adapter writes the runtime's result envelope to `<output_dir>/transcript.json`"), with "Gates and remediation" ("written through the `RunFiles` port") and "Domain model and storage", the M3 paragraph after "Ids" ("`RunFiles` ... writes a file of a run under `.openfactory/runs/<run id>/`"). This is audit F-5 of `docs/spec-audits/2026-10-13-proposal-v1.12.md`.
   - Missing: there are two writers under one directory, and no text says who creates it, whether `output_dir` is passed relative to the repo or absolute, or which component hands it to the use case.
   - Does not block this task: the signature is given word for word (`output_dir: Path`), the task writes no file and creates no directory, and AC1 to AC3 trace to text that is complete. The port's docstring repeats the spec's sentence and adds nothing about creation. (Superseded by the answer to Open question 4 (b): the docstring states the rule.)
   - Not assumed: nothing here decides who creates the directory. (Superseded: Open question 4 (b) decides it.)
   - Blocks later: the adapter piece that writes `transcript.json`. A criterion "the adapter creates `output_dir` when missing" or "resolves a relative `output_dir` against its repo" has no spec text to trace to. See Open question 4. (Superseded: answer (b) of 2026-10-14, a `docs/decisions.md` row, is what such a criterion traces to.)

Readings, not gaps (each follows from the text as written):
- The spec prints `RunResult` beside the Protocol under "Adapter interface". "Tech stack and repo layout" has `ports/ # interfaces` and `domain/ # pure models`, and `CLAUDE.md` says ports hold Protocols only, so the model goes in `domain` (the `LLMReply` precedent).
- A failed process is returned, not raised: `RunResult.exit` has `error` and `timeout`, the model has `error`, and "`summary` is ... empty when `exit` is `error` or `timeout`" describes a returned value. This differs from `LLMProvider`, which raises `LLMError`.
- "The other fields of `RunResult` become the fields of `AgentRunFinished`": `run_id` is the use case's, not the result's.
- The block's `Literal["ok", "error", "timeout"]` is the existing `RunExit`.

## Later lines in `docs/progress.md`: taken or left
- **"Spec wording: ... `output_dir` ... two writers ... (audit F-5) ... to be decided before the `AgentExecutor` task (outline item 1) is planned".** Not taken. It does not block this task (Spec gaps, item 1) and is reworded at close. It must be answered before the adapter piece that writes `transcript.json` is planned (Open question 4). (Superseded: answered (b) on 2026-10-14; the Later line now gives the answer.)
- **"The adapter does not read the envelope's `is_error` or `subtype` ..." (TASK-029, reviewer; TASK-031).** Does not block: this task reads no envelope. It also leaves the line as it is, since that line is about `ClaudeCodeLLM`, where the decision of 2026-10-11 stands for planner calls. For the executor, SC-71 already makes "an envelope that reports an error" a failed process. What that piece still needs:
  - a `docs/decisions.md` row naming the envelope field that says so (the fixture holds `is_error`, `subtype` and `api_error_status`; ADR-005 pins field names by fixture, not by the spec);
  - a note that no error envelope has been captured, so the test envelope for that case is edited by hand from a captured one.
- **"What `claude` prints when it exits non-zero in JSON output mode was not checked ..." (TASK-029, advisor).** Does not block this task or the adapter pieces. The spec fixes that `error` is set, not its text. The adapter piece carries the same unchecked assumption (standard error explains the failure), and the line then names both adapters.
- **Every other Later line:** left.
- **To add at close:**
  - "`RunResult` checks no link between `exit`, `error` and `summary`; the adapter keeps `summary` empty and `error` set for a failed process (TASK-047, planner)".
  - Carried to the adapter pieces: "`transcript.json` when the process gave no envelope (a timeout, a `claude` that cannot be started, output that is not JSON): 'Adapter interface' says the adapter writes 'the runtime's result envelope' and does not say what is written when there is none (TASK-047, planner)".

## Open questions
Answered by the human on 2026-10-14: the proposal for each of 1 to 3, and (b) for 4, decided now. Following from 4 (b): `transcript.json` for a successful run moves into the second piece of the split, and the port's docstring states the directory rule.

1. **The split of outline item 1.**
   - Proposed: three tasks. This one; then `claude_code_executor` for a run that succeeds (command line fixed against a newly captured agent-run envelope, environment, envelope to `RunResult`); then the failed-process cases, the envelope that reports an error and `transcript.json`.
   - Alternative: two tasks, this one and one adapter task of about 450 to 550 lines and seven criteria, which breaks the six-criteria rule.
   - Note for the second piece: capturing the fixture needs one real `claude -p` call with tools in a scratch repository, with the human's leave, as in TASK-029.
2. **Where the types live.**
   - Proposed: `RunResult` and `ContextPack` in a new `domain/agent_run.py`; the Protocol in `ports/agent_executor.py`.
   - Alternative (a): both types in the port module, as the spec's block prints them. This conflicts with "ports: Protocol interfaces only".
   - Alternative (b): `ContextPack` in the module outline item 2 creates for the context pack. The port would then import it from there, which must be in `domain`, not `app`.
3. **The model's config.** The spec's block shows a bare `BaseModel`.
   - Proposed: frozen and `extra="forbid"`, as `LLMReply` and the payload models; all eight fields required; `exit` typed as the existing `RunExit`; no check across fields; no exception type on the port.
   - Alternative: a validator that rejects a non-empty `summary` or a null `error` when `exit` is not `ok`.
4. **Audit F-5, for the later adapter piece; not needed to start this task.** The answer is the human's.
   - (a) As the audit and the advisor proposed: `RunFiles` gives the directory of a run, creating it, and the use case passes it as `output_dir`. This needs a `/spec-change` to the M3 paragraph and "Adapter interface", an amendment of ADR-014's `RunFiles` bullet, and a second method on `RunFiles`.
   - (b) The use case builds `Path(".openfactory/runs") / run_id` ("the path follows from the run id"), and the executor adapter creates the directory when missing and resolves a relative `output_dir` against its own repo. This is the rule already decided for the worktree path (F-7, 2026-10-13). It is a `docs/decisions.md` row plus a "Spec wording" Later line, with no spec change now.
   - Either way the answer must exist before the piece that writes `transcript.json` is planned. If it is given now, the second piece can take `transcript.json` for a successful run.

## Outcome
Built:
- `src/openfactory/domain/agent_run.py`: `ContextPack = str` and `RunResult` (frozen, `extra="forbid"`, the spec's eight fields in order, all required, `exit` typed `RunExit`, no cross-field check).
- `src/openfactory/ports/agent_executor.py`: Protocol `AgentExecutor` with `run(contract, context, workdir, output_dir) -> RunResult`. Its docstring says a failed process is returned, not raised, and that `output_dir` is passed relative to the repo and the adapter resolves it against its own repo and creates the directory when missing.
- Tests: new `tests/unit/test_agent_executor_port.py` (20 tests) and one test added to `tests/unit/test_spec_conformance.py`.
- Checks: 1170 tests passed; ruff, pyright and `scripts/check_docs.py` clean.
- No test from the test-writer was edited.
- No adapter; nothing calls the port; no `cli.py` wiring.

Answers of the human, 2026-10-14 (rows in `docs/decisions.md`):
1. Outline item 1 is three tasks: this one; `claude_code_executor` for a run that succeeds (command line fixed against a newly captured agent-run envelope, environment, envelope to `RunResult`, `transcript.json` for a successful run); then the failed-process cases and the envelope that reports an error, with what `transcript.json` holds when there is no envelope.
2. `RunResult` and `ContextPack` in `domain/agent_run.py`; the Protocol in `ports/agent_executor.py`.
3. Frozen, `extra="forbid"`, all fields required, `exit` as `RunExit`, no cross-field validator, no exception type on the port.
4. Audit F-5, answer (b): the use case builds `Path(".openfactory/runs") / run_id` and passes it as `output_dir`; the executor adapter creates the directory when missing and resolves a relative `output_dir` against its own repo (as for the F-7 worktree path). No spec change now.
