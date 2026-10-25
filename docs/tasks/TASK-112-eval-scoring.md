# TASK-112: Eval scoring

- Milestone: M7
- Status: done
- Branch: `task/TASK-112-eval-scoring`
- Tests: acceptance
- ADR: none. The task adds no port, adapter, event type, payload field, table, dependency or convention. It is one pure module in `domain/` that reads the existing `ImpactComputedPayload` (ADR-019). The answers to the open questions go in one row of `docs/decisions.md`. The case file format and fixture layout are not in this task (TASK-113, which may need an ADR).
- Spec impact: wording (see Spec gaps). The slice is built only from text the spec settles. The one gap (audit F-1) affects a later slice, not this one.
- Spec sections (spec v1.21):
  - "Evaluation plan" › Ground truth (SC-215, SC-227, SC-229): "the human's list of the tasks, files and tests the change truly affects, and the kind of each modified requirement; the downstream tasks, which Step 3 invalidates, count as affected, with their files and tests. The task list is reported and has no target. The new-requirement case is labelled with empty tasks, files and tests".
  - "Evaluation plan" › Metrics (SC-206, SC-212, SC-228): "precision and recall of affected files and tests per case; classification accuracy of `ChangeClass.kind`. Recall and precision are pooled over the cases whose ground truth is not empty, separately for files and for tests. A case with empty ground truth (the cosmetic and new-requirement cases) is left out of the pooled figures; the cosmetic cases are judged by the cosmetic target. Accuracy is the share of modified requirements, over all cases of a run, whose `kind` equals the labelled kind; it is reported, with no target."
  - "Evaluation plan" › Targets (SC-206, SC-212, SC-226): "recall ≥ 0.9 on files and tests …; precision ≥ 0.7; zero work triggered for cosmetic changes: a cosmetic case triggers no work when its `ImpactComputed` has empty `tasks`, `downstream`, `files` and `tests`. Each of the three runs must meet the targets. A case whose `impact` fails makes its run miss every target".
  - "Evaluation plan" › Run (SC-213): "one row per case and run with … the task, file and test precision and recall of the case (`-` where undefined)".
  - "Spec diff and impact analysis" › Step 3: "the downstream tasks … they are invalidated too".

## Outline item
This is the first slice of M7 outline item 5 in `docs/progress.md`: the scoring. It has no I/O, fixture, case files, `claude` or results file. Nothing calls the new functions yet. The rest of item 5 splits as follows:
- TASK-113, case format and fixture layout: where `tests/eval/fixture/` and `tests/eval/cases/<id>/` live and what goes in them (specs, labels, the fixture database and git history), plus a loader from a label file into `EvalLabels`, tested on a small synthetic case. Likely an ADR, because the human's item 6 fixture must follow the layout (SC-207 allows "a decisions row or an ADR").
- TASK-114, per-case procedure: copy the fixture, replace `specs/requirements.yaml` and `specs/adrs/`, run `approve spec` and `compute_impact` through the use cases; the result is the case's `ImpactComputedPayload` or `classifier call failed: <error>`. Tested with a stand-in `claude` on a tiny synthetic fixture.
- TASK-115, `docs/generated/eval-results.md` and `tests/eval/test_eval.py` (merged, human answer): the per-case and per-run rows and the min and max over the runs; marked `eval`, runs the cases three times, writes the results file and fails when any run misses a target. The tests only cover the wiring; the real run waits for item 6. Blocked until a `/spec-change` settles audit F-1, with F-2 in the same change; that `/spec-change` runs alongside TASK-113 and TASK-114, not after them.

