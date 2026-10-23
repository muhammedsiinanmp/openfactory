# TASK-092: Classifier reply, its checks and the lost criteria

- Milestone: M6
- Status: done
- Tests: acceptance
- ADR: ADR-019 (accepted). Its "Classifier" bullet: "reply `{"changes": [ChangeClass]}` with `extra="forbid"`; the checks `schema`, `unknown-requirement`, `duplicate-requirement`, `missing-requirement`, `unknown-criterion` and `cosmetic-with-work`; one retry." This task adds one pure domain module and widens the type of `rejection_lines`. It adds no port, adapter, event type, payload change, table or dependency.
- Spec impact: wording (see Spec gaps; none blocks)
- Spec sections (spec v1.18; SC-161, SC-171, SC-172):
  - "Spec diff and impact analysis" › "Step 2: change classification (LLM, validated)": "It replies `{"changes": [ChangeClass, ...]}`, one entry per modified requirement", then the `ChangeClass` block (`req_id`, `kind: Literal["cosmetic", "behavioral", "replacement"]`, `rationale`, `obsolete_criteria`, `new_work`, `extra="forbid"`).
  - Same section: "A criterion of a modified requirement that is absent from `to` is always obsolete: it is added to that requirement's `obsolete_criteria` whatever the classifier says."
  - "Spec diff and impact analysis" › "Classifier checks": the six-rule table, and "The rules of the plan checks for counting rejections, their messages and a `schema` rejection apply here too."
  - "Task contract" › "Plan checks", the paragraph after the table: "There is one rejection per subject and offending id, and the message names the offending id … A `schema` rejection for a Pydantic error has the field path in its message. When there is any `schema` rejection, the other checks are not run. There is one `schema` rejection per Pydantic error. A reply whose structured result is missing is one `schema` rejection with subject `reply` and the message `no structured result`."
  - "Task contract" › "Plan checks": "`AgentRunFinished` is recorded after the checks: a rejected reply has … `error` set to its rejection lines, as `rule  subject  message` in the sorted order `plan` prints them".
  - "Domain model and storage" › "Event payloads", the paragraph after the block: "then they are the classifier's, with the criteria that `to` lost added to `obsolete_criteria` …, sorted as strings."

## Outline item
M6 outline item 1, first half (1a). The prompt builder moves to 1b, the next task: a new `app/classifier_prompt.py` following the `app/planner_prompt.py` precedent, which settles the Later line on where `context_hash` lives. The split keeps both tasks under about 300 to 400 lines. Plan step 6 updates the outline.

## Objective
A new pure `domain/classifier.py` with five pieces:
- `ChangeClass` and the reply model;
- the `schema` rule (`parse_classifier_reply`);
- the five content checks (`check_classification`), with the subjects and messages the plan checks use;
- `add_lost_criteria`, which adds every criterion `to` lost to a modified requirement's `obsolete_criteria`.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- New `src/openfactory/domain/classifier.py`. It is pure and imports only `openfactory.domain.payloads` (`ChangeKind`), `openfactory.domain.spec_diff`, `openfactory.domain.plan_checks` (only if Design choice 2 is taken that way), pydantic and the standard library. It contains:
  - `ChangeClass`: the spec block, plus `frozen=True` (the `ReviewVerdict` precedent), with `kind: ChangeKind`.
  - `ClassifierReply(changes: list[ChangeClass])`, frozen, `extra="forbid"`.
  - `ClassifierRule` StrEnum: `schema`, `unknown-requirement`, `duplicate-requirement`, `missing-requirement`, `unknown-criterion`, `cosmetic-with-work`.
  - Frozen `ClassifierRejection(rule, subject, message)` (Design choice 2).
  - Frozen `ParsedClassification(changes: list[ChangeClass] | None, rejections)`.
  - `parse_classifier_reply(structured: object | None) -> ParsedClassification`.
  - `check_classification(changes, diff: SpecDiff) -> list[ClassifierRejection]`.
  - `add_lost_criteria(changes, diff: SpecDiff) -> list[ChangeClass]`.
