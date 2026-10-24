# TASK-093: Classifier prompt

- Milestone: M6
- Status: done
- Tests: acceptance
- ADR: ADR-019 (accepted). Its "Classifier" bullet covers the call: "At most one call per `impact`, as a planner call with role `classifier`; reply `{"changes": [ChangeClass]}` …; one retry." This task adds one pure `app` module. It adds no port, adapter, event type, payload change, table, dependency or new convention: it follows the `planner_prompt.py` and `review_prompt.py` pattern. Where `context_hash` lives is a row in `docs/decisions.md` (Design choice 2).
- Spec impact: wording (see Spec gaps; none blocks)
- Spec sections (spec v1.18; SC-161, SC-172):
  - "Spec diff and impact analysis" › "Step 2: change classification (LLM, validated)": "Its prompt is fixed instructions that define the three kinds, then, for each modified requirement in ascending id, its `from` and `to` versions with their acceptance criteria and the bodies of the ADRs each version is constrained by. It replies `{"changes": [ChangeClass, ...]}`, one entry per modified requirement". Also: "`cosmetic` changes (wording only) are shown but trigger no work."
  - "Spec diff and impact analysis" › "Classifier checks": "A rejected reply is retried once, and its `AgentRunFinished` is recorded, as for a planner reply."
  - "Task contract" › "Plan checks", last paragraph: "is retried once with the same prompt and the rejection lines added to it".
  - "Tech stack and repo layout": "If a reply fails Pydantic validation or has no structured result, the call is retried once with the validation error in the prompt".
  - "Domain model and storage" › "Event payloads", `AgentRunStarted`: "`context_hash`: the SHA-256 of the run's prompt text encoded as UTF-8".

## Outline item
M6 outline item 1b. It settles the TASK-031 Later line on where `context_hash` lives.

## Objective
A new pure `app/classifier_prompt.py` with `build_classifier_prompt`. It returns the classifier's first prompt, or with rejections its retry prompt. The text is built from the `from` and `to` spec sets and their `SpecDiff`.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- New `src/openfactory/app/classifier_prompt.py`. It is pure, imports from `openfactory.domain` only, and contains `build_classifier_prompt(old: SpecSet, new: SpecSet, diff: SpecDiff, rejections: Sequence[ClassifierRejection] = ()) -> str`.
  - The modified set is the requirements of `diff` with `change == "modified"`, in ascending id. This is the reading TASK-092 approved.
  - Each requirement's `from` version is read from `old` and its `to` version from `new`.
  - Each version's ADR bodies come from that version's own spec set.
- The retry section uses `rejection_lines` from `domain/plan_checks.py`, which already takes the read-only `Rejection` Protocol (TASK-092).
- New `tests/unit/test_classifier_prompt.py`.
- One conformance test in `tests/unit/test_spec_conformance.py`: the instructions name every kind of the spec's `ChangeClass.kind` Literal.

Out:
- The call, the run events, `AgentRunStarted.context_hash`, the retry loop and `classifier call failed` (item 3).
- What `impact` does when no requirement is modified: no call is made (item 3).
- Moving `context_hash` (Design choice 2 proposes it stays where it is).
- Excluding requirements that are deprecated in both versions (Later line, TASK-091 and TASK-092). This task takes the modified set as given.

## Acceptance criteria
- [ ] **AC1** ("Step 2": "for each modified requirement in ascending id, its `from` and `to` versions with their acceptance criteria"):
  - After the instructions, the prompt has one block per `modified` requirement of the diff, in ascending id.
  - Each block shows the `from` version (from `old`) and then the `to` version (from `new`). Each version gives its id, title, statement, priority, components, `constrained_by` ids, and every acceptance criterion as id and text.
  - A requirement whose change is `added`, `removed`, `deprecated` or `unchanged` does not appear.
- [ ] **AC2** ("Step 2": "and the bodies of the ADRs each version is constrained by"; decision row SC-172):
  - Under each version are the bodies of the ADRs in that version's `constrained_by`, read from that version's spec set. Each body sits in an `<adr id="...">` delimiter, as in the planner prompt.
  - A modified ADR shows its old body under `from` and its new body under `to`.
  - An ADR named by only one version appears only under that version.
  - An ADR that no modified requirement names does not appear.
