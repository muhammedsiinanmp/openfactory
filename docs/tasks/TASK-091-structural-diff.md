# TASK-091: Structural diff of two stored spec sets

- Milestone: M6
- Status: done
- Tests: acceptance
- ADR: ADR-019 (accepted). Its "Classifier" bullet: "ADR changes and newly deprecated requirements are decided by rules, not by the model (SC-161, SC-167, SC-169 …)"; its "Ports" bullet: "the diff reads `SpecVersions`". This task adds a pure domain module only: no port, adapter, event type, payload change, table, dependency or convention.
- Spec impact: wording (see Spec gaps)
- Spec sections (spec v1.18; SC-167, SC-169):
  - "Spec diff and impact analysis" › "Step 1: structural diff (deterministic)": "Compare the stored spec sets of `from` and `to` by ID and content hash. Each requirement, ADR and acceptance criterion is `added`, `removed`, `modified` or `unchanged`. A requirement that is deprecated in `to` and was not in `from` is `deprecated` instead: it is not classified, and no new work is planned for it. A requirement that is otherwise `unchanged` counts as `modified` when an ADR in the `constrained_by` of either of its versions is `added`, `removed` or `modified`."
  - "Spec diff and impact analysis", first paragraph: "a structural diff that finds which requirements changed … The LLM only classifies the change; it never decides what is affected."
  - "Spec input format" › "Hashing": "A requirement's hash covers the whole requirement, including its acceptance criteria, so changing a criterion makes its requirement `modified`." / "An ADR's hash covers `id`, `status` and `body`." / "An acceptance criterion's hash covers `id` and `text`. It is not stored; it is computed when the diff needs it."
  - "Spec diff and impact analysis" › Step 2: "A criterion of a modified requirement that is absent from `to` is always obsolete" (context only: this task supplies the criterion changes, item 2 uses them).

## Outline item
M6 outline item 1 in `docs/progress.md`, the whole item. TASK-090 was a payload task that came before the outline's item 1, even though its Done line says "M6 item 1 done". This task fixes that line (Plan step 6).

## Objective
A new pure domain function `diff_specs(old: SpecSet, new: SpecSet) -> SpecDiff` gives the change of every requirement, ADR and acceptance criterion between two stored spec sets, applying the `deprecated` rule and the ADR rule of Step 1.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- New `src/openfactory/domain/spec_diff.py`, pure, importing only `openfactory.domain.models`, `openfactory.domain.spec_hash`, pydantic and the standard library:
  - `ItemChange = Literal["added", "removed", "modified", "unchanged"]` and `DiffRequirementChange = Literal["added", "removed", "modified", "deprecated", "unchanged"]`.
  - Frozen models, all `extra="forbid"`: `CriterionDiff(id, change: ItemChange)`, `RequirementDiff(id, change: DiffRequirementChange, criteria: list[CriterionDiff])`, `AdrDiff(id, change: ItemChange)`, `SpecDiff(requirements: list[RequirementDiff], adrs: list[AdrDiff])`.
  - Every list is sorted by id as strings, and `unchanged` items are included (Open question 2).
  - `diff_specs(old, new)` compares by id and `content_hash`.
- New `tests/unit/test_spec_diff.py`.

Out:
- Reading the spec sets through `SpecVersions` (the `impact` use case, item 4).
- The classifier, `ChangeClass` and adding the removed criteria to `obsolete_criteria` (item 2).
- Seeds and traversal (item 3).
- Building `ImpactComputedPayload` entries (item 4).
- Duplicate ids inside one set: an approved set has passed `id-unique`.

