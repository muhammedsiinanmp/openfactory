# TASK-098: Diff and classifier rules from spec v1.19

- Milestone: M6
- Status: done
- Tests: acceptance
- ADR: ADR-019 (amended for spec v1.19). Its Classifier bullet says deprecated requirements "are decided by rules, not by the model". The decisions.md rows SC-190, SC-200 and SC-202 (2026-10-24) record the three rules. The task adds no port, adapter, event type, payload field, table, dependency or convention, so no new ADR is needed. The provisional TASK-095 row (deprecated-in-both stays `modified`) is superseded by SC-200; that row is left as history.
- Spec impact: none
- Spec sections (spec v1.19):
  - "Spec diff and impact analysis" › "Step 1: structural diff (deterministic)":
    - "A requirement deprecated in both `from` and `to` is `unchanged`, whatever its hash or ADRs." (SC-200)
    - "A requirement deprecated in `from` and not deprecated in `to` is `added`; its criteria are diffed against an empty side." (SC-202)
    - Unchanged text: "Compare the stored spec sets of `from` and `to` by ID and content hash. Each requirement, ADR and acceptance criterion is `added`, `removed`, `modified` or `unchanged`." Also unchanged: "A requirement that is deprecated in `to` and absent or not deprecated in `from` is `deprecated` instead".
  - "Spec diff and impact analysis" › "Classifier checks", the `cosmetic-with-work` row: "an entry of kind `cosmetic` has a non-empty `obsolete_criteria` or `new_work`, or is for a requirement that lost or gained a criterion". (SC-190)
  - "Spec diff and impact analysis" › "Step 2: change classification (LLM, validated)": "Its prompt is fixed instructions that define the three kinds …". The prompt already states the classifier checks in plain words (TASK-093).

## Outline item
M6 outline item 4a in `docs/progress.md`. It must land before item 5 (plan checks). `compute_impact` passes `diff_specs`' result through as given, so after this task an un-deprecated requirement shows up in `ImpactComputed` as `added` and gets no classifier entry. A requirement deprecated in both versions is never a seed and never classified.

## Objective
Make `diff_specs` follow SC-200 and SC-202. Widen `cosmetic-with-work`, and the matching rule line in the classifier prompt, to cover a requirement that gained a criterion (SC-190).

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/domain/spec_diff.py`, `diff_specs`:
  - deprecated in both `old` and `new` gives `unchanged`. This is checked before the hash result and before the ADR rule.
  - deprecated in `old` and present and not deprecated in `new` gives `added`, with criteria from `_criteria(None, after)`.
  - The module docstring is updated.
- `src/openfactory/domain/classifier.py`, `_cosmetic_with_work`:
  - a `cosmetic` entry for a modified requirement with a criterion whose change is `added` is offending.
  - The message and the module docstring are updated: "a lost or gained criterion", and "the ones it gained are those `added`".
- `src/openfactory/app/classifier_prompt.py`, `_INSTRUCTIONS`: the last Rules bullet (line 40) also covers a criterion the `from` version lacks.
- New tests:
  - `test_task098_ac<N>_...` in `tests/unit/test_spec_diff.py`, `tests/unit/test_classifier.py` and `tests/unit/test_classifier_prompt.py`.
  - The one approved edit is listed under Design choice 1.

Out:
- `app/impact.py`, `cli.py`, payload models: no change.
- `add_lost_criteria`: a gained criterion is not obsolete, and the spec only adds lost ones.
- Plan checks, replan, `approve plan` after a replan (items 5 to 7).
- Hardening for odd inputs, such as a requirement deprecated in `from` and absent in `to`. That case is already `removed` under the unchanged text and keeps its current behaviour.

## Acceptance criteria
- [ ] **AC1** ("Step 1": "A requirement deprecated in both `from` and `to` is `unchanged`, whatever its hash or ADRs"):
  - A requirement deprecated in both sets is `unchanged`:
    - when its title, statement or criteria differ between the sets;
    - when an ADR in its `constrained_by` is `added`, `removed` or `modified`.
  - With nothing else changed it is still `unchanged`, which the existing test covers.
  - Its criteria are still listed by id and hash, as for any requirement.
- [ ] **AC2** ("Step 1": "A requirement deprecated in `from` and not deprecated in `to` is `added`; its criteria are diffed against an empty side"):
  - A requirement deprecated in `old` and not deprecated in `new` is `added`:
    - when nothing else changed;
    - when other fields changed;
    - when an ADR in its `constrained_by` changed.
  - Every one of its `new` criteria is listed as `added`, sorted by id. None is `unchanged`, `modified` or `removed`.
- [ ] **AC3** ("Step 1": unchanged sentences): regression guards for the rules this task must not disturb.
  - Newly deprecated (from not deprecated or absent) stays `deprecated`.
  - Deprecated in `old` and absent from `new` stays `removed`.
  - For requirements deprecated in neither set, the ADR rule still turns an otherwise `unchanged` requirement into `modified`.
  - Every id is still listed once, sorted.
- [ ] **AC4** ("Classifier checks", `cosmetic-with-work`: "… or is for a requirement that lost or gained a criterion"):
  - A `cosmetic` entry with empty `obsolete_criteria` and `new_work`, for a modified requirement whose diff has a criterion `added` and none `removed`, gets exactly one `cosmetic-with-work` rejection with that `req_id` as subject. Its message names the `req_id`.
  - A `behavioral` or `replacement` entry for that requirement gets no rejection.
  - A `cosmetic` entry for a modified requirement whose criteria are only `modified` or `unchanged` still passes.
- [ ] **AC5** ("Step 2": fixed instructions; "Classifier checks", `cosmetic-with-work`):
  - The prompt's instructions state that a requirement whose `to` version lacks a criterion of its `from` version, or has a criterion its `from` version lacks, is not cosmetic.
  - The instruction text is still the same whatever the arguments.
- [ ] **AC6** (CLAUDE.md, tests are fixed; "Step 1" as above):
  - The only `src/` files changed are the three named under Scope.
  - The full suite passes. The only edit to an existing test is the one approved under Design choice 1.
  - `test_impact.py` and `test_cli_impact.py`, and the existing tests in `test_classifier_prompt.py`, pass unedited.

## Architecture rules that apply
- `domain/spec_diff.py` and `domain/classifier.py` stay pure and import only `openfactory.domain`.
- `app/classifier_prompt.py` imports only domain and the standard library.

## Plan
1. Create branch `task/TASK-098-diff-classifier-v119-rules` from an up-to-date main.
2. Record the human's answers to the Design choices in this record.
3. Test-writer: write the failing `test_task098_` tests for AC1 to AC5, and apply the approved edit to `test_task091_ac4_undeprecated_is_modified`.
4. Implement:
   - in `diff_specs`, the deprecated-in-both branch, then the deprecated-in-`old`-only branch (`added`, `_criteria(None, after)`), then the existing `deprecated` and ADR branches;
   - in `_cosmetic_with_work`, a `_gained` helper and the message;
   - in `_INSTRUCTIONS`, the reworded Rules bullet.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md` line 57: deprecated in both is `unchanged` whatever its hash or ADRs; deprecated in `old` only and present in `new` is `added` with criteria against an empty side.
   - `docs/architecture.md` line 66: `cosmetic-with-work` also covers a gained (`added`) criterion.
   - `docs/progress.md`: Current, a Done line, item 4a marked done.
   - `docs/decisions.md`: a row only if a Design choice departs from the proposal.
   - This record's Outcome.
