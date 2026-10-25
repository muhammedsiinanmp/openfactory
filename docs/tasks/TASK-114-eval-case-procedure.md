# TASK-114: Eval case procedure

- Milestone: M7
- Status: done
- Branch: `task/TASK-114-eval-case-procedure`
- Tests: acceptance
- ADR: ADR-021 (accepted) already covers the fixture restore and the case layout. Nothing new is needed with the proposed Q1 answer, which puts the procedure in test code under `tests/eval/`. Test code already imports both adapters and app, and ADR-011 binds only the modules under `src/`. It adds no port, adapter, event, payload field, table or dependency, so the placement choice is one row in `docs/decisions.md`. Q1's alternatives B and C would each need an ADR: B adds a second composition root under `src/` and changes ADR-011, C adds a new port.
- Spec impact: wording (see Spec gaps). It does not block this task, but it must be settled before TASK-115 scores a case.
- Spec sections (spec v1.21):
  - "Evaluation plan" › Procedure (SC-207): "each case runs on its own copy of the fixture: the case's spec files replace `specs/requirements.yaml` and `specs/adrs/`, `approve spec` and `impact` run through the use cases with the real classifier, and the case's `ImpactComputed` is compared with its labels. The fixture's layout and the case file format are set by the eval task."
  - "Evaluation plan" › Fixture: "a frozen snapshot of the target repo after the initial build, with its event log and git history."
  - "Evaluation plan" › Targets (SC-226): "A case whose `impact` fails makes its run miss every target; its row shows `classifier call failed` in place of its kinds and figures."
  - "Spec diff and impact analysis" › Step 2: "A second rejected reply or a failed process makes `impact` write `classifier call failed: <error>` …, with `<error>` the first line of the last classifier run's `AgentRunFinished.error`, record no `ImpactComputed`".
  - ADR-021 › Decision: "Restoring a copy" and "Case".
- Requirement IDs: none. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Outline item
This is M7 outline item 5c in `docs/progress.md`.
- Done before it: 5a (TASK-112, scoring) and 5b (TASK-113, `ADR-021` and `parse_eval_labels`).
- After it: 5d (TASK-115) lists the case directories, runs the cases three times, scores them, and writes `docs/generated/eval-results.md` and `tests/eval/test_eval.py`.

## Objective
A harness function restores one fresh copy of the eval fixture, replaces its spec files with one case's, and runs the `approve_spec` and `compute_impact` use cases on it with the given `LLMProvider`. It returns both use cases' results unchanged.