## Acceptance criteria
- [x] **AC1** (Step 1 by ID and content hash; Hashing: a requirement's hash covers the whole requirement):
  - A requirement only in `new` is `added`, one only in `old` is `removed`.
  - One in both with an equal `content_hash` is `unchanged`; with a different hash (title, statement, priority, criterion text, `constrained_by`, `components`) it is `modified`.
  - A pure reordering of the list in the files (same models in a different order) gives `unchanged`.
  - `SpecDiff.requirements` holds every id of either set exactly once, sorted by id.
- [x] **AC2** (Step 1 for ADRs; Hashing: an ADR's hash covers `id`, `status` and `body`):
  - An ADR is `added` when only in `new`, `removed` when only in `old`, `modified` when its `status` or `body` differs, `unchanged` otherwise.
  - `SpecDiff.adrs` holds every ADR id of either set once, sorted by id.
- [x] **AC3** (Step 1 for criteria; Hashing: a criterion's hash covers `id` and `text`, computed when the diff needs it):
  - Each `RequirementDiff.criteria` compares that requirement's criteria in `old` and `new` by id and `content_hash`, sorted by id.
  - A criterion whose text changed is `modified`, a dropped one `removed`, a new one `added`.
  - For an `added` requirement every criterion is `added`; for a `removed` one every criterion is `removed` (Open question 3).
- [x] **AC4** (Step 1: "A requirement that is deprecated in `to` and was not in `from` is `deprecated` instead"):
  - `deprecated: false` in `old` and `deprecated: true` in `new` is `deprecated`, whether or not anything else changed; its criteria are still diffed.
  - Deprecated in both and otherwise equal is `unchanged`.
  - Deprecated in `old` and not in `new` is `modified`, as the hash rule gives.
  - Absent from `old` and deprecated in `new` follows Open question 1.
- [x] **AC5** (Step 1 ADR rule):
  - A requirement whose own hash is equal is `modified` when an ADR it names in `constrained_by` is `modified`, `added` or `removed`.
  - It stays `unchanged` when only an ADR it does not name changed.
  - The rule never turns an `added`, `removed` or `deprecated` requirement into `modified`.
  - Its criteria stay as their own hashes give (all `unchanged` here).
- [x] **AC6** (deterministic; CLAUDE.md "domain: pure models and rules. No I/O"):
  - `domain/spec_diff.py` imports nothing from `openfactory` outside `openfactory.domain`.
  - The result models are frozen and forbid unknown fields.
  - `diff_specs` called twice on the same inputs gives equal results, and leaves its inputs unchanged.

## Architecture rules that apply
- `domain` stays pure: no I/O, no imports from ports, adapters, app or `cli.py`.
- The diff reuses `content_hash` from `domain/spec_hash.py`, so the hashing rule lives in one place.
- No event is recorded and no projection is touched.

## Plan
1. Create branch `task/TASK-091-structural-diff` from an up-to-date main.
2. Record the human's answers to Open questions 1 to 4 in this record.
3. Test-writer: failing tests `test_task091_ac<N>_...` in a new `tests/unit/test_spec_diff.py`, built from small inline `SpecSet`s (REQ-AUTH-001/002, ADR-001/002, AC-AUTH-001-1/2).
4. Implement `domain/spec_diff.py`: index both sets by id; diff the ADRs; diff each requirement by hash; apply the `deprecated` rule, then the ADR rule to the `unchanged` ones; diff the criteria; sort.
5. Run tests, ruff, pyright and check_docs until all pass.
6. Docs: `docs/architecture.md` new "Spec diff" section next to "Spec hashing"; `docs/progress.md` Current, Done line, item 1 removed from the M6 outline, the TASK-090 Done line's "M6 item 1 done" corrected to "the payload model before M6 item 1"; `docs/decisions.md` one row per answered open question; Outcome.
7. Commit `feat(domain): add the structural spec diff` with trailers `Task: TASK-091` and `Milestone: M6`. Do not push.

## Files expected to change
- `src/openfactory/domain/spec_diff.py` (new, about +70)
- `tests/unit/test_spec_diff.py` (new, about +170)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, this record

Not expected to change: `domain/payloads.py`, `domain/spec_hash.py`, `domain/models.py`, ports, adapters, app, `cli.py`, `docs/spec/`, `docs/adr/`.

## Open questions
1. **A requirement absent from `from` and deprecated in `to`.** Read literally ("was not in `from`") it is `deprecated`; under the audit's F-7 reading ("not deprecated in `from`") the line does not say, and the base rule would make it `added`.
   - Proposed: `deprecated`. "Not deprecated in `from`", with absence counting as not deprecated, satisfies both readings. The traversal is the same either way (a new requirement has no `contract` links); only the reported and stored `change` differs.
   - Alternative: `added`.
2. **Result shape.**
   - Proposed: `SpecDiff` lists every id of either set, `unchanged` included, sorted by id. The use case filters out `unchanged` when it builds the payload.
   - Alternative: list only changed items, reusing `RequirementChange` and `AdrChange` from `payloads.py`, with criteria only on `modified` and `deprecated` requirements.
3. **Criteria of `added` and `removed` requirements.**
   - Proposed: diff them against an empty side, so all are `added` or all are `removed`.
   - Alternative: an empty `criteria` list for `added` and `removed` requirements.
4. **Names and place.**
   - Proposed: new `domain/spec_diff.py` with `diff_specs`, `SpecDiff`, `RequirementDiff`, `AdrDiff`, `CriterionDiff`, `ItemChange`, `DiffRequirementChange`.
   - Alternative: `domain/impact.py`, which item 2's `ChangeClass` could join.

## Answers (human, 2026-10-24: approved the plan with the proposed answers)
1. `deprecated`: a requirement absent from `from` and deprecated in `to` is `deprecated` (absence counts as not deprecated in `from`).
2. `SpecDiff` lists every id, `unchanged` included, sorted by id, with its own Literals; the use case filters.
3. Criteria of `added` and `removed` requirements are diffed against an empty side.
4. New `domain/spec_diff.py` with the proposed names.

## Spec gaps
- "Spec diff and impact analysis" › "Step 1: structural diff (deterministic)": "A requirement that is deprecated in `to` and was not in `from` is `deprecated` instead."
  - Unclear: read literally, this means a requirement absent from `from`. Audit F-7 / M-3 of `docs/spec-audits/2026-10-24-proposal-v1.18.md` says SC-169 means "not deprecated in `from`"; the fix did not reach v1.18.
  - Why it does not block: the main case (present and not deprecated in `from`, deprecated in `to`) is clear and AC4 tests it; only a requirement added already deprecated differs (Open question 1), and the traversal is the same.
  - Suggested: fix the wording with `/spec-change` at the next spec round, with F-1 and F-2.

Readings, not gaps:
- A requirement deprecated in both versions is diffed by hash. One deprecated in `from` and not in `to` is `modified` (existing Later line, SC-169).
- Criteria are diffed within their requirement; a criterion id moved to another requirement shows as `removed` under one and `added` under the other.
- The ADR rule reads `constrained_by` from both versions; with an equal hash those lists are the same.

## Outcome
Built `src/openfactory/domain/spec_diff.py`: `diff_specs(old, new) -> SpecDiff` with frozen `SpecDiff`, `RequirementDiff`, `AdrDiff`, `CriterionDiff` and the Literals `ItemChange` and `DiffRequirementChange`. Items are compared by id and `content_hash`; the `deprecated` rule and the ADR rule of Step 1 are applied; criteria are diffed per requirement, against an empty side for `added` and `removed` requirements. New `tests/unit/test_spec_diff.py` (27 tests, AC1 to AC6).
- Deviations from the plan: none.
- Test edits: none; the test-writer's tests are unchanged.
- Docs: `docs/architecture.md` "Spec diff", `docs/progress.md`, four rows in `docs/decisions.md` for the answers to the open questions.
- Follow-up: the spec wording of SC-169 (audit F-7), already a Later line in `docs/progress.md`.
