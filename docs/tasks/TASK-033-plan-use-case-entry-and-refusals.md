# TASK-033: Plan use case, the entry and the refusals

- Milestone: M2
- Status: done
- Tests: acceptance
- ADR: ADR-013 (accepted) covers the two-call shape, and says "Names, signatures and result types are settled in the tasks that build them". No new port, adapter, dependency, event type, payload or storage change, so no new ADR. ADR-012 covers `Plans`, `SpecVersions.spec_set` and `GitProvider`, and tests with in-memory fakes; ADR-001 covers reading spec versions through `SpecVersions`. Names and result types are rows in `docs/decisions.md` (Open questions 1 to 3).
- Spec impact: none. The spec settles the three refusals, their order, the warning's condition and time, and the `git ls-files failed` refusal (see "Spec gaps": readings only).
- Spec sections (spec v1.11): "Task contract" › "Planning" (the first two bullets, and "the list of tracked files from `git ls-files`"); "Spec input format" › "Policies" ("`openfactory plan` refuses to run while the policy is invalid", "A missing file is a policy problem", "It is read when a plan is created"); "CLI commands" › "Output" (the `plan` refusals bullet and the warning bullet); "Domain model and storage" › "Ids" ("the stored spec set of a version", "the approved plan if there is one", "The list of tracked files comes from `GitProvider`") and "Streams and actors" (the paragraph that starts "`plan` records `AgentRunStarted` before each planner call")

## Outline item
M2 outline item 9b ("Plan use case, the entry and the refusals"). Item 10 (the `plan` command) is left.

## Objective
Add the two app-layer functions ADR-013 fixes: an entry function that returns one of the three refusals or the approved spec version's id and spec set, the policy and the `spec files differ` flag, and a second function that reads the tracked files from `GitProvider` and calls `run_planner`, returning a `GitError` as data.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings.

## Scope
In (names per Open questions 1 to 3), all in `src/openfactory/app/plan.py`:
- `PlanRefusal(StrEnum)`: `no_approved_spec`, `invalid_policy`, `approved_plan`.
- `PlanRefused` (frozen, `extra="forbid"`): `reason: PlanRefusal`, `plan_id: str | None` (set only for `approved_plan`).
- `PlanInputs` (frozen, `extra="forbid"`): `spec_version: str`, `spec: SpecSet`, `policy: Policy`, `spec_files_differ: bool`.
- `prepare_plan(files: SpecFiles, versions: SpecVersions, plans: Plans) -> PlanRefused | PlanInputs`.
- `create_plan(inputs: PlanInputs, *, git: GitProvider, llm: LLMProvider, runs: Runs, plans: Plans, recorder: EventRecorder) -> PlannerResult`.
- `PlannerOutcome` gains one member, `git_failed`; `PlannerResult.error` then holds the whole `GitError` text. `run_planner` never returns it.
- Unit tests with in-memory fakes. No database, no git, no `claude`.

Out (not this task):
- `cli.py`: the `plan` command, the refusal texts on standard error, the `spec files differ from approved sv_NN` line, the task and rejection lines, taking the first line of `error`, exit codes, structlog configuration (item 10).
- Any change to `run_planner`, `_attempt`, the prompt, the checks, the ports or the adapters.
- `approve plan`, the `deleted-requirement` rule, the M2 close test (items 11 to 13).
- Returning the policy problems with the `invalid_policy` refusal: the refusal is one line that points at `validate`.
- Hardening: `versions.spec_set(...)` returning `None` for the version `latest_approved()` just gave (an `assert`, as `approve_spec` does); a tracked name that is not UTF-8; `GIT_DIR` in the environment.

## Acceptance criteria
"Planning" is under "Task contract"; "Policies" under "Spec input format"; "Output" under "CLI commands"; "Ids" and "Streams and actors" under "Domain model and storage".

Fixtures:
- "The sample set" and "the sample policy file" (`forbidden_paths: ["secrets/**"]`) are those of TASK-031/TASK-032, written as spec file texts for a fake `SpecFiles` (a dict of path to text).
- The fake `SpecVersions` returns a chosen `latest_approved()` (`SpecVersionRef` with id and hash) and a chosen `spec_set(id)`; "approved `sv_02` equal to the files" means its hash is `content_hash` of the set the files load into.
- The fake `Plans` returns a chosen `approved()`, `current_draft()` and `next_id()`.
- The fake `GitProvider` returns a chosen list or raises a chosen `GitError`, and counts its calls.
- The fake LLM, `Runs` and recorder are those of `tests/unit/test_plan_use_case.py`; "a good reply" is the one defined there.