- Inputs: the modified set is the requirements of `diff` with `change == "modified"`. A requirement's `from` criteria are its `CriterionDiff`s whose change is not `added`. The criteria it lost are those whose change is `removed`.
- `domain/plan_checks.py`: `rejection_lines` accepts classifier rejections too (Design choice 2). Its output for plan rejections is unchanged.
- New `tests/unit/test_classifier.py`, and one conformance test in `tests/unit/test_spec_conformance.py` tying `ChangeClass`'s fields to the spec block.

Out:
- The classifier prompt (item 1b) and `context_hash`.
- The call, its retry, the run events and the `classifier call failed` line (item 3).
- Building `RequirementImpact` entries, filtering `unchanged`, and sorting `new_work` (item 3; see Spec gaps).
- Seeds and traversal (item 2).
- Changing which requirements are `modified` (see Spec gaps, deprecated in both versions).

## Acceptance criteria
- [x] **AC1** ("Step 2" › the `ChangeClass` block and "It replies `{"changes": [ChangeClass, ...]}`"):
  - `ChangeClass` has exactly `req_id`, `kind`, `rationale`, `obsolete_criteria`, `new_work`, all required. `ClassifierReply` has exactly `changes`.
  - Both are frozen and reject an unknown key.
  - `kind` accepts `cosmetic`, `behavioral` and `replacement`, and rejects anything else.
  - A conformance test reads the field names from the spec's `ChangeClass` block.
- [x] **AC2** ("Classifier checks" › `schema`; "Plan checks" paragraph on `schema` rejections):
  - `parse_classifier_reply(None)` gives exactly one rejection, `schema  reply  no structured result`, and `changes` `None`.
  - A reply that Pydantic rejects gives one `schema` rejection per Pydantic error, message `<field path>: <msg>`, and `changes` `None`.
  - The subject is the entry's `req_id` when the error lies in an entry whose `req_id` is a string, and `reply` otherwise (top-level error, non-string `req_id`, entry not an object).
  - A valid reply gives its `changes` and no rejections.
- [x] **AC3** ("Classifier checks" › `unknown-requirement`, `duplicate-requirement`, `missing-requirement`):
  - An entry whose `req_id` is not a `modified` requirement of the diff gives `unknown-requirement`, subject that `req_id`. This covers one absent from the diff and one that is `added`, `removed`, `deprecated` or `unchanged`.
  - Two or more entries with the same `req_id` give one `duplicate-requirement` for that id.
  - A `modified` requirement with no entry gives `missing-requirement`, subject that requirement id.
  - With no modified requirement and no entries, there are no rejections.
- [x] **AC4** ("Classifier checks" › `unknown-criterion`, `cosmetic-with-work`):
  - An id in an entry's `obsolete_criteria` that is not a criterion of that requirement's `from` version gives `unknown-criterion`, subject the `req_id`. This covers a criterion `added` in `to` and an id in neither version. A `removed`, `modified` or `unchanged` criterion is accepted.
  - A `cosmetic` entry with a non-empty `obsolete_criteria`, a non-empty `new_work`, or a requirement with a `removed` criterion gives `cosmetic-with-work`, subject the `req_id`.
  - A `behavioral` or `replacement` entry with work, and a `cosmetic` entry with neither, give none.
- [x] **AC5** ("Plan checks": "one rejection per subject and offending id, and the message names the offending id"; "rejection lines, as `rule  subject  message` in the sorted order"):
  - One rejection per subject and offending id. An unknown criterion listed twice in one entry, or across two duplicate entries, gives one rejection. Two different unknown criteria give two. `cosmetic-with-work` gives one per `req_id`.
  - Every message contains its offending id.
  - `rejection_lines` prints classifier rejections as `rule  subject  message`, sorted as for plan rejections.
  - Its output for plan rejections is unchanged: the existing tests pass without edits.
- [x] **AC6** ("Step 2": "A criterion of a modified requirement that is absent from `to` is always obsolete …"; "Event payloads": "… added to `obsolete_criteria` …, sorted as strings"; CLAUDE.md "domain: pure models and rules. No I/O"):
  - `add_lost_criteria` returns each entry with every `removed` criterion of its `modified` requirement in `obsolete_criteria`, whatever the classifier gave, with no id twice, sorted as strings (Design choice 3).
  - It changes nothing else, and leaves entries of requirements with no lost criterion as they were apart from the order.
  - Its inputs are not mutated, and two calls give equal results.
  - `domain/classifier.py` imports nothing from `openfactory` outside `openfactory.domain`.