## Scope
In:
- New `tests/eval/harness.py` (test code, under Q1's proposed answer):
  - `restore_fixture(fixture: Path, dest: Path) -> None`:
    - runs `git clone --quiet <fixture>/repo.bundle <dest>`;
    - creates `<dest>/.openfactory/`;
    - copies `<fixture>/openfactory.db` to `<dest>/.openfactory/openfactory.db` (ADR-021 "Restoring a copy").
  - `replace_specs(case: Path, dest: Path) -> None`:
    - removes `<dest>/specs/requirements.yaml` and `<dest>/specs/adrs/`;
    - copies in the case's `specs/requirements.yaml` and `specs/adrs/*.md`;
    - leaves `specs/policies.yaml` as the bundle has it.
  - `run_case(fixture: Path, case: Path, dest: Path, *, llm: LLMProvider) -> CaseRun`:
    - calls `restore_fixture`, then `replace_specs`;
    - opens the adapters `approve spec` and `impact` use (the same set as `cli._open_adapters`, plus `FilesystemSpecFiles(dest / "specs")`) on the copy's database;
    - calls `approve_spec`, then `compute_impact` with `llm`, always both, in that order.
  - Frozen `CaseRun` with `approve: ApproveResult` and `impact: ImpactResult`.
- New `tests/eval/test_harness.py`:
  - in the default suite (not marked `eval`);
  - builds a tiny synthetic fixture in `tmp_path`: a git repo with sv_01 specs, a database holding sv_01 approved, an approved plan and a `CommitRecorded`, then `git bundle create repo.bundle --all`;
  - uses a stand-in `LLMProvider`.

Out:
- Listing the case directories, `parse_eval_labels` calls, scoring, the three runs, `docs/generated/eval-results.md` and `tests/eval/test_eval.py` (all TASK-115).
- The real fixture and cases (item 6, the human's).
- Interpreting a refused `approve spec` or a refused `impact`, beyond returning them (see Spec gaps).
- Any change under `src/`, any existing test, `pyproject.toml`, `docs/spec/` and `docs/generated/`.

## Acceptance criteria
- [ ] **AC1** (Procedure: "each case runs on its own copy of the fixture"; Fixture: "with its event log and git history"; ADR-021 "Restoring a copy")
  - After `restore_fixture`, `dest` is a git clone of the bundle: the bundle's commit shas are reachable from it.
  - `dest/.openfactory/openfactory.db` holds the fixture database's events, the same `seq`, `event_id` and `type` in order.
  - Running two cases from one fixture into two `dest` directories leaves `fixture/repo.bundle` and `fixture/openfactory.db` byte-identical.
  - Neither copy's event log holds the other case's events.
- [ ] **AC2** (Procedure: "the case's spec files replace `specs/requirements.yaml` and `specs/adrs/`")
  - After `replace_specs`, `dest/specs/requirements.yaml` equals the case's.
  - `dest/specs/adrs/` holds exactly the case's ADR files: a fixture ADR the case lacks is gone.
  - `dest/specs/policies.yaml` is the bundle's.
- [ ] **AC3** (Procedure: "`approve spec` and `impact` run through the use cases …, and the case's `ImpactComputed` is compared with its labels")
  - For a case that modifies a requirement, with a stand-in classifier reply of kind `behavioral`, `run_case` returns `approve.outcome` `approved` with `approve.spec_version` `sv_02`.
  - It also returns an `impact.impact` equal to the `ImpactComputed` payload recorded in the copy's database, with `from_version` `sv_01`, `to_version` `sv_02`, and the fixture task and its committed files in `tasks` and `files`.
- [ ] **AC4** (Targets: "A case whose `impact` fails …"; Step 2: "A second rejected reply or a failed process … record no `ImpactComputed`")
  - When the stand-in `LLMProvider` raises `LLMError`, `run_case` returns `impact.impact` `None`.
  - Its `impact.error` is the last classifier run's `AgentRunFinished.error`.
  - The copy's database holds no `ImpactComputed`.
- [ ] **AC5** (Procedure: "`approve spec` and `impact` run")
  - `run_case` calls `approve_spec` and then `compute_impact` every time, and returns both results as the use cases gave them.
  - A case whose spec files equal the fixture's approved sv_01 gives `approve.outcome` `nothing_to_approve` and `impact.refusal` `no_spec_change`. The harness neither raises nor drops either result.
- [ ] **AC6** (CLAUDE.md: "Do not expand scope"; ADR-011)
  - Nothing under `src/` changes.
  - `tests/eval/test_harness.py` runs in the default `uv run pytest -q`, which still excludes `-m eval`.
  - No existing test is edited, and the full suite passes.

## Plan
1. Create branch `task/TASK-114-eval-case-procedure` from an up-to-date main.
2. Get the human's answers to Q1 and Q2 below, and record the Q1 placement as one row in `docs/decisions.md`.
3. Test-writer: write failing tests for AC1 to AC6 in `tests/eval/test_harness.py`.
   - Build the synthetic fixture with the real adapters: run `approve_spec` on sv_01, then record `PlanCreated`, `PlanApproved`, `TaskStateChanged` and `CommitRecorded` through `SqliteEventRecorder`.
   - Checkpoint the database, then make the bundle with real `git`.
   - Write two case directories with specs, plus `labels.yaml` per ADR-021.
   - Use a stand-in `LLMProvider` returning a fixed `ClassifierReply`, or raising `LLMError`.
4. Implement `tests/eval/harness.py`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`: an "Eval harness" subsection after "Eval cases".
   - `docs/progress.md`: Current, a Done line, item 5c ticked, and a Later line for the Spec gaps item if the human has not settled it.
   - This record's Outcome.
7. Commit `test(eval): add the eval case procedure` with trailers `Task: TASK-114` and `Milestone: M7`. Do not push.

## Files expected to change
- `tests/eval/harness.py` (new, about +80)
- `tests/eval/test_harness.py` (new, about +200)
- `docs/decisions.md` (one row), `docs/architecture.md`, `docs/progress.md`, this record

Not expected to change: anything under `src/`, `pyproject.toml`, existing tests, `docs/spec/`, `docs/generated/`, `tests/eval/fixture/` and `tests/eval/cases/` (no real fixture or case is committed).

Expected size: about 290 lines, none under `src/`.

## Open questions (for the human, before tests are written)
1. **Q1, where the procedure lives.**
   - Proposed: `tests/eval/harness.py`, test code. It sits in the same directory as TASK-115's `tests/eval/test_eval.py`, so pytest's default `prepend` import mode makes `import harness` work. ADR-011 is untouched. The cost: pyright (`include = ["src"]`) does not check it.
   - Alternative B: `src/openfactory/eval_harness.py`, a second composition root next to `cli.py`. Pyright checks it, but it changes ADR-011's "the one module that imports from `adapters` and from `app`", so it needs an ADR.
   - Alternative C: an `app/` use case behind a new fixture-restore port with an adapter. Layered, but it is a new port and adapter (ADR) for test infrastructure.
2. **Q2, cloning.**
   - Proposed: `subprocess.run(["git", "clone", "--quiet", bundle, dest], check=True)` in the harness. No branch-name fetch is needed, because `approve spec` and `impact` read only the specs and the database (ADR-021).
   - Alternative: also fetch `refs/*:refs/*`, as ADR-021 describes for a step that reads branch names. No such step exists here.

## Answers (human, 2026-10-25)
Plan approved as proposed: Q1 test code in `tests/eval/harness.py`; Q2 plain clone; the spec gap is deferred with both results returned unchanged. The harness copies `cli._open_adapters`'s adapter list rather than importing the private name. Recorded in `docs/decisions.md`.

## Spec gaps
- **"Evaluation plan" › Targets (SC-226) and › Procedure.**
  - What is unclear: the spec scores a case whose `impact` "fails", and the row shows `classifier call failed`. It does not say what a case is when `approve spec` refuses its spec files (violations, unloadable, nothing to approve), or when `impact` refuses (`no spec change since sv_NN`). Is that a failed `impact`, which misses every target, or a broken case that stops the eval?
  - Why it does not block TASK-114: the harness interprets neither result. It runs both use cases and returns both results unchanged (AC5), so the decision falls to TASK-115's scoring.
  - It must be settled before TASK-115 is planned: through a `/spec-change`, or, if the human reads it as a malformed case outside the spec, through a decisions row that makes the eval raise.

## Outcome
Added `tests/eval/harness.py` (`restore_fixture`, `replace_specs`, `run_case`, frozen `CaseRun`) and `tests/eval/test_harness.py` (8 tests, default suite). Nothing under `src/` changed. Results: full suite 2197 passed, ruff clean, pyright clean, check_docs passed. Docs: "Eval harness" in `docs/architecture.md`, `docs/progress.md`, the `docs/decisions.md` row. The refused-case Spec gap stays open as a Later line for TASK-115.

Mechanical test edits by the implementer (assertion intent unchanged), all in `tests/eval/test_harness.py`:
- the long trailing comment on `import harness` moved to its own line above it (E501);
- ruff sorted `import harness` into the third-party import block;
- ruff format split the `FIXTURE_ADRS` dict over several lines (E501).