- [x] AC1 ("Planning": "`openfactory plan` uses the latest approved spec version. It fails if there is none"; "Output": "The refusals, checked in this order: `no approved spec version`; `policy is invalid; run openfactory validate`; `plan_NN is already approved; use replan`"). With `latest_approved()` `None`, a policy file with an unknown key, and `Plans.approved()` returning `plan_01`:
  - `prepare_plan` returns `PlanRefused` with `reason` `no_approved_spec` and `plan_id` `None`.
- [x] AC2 ("Policies": "`openfactory plan` refuses to run while the policy is invalid" and "A missing file is a policy problem"; "Planning": "`openfactory plan` refuses to run while `specs/policies.yaml` is invalid"; "Output": the same order). With approved `sv_02` and `Plans.approved()` returning `plan_01`:
  - A policy file with an unknown key gives `PlanRefused` with `reason` `invalid_policy` and `plan_id` `None`.
  - No `policies.yaml` gives the same.
- [x] AC3 ("Planning": "It fails if an approved plan exists, for any spec version"; "Output": "`plan_NN is already approved; use replan`"; "Ids": "the approved plan if there is one"). With approved `sv_02`, the sample policy file, and `Plans.approved()` returning `PlanRef(id="plan_03", spec_version="sv_01")`:
  - `prepare_plan` returns `PlanRefused` with `reason` `approved_plan` and `plan_id` `plan_03`.
- [x] AC4 ("Planning": "`openfactory plan` uses the latest approved spec version"; "Policies": "It is read when a plan is created"; "Ids": "the stored spec set of a version"; "Planning": "Running `plan` again while a draft plan exists records a new `PlanCreated`"). With approved `sv_02` equal to the files, the sample policy file, no approved plan and `current_draft()` returning `plan_01`:
  - `prepare_plan` returns `PlanInputs` with `spec_version` `sv_02`, `spec` equal to what `spec_set("sv_02")` returned, `policy` equal to `load_policy(files).policy` (its `forbidden_paths` is `["secrets/**"]`) and `spec_files_differ` `False`.
  - `prepare_plan` takes exactly the three ports `SpecFiles`, `SpecVersions` and `Plans` (checked with `inspect.signature`): no recorder, no `GitProvider`, no LLM.
- [x] AC5 ("Output": "When the spec files differ from the latest approved version, or cannot be loaded, `plan` writes the warning ... and carries on"; "Planning": "warns if the files on disk differ from it"). With approved `sv_02`, the sample policy file and no approved plan:
  - Files that load into a set whose hash is not `sv_02`'s (one criterion text changed) give `PlanInputs` with `spec_files_differ` `True`, and `spec` is the set `spec_set("sv_02")` returned, not the set in the files.
  - No `requirements.yaml` gives `PlanInputs` with `spec_files_differ` `True` and the same stored `spec`.
- [x] AC6 ("Planning": "the list of tracked files from `git ls-files`"; "Ids": "The list of tracked files comes from `GitProvider`"; "Output": "`git ls-files failed: <error>`; `planner call failed: <error>`. `<error>` is the first line of the failure's text"; "Streams and actors": "`plan` records `AgentRunStarted` before each planner call"). With a `PlanInputs` for `sv_02`, the sample set and the sample policy:
  - Git returns the sample files and the LLM a good reply:
    - `GitProvider.tracked_files` is called once.
    - The prompt the LLM received equals `build_planner_prompt(inputs.spec, inputs.policy, <the files>)`.
    - Three events are recorded, and `PlanCreated.spec_version` is `sv_02`.
    - The result is `created` with the plan id from `Plans.next_id`.
  - Git raises `GitError("warning: first\nfatal: second")`:
    - The result has `outcome` `git_failed`, `error` equal to that two-line text unchanged, `plan_id` `None`.
    - The LLM is not called, no event is recorded, and neither `Runs.next_id` nor `Plans.next_id` is called.

## Architecture rules that apply
- `src/openfactory/app` depends on `domain` and `ports` only. `plan.py` imports `GitError` and `GitProvider` from `ports/git_provider.py`, and `load_policy`, `load_spec` from `app/spec_loader.py`. The existing `ast` import test of `tests/unit/test_plan_use_case.py` must still pass.
- Both functions return data and print nothing (ADR-013; decisions row of 2026-10-10, TASK-018). No refusal text and no warning text is written in `app`.
- `prepare_plan` records no event: `plan` records only the run events and `PlanCreated` ("Streams and actors"), so files that differ are not imported.
- All state changes go through the events table: `create_plan` records only through `run_planner`.
- Tests from the test-writer are fixed. No existing test is changed.
- No hardening beyond the spec's rules.

