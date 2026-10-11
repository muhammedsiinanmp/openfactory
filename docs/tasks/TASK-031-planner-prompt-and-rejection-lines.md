# TASK-031: Planner prompt, rejection lines and the prompt hash

- Milestone: M2
- Status: done
- Tests: acceptance
- ADR: none needed for this task's code; ADR-013 (proposed) records the answer to Open question 8 for slice 9b. No new port, adapter, dependency, event type, payload or storage change. ADR-005 (accepted, with its amendment of 2026-10-11) covers the planner call and "the validation error in the prompt"; ADR-012 covers where the spec set and the tracked files come from. The module, the names and the prompt's layout are rows in `docs/decisions.md` (Open questions 1 to 5).
- Spec impact: wording. One item, which does not block (see "Spec gaps").
- Spec sections (spec v1.11): "Task contract" ("Planning": the bullet that starts "The planner receives one prompt and no tools"; "Plan checks": the paragraph that starts "A reply rejected by Pydantic or by the plan checks is retried once"); "Spec input format" ("Spec field rules": "the planner creates no tasks for it"); "Domain model and storage" ("Event payloads": the `context_hash` line of `AgentRunStarted`); "CLI commands" ("Output": the `plan` rejection lines and "sorted by rule name, then by subject, then by message, as strings"); "Tech stack and repo layout" ("retried once with the validation error in the prompt")

## Outline item
First slice of M2 outline item 9 ("Plan use case: the prompt, the single retry, run and plan ids, the events and their `causation_id`; ..."). This slice is the text the use case needs: the prompt, the retry prompt, the rejection lines and the prompt hash. The calls, the retry, the ids, the events and the refusals are left (see "Left of outline item 9").

## Objective
Add the pure functions that build the planner prompt from the approved spec set, the policy and the tracked files, build the retry prompt with the rejections in it, write rejections as sorted `rule  subject  message` lines, and hash a prompt for `context_hash`, so the plan use case can make and record a planner call.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings.

## Scope
In (names and modules per Open questions 1 and 2):
- `src/openfactory/app/planner_prompt.py` (new):
  - `build_planner_prompt(spec: SpecSet, policy: Policy, tracked_files: Sequence[str], rejections: Sequence[PlanRejection] = ()) -> str`. With no rejections it is the first prompt; with rejections it is the retry prompt.
  - `context_hash(prompt: str) -> str`: the SHA-256 of the prompt encoded as UTF-8, as 64 lowercase hex characters.
- `src/openfactory/domain/plan_checks.py`:
  - `rejection_lines(rejections: Sequence[PlanRejection]) -> list[str]`: one `rule  subject  message` line per rejection, sorted by rule, then subject, then message, as strings.
- Unit tests built from Python values. No files, no database, no git, no LLM.

Out (not this task):
- Every caller: `LLMProvider.complete`, the JSON Schema of `PlannerReply`, `parse_reply` and `check_plan` on a reply, the single retry, run and plan ids, `AgentRunStarted`, `AgentRunFinished` and `PlanCreated`, `causation_id`, `str(LLMError)` in `AgentRunFinished.error`.
- The refusals of `plan`, the `spec files differ` warning, `GitError`, and the result type of the use case.
- The `plan` command, its output and structlog configuration (outline item 10). `cli.py` and its `_result_lines` are not changed.
- Whether a reply with no structured result is retried, and an envelope that reports an error with exit status 0: this task makes no call.
- The exact wording and layout of the prompt. Criteria assert what the prompt holds, not its text.
- Hardening: prompt size limits, escaping of text that looks like instructions, a file name with a line break.

## Acceptance criteria
"Planning" and "Plan checks" are under "Task contract"; "Event payloads" is under "Domain model and storage"; "Output" is under "CLI commands". "The sample set" is a `SpecSet` with components `[auth]`, the requirement `REQ-AUTH-001` of the spec's example (two criteria, `constrained_by: [ADR-001]`) and `ADR-001` (accepted) with a body the test chooses. "The sample policy" is a `Policy` with `forbidden_paths: ["secrets/**"]`. "The sample files" are `["app/main.py", "tests/test_main.py"]`. "Holds X" means the string X is in the prompt. Names follow the proposals under Open questions; if the human answers otherwise, the names change and the assertions do not.

