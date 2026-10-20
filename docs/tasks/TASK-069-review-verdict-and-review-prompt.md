# TASK-069: `ReviewVerdict`, the reviewer reply's rejection lines, the review prompt and the review file text

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-015 (accepted), "How accepted ADRs are read from now on": "The reviewer is instead one `LLMProvider` call with no tools, set up as a planner call, replying `ReviewVerdict`." The task adds no port, adapter, dependency, event type, payload, schema or convention. Two new modules, each a pure function set like `planner_prompt.py` and `plan_checks.py`, are not an ADR trigger.
- Spec impact: wording (see Spec gaps)
- Spec sections (spec v1.16; SC-87, SC-106, SC-119):
  - "Gates and remediation" › "The review gate": "Its prompt is the task contract and the text of `git diff --cached <base>` in the worktree. It replies: `class ReviewVerdict(BaseModel): model_config = ConfigDict(extra="forbid"); verdict: Literal["approve", "reject"]; comments: str`"
  - "Gates and remediation" › "The review gate": "a rejected reply is retried once, as for a planner call. A rejected reviewer reply has `exit: ok` and `error` set to its rejection lines, `schema  reply  <message>`: one per Pydantic error with the field path in its message, or `no structured result` when the structured result is missing, sorted and joined by newlines, as for a planner reply."
  - "Gates and remediation" › "The review gate": "The gate's output file holds the verdict and the comments; when there is no verdict, it holds the run's `error`."
  - "Task contract" › "Plan checks", last paragraph: "is retried once with the same prompt and the rejection lines added to it".
  - "Tech stack and repo layout": "If a reply fails Pydantic validation or has no structured result, the call is retried once with the validation error in the prompt, then fails."

## Outline item
M4 outline item 8, first slice: the pure parts of the review gate. The second slice (8b) wires the gate into `run_task`:
- `llm: LLMProvider` on `run_task` and `run_plan`;
- `GitProvider.staged_diff`, and `git:` failures on it;
- the reviewer's `AgentRunStarted`/`AgentRunFinished` pairs with the retry;
- a failed process or a second rejected reply fails the gate;
- the `review` `GateEvaluated` with the implementer's `run_id`, written to `review.txt`;
- `reject` gives `failed` with reason `review`, `approve` gives the commit;
- `cli.py` wires `ClaudeCodeLLM`;
- approved test edits in `test_run_task.py`, `test_run_plan.py` and `test_m3_close.py` (a stand-in reviewer reply).

That slice stays as item 8 in the outline (SC-105, SC-107 and the rest of SC-87, SC-106, SC-119).

## Objective
Add `ReviewVerdict` and a parser that turns a reviewer's structured result into a verdict or its `schema  reply  <message>` rejection lines. Add the review prompt (contract plus staged diff, and the retry form with rejection lines) and the text of the review gate's output file. All are pure functions that nothing calls yet.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- New `src/openfactory/domain/review.py`, importing only `pydantic`, the standard library and `openfactory.domain`:
  - `ReviewVerdict` exactly as the spec's class block, plus `frozen=True`, as for `RunResult` (TASK-047).
  - Frozen `ParsedReview` (`verdict: ReviewVerdict | None`, `rejections: list[PlanRejection]`).
  - `parse_review_reply(structured: object | None) -> ParsedReview`. It reuses `PlanRejection` with `PlanRule.schema` and subject `reply`, so `rejection_lines` of `domain/plan_checks.py` gives the lines unchanged.
  - `review_file_text(verdict: ReviewVerdict | None, error: str | None) -> str`.
- New `src/openfactory/app/review_prompt.py`, importing only `openfactory.domain`:
  - `build_review_prompt(contract: TaskContract, diff: str, rejections: Sequence[PlanRejection] = ()) -> str`.
  - It does not import `context_hash`; the caller uses the one in `app/planner_prompt.py`, as `build_context_pack` does.
- Tests: new `tests/unit/test_review.py` and `tests/unit/test_review_prompt.py`, plus one conformance test in `tests/unit/test_spec_conformance.py` tying `ReviewVerdict`'s field names and `verdict` values to the spec's class block.

Out:
- Any call of these functions from `app/run.py`; `LLMProvider` on `run_task`/`run_plan`; events; `cli.py` (slice 8b).
- The cost limit (item 9), retry and the failure report (item 10).
- Any change to `ports/`, `adapters/`, events, payloads or the schema. No existing test is edited.

## Acceptance criteria
- [ ] **AC1** ("The review gate", the `ReviewVerdict` class block):
  - `ReviewVerdict` has exactly the fields `verdict` (`"approve"` or `"reject"`) and `comments` (`str`), both required.
  - An extra key, another `verdict` value or a missing field is rejected by Pydantic.
  - A conformance test ties the field names and the two values to the spec's block.
- [ ] **AC2** ("The review gate": "`schema  reply  <message>`: one per Pydantic error with the field path in its message, or `no structured result` when the structured result is missing"):
  - `parse_review_reply(None)` gives no verdict and one rejection, which `rejection_lines` prints as `schema  reply  no structured result`.
  - A result `ReviewVerdict` rejects gives no verdict and one `schema` rejection per Pydantic error. Each has subject `reply` and a message `<field path>: <Pydantic msg>`, or only the message when the error has no field path, as `parse_reply` does.
  - A valid result gives the verdict and no rejections.
- [ ] **AC3** ("The review gate": "sorted and joined by newlines, as for a planner reply"):
  - For a reply with several errors (for example, `verdict` invalid and `comments` missing), `"\n".join(rejection_lines(parsed.rejections))` gives the lines sorted as strings.
