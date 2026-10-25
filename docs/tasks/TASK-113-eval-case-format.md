# TASK-113: Eval case format, fixture layout and labels loader

- Milestone: M7
- Status: done
- Branch: `task/TASK-113-eval-case-format`
- Tests: acceptance
- ADR: needed (eval fixture layout and case file format). The task drafts it as `ADR-021`, Status: proposed. Two CLAUDE.md triggers apply:
  - "a new convention other code must follow": the human's item 6 fixture and labelled cases, TASK-114 and TASK-115 must all follow the layout.
  - "a choice between real alternatives with lasting consequences": a git bundle and the database, a copied working tree, or the database only (Q1).
  - SC-207 allows "a decisions row or an ADR"; the triggers make it an ADR. TASK-114 should not start until the human accepts `ADR-021`.
- Spec impact: none. SC-207 hands the layout and the case format to the eval task. The spec settles what a case labels (SC-215, SC-227, SC-229) and what a case replaces.
- Spec sections (spec v1.21):
  - "Evaluation plan" › Fixture: "a frozen snapshot of the target repo after the initial build, with its event log and git history."
  - "Evaluation plan" › Cases: "8 spec changes, each with a hand-written list of truly affected tasks, files and tests."
  - "Evaluation plan" › Ground truth (SC-215, SC-227, SC-229): "the human's list of the tasks, files and tests the change truly affects, and the kind of each modified requirement; … The new-requirement case is labelled with empty tasks, files and tests".
  - "Evaluation plan" › Procedure (SC-207): "each case runs on its own copy of the fixture: the case's spec files replace `specs/requirements.yaml` and `specs/adrs/` … The fixture's layout and the case file format are set by the eval task."
  - "Spec diff and impact analysis" › Step 2: the three kinds `cosmetic`, `behavioral`, `replacement` (`ChangeKind`).
- Requirement IDs: none. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Outline item
This is M7 outline item 5b. Item 5a (TASK-112, `domain/eval_scoring.py` with `EvalLabels`) is done. 5c (TASK-114) copies the fixture and runs `approve spec` and `compute_impact`. 5d (TASK-115) builds the results file and `tests/eval/test_eval.py`.

## Objective
Fix where the eval fixture and the cases live and what they contain, in proposed `ADR-021`, and add a pure loader that turns a case's labels file into `EvalLabels`.

## Scope
In:
- New `docs/adr/ADR-021-eval-fixture-and-case-format.md` (proposed). Its proposed content, subject to Q1 to Q3:
  - **Fixture:** `tests/eval/fixture/` holds:
    - `repo.bundle`: a `git bundle --all` of the target repo after the initial build;
    - `openfactory.db`: that repo's `.openfactory/openfactory.db`, one checkpointed file with no `-wal` or `-shm`.
    - Both come from the human's one real build (item 6). `specs/policies.yaml` comes from the bundle.
  - **Case:** `tests/eval/cases/<case id>/` holds:
    - `specs/requirements.yaml` and `specs/adrs/*.md`: the files that replace the fixture's (no `policies.yaml`);
    - `labels.yaml`: the ground truth.
  - **Labels file:** a YAML mapping with exactly four keys:
    - `tasks`, `files`, `tests`: each a list of strings;
    - `kinds`: a mapping from a modified requirement's id to `cosmetic`, `behavioral` or `replacement`.
  - **Case id:** the directory name.
- New `src/openfactory/app/eval_cases.py` with `parse_eval_labels(text: str) -> EvalLabels`. It is pure (text in, model out, no file reading) and imports only `openfactory.domain`, `pydantic`, `yaml` and the standard library. Reading the file is the harness's job (TASK-114/115).
- New `tests/unit/test_eval_cases.py`, in the default suite (not `-m eval`).