7. Commit `feat(domain): apply the v1.19 diff and cosmetic rules` with trailers `Task: TASK-098` and `Milestone: M6`. Do not push.

## Files expected to change
- `src/openfactory/domain/spec_diff.py` (about +8)
- `src/openfactory/domain/classifier.py` (about +6)
- `src/openfactory/app/classifier_prompt.py` (1 line)
- `tests/unit/test_spec_diff.py` (about +50, including the one approved edit)
- `tests/unit/test_classifier.py` (about +30)
- `tests/unit/test_classifier_prompt.py` (about +10)
- `docs/architecture.md`, `docs/progress.md`, this record

Not expected to change: `app/impact.py`, `cli.py`, `ports/`, `adapters/`, `domain/payloads.py`, `docs/spec/`, `docs/adr/`.

## Design choices to confirm at planning
1. **Edit to a fixed test (needs your approval).**
   - `tests/unit/test_spec_diff.py::test_task091_ac4_undeprecated_is_modified` (line 172) asserts `req_change(d) == "modified"` for `diff_specs(spec([req(deprecated=True)]), spec([req()]))`. SC-202 makes that `"added"`.
   - Proposed: change the assertion to `"added"`, rename the test to `test_task091_ac4_undeprecated_is_added`, and add a check that its criterion is `added`.
   - No other existing test contradicts the new rules:
     - `test_task091_ac4_deprecated_in_both_is_unchanged` already holds.
     - `test_task091_ac5_rule_does_not_override_added_removed_deprecated` deprecates only in `new`.
     - The fixtures in `test_classifier.py`, `test_impact.py` and `test_cli_impact.py` have no cosmetic entry for a requirement that gained a criterion, and no requirement deprecated in `from`.
2. **Criteria of a requirement deprecated in both.**
   - Proposed: keep diffing them by id and hash, from the general Step 1 sentence. The requirement's change is `unchanged`, but its criteria may show `modified`, `added` or `removed`.
   - Nothing reads them: `ImpactComputed` stores no criteria, and the classifier reads criteria only for `modified` requirements.
   - Alternative: force them all to `unchanged`. That needs extra code the spec does not ask for.
3. **Prompt bullet wording.**
   - Proposed: "A requirement whose to version lacks a criterion of its from version, or has a criterion its from version lacks, is not cosmetic."
   - This changes the `context_hash` of later classifier runs. Nothing pins it.

## Answers (human, 2026-10-24)
1. Approved as proposed: assert `"added"`, rename to `test_task091_ac4_undeprecated_is_added`, check its criterion is `added`.
2. As proposed: criteria of a requirement deprecated in both stay diffed by id and hash.
3. As proposed: the wording above, unchanged.

## Spec gaps
None; Spec impact is none. Design choice 2 is the literal reading of Step 1's general sentence, not a gap: the new sentence fixes the requirement's change, not its criteria, and no behaviour depends on them.

## Outcome
- `diff_specs`: deprecated in both is `unchanged` (checked before hash and ADR rules, criteria still diffed); deprecated in `old` and not deprecated in `new` is `added` with `_criteria(None, after)` (SC-200, SC-202).
- `_cosmetic_with_work`: new helper `_gained`; a cosmetic entry for a requirement with an `added` criterion is rejected, message "or a lost or gained criterion" (SC-190).
- `_INSTRUCTIONS`: last rule now reads "A requirement whose to version lacks a criterion of its from version, or has a criterion its from version lacks, is not cosmetic."
- Tests: 15 new `test_task098_*` cases. One approved edit: `test_task091_ac4_undeprecated_is_modified` renamed `..._is_added`, asserts `added` and its criterion `added`. No mechanical test fixes.
- Full suite: 1959 passed. No departure from the plan, so no decisions.md row; no ADR.