## Objective
A pure module scores one eval case's `ImpactComputedPayload` against its labels, then scores one run's cases:
- per case: task, file and test precision and recall;
- per run: pooled file and test precision and recall, accuracy, and the cosmetic outcome;
- the target check, where any failed case misses every target.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- New `src/openfactory/domain/eval_scoring.py`. It is pure and imports only `openfactory.domain`, `pydantic` and the standard library. All models are frozen with `extra="forbid"`. It holds:
  - `EvalLabels` with these fields:
    - `tasks: list[str]`
    - `files: list[str]`
    - `tests: list[str]`
    - `kinds: dict[str, ChangeKind]`, the labelled kind of each modified requirement.

    This is the in-memory shape. The file format comes in TASK-113.
  - `PrecisionRecall` with `precision: float | None` and `recall: float | None`, where `None` means undefined (0/0).
  - `CaseScore` with `tasks`, `files` and `tests` (each a `PrecisionRecall`), plus the counts that pooling needs: true positives, predicted and labelled, for files and for tests.
  - `score_case(labels, impact) -> CaseScore`.
  - `RunScore` with these fields:
    - `files: PrecisionRecall` and `tests: PrecisionRecall`, both pooled;
    - `accuracy: float | None`;
    - `cosmetic_no_work: bool`.
  - `score_run(cases: Sequence[tuple[EvalLabels, ImpactComputedPayload]]) -> RunScore`.
  - `meets_targets(run: RunScore, *, any_case_failed: bool) -> bool`.
  - Constants `RECALL_TARGET = 0.9` and `PRECISION_TARGET = 0.7`.
- New `tests/unit/test_eval_scoring.py`. It builds payloads from the real `ImpactComputedPayload` and runs in the default suite, not under `-m eval`.

Out:
- The case file format, the fixture layout, any loader, copying the fixture, running `approve spec` and `impact`, `tests/eval/`, `docs/generated/eval-results.md`, the min and max over runs, and number formatting (TASK-113 to TASK-116).
- What a run's pooled figures and accuracy are when one of its cases failed (audit F-1, not in the spec). `score_run` takes only cases that have an `ImpactComputed`. Which cases the caller passes for a run with a failed case is left to TASK-115.
- Any change to `domain/payloads.py`, `app/`, `ports/`, `adapters/`, `cli.py` or existing tests.

## Acceptance criteria
- [ ] **AC1** (Metrics: "precision and recall of affected files and tests per case"; Run: "the task, file and test precision and recall of the case (`-` where undefined)"; Ground truth: "the downstream tasks … count as affected")
  - `score_case` compares, as exact strings and as sets:
    - the predicted tasks, which are `impact.tasks` together with `impact.downstream`, with `labels.tasks`;
    - `impact.files` with `labels.files`;
    - `impact.tests` with `labels.tests`.
  - Precision is |predicted ∩ labelled| / |predicted|, and recall is |predicted ∩ labelled| / |labelled|. Each is `None` when its denominator is 0.
  - Example: 4 predicted files, 3 of them labelled, 5 labelled in all, gives precision 0.75 and recall 0.6.
  - A downstream task that is labelled counts as a true positive.
- [ ] **AC2** (Metrics: "Recall and precision are pooled over the cases whose ground truth is not empty, separately for files and for tests. A case with empty ground truth … is left out of the pooled figures")
  - `score_run` pools files and tests separately. It sums true positives, predicted and labelled over the included cases (micro-averaging), then divides.
  - A case with empty ground truth (empty `tasks`, `files` and `tests`; `kinds` does not count) is left out of both pools, even when it predicted work. A case with any of the three non-empty enters both pools, so tests it predicts count against test precision even when it labels no tests (Q1).
  - A pooled figure is `None` when its denominator is 0.
- [ ] **AC3** (Metrics: "Accuracy is the share of modified requirements, over all cases of a run, whose `kind` equals the labelled kind"; Ground truth: "the kind of each modified requirement")
  - `accuracy` is the number of labelled modified requirements, over all the run's cases, whose entry in `impact.requirements` has a `kind` equal to the labelled kind, divided by the number of labelled modified requirements. A labelled requirement missing from `impact.requirements`, or with a null `kind` there, counts as not equal (Q2).
  - Cosmetic cases count here.
  - `accuracy` is `None` when no case labels a kind.
