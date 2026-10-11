# TASK-032: Plan use case, the planner call

- Milestone: M2
- Status: done
- Tests: acceptance
- ADR: none. No new port, adapter, dependency, event type, payload or storage change. ADR-005 (accepted, with its amendment of 2026-10-11) covers the call, the single retry "for a rejected reply only" and "The retry is one function in the app layer"; ADR-001 covers recording through `EventRecorder`; ADR-012 covers `Plans` and `Runs` and tests with in-memory fakes; ADR-007 covers the payload models. ADR-013 (proposed) is not needed here: this function takes the tracked files as an argument and calls no `GitProvider`. The module, the names and the result type are rows in `docs/decisions.md` (Open questions 1 to 3).
- Spec impact: wording. Two items, neither blocks (see "Spec gaps").
- Spec sections (spec v1.11): "Tech stack and repo layout" (the "Planner and diff LLM calls" row; the paragraph that starts "All model calls go through Claude Code"); "Domain model and storage" ("Streams and actors": the paragraph that starts "`plan` records `AgentRunStarted` before each planner call"; "Event payloads": the `PlanCreated`, `AgentRunStarted` and `AgentRunFinished` blocks; "Ids"); "Spec input format" ("Policies": "its own hash is recorded in `PlanCreated`"); "Task contract" (the four bullets after "For every task, the orchestrator:"; "Planning"; "Plan checks"); "Metrics" ("A retried call is a second run"); "CLI commands" ("Output": the source of `<error>`)

## Outline item
M2 outline item 9a ("Plan use case, the planner call"). Item 9b (the entry, the refusals, the warning, `GitError`) and item 10 (the `plan` command) are left.

## Objective
Add the app-layer function that, given the approved spec version and its spec set, the policy, the tracked files and the ports, makes the planner call with its single retry, records the run events and `PlanCreated` with `causation_id` chained, and returns the created plan, the second reply's rejections or the failed call's text.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings.