- [ ] **AC4** ("The review gate": "Its prompt is the task contract and the text of `git diff --cached <base>`"):
  - `build_review_prompt(contract, diff)` holds the fixed reviewer instructions (see Spec gaps, G1).
  - It holds the contract as `contract.model_dump_json(indent=2)` under `## Task contract`.
  - It holds the diff text unchanged under `## Staged diff`, and nothing else from the repo or the spec.
  - Equal arguments give an equal text.
  - `app/review_prompt.py` imports nothing outside `openfactory.domain` and the standard library.
- [ ] **AC5** ("Plan checks": "retried once with the same prompt and the rejection lines added to it"; "The review gate": "retried once, as for a planner call"):
  - With `rejections`, the text is the first prompt followed by one last section that lists `rejection_lines(rejections)`.
  - The rejected reply itself is not in it.
  - Its `context_hash` differs from the first prompt's.
- [ ] **AC6** ("The review gate": "The gate's output file holds the verdict and the comments; when there is no verdict, it holds the run's `error`"):
  - `review_file_text(verdict, None)` holds the verdict word and the comments.
  - `review_file_text(None, error)` holds the error text unchanged.
  - The exact form follows the answer to G2.

## Architecture rules that apply
- `domain` has no I/O and imports nothing from `app`, `ports` or `adapters`. `app/review_prompt.py` imports only `domain`.
- All LLM output is validated by a Pydantic model before use: `ReviewVerdict` is that model for the reviewer.
- No event, payload, schema or dependency change.

## Plan
1. Create branch `task/TASK-069-review-verdict-and-review-prompt` from an up-to-date main.
2. Test-writer: write failing tests for AC1 to AC6 in `tests/unit/test_review.py` and `tests/unit/test_review_prompt.py`, plus the conformance test.
3. Implement `domain/review.py` on the model of `parse_reply` in `domain/plan_checks.py`. Implement `app/review_prompt.py` on the model of `build_planner_prompt`, reusing its `_section` layout and the same retry heading wording, adapted to a review.
4. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
5. Update the living docs and the Outcome.
6. Commit `feat(domain): add ReviewVerdict, the review reply's rejection lines and the review prompt` with the trailers `Task: TASK-069` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/domain/review.py` (new, about +55)
- `src/openfactory/app/review_prompt.py` (new, about +45)
- `tests/unit/test_review.py` (new, about +110)
- `tests/unit/test_review_prompt.py` (new, about +70)
- `tests/unit/test_spec_conformance.py` (one new test, about +15)
- `docs/architecture.md`: entries for `domain/review.py` and `app/review_prompt.py`; data flow: nothing calls them yet.
- `docs/decisions.md`: rows for G1, G2 and G3 as answered.
- `docs/progress.md`: Current, Done, Outline item 8 narrowed, Later wording items.
- `docs/tasks/TASK-069-review-verdict-and-review-prompt.md` (this record).

Not expected to change: `ports/`, `adapters/`, `app/run.py`, `cli.py`, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 300 lines with tests, about 100 of them in `src/`.

## Spec gaps
- **G1. "Gates and remediation" › "The review gate", "Its prompt is the task contract and the text of `git diff --cached <base>`."**
  - Unclear: the spec names the prompt's contents but no reviewer instructions (what to judge, how to reply).
  - Precedent: the planner prompt (TASK-031) has a fixed instruction header.
  - Proposed answer: a fixed instruction block first, saying the reviewer judges whether the staged diff meets the contract's objective and acceptance criteria within `allowed_paths`, and replies `{"verdict": "approve" | "reject", "comments": "..."}`. The contract and the diff follow.
- **G2. "Gates and remediation" › "The review gate", "The gate's output file holds the verdict and the comments; when there is no verdict, it holds the run's `error`."**
  - Unclear: no form for the file.
  - Proposed answer: `verdict: <approve|reject>\n` then the comments, ending in `\n` if they lack one. With no verdict, the error text with a trailing `\n` added if it lacks one.
- **G3. "Gates and remediation" › "The review gate", "a rejected reply is retried once, as for a planner call".**
  - Unclear: the heading of the added retry section.
  - Proposed answer: a last section headed like the planner's, worded for a review: `## Rejections of your earlier reply (rule  subject  message); reply again with a verdict that has none of them`.

## Design choices to confirm at planning
1. Reuse `PlanRejection`/`PlanRule.schema` and `rejection_lines` for the reviewer's lines rather than a new rejection type ("as for a planner reply").
2. `ReviewVerdict` adds `frozen=True` to the spec's `model_config`, as for `RunResult`.
3. Item 8 is split; slice 8b (wiring in `run_task`/`run_plan`/`cli.py` and the test edits) is planned next.

## Answers (2026-10-20)
The human approved G1, G2, G3 and design choices 1 to 3 as proposed; the advisor's two wording points (Q1 `allowed_paths` clause, Q3 "verdict" vs "result") were not taken.

## Outcome
Added `src/openfactory/domain/review.py` (`ReviewVerdict`, `ParsedReview`, `parse_review_reply`, `review_file_text`) and `src/openfactory/app/review_prompt.py` (`build_review_prompt`), with G1, G2 and G3 as answered on 2026-10-20 and `PlanRejection`/`rejection_lines` reused. Tests: `tests/unit/test_review.py`, `tests/unit/test_review_prompt.py` and one conformance test in `tests/unit/test_spec_conformance.py`. No test edits were made by the implementer; the tests from the test-writer are unchanged. Nothing calls the new functions; wiring is slice 8b. Living docs: `docs/architecture.md`, `docs/decisions.md` (four rows), `docs/progress.md` (Current, Done, item 8 narrowed, three Later lines).