- [ ] **AC4** (Targets: "a cosmetic case triggers no work when its `ImpactComputed` has empty `tasks`, `downstream`, `files` and `tests`")
  - `cosmetic_no_work` is true when every cosmetic case of the run has empty `tasks`, `downstream`, `files` and `tests`.
  - It is false when any cosmetic case has a non-empty one of the four, including only `downstream`.
  - A case is cosmetic when `labels.kinds` is non-empty and every value is `cosmetic` (Q3). A run with no cosmetic case gives true.
- [ ] **AC5** (Targets: "recall ≥ 0.9 on files and tests; precision ≥ 0.7; zero work triggered for cosmetic changes … A case whose `impact` fails makes its run miss every target")
  - `meets_targets` is true only when all of these hold:
    - the file and test recall are each ≥ `RECALL_TARGET`;
    - the file and test precision are each ≥ `PRECISION_TARGET`;
    - `cosmetic_no_work` is true;
    - `any_case_failed` is false.
  - A `None` figure misses its target.
  - Exactly 0.9 recall and 0.7 precision meet the targets, for example 9/10 and 7/10.
  - With `any_case_failed`, the result is false even when every figure is 1.0.
- [ ] **AC6** (CLAUDE.md architecture rules: "domain: pure models and rules. No I/O, no imports from adapters/app")
  - `domain/eval_scoring.py` imports only `openfactory.domain`, `pydantic` and the standard library, and does no I/O.
  - The new tests run in the default `uv run pytest -q`, which excludes `-m eval`.
  - Under `src/`, only the new module changes. No existing test is edited, and the full suite passes.

## Architecture rules that apply
- The scoring is pure domain rules over a domain payload. Rounding and Markdown belong to the results writer (TASK-115).
- No I/O, no ports, no LLM.

## Plan
1. Create branch `task/TASK-112-eval-scoring` from an up-to-date main.
2. Test-writer: write failing tests in `tests/unit/test_eval_scoring.py` for AC1 to AC6. Include worked examples with hand-computed fractions for AC1, the AC2 pooling and the AC5 boundaries.
3. Implement `domain/eval_scoring.py`.
4. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
5. Update the docs:
   - `docs/architecture.md`: a new "Eval scoring" section.
   - `docs/decisions.md`: one row for the answers.
   - `docs/progress.md`: Current, a Done line, item 5 split into 5a done and 5b to 5d.
   - This record's Outcome.
6. Commit `feat(domain): add eval scoring` with trailers `Task: TASK-112` and `Milestone: M7`. Do not push.

## Files expected to change
- `src/openfactory/domain/eval_scoring.py` (new, about +110)
- `tests/unit/test_eval_scoring.py` (new, about +180)
- `docs/architecture.md`, `docs/decisions.md`, `docs/progress.md`, this record

Not expected to change: `domain/payloads.py`, `app/`, `ports/`, `adapters/`, `cli.py`, `tests/eval/`, `docs/generated/`, `docs/spec/`, `docs/adr/`, `CHANGELOG.md`.

Expected size: about 290 lines, about 110 of them under `src/`.

## Reading notes (none of them a spec gap)
- **Precision and recall formulas.** The spec does not write them out; they are the standard set definitions. "`-` where undefined" fixes 0/0 as undefined (`None` here).
- **"Pooled".** Read as summing the counts over cases before dividing (micro-averaging), not averaging each case's ratio.
- **A run that predicts nothing.** Its pooled precision is `None`. Its recall is then 0 against a non-empty label set, so the run misses either way; no extra rule is needed.
- **The task list.** It is scored per case only. Nothing pools it and no target applies ("reported and has no target").

## Open questions (answered by the human 2026-10-25: "do as the advisor says")
Answers: Q1 the alternative (case-level entry, `kinds` excluded); Q2, Q3 and Q4 as proposed. Also: TASK-115 and TASK-116 merged into one task (TASK-115), blocked by F-1 as well; the F-1/F-2 `/spec-change` runs alongside TASK-113 and TASK-114; the sanity checks of Q3 (the case set has a cosmetic case, a cosmetic case labels no tasks, files or tests) go in TASK-113 or TASK-115.