## Plan
1. Create branch `task/TASK-033-plan-use-case-entry-and-refusals` from an up-to-date main, carrying the human's two uncommitted edits (ADR-013 accepted, the `CLAUDE.md` line), and commit them there unmodified as their own commit `docs(adr): accept ADR-013` (Open question 6).
2. Get the human's answers to the Open questions; record them here and as rows in `docs/decisions.md`.
3. Write failing tests in `tests/unit/test_plan_entry.py` (new) for AC1 to AC6, with fakes for `SpecFiles`, `SpecVersions`, `Plans` and `GitProvider`, and the LLM, `Runs` and recorder fakes redefined locally (the repo has no shared test helpers).
4. In `app/plan.py`:
   - Add `PlanRefusal`, `PlanRefused`, `PlanInputs`, and `git_failed` on `PlannerOutcome`.
   - `prepare_plan`, in this order, returning at the first that applies:
     - `versions.latest_approved()` is `None`: `no_approved_spec`.
     - `load_policy(files)` has violations: `invalid_policy`.
     - `plans.approved()` is not `None`: `approved_plan` with its id.
     - Then `load_spec(files)`; the flag is true when it has no spec set or `content_hash` of the set is not the approved version's hash. The spec files are loaded only here, after the three checks.
     - `versions.spec_set(approved.id)`, asserted not `None`; return `PlanInputs`.
   - `create_plan`: call `git.tracked_files()`; on `GitError` return `PlannerResult(outcome=git_failed, error=str(error))`; otherwise return `run_planner(inputs.spec_version, inputs.spec, inputs.policy, files, llm=..., runs=..., plans=..., recorder=...)`.
   - Extend the module docstring to name the two functions and ADR-013.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until green.
6. Update the living docs and the Outcome. Commit `feat(app): add the entry and the refusals of the plan use case` with trailers `Task: TASK-033` and `Milestone: M2`.