## Architecture rules that apply
- `domain` stays pure: no I/O, no imports from ports, adapters, app or `cli.py`.
- The checks never return `schema`, mirroring `check_plan`. The use case runs them only when `parse_classifier_reply` gave no rejections ("When there is any `schema` rejection, the other checks are not run").
- No event is recorded and no projection is touched.

## Plan
1. Create branch `task/TASK-092-classifier-reply-and-checks` from an up-to-date main.
2. Record the human's answers to Design choices 1 to 4 in this record.
3. Test-writer: failing tests `test_task092_ac<N>_...` in a new `tests/unit/test_classifier.py`. Build small `SpecDiff`s inline (REQ-AUTH-001 modified with AC-AUTH-001-1 removed and AC-AUTH-001-3 added, REQ-AUTH-002 unchanged, REQ-AUTH-003 added). Add the AC1 conformance test to `tests/unit/test_spec_conformance.py`.
4. Implement `domain/classifier.py`:
   - the models and `ClassifierRule`;
   - `parse_classifier_reply` with a `_schema_subject` over `changes[i].req_id`;
   - the five checks in table order (`unknown-requirement`, `duplicate-requirement`, `missing-requirement`, `unknown-criterion`, `cosmetic-with-work`);
   - `add_lost_criteria`.
   Then widen `rejection_lines` per Design choice 2.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Docs:
   - `docs/architecture.md`: a new "Classifier" section after "Spec diff", and the `rejection_lines` line.
   - `docs/progress.md`: Current, a Done line, outline item 1 split into 1a (done) and 1b (prompt builder, `context_hash` Later line), and a Later line for the spec items below.
   - `docs/decisions.md`: one row per answered design choice.
   - This record's Outcome.
7. Commit `feat(domain): add the classifier reply and checks` with trailers `Task: TASK-092` and `Milestone: M6`. Do not push.

## Files expected to change
- `src/openfactory/domain/classifier.py` (new, about +160)
- `src/openfactory/domain/plan_checks.py` (about ±10, `rejection_lines` typing)
- `tests/unit/test_classifier.py` (new, about +200)
- `tests/unit/test_spec_conformance.py` (one new test, about +15)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, this record

Not expected to change: `domain/payloads.py`, `domain/spec_diff.py`, `app/`, ports, adapters, `cli.py`, `docs/spec/`, `docs/adr/`.

## Design choices to confirm at planning
1. **Place and names.**
   - Proposed: a new `domain/classifier.py` with `ChangeClass`, `ClassifierReply`, `ClassifierRule`, `ClassifierRejection`, `ParsedClassification`, `parse_classifier_reply`, `check_classification` and `add_lost_criteria`. `kind` reuses `ChangeKind` from `payloads.py`, as TASK-090 Design choice 1 foresaw.
   - Alternative: put them in `domain/spec_diff.py`. TASK-091's decision says "`ChangeClass` can get its own module".
2. **Rejection type.** The spec says the classifier's rule names are not the plan's ("These names are the plan's own set"). The plan checks lack `duplicate-requirement`, `missing-requirement` and `cosmetic-with-work`, so reusing `PlanRejection` as the reviewer does (TASK-069 row) does not fit.
   - Proposed: an own `ClassifierRule` and `ClassifierRejection`. `rejection_lines` in `plan_checks.py` is typed over a small read-only Protocol (`rule: StrEnum`, `subject`, `message`), so one function keeps one format and sort, and `plan_checks.py` does not import `classifier.py`.
   - Alternative A: widen `PlanRejection.rule` to `PlanRule | ClassifierRule`.
   - Alternative B: a separate `classifier_rejection_lines` in `classifier.py`, which repeats the three-line sort.
3. **Shape of `obsolete_criteria` after `add_lost_criteria`.**
   - Proposed: the sorted set union of the classifier's ids and the lost ids. Adding an id already listed leaves it once, and the result is sorted as strings, as the payload paragraph asks. This also removes duplicates the classifier itself gave; no check rejects those.
   - Alternative: keep the classifier's list as given (duplicates and order included), and append only the lost ids not already present, leaving sorting to the payload builder (item 3).