1. **Q1, which cases enter each pool.** "Pooled over the cases whose ground truth is not empty, separately for files and for tests."
   - Proposed: the file pool takes the cases with non-empty `files` labels, and the test pool the cases with non-empty `tests` labels.
   - Alternative: a case enters both pools when any of its three lists is non-empty. **Chosen.**
   - The two readings agree for the spec's mix when every behavioral and replacement case labels both files and tests.
2. **Q2, the accuracy denominator.**
   - Proposed: the labelled modified requirements (`labels.kinds`). A labelled requirement that is missing from `impact.requirements`, or has a null `kind` there, counts as not equal.
   - Alternative: the requirements with `change: modified` in `impact.requirements`. That would leave a labelled-but-unmodified requirement uncounted.
3. **Q3, which cases are "the cosmetic cases".** The spec's mix names them, but the labels (SC-229) carry only a kind per modified requirement.
   - Proposed: a case is cosmetic when `labels.kinds` is non-empty and every value is `cosmetic`.
   - Alternative: a separate case category label. That is part of the case format, which TASK-113 would then have to fix first.
4. **Q4, location.**
   - Proposed: `src/openfactory/domain/eval_scoring.py`, so the default suite and pyright cover it.
   - Alternative: a helper under `tests/eval/`. That is shipped nowhere, but its tests would have to import from `tests/`.

## Spec gaps
Spec impact is "wording". None of these blocks TASK-112.
- **"Evaluation plan" › Targets, Run (audit F-1, gap, open in `docs/spec-audits/2026-10-25-proposal-v1.21.md`).** The spec does not say what a run's pooled figures and accuracy are when one of its cases has no `ImpactComputed`. It does not block this slice: `score_run` takes only scored cases, and `meets_targets` applies the settled SC-226 rule ("miss every target"). It blocks TASK-115 (the results file and the eval test) until a `/spec-change`.
- **"Evaluation plan" › Run, Metrics (audit F-2, wording).** The "minimum and maximum of each pooled figure" does not name accuracy, though SC-228 says the results give its minimum and maximum. It does not block: min and max over runs are not in this slice. It should be settled in the same `/spec-change` as F-1.
- **"Evaluation plan" › Metrics: "pooled over the cases whose ground truth is not empty, separately for files and for tests"** can be read per list or per case (Q1). It does not block: the readings agree for the spec's mix, and the human picks before tests are written.
- **"Evaluation plan" › Metrics: "share of modified requirements"** does not say whether the modified requirements are the labelled ones or those in `ImpactComputed` (Q2). It does not block, for the same reason.
- **"Evaluation plan" › Cases, Targets: "the cosmetic cases"** has no label that marks a case cosmetic; SC-229 labels only kinds (Q3). It does not block: it can be derived from the labelled kinds, and the human confirms.

## Outcome
- New pure `src/openfactory/domain/eval_scoring.py` (`EvalLabels`, `PrecisionRecall`, `CaseScore`, `RunScore`, `score_case`, `score_run`, `meets_targets`, `RECALL_TARGET`, `PRECISION_TARGET`) and `tests/unit/test_eval_scoring.py` (31 tests, AC1 to AC6). Only the new module changed under `src/`.
- Human answers: Q1 case-level pool entry with `kinds` excluded, Q2 labelled denominator, Q3 cosmetic = non-empty labelled kinds all cosmetic, Q4 domain location; recorded in one row of `docs/decisions.md`. TASK-115 and TASK-116 merged into TASK-115.
- No test-writer test was edited and there were no mechanical fixes.
- Full suite 2177 passed; ruff, pyright and check_docs clean.
- Docs: "Eval scoring" section in `docs/architecture.md`, `docs/progress.md` (item 5 split into 5a to 5d).
