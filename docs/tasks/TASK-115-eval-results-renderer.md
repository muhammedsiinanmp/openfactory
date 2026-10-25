# TASK-115: Eval results renderer

- Milestone: M7
- Status: done
- Branch: `task/TASK-115-eval-results-renderer`
- Tests: acceptance
- ADR: none.
  - The task adds one pure module under `app/` that reads the existing `EvalLabels`, `ImpactComputedPayload`, `score_case` and `RunScore` (ADR-019, ADR-021).
  - It adds no port, adapter, event type, payload field, table, dependency or convention other code must follow.
  - The Markdown layout and number format go in one row of `docs/decisions.md`, as TASK-111 did for `report`.
- Spec impact: wording (see Spec gaps). This slice is built only from settled text. Two items under Spec gaps block the later eval-test slice (TASK-116), not this one.
- Spec sections (spec v1.21):
  - "Evaluation plan" › Run (SC-213): "The eval writes `docs/generated/eval-results.md`, which is committed, before it checks the targets: one row per case and run with the labelled and classified kinds and the task, file and test precision and recall of the case (`-` where undefined); then, per run, the pooled file and test precision and recall, the accuracy and whether the cosmetic cases triggered no work; then the minimum and maximum of each pooled figure over the runs."
  - "Evaluation plan" › Targets (SC-226): "A case whose `impact` fails makes its run miss every target; its row shows `classifier call failed` in place of its kinds and figures."
  - "Evaluation plan" › Ground truth (SC-215, SC-229): "the kind of each modified requirement".
  - "Evaluation plan" › Metrics (SC-206, SC-212, SC-228): "precision and recall of affected files and tests per case; classification accuracy of `ChangeClass.kind`."