4. **What the checks read.**
   - Proposed: only the `SpecDiff`. The modified set is `change == "modified"`, the `from` criteria are those not `added`, and the lost ones are `removed`. This needs no second `SpecSet` argument.
   - Alternative: also pass the `from` `SpecSet` and read criteria from it.

## Answers (human, 2026-10-24)
Design choices 1 to 4 and the spec-gap handling are approved as proposed. Design choice 2: the Protocol in `plan_checks.py` declares its members as read-only `@property`s (advisor). The deprecated-in-both-versions Later line of TASK-091 is merged into the TASK-092 one, with the deadline moved to before M6 item 3.

## Open questions
None beyond the design choices and the spec items below.

## Spec gaps
- **"Spec diff and impact analysis" › Step 1 and Step 2: a requirement deprecated in both versions** (Later line, TASK-091 reviewer).
  - Unclear: if its hash differs, or an ADR in its `constrained_by` changed, Step 1 read literally makes it `modified`. Step 2 then sends it to the classifier, and Step 3 may seed it. Whether this is meant is not stated. The "is `deprecated` instead" sentence covers only one not deprecated (or absent) in `from`.
  - Why it does not block: this task takes the `modified` set from the diff as given and follows the literal reading. Whichever way it is settled (the diff excludes it, or the use case filters it), the checks are unchanged.
  - To raise: settle on purpose with `/spec-change`, together with F-1, F-2 and the SC-169 wording (F-7), before outline item 3 (`impact`). Not filled with an assumption here.
- **"Event payloads", the paragraph after the block: "… with the criteria that `to` lost added to `obsolete_criteria` …, sorted as strings."**
  - Unclear: whether "sorted as strings" covers `new_work` too, or only `obsolete_criteria`. The report example's `new-work` lines happen to be in string order.
  - Why it does not block: this task sorts only `obsolete_criteria` (Design choice 3) and leaves `new_work` as the classifier gave it. Building the payload is item 3.
  - Suggested: clarify at the next `/spec-change`, or settle when item 3 is planned.
- **"Classifier checks" › `unknown-criterion` for an entry whose `req_id` is not a modified requirement.** This is a reading, not a gap. "Not a criterion of the `from` version of that requirement" is read against the diff's criteria for that id, so a requirement absent from `from` has none. Such an entry is already rejected by `unknown-requirement`, and a second rejection under another rule is allowed (the counting rule is per rule, subject and offending id).

## Outcome
Built:
- New pure `src/openfactory/domain/classifier.py`: `ChangeClass`, `ClassifierReply`, `ClassifierRule`, `ClassifierRejection`, `ParsedClassification`, `parse_classifier_reply`, `check_classification` and `add_lost_criteria`, as planned and with the approved design choices 1 to 4.
- `domain/plan_checks.py`: a read-only `Rejection` Protocol; `rejection_lines` takes `Sequence[Rejection]`; its output for plan rejections is unchanged and the existing tests pass without edits.
- New `tests/unit/test_classifier.py` and one conformance test in `tests/unit/test_spec_conformance.py`.
- `ClassifierRule` members are UPPER_CASE, because the test-writer's tests fix those names.

Test edit (non-mechanical, approved by the human, advisor AGREE): in `test_task092_ac5_messages_name_the_offending_id` the first loop input changed from `[entry(req_id="REQ-AUTH-003")]` to `[entry(), entry(req_id="REQ-AUTH-003")]`, because `missing-requirement` for REQ-AUTH-001 correctly fires too. The assertion is unchanged. `ruff format` also re-wrapped one line of the test file.

Reviewer fix (round 1, blocking): `unknown-criterion` read the known criteria only from modified requirements, so an entry for an unchanged, removed or deprecated requirement naming a real `from` criterion got a false rejection; it now reads every requirement of the diff (criteria not `added`). One test added, `test_task092_ac4_from_criteria_of_a_requirement_not_modified_are_accepted`; no existing test changed.

Checks: 1886 tests pass; ruff, pyright and `check_docs` clean.

Docs: `docs/architecture.md` (Classifier section, `rejection_lines`), `docs/progress.md` (item 1 split into 1a done and 1b), `docs/decisions.md` (six rows).