- [ ] **AC3** ("Step 2": "fixed instructions that define the three kinds"; "It replies `{"changes": [ChangeClass, ...]}`, one entry per modified requirement"; "`cosmetic` changes (wording only) … trigger no work"):
  - The instructions name and define `cosmetic`, `behavioral` and `replacement`. `cosmetic` is described as wording only, triggering no work.
  - The instructions give the reply form `{"changes": [...]}` with the five fields `req_id`, `kind`, `rationale`, `obsolete_criteria` and `new_work`, and ask for one entry per modified requirement.
  - The instruction text does not change with the arguments.
  - A conformance test reads the three kind names from the spec's `ChangeClass` block and finds each in the instructions.
- [ ] **AC4** ("Classifier checks": "A rejected reply is retried once … as for a planner reply"; "Plan checks": "retried once with the same prompt and the rejection lines added to it"):
  - With `rejections` the prompt is the text without them, followed by a last section that holds `rejection_lines(rejections)` (`rule  subject  message`, sorted).
  - The rejected reply is not in the prompt.
  - With no rejections there is no such section.
- [ ] **AC5** ("Event payloads": "`context_hash`: the SHA-256 of the run's prompt text encoded as UTF-8"; CLAUDE.md "app: use cases, depends on domain + ports only"):
  - Equal arguments give equal text. A change to a modified requirement's `to` statement, or to an ADR body under a version, gives a different `context_hash` (the existing function in `app/planner_prompt.py`).
  - The inputs are not mutated.
  - `app/classifier_prompt.py` imports nothing from `openfactory` outside `openfactory.domain`.
  - The existing planner, review and context-pack tests pass without edits.

## Architecture rules that apply
- `app` module, pure: no I/O, no ports used, no events recorded, no projection touched.
- Like `review_prompt.py` and `context_pack.py`, the module does not import `context_hash`. The caller takes the hash, which happens in item 3.
- The prompt holds no file contents.

## Plan
1. Create branch `task/TASK-093-classifier-prompt` from an up-to-date main.
2. Record the human's answers to Design choices 1 to 3 in this record.
3. Test-writer: failing tests `test_task093_ac<N>_...` in a new `tests/unit/test_classifier_prompt.py`.
   - Build small `SpecSet` pairs inline:
     - REQ-AUTH-001 modified, with AC-AUTH-001-1 removed and AC-AUTH-001-3 added;
     - REQ-AUTH-002 modified only through ADR-001's body;
     - REQ-AUTH-003 added and REQ-AUTH-004 unchanged.
   - Get the diff with `diff_specs`.
   - Add the AC3 conformance test to `tests/unit/test_spec_conformance.py`.