- Requirement IDs: none. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Outline item
This is M7 outline item 5d in `docs/progress.md`, split in two (needs the human's OK, since TASK-112 merged TASK-115 and TASK-116):
- **5d (this task, TASK-115):** the pure renderer of the results text. Nothing calls it yet.
- **5e (TASK-116), `tests/eval/test_eval.py`:**
  - What it does: lists `tests/eval/cases/`, reads `labels.yaml` with `parse_eval_labels`, runs `harness.run_case` three times, builds each run's `RunScore`, writes `docs/generated/eval-results.md` with this renderer, then fails when any run misses a target (`meets_targets`).
  - Blocked on: the refused-case question and audit F-1 (Spec gaps 1 and 2).
  - Its wiring can be tested on TASK-114's synthetic fixture with a stand-in `LLMProvider`.
  - Its real run waits for item 6's fixture and cases.

## Objective
A pure function turns the three eval runs' case results and run scores into the Markdown text of `docs/generated/eval-results.md`, with:
- one row per case and run, scored or `classifier call failed`;
- one line per run with its pooled figures, accuracy and cosmetic outcome;
- the minimum and maximum of each pooled figure over the runs.

## Scope
In:
- New `src/openfactory/app/eval_results.py`. It is pure: it imports only `openfactory.domain`, `pydantic` and the standard library, and does no I/O. Models are frozen, with `extra="forbid"`.
  - `EvalCaseResult` has `case_id: str`, `labels: EvalLabels` and `impact: ImpactComputedPayload | None`. `None` means the case's `impact` failed (SC-226).
  - `EvalRunResult` has `cases: list[EvalCaseResult]` and `score: RunScore`. The caller builds the `RunScore`; the renderer never calls `score_run`.
  - `render_eval_results(runs: Sequence[EvalRunResult]) -> str`:
    - computes each case's figures with `score_case`;
    - formats the text with the Q2 layout;
    - returns the text, ending in a line break.
- New `tests/unit/test_eval_results.py`, in the default suite (not marked `eval`). It uses real `EvalLabels`, `ImpactComputedPayload` and `RunScore` values.

Out:
- Writing the file, listing cases, `parse_eval_labels`, `run_case`, building a `RunScore`, `meets_targets`, the three runs, and `tests/eval/test_eval.py` (all TASK-116).
- Which cases feed a failed run's `RunScore` (audit F-1), and what a refused `approve spec` or `impact` is (Spec gaps 1 and 2).
- Any change to `domain/eval_scoring.py`, `app/eval_cases.py`, `tests/eval/`, `cli.py`, existing tests, `docs/generated/` and `docs/spec/`.

## Acceptance criteria
- [x] **AC1** (Run: "one row per case and run with the labelled and classified kinds and the task, file and test precision and recall of the case (`-` where undefined)")
  - The case table has one row per case of each run: runs in the order given (numbered from 1), then cases in ascending `case_id`.
  - Each row shows the run number, the case id, the labelled kinds (`labels.kinds`), the classified kinds (the entries of `impact.requirements` with a non-null `kind`), and the task, file and test precision and recall from `score_case`.
  - A `None` figure prints `-`. A worked example with hand-computed fractions (for example 3/4 and 3/5) prints the Q2 number format (three decimals: 3/4 `0.750`, 3/5 `0.600`).
- [x] **AC2** (Targets: "its row shows `classifier call failed` in place of its kinds and figures")
  - A case with `impact` `None` keeps its run number and case id.
  - Both kinds cells and all six figure cells show `classifier call failed` (Q3).
  - `score_case` is not called for it.
- [x] **AC3** (Run: "then, per run, the pooled file and test precision and recall, the accuracy and whether the cosmetic cases triggered no work")
  - After the case table, the text has one line per run, in run order, built from that run's given `RunScore`:
    - pooled file precision and recall;
    - pooled test precision and recall;
    - `accuracy`;
    - `cosmetic_no_work`, as `yes` or `no`.
  - A `None` figure prints `-`.
  - The renderer uses the given `RunScore` as is, even when it does not match the run's cases.
- [x] **AC4** (Run: "then the minimum and maximum of each pooled figure over the runs")
  - After the per-run lines, the text gives the minimum and maximum over the runs of each of the four pooled figures: file precision, file recall, test precision and test recall.
  - Each is taken over the runs where the figure is not `None`, and is `-` when no run has one (Q4).
  - An `Accuracy` row follows the four, by the same rule (Q5).
- [x] **AC5** (Run: the results text is the eval's output; CLAUDE.md: "app: use cases, depends on domain + ports only")
  - `render_eval_results` is deterministic: the same input gives the same text, byte for byte.
  - It does no I/O and imports only `openfactory.domain`, `pydantic` and the standard library.
- [x] **AC6** (CLAUDE.md: "Do not expand scope")
  - Under `src/`, only the new module changes.
  - The new tests run in the default `uv run pytest -q`, which still excludes `-m eval`.
  - No existing test is edited, and the full suite passes.

## Plan
1. Create branch `task/TASK-115-eval-results-renderer` from an up-to-date main.
2. Get the human's answers:
   - Q1 to Q5 below;
   - the OK to split 5d into 5d and 5e;
   - whether Spec gaps 1 and 2 go to a `/spec-change` before TASK-116.

   Record the layout, number format and location in one row of `docs/decisions.md`.
3. Test-writer: write failing tests for AC1 to AC6 in `tests/unit/test_eval_results.py`. Include:
   - a two-run example with one failed case;
   - a run whose pooled figures are `None`;
   - hand-computed fractions for the number format.
4. Implement `src/openfactory/app/eval_results.py`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`: an "Eval results" subsection after "Eval harness".
   - `docs/progress.md`:
     - Current;
     - a Done line;
     - item 5d split into 5d (ticked) and 5e (TASK-116);
     - item 5d's text corrected: the four v1.20-audit findings are settled in v1.21, but v1.21-audit F-1 is not;
     - the TASK-114 Later line updated, and a Later line for the "its kinds" wording (Spec gap 4).
   - This record's Outcome.
7. Commit `feat(app): add the eval results renderer` with trailers `Task: TASK-115` and `Milestone: M7`. Do not push.

## Files expected to change
- `src/openfactory/app/eval_results.py` (new, about +110)
- `tests/unit/test_eval_results.py` (new, about +170)
- `docs/decisions.md` (one row), `docs/architecture.md`, `docs/progress.md`, this record

Not expected to change: `domain/eval_scoring.py`, `app/eval_cases.py`, `tests/eval/harness.py`, `tests/eval/test_harness.py`, `cli.py`, `pyproject.toml`, existing tests, `docs/spec/`, `docs/adr/`, `docs/generated/` (no results file is written; the eval writes it in TASK-116).

Expected size: about 290 lines, about 110 of them under `src/`.

## Open questions (for the human, before tests are written)
1. **Q1, location.**
   - Proposed: `src/openfactory/app/eval_results.py`, pure, next to `app/eval_cases.py`. Pyright and the default suite cover it.
   - Alternative: `tests/eval/results.py`, next to `harness.py`. Pyright would not check it.
   - **Answer:** as proposed, `app/eval_results.py`.
2. **Q2, layout and number format.** The spec gives the content, not the Markdown.
   - Proposed:
     - `# Eval results`;
     - `## Cases` with the table `| Run | Case | Labelled kinds | Classified kinds | Tasks P | Tasks R | Files P | Files R | Tests P | Tests R |`;
     - `## Runs` with the table `| Run | Files P | Files R | Tests P | Tests R | Accuracy | Cosmetic no work |`;
     - `## Spread` with the table `| Figure | Min | Max |` (one row per pooled figure).
   - Kinds cell: `<id> <kind>` pairs sorted by id and joined by `, `, or `-` when there are none.
   - Ratios: two decimals.
   - **Answer:** as proposed, but ratios to three decimals (advisor DISAGREE: two decimals print 26/29 as `0.90`).
   - Parts are separated by one blank line, and the separator rows are `| --- |`, as in `report`.
3. **Q3, the failed row.** "In place of its kinds and figures."
   - Proposed: the literal reading. Both kinds cells and all six figure cells show `classifier call failed`.
   - Alternative: keep the labelled kinds, since they come from the labels, and replace only the classified kinds and the figures.
   - **Answer:** as proposed, the literal reading.
4. **Q4, min and max with an undefined figure.**
   - Proposed: taken over the runs where the figure is defined, `-` when none is.
   - Alternative: `-` when any run's figure is undefined.
   - **Answer:** as proposed.
5. **Q5, accuracy in the spread.** Audit F-2 (wording); the SC-228 decisions row says "the results give its minimum and maximum".
   - Proposed: add an `Accuracy` row to `## Spread` now, on the strength of that row.
   - Alternative: leave it out until a `/spec-change` adds it to Run.
   - **Answer:** as proposed, the `Accuracy` row is added now.

**Human's answers (2026-10-25):** "do as the advisor says": the split of 5d into 5d and 5e is approved; Spec gaps 1 and 2, F-2 and the "its kinds" wording go to one `/spec-change` before TASK-116; Q1, Q3, Q4 and Q5 as proposed; Q2 with three decimals. Recorded in `docs/decisions.md`.

## Spec gaps
Spec impact for this task is "wording". Items 1 and 2 block TASK-116 (5e), not this task.

1. **"Evaluation plan" › Targets (SC-226), Procedure: a refused case.**
   - What is unclear: SC-226 scores a case whose `impact` "fails", with the classifier-failure row text. The spec does not say what a case is when `approve spec` refuses its spec files (violations, unloadable, `nothing to approve`), or when `impact` refuses (`no spec change since sv_NN`, `no approved plan`). Either it is a failed `impact` that misses every target (and if so, with what row text), or it is a broken case that stops the eval.
   - Not settled in v1.21, and no decisions row since TASK-114.
   - Why it does not block this task: the renderer only takes an `ImpactComputedPayload` or `None`, so it never sees a `CaseRun`. If the answer is a third row text, it is a small later addition.
   - It blocks TASK-116, which has to interpret `CaseRun`. It needs a `/spec-change`, or a decisions row that makes the eval raise on a malformed case.
2. **"Evaluation plan" › Targets, Run: a failed run's figures (audit F-1 of `docs/spec-audits/2026-10-25-proposal-v1.21.md`, gap).**
   - What is missing: the per-run figures, accuracy and min/max for a run with a failed case. The proposed text "that run's pooled figures and accuracy are computed over its other cases" is not in v1.21.
   - Why it does not block this task: the renderer takes each run's `RunScore` from the caller (AC3).
   - It blocks TASK-116, which builds that `RunScore`.
3. **"Evaluation plan" › Run, Metrics: the accuracy's min and max (audit F-2, wording).** "Each pooled figure" does not name the accuracy, though the SC-228 row says the results give its minimum and maximum. It does not block: Q5 lets the human choose, and it can be settled with item 2.
4. **"Evaluation plan" › Targets: "in place of its kinds".** It is unclear whether the labelled kinds are covered too (Q3). It does not block: either reading is one cell, and the human picks before tests are written.

## Outcome
- New pure `src/openfactory/app/eval_results.py` (`EvalCaseResult`, `EvalRunResult`, `render_eval_results`); nothing calls it yet, TASK-116 will. Only that module changed under `src/`.
- Tests: 7 in `tests/unit/test_eval_results.py`, all pass. Full suite 2204 passed; ruff, pyright and check_docs clean.
- Test edits: `ruff format` wrapped four over-long `RunScore(...)` lines in the test-writer's file (lines 76, 80, 158, 170); layout only, no assertion changed.
- Not tested directly: AC2's "`score_case` is not called" for a failed case, since that would need patching internals; the failed row's text is tested.
- Docs: `docs/architecture.md` ("Eval results"), `docs/progress.md` (5d ticked, 5e added, Later lines now say TASK-116), `docs/decisions.md` (one row, written earlier). No CHANGELOG line (no user-visible command).