- [x] AC1 ("Planning": "The planner receives one prompt and no tools: the requirements that are not deprecated, their acceptance criteria, the bodies of the ADRs they are constrained by, the declared components, the baseline and the policy's forbidden paths, the names of the gates, and the list of tracked files from `git ls-files`"):
  - `build_planner_prompt(the sample set, the sample policy, the sample files)` returns one string.
  - It holds `REQ-AUTH-001`, its title and its statement; `AC-AUTH-001-1` and `AC-AUTH-001-2`, each with its text; the body of `ADR-001`; and `auth`.
  - It holds the four baseline paths `specs/**`, `.openfactory/**`, `.env` and `.env.*`, and `secrets/**`.
  - It holds the five gate names `path_check`, `ruff`, `pytest`, `gitleaks` and `review`.
  - It holds `app/main.py` and `tests/test_main.py`.
- [x] AC2 ("Planning": "the requirements that are not deprecated" and "the bodies of the ADRs they are constrained by"; "Spec field rules": "A deprecated requirement is validated like any other, but the planner creates no tasks for it"):
  - With a second requirement `REQ-AUTH-002` that is deprecated and constrained by `ADR-002`, the prompt holds none of: `REQ-AUTH-002`, its statement, its criterion's id, its criterion's text, the body of `ADR-002`.
  - With an `ADR-003` that no requirement is constrained by, the prompt does not hold its body.
  - With `ADR-001` named by both `REQ-AUTH-001` and the deprecated requirement, the prompt still holds the body of `ADR-001`.
- [x] AC3 ("Planning": "the list of tracked files from `git ls-files`. It receives no file contents"):
  - Every name of the tracked files is in the prompt unchanged, a name with a space and a name with a non-ASCII character included, and the names appear in the order given.
  - With an empty list of tracked files the function still returns a prompt that holds the items of AC1 other than the file names.
  - `openfactory.app.planner_prompt` imports nothing from `openfactory.adapters` or `openfactory.cli` (checked by parsing its imports with `ast`), so it reads no file.
- [x] AC4 ("Output": "it prints that reply's rejections as `rule  subject  message`, sorted as violation lines are" and "sorted by rule name, then by subject, then by message, as strings" and "The three fields are separated by exactly two spaces, with no padding"; "Plan checks": "its rejection lines, as `rule  subject  message` in the sorted order `plan` prints them"):
  - `rejection_lines` of one `schema` rejection with subject `reply` and message `no structured result` is `["schema  reply  no structured result"]`.
  - Given, in this order, an `uncovered` rejection for `REQ-AUTH-001`, a `cycle` for `AUTH-002`, a `cycle` for `AUTH-001` and a second `cycle` for `AUTH-001` with a message that sorts earlier, the lines come back as: the two `cycle` lines of `AUTH-001` in message order, the `cycle` line of `AUTH-002`, then the `uncovered` line.
  - An empty list gives `[]`, and the list passed in is unchanged.
- [x] AC5 ("Plan checks": "A reply rejected by Pydantic or by the plan checks is retried once with the rejections in the prompt"; "Tech stack and repo layout": "retried once with the validation error in the prompt"):
  - With two rejections passed as `rejections`, the prompt holds every line of `rejection_lines(rejections)`.
  - That prompt also holds every item asserted in AC1, and it is not equal to the prompt built without rejections.
  - The prompt built without rejections holds none of those lines.