## Scope
In (names per Open questions 1 and 2):
- `src/openfactory/app/plan.py` (new):
  - `run_planner(spec_version: str, spec: SpecSet, policy: Policy, tracked_files: Sequence[str], *, llm: LLMProvider, runs: Runs, plans: Plans, recorder: EventRecorder) -> PlannerResult`.
  - `PlannerOutcome(StrEnum)`: `created`, `rejected`, `failed`.
  - `PlannerResult` (frozen, `extra="forbid"`): `outcome`, `plan_id: str | None`, `tasks: list[TaskContract]` (the stored contracts, sorted by `task_id`), `rejections: list[PlanRejection]` (the second reply's), `error: str | None` (the whole text of a failed call).
- One attempt, made at most twice:
  - `Runs.next_id`, then `AgentRunStarted` with `context_hash(prompt)`.
  - `LLMProvider.complete(prompt, PlannerReply.model_json_schema())`.
  - `parse_reply`, then `check_plan` when `tasks` is not `None`.
  - `AgentRunFinished`.
- The second attempt's prompt is `build_planner_prompt(..., rejections=<the first reply's>)`.
- On an accepted reply: `Plans.next_id`, `complete_contract` per task, `policy_hash`, then `PlanCreated`.
- An `LLMError` ends the function after its `AgentRunFinished`; `str(error)` goes into `error` unchanged (audit Q4 of `docs/spec-audits/2026-10-11-proposal-v1.11.md`).
- Unit tests with in-memory fakes. No database, no git, no `claude`.

Out (not this task):
- The three refusals, the `spec files differ` warning, `GitProvider` and `GitError`, reading `SpecVersions` and the policy file, and the result type of the command as a whole (9b).
- `cli.py`, the task lines, the rejection lines on standard output, taking the first line of `error`, exit codes and structlog configuration (item 10).
- `approve plan`, the `deleted-requirement` rule and the M2 close test (items 11 to 13).
- Task-id uniqueness against the `tasks` projection (Later line, before M6).
- An envelope that reports an error with exit status 0: it stays a rejected reply (decision of 2026-10-11).
- Hardening: an exception from the LLM that is not `LLMError`, or a recorder that raises between the two run events, propagates and leaves a started run with no finish (Open question 5).

## Acceptance criteria
"Streams and actors", "Event payloads" and "Ids" are under "Domain model and storage"; "Planning" and "Plan checks" are under "Task contract"; "Policies" is under "Spec input format"; "Output" is under "CLI commands".

Fixtures:
- "The sample set", "the sample policy" (`forbidden_paths: ["secrets/**"]`) and "the sample files" are those of TASK-031; the version is `sv_01`.
- "A good reply" is an `LLMReply` with a model name, tokens, cost and duration the test chooses. Its structured result holds `AUTH-002` (depends on `AUTH-001`, with one `forbidden_paths` entry of its own) and then `AUTH-001` (no `depends_on` or `forbidden_paths` key), in that order. Together they cover `REQ-AUTH-001` and both criteria.
- "A reply the checks reject" loads into `PlannerReply` and has at least two `check_plan` rejections.
- The fake recorder keeps the events it is given, in order.
- The fake `Runs` returns the id after the number of `AgentRunStarted` events recorded so far, counted from a start the test chooses that is not 1.
- The fake `Plans.next_id` returns an id the test chooses that is not `plan_01`.
- The fake LLM returns scripted replies or raises scripted `LLMError`s, and keeps each prompt and schema it received.
- "Chained" means each recorded event's `causation_id` is the `event_id` of the event recorded just before it, and the first has none.

- [x] AC1 ("Streams and actors": "`plan` records `AgentRunStarted` before each planner call and `AgentRunFinished` after it; a retried call is a second pair; then `PlanCreated`. For these events `causation_id` is the `event_id` of the event recorded just before it in the same command, and the first has none"; "Event payloads": the `AgentRunStarted` and `AgentRunFinished` blocks; "Planning": "The planner receives one prompt" and "The planner replies with `{"tasks": [PlannedTask, ...]}`"; "Tech stack and repo layout": "`claude -p --output-format json --json-schema`) behind `LLMProvider`, validated by Pydantic"). With a good reply:
  - The LLM is called once, with `build_planner_prompt(the sample set, the sample policy, the sample files)` and `PlannerReply.model_json_schema()`.
  - Exactly three events are recorded, `AgentRunStarted`, `AgentRunFinished`, `PlanCreated`, chained, all with actor `orchestrator`.
  - Both run events are on stream `run:<the id from Runs>`.
  - `AgentRunStarted` holds that `run_id`, `task_id` null, `role` `planner`, `runtime` `claude-code` and `context_hash` equal to `context_hash` of the prompt the LLM received.
  - `AgentRunFinished` holds `exit` `ok`, the reply's model, tokens, cost and duration, and `error` null.
  - The result is `created` with the plan id.
  - `openfactory.app.plan` imports nothing from `openfactory.adapters` or `openfactory.cli` (checked by parsing its imports with `ast`).
- [x] AC2 ("Event payloads": "`tasks: [ TaskContract ]` # complete contracts, as the orchestrator stored them, sorted by task_id as strings; the lists inside a contract keep their order" and "the use case writes every field of them explicitly"; "Task contract": the four bullets after "For every task, the orchestrator:"; "Policies": "its own hash is recorded in `PlanCreated`"; "Ids": "chosen by the use case from the projections when a command runs"). With a good reply, the `PlanCreated` event:
  - Is on stream `plan:<the id from Plans.next_id>`.
  - Holds that `plan_id`, `spec_version` `sv_01`, `policy_hash` equal to `policy_hash(the sample policy)`, and the `run_id` of the run events.
  - Has `tasks` equal to the JSON dump of `complete_contract(task, the sample policy)` for each task, with `AUTH-001` before `AUTH-002` though the reply gave them the other way round.
  - Has in each stored task every `TaskContract` field as a key, `depends_on` and `forbidden_paths` included for the task whose reply omitted them.
  - Has in `AUTH-002` `forbidden_paths` equal to the four baseline paths, then `secrets/**`, then the planner's entry.
  - Has a payload that validates as `PlanCreatedPayload`, and the result's `tasks` are the same contracts in the same order.
- [x] AC3 ("Plan checks": "A reply rejected by Pydantic or by the plan checks is retried once with the rejections in the prompt" and "`AgentRunFinished` is recorded after the checks: a rejected reply has `exit: ok` and `error` set to its rejection lines, as `rule  subject  message` in the sorted order `plan` prints them, joined by newlines; an accepted one has `error: null`"; "Metrics": "A retried call is a second run, so a rejected call keeps its cost"; "Event payloads": "`run_id` # the planner run that produced it"). With a reply the checks reject, then a good reply:
  - The LLM is called twice, and five events are recorded: `AgentRunStarted`, `AgentRunFinished`, `AgentRunStarted`, `AgentRunFinished`, `PlanCreated`, chained.
  - The first `AgentRunFinished` has `exit` `ok`, the first reply's model, tokens, cost and duration, and `error` equal to `"\n".join(rejection_lines(check_plan(<the first reply's tasks>, the sample set)))`.
  - The second prompt equals `build_planner_prompt(..., rejections=<those rejections>)`.
  - The second pair is on the stream of the next run id, and its `context_hash` is that of the second prompt and differs from the first.
  - The second `AgentRunFinished` has `error` null, and `PlanCreated.run_id` is the second run's id.
- [x] AC4 ("Plan checks": "A reply whose structured result is missing is one `schema` rejection with subject `reply` and the message `no structured result`", "A `schema` rejection has the field path in its message, and when there is one the other checks are not run" and "whichever kind of rejection the first reply had"; "Tech stack and repo layout": "An envelope that parses but whose structured result is missing or fails Pydantic validation is a rejected reply"):
  - With a first reply whose `structured` is `None`, then a good reply: the first `AgentRunFinished` has `exit` `ok` and `error` exactly `schema  reply  no structured result`, a second call is made and the result is `created`.
  - With a first reply in which one task carries `required_gates`, then a good reply: every line of the first `AgentRunFinished.error` starts with `schema  `, and the result is `created`.
- [x] AC5 ("Plan checks": "one `plan` makes at most two planner calls" and "If the second reply is also rejected, `plan` exits 1 and no `PlanCreated` is recorded"; "Output": "When the second reply is rejected it prints that reply's rejections"). With a reply the checks reject, then a reply whose `structured` is `None`:
  - The LLM is called exactly twice.
  - Four events are recorded, chained, and none is `PlanCreated`.
  - The second `AgentRunFinished` has `exit` `ok` and `error` `schema  reply  no structured result`.
  - The result is `rejected`, its `rejections` are the second reply's one rejection and none of the first's, and `plan_id` is `None`.
- [x] AC6 ("Tech stack and repo layout": "A non-zero exit, an envelope that cannot be parsed, or a timeout is a failed process: it is not retried, the run is recorded with `exit: error` or `timeout` and `error` set"; "Event payloads": "`duration_s` ... measured by the adapter when the process failed or timed out" and "null when the runtime reported none"; "Output": "for a planner call that text is `AgentRunFinished.error`"):
  - The LLM raises `LLMError("first line\nsecond line", duration_s=2.5, timeout=False)`:
    - The LLM is called once.
    - Two events are recorded, chained.
    - `AgentRunFinished` has `exit` `error`, `error` equal to that two-line text unchanged, `duration_s` 2.5, and `model`, `tokens_in`, `tokens_out` and `cost_usd` null.
    - The result is `failed` with `error` equal to the same text.
  - With `timeout=True`, `exit` is `timeout`.
  - With a reply the checks reject, then an `LLMError`:
    - Four events are recorded, chained, and the last has `exit` `error`.
    - There is no third call and no `PlanCreated`.
    - The result is `failed`.

## Architecture rules that apply
- `src/openfactory/app` depends on `domain` and `ports` only; `plan.py` may import `app/planner_prompt.py`.
- All state changes go through the events table: events are recorded only through `EventRecorder.record`, built through the payload models with `Event.new`, as `app/validate.py` does.
- All LLM output is validated by a Pydantic model before use: `parse_reply` runs before `check_plan` and before any contract is built.
- All LLM calls go through `claude -p`: the function sees only the `LLMProvider` port.
- Use cases return data and print nothing (decisions row of 2026-10-10, TASK-018).
- Tests from the test-writer are fixed. No existing test is changed.
- No hardening beyond the spec's rules.

## Plan
1. Create branch `task/TASK-032-plan-use-case-planner-call` from an up-to-date main.
2. Get the human's answers to the Open questions; record them here and as rows in `docs/decisions.md`.
3. Write failing tests in `tests/unit/test_plan_use_case.py` (new) for AC1 to AC6, with the four fakes and one helper for a good reply.
4. Add `app/plan.py`:
   - A private helper builds an `orchestrator` event from a stream, a type, a payload model and the previous event's id.
   - A private attempt function takes the prompt and the previous event id. It reads `Runs.next_id`, records `AgentRunStarted` and calls the LLM.
     - On `LLMError` it records `AgentRunFinished` (`exit` from `error.timeout`, `error` `str(error)`, metrics null, `duration_s` from the error) and reports the failure.
     - Otherwise it runs `parse_reply`, then `check_plan` when tasks loaded, records `AgentRunFinished` (`exit: ok`, `error` the joined `rejection_lines` or null), and returns the tasks or the rejections with the run id and the last event id.
   - `run_planner` makes the first attempt, and a second with the retry prompt when the first was rejected.
   - On acceptance it reads `Plans.next_id`, completes and sorts the contracts, records `PlanCreated` and returns `created`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until green.
6. Update the living docs and the Outcome. Commit `feat(app): add the planner call of the plan use case` with trailers `Task: TASK-032` and `Milestone: M2`.

## Files expected to change
- `src/openfactory/app/plan.py` (new, about 130 lines)
- `tests/unit/test_plan_use_case.py` (new, about 330 lines)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-032-plan-use-case-planner-call.md`

Over the 300-line aim with tests, within six criteria (Open question 6).

Not expected to change: `cli.py`, the other modules under `app/`, everything under `domain/`, `ports/` and `adapters/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, and every existing test file.

## Living docs to update
- `docs/architecture.md`:
  - New section "Plan use case: the planner call" (`app/plan.py`): the order of reads, events and calls, the retry, the failed process, and the result.
  - "Data flow": `run_planner` now calls `Runs.next_id`, `Plans.next_id`, `LLMProvider.complete`, `parse_reply`, `check_plan`, `complete_contract`, `policy_hash`, `build_planner_prompt`, `context_hash` and `rejection_lines`; no command calls `run_planner` yet.
- `docs/progress.md`:
  - Current, then Done; remove outline item 9a.
  - A Later line for Spec gaps item 2.
- `docs/decisions.md`: rows for the answered questions.
- `CHANGELOG.md`, `README.md`: no change (no command or output is added).

## New dependencies
None.

## Spec gaps
Spec impact is "wording". Neither item blocks.

1. "Tech stack and repo layout": "If a reply fails Pydantic validation, the call is retried once"; "Task contract" › "Plan checks": "A reply rejected by Pydantic or by the plan checks is retried once with the rejections in the prompt".
   - Unclear: neither sentence names a reply with no structured result (audit F-6 of `docs/spec-audits/2026-10-11-proposal-v1.11.md`).
   - Does not block:
     - "Plan checks" makes it a `schema` rejection.
     - "Tech stack and repo layout" calls it "a rejected reply".
     - The ADR-005 amendment retries "a rejected reply".
     - The human confirmed on 2026-10-11 that it is retried once (TASK-031, answer 7).
   - AC4 follows that. The item is already a Later line in `docs/progress.md`; no new line.
2. "Task contract" › "Plan checks" and "Planning".
   - Missing: whether a plan with no tasks is created. A reply `{"tasks": []}` against an approved spec set with no requirement that is not deprecated breaks no rule of the table, so by the text a `PlanCreated` with an empty `tasks` list is recorded.
   - Does not block: no criterion asserts the case and the code takes no special path for it. A Later line asks whether `plan` should refuse instead; the planner does not decide it.

Already decided, not gaps of this task:
- The text of `AgentRunFinished.error` for a failed process is `str(LLMError)`, copied unchanged (audit F-4 and Q4; SC-50 row; TASK-029 answer 6). AC6 asserts the copy, not the adapter's wording.
- An envelope that reports an error with exit status 0 is a rejected reply and is retried (decision of 2026-10-11, TASK-031 answer 6).

Readings, not gaps:
- `PlanCreated.run_id`, "the planner run that produced it", is the run of the accepted reply: the second run after a retry.
- "`AgentRunFinished` is recorded after the checks" fixes the order within one attempt: call, `parse_reply`, `check_plan`, then the event.
- A failed process has `model`, `tokens_in`, `tokens_out` and `cost_usd` null: `LLMError` carries none of them, and the spec says "null when the runtime reported none".
- A failed second call is "a failed process" like a first one: the result is `failed`, not `rejected`, and the first reply's rejections are not returned.
- `Runs.next_id` is read once per attempt, after the earlier `AgentRunStarted` is recorded (ADR-012, Consequences).
- `Plans.next_id` is read after a reply is accepted. The spec says only "when a command runs"; the criteria use a fixed fake and do not fix the moment.
- "A task id is unique among all tasks in the `tasks` projection" needs no check in M2. `plan` is refused while an approved plan exists (9b), and a new `PlanCreated` removes the earlier draft's tasks, so the projection holds no other task when this function records. The check is a Later line before M6.

## Open questions
None is a spec decision. Each has a proposal.

1. **Module and name.** Proposed: `app/plan.py`, function `run_planner`, with the spec version id as the first argument and the four ports keyword-only; 9b adds its two functions to the same module. Alternative: `app/planner_call.py`, leaving `app/plan.py` to 9b.
2. **The result type.** The outline gives "the result type" to 9b, but this function must return something. Proposed: `PlannerResult` with `PlannerOutcome` (`created`, `rejected`, `failed`) as in Scope; 9b decides whether its second function returns it as it is or wraps it for `git ls-files failed`. Alternative: plan the result type of the whole command now, which pulls 9b's refusals into this task.
3. **Where the retry lives.** ADR-005 says "The retry is one function in the app layer". Proposed: `run_planner` is that function for the planner, with the two attempts written inside it; a helper shared with the classifier waits for M6. Alternative: a generic `call_with_retry(llm, build_prompt, check)` now.
4. **Fakes or SQLite.** Proposed: in-memory fakes (ADR-012: "The M2 use cases are tested with in-memory fakes"), with the fake `Runs` counting recorded `AgentRunStarted` events so a second id is only right when it is read after the first run started; the real adapters meet this code in the M2 close test (item 13). Alternative: `SqliteEventRecorder`, `SqliteRuns` and `SqlitePlans` under `tmp_path` with a fake LLM, which also checks the projections here.
5. **A started run with no finish.** An exception from the LLM that is not `LLMError`, or a recorder that raises, leaves `AgentRunStarted` with no `AgentRunFinished`. Proposed: let it propagate, no criterion, as the M1 use cases do. Alternative: catch every exception and record `exit: error`.
6. **Size.** Proposed: one task of about 460 lines with tests and six criteria; the three paths share one attempt function and one set of fakes. Alternative: TASK-032 takes AC1 to AC5 and a TASK-033 takes the failed process (AC6).

Answers (human, 2026-10-11): the plan was approved with the proposed answer to each of questions 1 to 6. The advisor agreed with all six.

## Outcome
Built:
- `src/openfactory/app/plan.py`: `run_planner`, `PlannerOutcome`, `PlannerResult`, a private `_Attempt` model and `_attempt` function.
- `tests/unit/test_plan_use_case.py`: AC1 to AC6; 949 tests pass.

Deviations: none. No test from the test-writer was edited.

Notes:
- The test-writer redefined the TASK-031 sample set, policy and files locally, because the repo has no shared test helpers.
- `Plans.next_id` is read after a reply is accepted.

Review: the reviewer approved with no blocking issues. Two of its notes were applied at the human's word:
- `docs/architecture.md` "Data flow": the lines that still said "no use case calls them yet" of functions `run_planner` calls were corrected.
- `docs/progress.md`: a Later line ("Spec gap", before M7) that a started run can lack a finish.

Follow-ups, not applied:
- A Later line that the classifier must reuse or extract this retry in M6 (advisor).
- A note on outline item 13 that the close test includes one retried planner call (advisor).
- Thin spots in the tests: the failed-second-call test does not assert `result.rejections == []` or the error text, and the AC4 test does not assert the event count or the retry prompt (reviewer).