Out:
- Producing the real fixture or real cases (item 6, the human's).
- Copying the fixture, cloning the bundle, `approve spec`, `compute_impact` (TASK-114).
- Listing the case directories, and the case-set checks from the TASK-112 Q3 Later line: the set has a cosmetic case, and a cosmetic case labels no tasks, files or tests (TASK-115).
- `tests/eval/test_eval.py` and `docs/generated/eval-results.md` (TASK-115).
- Any change to `domain/eval_scoring.py`, `app/spec_loader.py`, `ports/`, `adapters/`, `cli.py` or existing tests.

## Acceptance criteria
- [ ] **AC1** (Procedure: "The fixture's layout and the case file format are set by the eval task"; Fixture: "with its event log and git history"; Procedure: "the case's spec files replace `specs/requirements.yaml` and `specs/adrs/`")
  - `ADR-021` (Status: proposed) states the fixture layout, the case directory layout and the labels file format above.
  - The fixture carries both the event log and the git history.
  - A case carries only the files that replace `specs/requirements.yaml` and `specs/adrs/`.
  - This is a docs criterion: the reviewer checks it and `check_docs` must pass.
- [ ] **AC2** (Ground truth: "the tasks, files and tests the change truly affects, and the kind of each modified requirement")
  - `parse_eval_labels` turns a mapping with `tasks`, `files`, `tests` and `kinds` into the equal `EvalLabels`.
  - Lists keep the order written.
  - Each `kinds` value is a `ChangeKind`.
- [ ] **AC3** (Ground truth: "The new-requirement case is labelled with empty tasks, files and tests"; Metrics: "A case with empty ground truth (the cosmetic and new-requirement cases)")
  - `tasks: []`, `files: []`, `tests: []`, `kinds: {}` parses to empty `EvalLabels`.
  - The same with `kinds: {REQ-AUTH-002: cosmetic}` parses to that one kind.
- [ ] **AC4** (Ground truth: "the kind of each modified requirement"; Step 2's three kinds)
  - These cases raise `ValueError` (a Pydantic `ValidationError` counts):
    - a `kinds` value outside `cosmetic`, `behavioral` and `replacement`;
    - a missing key or a key other than the four;
    - text that is not YAML or not a mapping.
- [ ] **AC5** (CLAUDE.md architecture rules: "app: use cases, depends on domain + ports only")
  - `app/eval_cases.py` imports only `openfactory.domain`, `pydantic`, `yaml` and the standard library, and does no I/O.
  - Under `src/`, only the new module changes.
  - No existing test is edited, and the full suite passes.

## Plan
1. Create branch `task/TASK-113-eval-case-format` from an up-to-date main.
2. Draft `docs/adr/ADR-021-eval-fixture-and-case-format.md` as proposed, with the human's answers to Q1 to Q3.
3. Test-writer: write failing tests for AC2 to AC5 in `tests/unit/test_eval_cases.py`, with inline YAML text.
4. Implement `app/eval_cases.py`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`: an "Eval cases" subsection next to "Eval scoring".
   - `docs/progress.md`: Current, a Done line, item 5b ticked.
   - This record's Outcome.
7. Commit `feat(app): add the eval labels loader` with trailers `Task: TASK-113` and `Milestone: M7`. Do not push.

## Files expected to change
- `docs/adr/ADR-021-eval-fixture-and-case-format.md` (new, about +60)
- `src/openfactory/app/eval_cases.py` (new, about +35)
- `tests/unit/test_eval_cases.py` (new, about +110)
- `docs/architecture.md`, `docs/progress.md`, this record

Not expected to change: `domain/`, `ports/`, `adapters/`, `cli.py`, `tests/eval/` (no fixture or case is committed in this task), `docs/generated/`, `docs/spec/`, `pyproject.toml`.

Expected size: about 250 lines, about 35 of them under `src/`.

## Open questions (for the human, before tests are written)
1. **Q1, form of the fixture.**
   - Proposed: `repo.bundle` (`git bundle --all`) plus a checkpointed `openfactory.db`. This keeps the git history the spec names without a nested `.git` in this repo.
   - Alternative A: a tarball of the target repo's working tree with its `.git`.
   - Alternative B: the database and `specs/` only. `impact` reads only projections, but this drops the "git history" in "Evaluation plan" › Fixture.
2. **Q2, labels file shape.**
   - Proposed: one `labels.yaml` per case, all four keys required.
   - Alternative A: the keys are optional and default to empty.
   - Alternative B: one `tests/eval/cases.yaml` for all eight cases, with spec files still per case directory.
3. **Q3, where the loader lives.**
   - Proposed: `src/openfactory/app/eval_cases.py`, a pure text parser. Pyright includes only `src`, and this follows TASK-112's Q4 answer, which put the scoring in `domain/`.
   - Alternative: a helper under `tests/eval/`, which pyright does not check.
4. **Q4, duplicate keys in `labels.yaml`.**
   - Proposed: `yaml.safe_load`. A duplicated `kinds` key keeps the last value, and this goes on a Later line.
   - Alternative: reuse `_UniqueKeyLoader` from `app/spec_loader.py`, which is private, so `spec_loader.py` would have to change.

## Human answers (2026-10-25)
- Q1: proposed, a `repo.bundle` and a checkpointed `openfactory.db`. ADR-021 also states the restore steps (clone, then place the database) and the remote-tracking refs, per the advisor.
- Q2: proposed, one `labels.yaml` per case, all four keys required.
- Q3: proposed, `src/openfactory/app/eval_cases.py`.
- Q4: proposed, `yaml.safe_load`; a Later line records the duplicate-key gap.

## Spec gaps
None. Spec impact is "none". The layout and the case format are left to the eval task by "Evaluation plan" › Procedure (SC-207), so Q1 to Q4 are design choices for the task, not spec gaps. Audit F-1 and F-2 of `docs/spec-audits/2026-10-25-proposal-v1.21.md` still block TASK-115 only, not this task.

## Outcome
- New `docs/adr/ADR-021-eval-fixture-and-case-format.md`: fixture `tests/eval/fixture/` (`repo.bundle`, `openfactory.db`), case directory `tests/eval/cases/<case id>/` (replacing specs, `labels.yaml`), labels file with four required keys. The human accepted it at the close of the task.
- New pure `src/openfactory/app/eval_cases.py` (`parse_eval_labels`) and `tests/unit/test_eval_cases.py` (6 test functions, 12 cases, AC2 to AC5). Only the new module changed under `src/`.
- Human answers Q1 to Q4 as proposed; the duplicate-key gap is a Later line in `docs/progress.md`.
- No test was edited and there were no mechanical fixes.
- Full suite 2189 passed; ruff, pyright and check_docs clean.
- Docs: "Eval cases" section in `docs/architecture.md`, `docs/progress.md` (Current, Done, item 5b ticked).