- [x] AC6 ("Event payloads": "`context_hash: "<64 hex>"` # for a planner or classifier run, the SHA-256 of the prompt text encoded as UTF-8"):
  - `context_hash("")` is `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
  - For a prompt with a non-ASCII character, `context_hash(prompt)` equals `hashlib.sha256(prompt.encode("utf-8")).hexdigest()` and is 64 lowercase hex characters.
  - Two calls of `build_planner_prompt` with equal arguments return equal strings, so equal inputs give one hash.

## Architecture rules that apply
- `src/openfactory/app` depends on `domain` and `ports` only. `planner_prompt.py` needs `domain` only and does no I/O.
- `src/openfactory/domain` stays pure. The existing import-guard test for `plan_checks.py` keeps covering it.
- "All LLM calls go through `claude -p`": this task makes no call and adds no SDK.
- No event is recorded, and no projection is read or written.
- Tests from the test-writer are fixed. No existing test is changed.
- No hardening beyond the spec's rules.

## Plan
1. Create branch `task/TASK-031-planner-prompt-and-rejection-lines` from an up-to-date main.
2. Get the human's answers to the Open questions; record them here and as rows in `docs/decisions.md`.
3. Write failing tests:
   - `tests/unit/test_planner_prompt.py` (new) for AC1, AC2, AC3, AC5 and AC6, with one helper that returns the sample set.
   - `tests/unit/test_rejection_lines.py` (new) for AC4.
4. In `domain/plan_checks.py`, add `rejection_lines`: sort the `(rule value, subject, message)` tuples, then join each with two spaces, as `_result_lines` in `cli.py` does for violations.
5. Add `app/planner_prompt.py`:
   - Select the requirements with `deprecated` false, and the ADRs whose id is in the `constrained_by` of one of them.
   - Write the sections in a fixed order: instructions, components, requirements with their criteria, ADR bodies, forbidden paths (`BASELINE_FORBIDDEN_PATHS`, then the policy's), gate names (`REQUIRED_GATES`), tracked files one per line.
   - When `rejections` is not empty, add a last section with `rejection_lines(rejections)`.
   - `context_hash` is `hashlib.sha256(prompt.encode("utf-8")).hexdigest()`.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until green.
7. Update the living docs and the Outcome. Commit `feat(app): add the planner prompt and the rejection lines` with trailers `Task: TASK-031` and `Milestone: M2`.

## Files expected to change
- `src/openfactory/app/planner_prompt.py` (new, about 80 lines)
- `src/openfactory/domain/plan_checks.py` (about 12 lines added)
- `tests/unit/test_planner_prompt.py` (new, about 170 lines)
- `tests/unit/test_rejection_lines.py` (new, about 50 lines)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-031-planner-prompt-and-rejection-lines.md`

About 90 lines of source and 220 of tests.

