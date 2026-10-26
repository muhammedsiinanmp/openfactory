# TASK-116: Eval test

- Milestone: M7
- Status: done
- Branch: `task/TASK-116-eval-test`
- Tests: acceptance. The new behaviour is the driver: listing cases, three runs, scoring, writing the file, the malformed-case stop, the case-set check and the target check.
  - It is tested in the default suite on TASK-114's synthetic fixture with a stand-in `LLMProvider`.
  - The one `@pytest.mark.eval` test cannot run in this task: the real fixture and cases are outline item 6 (the human's), and the eval uses the Claude subscription.
- ADR: none.
  - The driver is test code in `tests/eval/`, like `harness.py`. That placement was the TASK-114 decisions row; ADR-011 binds only `src/`.
  - ADR-021 (accepted) already covers the fixture and case layout.
  - There is no new port, adapter, event, payload field, table, dependency or convention.
  - The answers to Q1 to Q4 go in one row of `docs/decisions.md`.
- Spec impact: none. v1.22 settles the refused case (SC-234), a failed run's figures (SC-235), accuracy's min and max (SC-236), pooling (SC-239), the accuracy base (SC-240), what a cosmetic case is (SC-241), the failed row (SC-242) and undefined figures (SC-243). The exact text of the malformed-case error is a layout choice (Q2), not a spec gap.
- Spec sections (spec v1.22):
  - "Evaluation plan" › Procedure (SC-207, SC-234): "each case runs on its own copy of the fixture … A case whose `approve spec` or `impact` refuses is malformed: the eval stops with an error naming the case and the first refusal, before it writes the results file."
  - "Evaluation plan" › Targets (SC-206, SC-226, SC-235): "Each of the three runs must meet the targets. A case whose `impact` fails makes its run miss every target; … that run's pooled figures, accuracy and cosmetic outcome are computed over its other cases."
  - "Evaluation plan" › Run (SC-213): "`pytest tests/eval -m eval`. The eval writes `docs/generated/eval-results.md`, which is committed, before it checks the targets … The eval test fails when any run misses a target."
  - "Evaluation plan" › Cases (SC-241) and › Metrics (SC-239): "A case is cosmetic when it labels at least one kind and every labelled kind is `cosmetic`"; "a case whose labelled tasks, files and tests are all empty (the cosmetic and new-requirement cases)".
  - The paragraph after Run: "only the classifier varies, so eval runs 3 times."
- Requirement IDs: none (decision of 2026-10-08).

## Outline item
M7 outline item 5e in `docs/progress.md`. The real `-m eval` run waits for item 6.

## Objective
A test-code driver lists the eval cases, runs each one three times through `harness.run_case`, builds each run's `EvalRunResult` and `RunScore`, and writes the results file with `render_eval_results`. `tests/eval/test_eval.py` runs it on the real fixture with `ClaudeCodeLLM` and fails when any run misses a target.

## Scope
In:
- Additions to `tests/eval/harness.py` (Q1). All names are provisional.
  - `EVAL_RUNS = 3`.
  - `MalformedCase(Exception)`.
  - `load_cases(cases_dir) -> list[tuple[str, Path, EvalLabels]]`: lists the case directories in ascending id, reads each `labels.yaml` with `parse_eval_labels`, checks the case set (AC5).
  - `run_eval(fixture, cases_dir, workdir, out, *, llm, runs=EVAL_RUNS) -> list[EvalRunResult]`:
    - runs all cases for run 1, then run 2, then run 3, each case on its own copy under `workdir/run_<n>/<case id>`;
    - a refusal raises `MalformedCase` at once;
    - a failed `impact` gives an `EvalCaseResult` with `impact=None`;
    - each run's score is `score_run` over the cases that have an `ImpactComputed`;
    - writes `render_eval_results(...)` to `out`, creating its parent directory, and returns the runs.
  - `missed_runs(runs) -> list[int]`: the 1-based numbers of runs where `meets_targets(score, any_case_failed=...)` is false.
- New `tests/eval/test_eval.py` with one test marked `eval`: `fixture=tests/eval/fixture`, `cases_dir=tests/eval/cases`, `workdir=tmp_path`, `out=<repo>/docs/generated/eval-results.md`, `llm=ClaudeCodeLLM()`; asserts `missed_runs(runs) == []`.
- New default-suite wiring tests on TASK-114's synthetic fixture with a stand-in `LLMProvider`, writing to `tmp_path`. The test-writer reuses the fixture builder in `tests/eval/test_harness.py`. No existing test function is edited.

Out:
- The real fixture, the real cases and committing `docs/generated/eval-results.md` (item 6, the human's).
- Checking the 8-case mix beyond the human's TASK-112 Q3 answer.
- Any change under `src/`, to `pyproject.toml`, `docs/spec/` or `docs/adr/`.
- Writing any file under `docs/generated/` in this task.

## Acceptance criteria
- [x] **AC1** (Procedure "each case runs on its own copy of the fixture"; "eval runs 3 times"; Run "one row per case and run"; Targets SC-235)
  - `run_eval` runs every case directory once in each of the 3 runs, each on its own copy.
  - It returns 3 `EvalRunResult`s. Each holds one `EvalCaseResult` per case (case id = directory name, labels from `labels.yaml`, the case's `ImpactComputed` payload), and a `score` equal to `score_run` over that run's cases.
- [x] **AC2** (Targets: "A case whose `impact` fails makes its run miss every target; its row shows `classifier call failed` …; that run's pooled figures, accuracy and cosmetic outcome are computed over its other cases.")
  - When the stand-in classifier fails for one case in one run: that case's result has `impact=None`; the file shows its row as `classifier call failed`; that run's `score` equals `score_run` over its other cases; `missed_runs` includes that run; the other runs are unaffected and the eval does not stop.
- [x] **AC3** (Procedure: "A case whose `approve spec` or `impact` refuses is malformed: the eval stops with an error naming the case and the first refusal, before it writes the results file.")
  - A case whose `approve spec` does not approve raises `MalformedCase` (for example spec files equal to the fixture's sv_01 give `nothing_to_approve`). The message names the case id and the approve outcome, not the `impact` refusal that follows it.
  - An approved case whose `impact` refuses raises the same error, naming the `impact` refusal.
  - In both cases `out` is not created. Tests check that the id and the refusal name appear in the message, not the exact text.
- [x] **AC4** (Run: "writes `docs/generated/eval-results.md` … before it checks the targets … The eval test fails when any run misses a target.")
  - After `run_eval` returns, `out` holds exactly `render_eval_results(runs)`, also when a run misses a target.
  - `missed_runs` returns the numbers of the runs whose `meets_targets` is false, `[]` when all runs meet the targets.
- [x] **AC5** (Cases mix and SC-241; Metrics "(the cosmetic and new-requirement cases)"; the human's TASK-112 Q3 answer)
  - `load_cases` raises `MalformedCase` before any case runs (no stand-in call, no copy made) when the case set has no cosmetic case, or when a cosmetic case labels a task, file or test; the error names that case.
- [x] **AC6** (Run "`pytest tests/eval -m eval`"; Procedure "with the real classifier"; CLAUDE.md "Do not expand scope")
  - `tests/eval/test_eval.py` has exactly one test, marked `eval`. It uses `tests/eval/fixture`, `tests/eval/cases`, `ClaudeCodeLLM()` and the output `docs/generated/eval-results.md`, and fails when `missed_runs` is not empty.
  - The default `uv run pytest -q` deselects it, and a default-suite test checks its mark.
  - Nothing under `src/` changes, no existing test is edited, and the full suite passes.

## Plan
1. Create `task/TASK-116-eval-test` from an up-to-date main.
2. Record the answers to Q1 to Q4 in one row of `docs/decisions.md`.
3. Test-writer: failing default-suite tests for AC1 to AC6 on the synthetic fixture, with a stand-in whose classifier kind depends on the case (or the call) and which can fail on a chosen call; cases: a behavioral case labelling `AUTH-001` and `app/a.py`, a cosmetic case with empty labels, a refused case.
4. Implement the harness additions and `tests/eval/test_eval.py`.
5. Run pytest, ruff, pyright and check_docs.
6. Docs: `docs/architecture.md` ("Eval harness" gains the driver; "Eval results" no longer says nothing calls it); `docs/progress.md` (Current, Done line, item 5e ticked with the real run waiting for item 6, the TASK-112 Q3 Later line removed); this record's Outcome.
7. Commit `test(eval): add the eval test` with trailers `Task: TASK-116` and `Milestone: M7`. Do not push.

## Files expected to change
- `tests/eval/harness.py` (about +80)
- `tests/eval/test_eval.py` (new, about +35)
- Default-suite wiring tests: new `tests/eval/test_eval_driver.py`, or appended to `tests/eval/test_harness.py` (about +180)
- `docs/decisions.md` (one row), `docs/architecture.md`, `docs/progress.md`, this record

Not expected to change: anything under `src/`, `pyproject.toml` (the `eval` marker and `addopts = "-m 'not eval'"` already exist), `docs/spec/`, `docs/adr/`, `docs/generated/`, `tests/eval/fixture/`, `tests/eval/cases/`.

## Open questions (for the human, before tests are written)
1. **Q1, where the driver lives.** Proposed: in `tests/eval/harness.py`, next to `run_case`, so the default-suite tests and `test_eval.py` share it (the TASK-114 placement). Alternative: in `tests/eval/test_eval.py`, with the wiring tests importing from a test module.
2. **Q2, the malformed-case error.** Proposed: `MalformedCase` with the text `case <id>: approve spec <outcome>` (`refused`, `unloadable` or `nothing_to_approve`) or `case <id>: impact <refusal>` (`no_approved_plan` or `no_spec_change`). Every outcome other than `approved` counts as an `approve spec` refusal. "First refusal" means the approve refusal when there is one, since on a fixture whose plan is on the latest approved version `impact` then refuses as well.
3. **Q3, `-m eval` before item 6.** Proposed: when `tests/eval/fixture/repo.bundle`, `tests/eval/fixture/openfactory.db` or `tests/eval/cases/` is missing, the eval test fails with `pytest.fail` naming the missing path; a skip could be read as a pass. Alternative: `pytest.skip`.
4. **Q4, the case-set check.** Proposed: exactly the TASK-112 Q3 answer: at least one cosmetic case, and every cosmetic case labels no tasks, files or tests, checked in `load_cases` before any copy or classifier call. It does not check 8 cases or the 2/3/2/1 mix.

## Answers (the human, 2026-10-26)
Q1 to Q4 approved as proposed, with the advisor's two fixes: Q2's "always" softened to a fixture whose plan is on the latest approved version; Q3 also checks `tests/eval/fixture/openfactory.db`. The eval test overwrites the committed `docs/generated/eval-results.md` on each deliberate run (SC-213); step 6 also clears the "blocked" wording of progress.md Current and item 5e.

## Spec gaps
None.

## Outcome
Built:
- `tests/eval/harness.py` gains `EVAL_RUNS`, `MalformedCase`, `load_cases`, `run_eval` and `missed_runs`.
- New `tests/eval/test_eval.py` with one `eval`-marked test, and `tests/eval/test_eval_driver.py` with 12 default-suite tests on the synthetic fixture.
- Q1 to Q4 are one row of `docs/decisions.md`. Nothing under `src/` changed. The real `-m eval` run waits for outline item 6.

Test edits outside the test-writer:
1. Mechanical: `# noqa: F811` on the six lines of `test_eval_driver.py` where the imported `fixture` pytest fixture is shadowed by parameters (ruff F811). No assertion changed.
2. Non-mechanical, approved by the human (decisions row 2026-10-26): in `test_refused_case_stops_the_eval_before_the_file`, the approve case now builds `c0_refused` with `make_case(..., FIXTURE_ADRS)`, because `add_case` dropped ADR-002, so `approve spec` approved sv_02. Assertions unchanged.

Verification: full suite 2216 passed, 1 deselected; ruff, pyright and check_docs clean.