4. Implement `app/classifier_prompt.py`:
   - `_INSTRUCTIONS`, worded per Design choices 1 and 3;
   - a private version-text helper (its own, not `planner_prompt`'s private `_requirement_text`);
   - `_section`;
   - `build_classifier_prompt`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Docs:
   - `docs/architecture.md`: a new "Classifier prompt" section after "Review prompt". In the "Planner prompt" section, note that `context_hash` serves every role.
   - `docs/progress.md`: Current, a Done line, outline item 1b marked done, and the TASK-031 `context_hash` Later line removed.
   - `docs/decisions.md`: one row per answered design choice.
   - This record's Outcome.
7. Commit `feat(app): add the classifier prompt` with trailers `Task: TASK-093` and `Milestone: M6`. Do not push.

## Files expected to change
- `src/openfactory/app/classifier_prompt.py` (new, about +110)
- `tests/unit/test_classifier_prompt.py` (new, about +180)
- `tests/unit/test_spec_conformance.py` (one new test, about +15)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, this record

Not expected to change: `app/planner_prompt.py`, `app/review_prompt.py`, `app/plan.py`, `app/run.py`, `domain/`, ports, adapters, `cli.py`, `docs/spec/`, `docs/adr/`.

## Design choices to confirm at planning
1. **Wording of the three kinds.** This is the module's own instruction text; the spec defines only `cosmetic` ("wording only … trigger no work"). See Spec gaps.
   - Proposed:
     - `cosmetic`: the wording changed but the required behaviour did not. No work, `obsolete_criteria` and `new_work` empty.
     - `behavioral`: the requirement keeps its purpose, but what the system must do changed (added, removed or altered behaviour or criteria). Existing work is revised.
     - `replacement`: the requirement now asks for a different way of meeting its purpose, so the existing implementation is replaced. The demo example: authentication by membership number becomes OTP.
   - Alternative: define only `cosmetic` from the spec and leave the other two names undefined until a `/spec-change` defines them.
2. **Where `context_hash` lives** (TASK-031 Later line).
   - Proposed: it stays in `app/planner_prompt.py`. `plan.py`, `run.py` (implementer and reviewer runs) and the `impact` use case (item 3) import it from there. The classifier module does not import it, as `review_prompt.py` and `context_pack.py` already work. No code change and no fixed test edited. The Later line closes with a decisions.md row.
   - Alternative A: move it to a neutral module (for example `app/prompt_hash.py`) and update the imports in `plan.py`, `run.py` and five test files. Those are import-path edits to fixed tests, needing the human's approval.
   - Alternative B: move it and keep a re-export in `planner_prompt.py`.
3. **Should the instructions also state the checks?** The planner prompt states what the plan checks enforce.
   - Proposed: yes, state them in plain words:
     - one entry per modified requirement and none for any other, no requirement twice;
     - `obsolete_criteria` holds only criterion ids of the `from` version;
     - a `cosmetic` entry has empty `obsolete_criteria` and `new_work`, and is not used for a requirement that lost a criterion.

     This is the same precedent. It should cut retries, and leaves the checks themselves unchanged.
   - Alternative: the kinds and the reply form only, the minimum the spec names.

## Answers (human, 2026-10-24)
Approved as proposed: 1. the proposed definitions of the three kinds, with the Spec wording Later line; 2. `context_hash` stays in `app/planner_prompt.py`, closed by a decisions.md row; 3. the instructions state the classifier checks in plain words.

## Open questions
None beyond the design choices and the spec item below.

## Spec gaps
- **"Spec diff and impact analysis" › "Step 2": "fixed instructions that define the three kinds".**
  - Unclear: the spec defines `cosmetic` ("wording only"), but gives no definition for `behavioral` or `replacement`. Both are seeds (Step 3), so they behave the same in the code. Eval measures accuracy of `ChangeClass.kind` against hand labels (M7), so the line between the two matters for the labels.
  - Why it does not block: the definitions are prompt text this module owns, and no deterministic behaviour depends on them. Design choice 1 asks the human to pick the wording, and no assumption is coded without that answer.
  - Suggested: add one-line definitions of the two kinds at the next `/spec-change` (with F-1, F-2 and F-7), before M7 eval cases are labelled. Recorded as a Later line.
- **Existing Later line (TASK-091 and TASK-092): a requirement deprecated in both versions is `modified` read literally.** It would appear in this prompt too. This task takes the modified set from the diff as given, as TASK-092 did. The settlement before item 3 decides whether the diff or the use case filters it. Nothing new to raise.

## Outcome
- Added `src/openfactory/app/classifier_prompt.py` (`build_classifier_prompt`), `tests/unit/test_classifier_prompt.py` and one conformance test in `tests/unit/test_spec_conformance.py`. No `domain/`, port, adapter, `cli.py` or other `app/` change.
- Design choices 1 to 3 implemented as approved; three rows in `docs/decisions.md`. The TASK-031 `context_hash` Later line is removed.
- Test edits by the implementer: none. Spec wording Later line (`behavioral` and `replacement` undefined) kept.
- Docs: `docs/architecture.md` (new "Classifier prompt", `context_hash` note), `docs/progress.md`, `docs/decisions.md`.
- Results: pytest 1900 passed, ruff, pyright and check_docs pass.