Not expected to change: `cli.py`, the other modules under `app/`, `domain/`, `ports/` and `adapters/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, and every existing test file.

## Living docs to update
- `docs/architecture.md`:
  - New section "Planner prompt" (`app/planner_prompt.py`): what the prompt holds, what it leaves out, the retry form and `context_hash`.
  - "Plan checks" gains `rejection_lines`.
  - "Data flow": one sentence, no use case calls them yet.
- `docs/progress.md`:
  - Current, then Done.
  - Outline item 9 is rewritten as what is left of it (see "Left of outline item 9").
  - Later line for the Spec gaps item.
  - The two "Spec gap (before outline item 9 is planned)" lines are reworded with the human's answers to Open questions 6 and 7.
- `docs/decisions.md`: rows for the answered questions.
- `CHANGELOG.md`, `README.md`: no change (no command or output is added).

## New dependencies
None.

## Spec gaps
Spec impact is "wording". The one item does not block.

1. "Task contract" › "Plan checks": "A reply rejected by Pydantic or by the plan checks is retried once with the rejections in the prompt".
   - Unclear: the sentence does not say that the retry prompt also holds the whole planning input, or in what form the rejections are written.
   - Does not block: "Planning" says what "the planner receives", and a retried call is a planner call ("a retried call is a second pair"), so the retry prompt is that list plus the rejections. Each call is a new `claude` process with no memory of the first. The only form the spec gives a rejection is the `rule  subject  message` line. AC5 follows both.
   - Proposed text: "... is retried once with the same prompt and the rejection lines added to it".

Not this task's, checked because `docs/progress.md` marks them "before outline item 9 is planned". This task makes no call and decides no retry.
- The retry sentences do not name a reply with no structured result (audit F-6 of `docs/spec-audits/2026-10-11-proposal-v1.11.md`).
  - Reading of the planner: wording, not a gap.
  - "Plan checks" opens "a reply is rejected under one of these rules" and `schema` is a row of that table.
  - The same section says "A reply whose structured result is missing is one `schema` rejection", and "whichever kind of rejection the first reply had".
  - "Tech stack and repo layout" calls it "a rejected reply", and the accepted ADR-005 amendment says "the single retry is for a rejected reply only".
  - So it is retried. Open question 7 asks the human to confirm.
- A structured result that is JSON `null`.
  - The adapter gives `None` for a missing key and for `null`, and `parse_reply(None)` gives `no structured result`; both are decisions rows of 2026-10-11 (TASK-028, TASK-029).
  - Under either reading it is one `schema` rejection with subject `reply`, and the use case cannot tell the two apart.
- An envelope that reports an error with exit status 0 (`is_error`, `subtype` not read).
  - "A non-zero exit, an envelope that cannot be parsed, or a timeout is a failed process" names three cases and this is none of them.
  - "An envelope that parses but whose structured result is missing ... is a rejected reply" then makes it a rejected reply, which is retried.
  - The spec's text covers the case. Whether that is what the human wants is Open question 6.
  - The answer changes the adapter (`LLMReply` or `LLMError`), not the use case.
- "CLI commands" › "Output": "The warning is written after the first three refusals have been checked and before `git ls-files` runs".
  - Audit F-7 / M-2 of the same report left "The human chooses" between a time and a line order, and no row in `docs/decisions.md` answers it.
  - It decides whether the use case can return a flag, so it concerns the slice that builds the refusals (Open question 8).

Readings, not gaps:
- "The requirements that are not deprecated" leaves a deprecated requirement out whole: its id, statement and criteria.
- "The bodies of the ADRs they are constrained by": "they" are the requirements that are not deprecated. An ADR named only by a deprecated requirement, or by none, is left out.
- "The baseline and the policy's forbidden paths" are `BASELINE_FORBIDDEN_PATHS` and then `Policy.forbidden_paths`; "the names of the gates" are `REQUIRED_GATES`.
- "It receives no file contents" is met by the function taking names only and doing no I/O.
- The spec set passed in is the stored set of the approved version (`SpecVersions.spec_set`), not the files on disk: "`openfactory plan` uses the latest approved spec version". Passing it is the caller's.

## Open questions
Questions 1 to 5 are not spec decisions; each has a proposal. Questions 6 to 8 are for the slices after this one.

1. **Module of the prompt.** Proposed: `app/planner_prompt.py`, beside `app/spec_loader.py`, since only the plan use case builds a prompt. Alternative: `domain/planner_prompt.py`, since it is pure.
2. **Module of `rejection_lines`.** Proposed: `domain/plan_checks.py`, beside `PlanRejection`, because the spec defines the content of `AgentRunFinished.error` by these lines and the `plan` command prints the same ones. Alternative: `app/planner_prompt.py`, with `cli.py` importing it from there.
3. **One function or two.** Proposed: one, `build_planner_prompt(..., rejections=())`, so the retry prompt cannot drift from the first. Alternative: `build_retry_prompt(first_prompt, rejections)`.
4. **The earlier reply in the retry prompt.** Proposed: not included; the retry prompt holds the planning input and the rejection lines only, which is what the spec lists. Including the rejected reply's JSON would add to what "the planner receives" and needs `/spec-change`.
5. **Layout and wording of the prompt.** Proposed: plain text with one headed section per item of the "Planning" bullet, requirements written as id, title, statement, priority, components and criteria, tracked files one per line; no test fixes the wording. Alternative: the planning input as one JSON object inside the prompt.
6. **An error envelope with exit status 0.** By the spec's text it is a rejected reply: it is retried, and the runtime's error text is not recorded. Is that intended? If not, it needs `/spec-change` (a fourth failed-process case) and a small adapter task before the slice that makes the call. The planner does not decide this.
7. **A reply with no structured result is retried.** The planner reads the spec and the ADR-005 amendment as settling it (see "Spec gaps"). Confirm, or settle the wording by `/spec-change` with audit F-2 and F-3 before the next slice.
8. **When the warning is written.** Time (the use case surfaces the warning before it calls `GitProvider`, by a callback or by two use-case functions) or line order (the use case returns a flag and `cli.py` prints the warning first). Audit F-7 / M-2 left this to the human. Needed before the slice that builds the refusals.

### Answers (human, 2026-10-11: "do as the advisor says")
1. `app/planner_prompt.py`. Moving or renaming `context_hash` can wait for M6.
2. `domain/plan_checks.py`.
3. One function, `build_planner_prompt(..., rejections=())`.
4. The earlier reply is not included. A Later line says to look again if real runs show second replies repeating the first's mistakes.
5. Plain headed text. Each ADR body is written with its ADR id and a clear delimiter, each requirement is written with its `constrained_by` ids, and the order of the text is fixed by the inputs alone. The instructions say what the plan checks enforce.
6. The spec stays as it is: an error envelope with exit status 0 is a rejected reply and is retried. The Later line stays, reworded: exit status and `is_error` are observed at the first real `plan` run (the M2 close).
7. Confirmed: a reply with no structured result is retried once. A JSON `null` structured result is treated as missing. The wording items stay in Later.
8. The time reading, by two use-case functions that `cli.py` calls in turn: the entry function returns a refusal or the spec set, the policy and the differs flag; `cli.py` prints the warning; the second function calls `GitProvider` and the planner. No `/spec-change`.

## Left of outline item 9
- **Planner call and events.** Given the spec set, the policy, the tracked files and the ports, in this order:
  - `Runs.next_id`, `AgentRunStarted` with `context_hash`, then `LLMProvider.complete` with the JSON Schema of `PlannerReply`.
  - `parse_reply`, then `check_plan`.
  - `AgentRunFinished`: `exit: ok` with `error` the rejection lines or null; or `exit: error` / `timeout` with `str(LLMError)` unchanged and no retry.
  - The single retry as a second pair of run events.
  - `Plans.next_id`, `complete_contract`, `policy_hash`, and `PlanCreated` with tasks sorted by `task_id`.
  - `causation_id` chained through the command.
  - Depends on this task and on Open questions 6 and 7.
- **Entry and refusals.** The three refusals in order (`no approved spec version`, invalid policy, approved plan), the `spec files differ` warning, `GitError` as `git ls-files failed`, the result type, and the call into the slice above. Depends on Open question 8.

## Outcome
**Built.**
- `app/planner_prompt.py`: `build_planner_prompt(spec, policy, tracked_files, rejections=())` returns plain headed text: instructions (they state what the plan checks enforce), components, the requirements that are not deprecated with their criteria and `constrained_by` ids, the bodies of the ADRs those requirements name (each in an `<adr id="...">` delimiter), forbidden paths (baseline, then the policy's), the five gate names and the tracked file names in the order given. With rejections it adds a last section with `rejection_lines(rejections)`: the retry prompt. `context_hash(prompt)` is the SHA-256 of the UTF-8 text as 64 lowercase hex characters. No file is read and no adapter is imported.
- `domain/plan_checks.py`: `rejection_lines(rejections)`, one `rule  subject  message` line per rejection, sorted by rule, subject, then message as strings.
- Tests: `tests/unit/test_planner_prompt.py` (AC1, AC2, AC3, AC5, AC6) and `tests/unit/test_rejection_lines.py` (AC4).
- Decisions are seven rows in `docs/decisions.md`; architecture and progress updated. CHANGELOG and README unchanged: no command or output was added.

**Deviations from plan.**
- The record was not committed separately; there is one commit at the end, per the /next-task workflow.
- Test edits after the review, asked for by the human ("apply all 4"); each adds an assertion and none is weakened, all in `tests/unit/test_planner_prompt.py`:
  - both sample sets declare a second component, `billing`, that no requirement uses, and `ac1_items` gains `billing` and `ADR-001`, so the components section and the ADR id are pinned;
  - `test_ac1_prompt_holds_the_planning_input` also asserts `.env` is in the prompt apart from `.env.*`, and that `ADR-001` appears at least twice (with its body and with the requirement it constrains);
  - new `test_ac1_requirement_without_adrs_and_empty_lists_leave_no_trailing_space`.
- No existing test file changed.
- An empty part is written as `(none)`: a requirement's `constrained_by`, and the components, ADRs, tracked files sections (reviewer's minor note).
- ADR-013 (proposed) drafted for the answer to Open question 8: the `plan` command as two use-case calls with the warning printed between them. No code in this task depends on it; the human accepts it or not before 9b is planned.

**Follow-ups.** Later lines in `docs/progress.md`: look again at including the rejected reply in the retry prompt; the spec wording of the retry sentence; the wording items on a missing structured result (F-2, F-3, F-6); observing exit status and `is_error` at the first real `plan` run; `context_hash` may need moving or renaming for the M6 classifier. Outline item 9 is rewritten as 9a (planner call and events) and 9b (entry and refusals).