## Files expected to change
- `src/openfactory/app/plan.py` (about 80 lines added)
- `tests/unit/test_plan_entry.py` (new, about 300 lines)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-033-plan-use-case-entry-and-refusals.md`

Not expected to change: `cli.py`, the other modules under `app/`, everything under `domain/`, `ports/` and `adapters/`, `pyproject.toml`, `docs/spec/`, and every existing test file. `docs/adr/ADR-013-*.md` and `CLAUDE.md` change only by the human's two edits, in their own commit (Open question 6).

## Living docs to update
- `docs/architecture.md`:
  - New section "Plan use case: the entry and the refusals": the order of the three checks, when the spec files are loaded, the flag, what each function returns, the `GitError` path, and that `cli.py` keeps the order of the two calls (ADR-013).
  - "Data flow": `prepare_plan` now calls `SpecVersions.latest_approved`, `SpecVersions.spec_set`, `Plans.approved`, `load_policy` and `load_spec`; `create_plan` calls `GitProvider.tracked_files` and `run_planner`. Correct the lines that say no use case calls `spec_set`, `Plans.approved` or `GitProvider`. No command calls either function yet, and `cli.py` wires no M2 adapter.
- `docs/progress.md`:
  - When the task starts: Current, and drop the clause "ADR-013 (proposed) records the two-call shape; the human accepts it, and words the `CLAUDE.md` line ..., before this is planned" from item 9b (the ADR is accepted).
  - At close: Done line, remove item 9b, Current to "next is outline item 10".
  - Reword the TASK-030 Later line on the `warning:` first line so it names item 10 and says `create_plan` returns the whole text.
- `docs/decisions.md`: rows for the answered questions.
- `CHANGELOG.md`, `README.md`: no change (no command or output is added).

## New dependencies
None.

## Spec gaps
Spec impact is "none". Nothing is missing for this task.

Readings, not gaps:
- "Output" lists five refusals "checked in this order". The first three are `prepare_plan`'s; `git ls-files failed` is `create_plan`'s; `planner call failed` is `run_planner`'s `failed` outcome, already built. The warning's time ("after the first three refusals have been checked and before `git ls-files` runs") is kept by `cli.py` between the two calls (ADR-013).
- "The policy is invalid" covers a missing `policies.yaml`: "Policies" calls a missing file a policy problem.
- "Differ" is hash inequality with the latest approved version, the comparison "Spec versions" uses for `validate`. "Cannot be loaded" is `load_spec` returning violations. A draft spec version has no part in it.
- "A `plan` refused by one of them writes no warning": a `PlanRefused` has no flag, so `cli.py` cannot print one.
- "It fails if an approved plan exists, for any spec version": `Plans.approved()` is not `None`; its `spec_version` is not compared (AC3 uses an older one).
- `plan` plans from the stored spec set of the approved version, not from the files, also when the files are equal to it.
- `<error>` "is the first line of the failure's text": the function returns the whole text and item 10 takes the first line, as TASK-032 left it for `planner call failed`.

## Later lines in `docs/progress.md`: taken or left
- `GitCli.tracked_files`, a `warning:` line before `fatal:` becomes `<error>` (TASK-030, reviewer): left to item 10, which builds the line. This task returns the whole text; AC6 uses a `warning:` first line so the whole text is visibly kept. The line is reworded, not removed.
- A tracked name that is not UTF-8 raises `UnicodeDecodeError`, not `GitError` (TASK-030, reviewer): left. `create_plan` catches `GitError` only; catching more is hardening, and the fix belongs in the adapter.
- `GitCli` passes the caller's environment (TASK-030, reviewer): left, M3.
- Spec wording on the form of a path name from `git ls-files` (TASK-030, planner): left; no criterion depends on it.
- Whether a plan with no tasks is created (TASK-032, planner): left. `prepare_plan` adds no check for an approved spec set with no live requirement; inventing a fourth refusal is the spec's decision.
- A started run can lack a finish (TASK-032): left, before M7. `create_plan` adds no handling.
- An envelope with `is_error` and exit status 0, and what `claude` prints on a non-zero exit (TASK-029/TASK-031): left to the M2 close.
- Spec gap F-1, what a command prints when the recorder's catch-up fails: left; `prepare_plan` takes no recorder, and opening one is item 10's wiring.

## Open questions
None is a spec decision. Each has a proposal.

1. **Names.** Proposed: `prepare_plan` and `create_plan` in `app/plan.py` (TASK-032 row: "9b adds its functions to the same module"). Alternative: `check_plan_entry` and `plan`; `plan` would shadow the module name and `check_plan` already exists in the domain.
2. **Result of the second function.** Proposed: `create_plan` returns `PlannerResult`, and `PlannerOutcome` gains `git_failed`. One type for `cli.py` to match on, about three lines of code, and no existing test asserts the enum's exact members. Alternative: a new `PlanResult`/`PlanOutcome` that wraps `PlannerResult`, which repeats four fields to keep `PlannerOutcome` free of a value `run_planner` never returns.
3. **Result of the entry function.** Proposed: a union, `PlanRefused | PlanInputs`, so `create_plan` takes a `PlanInputs` whose fields are never `None` and `cli.py` needs one `isinstance`. The refusal is an enum plus the plan id; `cli.py` writes the spec's texts, as it does for `nothing to approve`. Alternative: one model with an outcome enum and nullable fields, as `ValidateResult` has, which needs asserts before the second call. A second alternative puts the refusal text in the result; it moves output wording into `app`.
4. **Spec files not loaded on a refusal.** The SC-46 decisions row says "A refused `plan` then loads no spec files"; the spec text says only that no warning is written. Proposed: the code loads them after the three checks (plan step 4) and no criterion asserts it, since it traces to the decisions log and not to spec text. Alternative: assert on the fake `SpecFiles` that `requirements.yaml` is not read when refused.
5. **Test file.** Proposed: a new `tests/unit/test_plan_entry.py`, leaving the fixed `test_plan_use_case.py` untouched, at the price of repeating three fakes. Alternative: add to the existing file.
6. **The uncommitted precondition.** `git status` shows `CLAUDE.md` and `docs/adr/ADR-013-...md` modified on main and not committed. Proposed: carry them onto the task branch and commit them there, unmodified, as their own commit `docs(adr): accept ADR-013` before the task's commit, so one PR brings both and main is not committed to. Alternative (the planner's): the human commits both through their own branch and PR before the task branch is cut.

Answers (the human, 2026-10-12): all six proposals approved as written, after the advisor agreed with each.

## Outcome
Built:
- `src/openfactory/app/plan.py`: `PlanRefusal`, `PlanRefused`, `PlanInputs`, `prepare_plan`, `create_plan`, and the outcome `git_failed` on `PlannerOutcome`.
- `tests/unit/test_plan_entry.py`: AC1 to AC6, with in-memory fakes.
- Commit `docs(adr): accept ADR-013`: the human's two edits, unmodified.

Deviations: none in the code. Two edits to the test-writer's `tests/unit/test_plan_entry.py`, both asked for by the human after the review (reviewer notes 1 and 3), neither weakening an assertion:
- `FakeVersions.spec_set` records the ids it is asked for, and the first AC4 test now also asserts `prepare_plan` asked for `sv_02` only (a stronger check).
- The comment on `stored_set()` said "A set that is not the sample set"; it now says what the helper returns.

Reviewer note 2 was also applied: `prepare_plan` and `create_plan` have docstrings. `git pull` could not run at task start because of the two uncommitted edits, so `git fetch` confirmed main was level with origin/main.

Follow-ups:
- Item 10 builds the `plan` command, the refusal and warning texts, and takes the first line of `error`.
