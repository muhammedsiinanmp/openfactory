# TASK-050: Context pack for an implementer run

- Milestone: M3
- Status: done
- Tests: acceptance
- ADR: ADR-014 (accepted). "The context pack (SC-64)": "One prompt text with the instructions, the contract, the spec items it names and the names of the tracked files that match `allowed_paths`. It holds no file contents ... Its SHA-256 is the run's `context_hash`." No new port, adapter, dependency, event type, payload or storage change. The module name, the form of the contract in the text, the order of the spec items and where `context_hash` lives are rows in `docs/decisions.md` (Open questions 1 to 5, answered), as in TASK-031.
- Spec impact: wording. Three items, none stops the task (see "Spec gaps").
- Spec sections (spec v1.12, SC-64): "Execution" › "The context pack", "Per-task sequence" (step 2); "Task contract" › "Path patterns"; "Traceability" (the sentence "The implementer's instructions require every new test to carry a `req` marker"); "Domain model and storage" › "Event payloads" (the `context_hash` line of `AgentRunStarted`)

## Outline item
M3 outline item 1, first of two pieces. Left in item 1: the commit message (SC-65), planned as TASK-051. Items 2 to 5 are left.

## Objective
Give the run use case one pure function that builds the context pack of an implementer run from a task contract, the stored spec set of the plan's spec version and the tracked file names of the worktree. Its hash is taken with the existing `context_hash`.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings and to SC-64.

## Prerequisite
None. No `claude` call and no git call.

## Scope
In:
- `src/openfactory/app/context_pack.py` (new), pure, no I/O:
  - `build_context_pack(contract: TaskContract, spec: SpecSet, tracked_files: Sequence[str]) -> ContextPack`.
  - Plain headed text in fixed order: instructions, the task contract, the named requirements with their named criteria, the bodies of the ADRs those requirements are constrained by, the tracked file names that match `allowed_paths`.
  - The instructions hold the opening sentence and the six bullets of the spec's "Path patterns" word for word, as the module's own text (Open question 4).
  - The spec items are in the stored set's order, by filtering (Open question 5).
  - An empty part is written as `(none)`, as in the planner prompt.
  - The module does not import `context_hash`: nothing in it calls the function. The run use case (outline item 2) takes the hash with `context_hash` of `app/planner_prompt.py`, which is not moved (Open question 1).
- Tests: a new unit file, and one conformance test added for the path pattern block.

Out (not this task):
- The commit message (TASK-051).
- Any change to `src/openfactory/app/planner_prompt.py`.
- Any caller: reading `SpecVersions.spec_set(<plan's spec version>)`, calling `GitProvider.tracked_files(worktree)`, recording `AgentRunStarted` with the hash (outline item 2).
- "The last failure report if this is a retry (from M4)": no parameter for it now.
- File contents in the pack (ADR-014 rejected them).
- Moving or renaming `context_hash`.
- Hardening: a contract id that the spec set does not hold. Plan checks make it unreachable; such an id is left out and no test covers it.
- Any test of the instructions' wording or of the text's layout.

## Acceptance criteria
"The context pack" and "Per-task sequence" are under "Execution"; "Path patterns" is under "Task contract". Tests check what the pack holds, never wording or layout (the TASK-031 rule).

Terms:
- **The sample contract** is a `TaskContract` for `AUTH-002` that names `REQ-AUTH-001` and the criterion `AC-AUTH-001-1` only, with `allowed_paths` `["app/auth/**", "tests/auth/**"]`.
- **The sample set** is a `SpecSet` with:
  - `REQ-AUTH-001` (criteria `AC-AUTH-001-1` and `AC-AUTH-001-2`, `constrained_by` `ADR-001`);
  - `REQ-BILL-001` (`constrained_by` `ADR-002`), which the contract does not name;
  - `ADR-001`, `ADR-002` and `ADR-003`, each with a body no other text holds.

- [x] AC1 ("The context pack": "the implementer's instructions, which require a `req` marker on every new test, forbid `git commit`, and tell the agent to leave no file outside `allowed_paths`, by-products of the tools it runs included (for example `__pycache__/`)"; "Traceability": "The implementer's instructions require every new test to carry a `req` marker"; SC-64):
  - `build_context_pack` returns a `str`.
  - The text holds `pytest.mark.req`, `git commit`, `allowed_paths` and `__pycache__`.
- [x] AC2 ("The context pack": "the task contract"; SC-64):
  - The pack holds the contract's task id and objective.
  - It holds every requirement id, criterion id, `depends_on` id, component, `allowed_paths` entry and `forbidden_paths` entry of the contract.
  - It holds the five gate names and the three limit values.
  - The text holds `contract.model_dump_json(indent=2)` unchanged (Open question 3).
- [x] AC3 ("The context pack": "the requirements and acceptance criteria the contract names and the bodies of the ADRs they are constrained by, all from the plan's spec version as stored"; SC-64):
  - The pack holds the id, title and statement of `REQ-AUTH-001`, the id and text of `AC-AUTH-001-1`, and the body of `ADR-001` unchanged.
  - It does not hold the statement of `REQ-BILL-001`, or the bodies of `ADR-002` and `ADR-003`.
  - It does not hold the text of `AC-AUTH-001-2` (Open question 2).
  - The spec items come only from the `spec` argument. The function takes no `SpecFiles` and no port.
- [x] AC4 ("The context pack": "the names of the tracked files in the worktree that match `allowed_paths`" and "It holds no file contents"; "Path patterns"; SC-64):
  - With tracked files `["README.md", "app/auth/login.py", "app/billing/pay.py", "tests/auth/test_login.py"]`, the pack holds `app/auth/login.py` and `tests/auth/test_login.py`, each on its own line and in that order.
  - It holds neither `README.md` nor `app/billing/pay.py`.
  - With no matching file, and with an empty list, the pack still holds the instructions, the contract and the spec items.
  - Matching is `matches_any(contract.allowed_paths, name)` from `domain/path_patterns.py`.
- [x] AC5 ("The context pack": "`context_hash` is the SHA-256 of the text encoded as UTF-8, as for a planner run"; "Per-task sequence" step 2: "Build the context pack and hash it; the hash is the run's `context_hash`"; SC-64):
  - Two calls with equal arguments give equal text.
  - `context_hash(pack)`, with `context_hash` imported by the test from `openfactory.app.planner_prompt`, equals `hashlib.sha256(pack.encode("utf-8")).hexdigest()`, for a pack that holds a non-ASCII character in the objective.
  - A changed objective, a changed ADR body and one more matching file name each give a different hash.
  - `app/context_pack.py` imports only from `openfactory.domain` (and the standard library), and nothing from `ports`, `adapters` or `cli` (checked with `ast`, as in `tests/unit/test_planner_prompt.py`).
- [x] AC6 ("Path patterns": the opening sentence and its six bullets; Open question 4):
  - A conformance test in `tests/unit/test_spec_conformance.py`, of the TASK-039 form, finds the opening sentence and the six bullets of the spec's "Path patterns" word for word in the pack.
  - `src/openfactory/app/planner_prompt.py` is not changed, and every existing test passes unchanged.

## Architecture rules that apply
- `app` depends on `domain` and `ports` only. This module needs no port and does no I/O.
- `ContextPack` comes from `domain/agent_run.py`.
- No event is recorded. `cli.py`, `ports/` and `adapters/` are not changed.
- No new dependency. No `req` markers on OpenFactory's own tests.
- Existing tests are fixed: none is edited. The planner prompt's text, and so the `context_hash` of a planner run, does not change: its module is not touched.
- No hardening beyond what the spec asks.

## Plan
1. Create branch `task/TASK-050-context-pack` from an up-to-date main.
2. Write failing tests:
   - `tests/unit/test_context_pack.py` (new) for AC1 to AC5;
   - one test in `tests/unit/test_spec_conformance.py` for AC6.
3. Add `app/context_pack.py`: the instructions constant with the path pattern lines, private section helpers and `build_context_pack`. The spec items are filtered from `spec.requirements`, each requirement's `acceptance_criteria` and `spec.adrs`, as `build_planner_prompt` does.
4. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
5. Update the living docs, the rows in `docs/decisions.md` and the Outcome. Commit `feat(app): build the context pack of an implementer run` with trailers `Task: TASK-050` and `Milestone: M3`.

## Files expected to change
- `src/openfactory/app/context_pack.py` (new, about 90 lines)
- `tests/unit/test_context_pack.py` (new, about 170 lines)
- `tests/unit/test_spec_conformance.py` (one test added, about 15 lines)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-050-context-pack.md` (this record; Outcome at close)

Not expected to change: `cli.py`, `app/planner_prompt.py`, `app/plan.py`, everything under `domain/`, `ports/` and `adapters/`, every existing test, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 275 lines with tests.

## Living docs to update
- `docs/architecture.md`: new section "Context pack" (`app/context_pack.py`); "Data flow" says `build_context_pack` exists for the run use case and nothing calls it yet.
- `docs/progress.md`: Current, Done, outline item 1 reworded to the commit message alone, and the Later lines listed below.
- `docs/decisions.md`: rows for the answered open questions and for the split of outline item 1.
- `CHANGELOG.md` and `README.md`: no change (nothing a user sees).

## New dependencies
None.

## Spec gaps
Spec impact is "wording": three items, none stops the task.

1. "Execution" › "The context pack", bullet "the requirements and acceptance criteria the contract names".
   - Unclear: whether a named requirement is shown with all its criteria or only with those the contract names.
   - Does not block: either reading gives a valid pack. Answered by Open question 2.
2. "Execution" › "The context pack", the list as a whole, against "Task contract" › "Planning" ("The prompt states the path pattern syntax").
   - Missing: the planner prompt must state the pattern syntax; the context pack's list does not say so. The implementer is told to leave no file outside `allowed_paths`, and a path violation escalates with no retry.
   - Does not block: the instructions' wording is free beyond the three things the bullet requires. Answered by Open question 4.
3. "Execution" › "The context pack", bullet "the names of the tracked files in the worktree that match `allowed_paths`".
   - Unclear: a tracked file that matches both an `allowed_paths` and a `forbidden_paths` pattern is listed, though changing it is a violation.
   - Does not block: the task follows the text as written (only `allowed_paths` is consulted), with no test of that case.

Readings, not gaps (each follows from the text as written):
- "the task contract": the spec gives no form for it in the text; the layout is the task's, as for the planner prompt (TASK-031 row of 2026-10-11).
- "all from the plan's spec version as stored": the function takes a `SpecSet`; the run use case reads it with `SpecVersions.spec_set`. The spec files on disk are never read.
- "as for a planner run": the same hash function.
- "the last failure report if this is a retry (from M4)": not built in M3.

## Later lines in `docs/progress.md`: taken or left
- **"A caller that omits the path to `GitProvider.tracked_files` silently reads the checkout ... the context-pack task asserts the path it passes" (TASK-043, advisor).** Not taken. The builder is pure and takes the names as an argument, as `build_planner_prompt` does; the port call is in the run use case. Reworded at close to "the run use case task (outline item 2) asserts the path it passes".
- **"`context_hash` lives in `app/planner_prompt.py` and may need moving or renaming when the M6 classifier needs it" (TASK-031, advisor).** Left. Reworded at close to say the run use case will import it for implementer runs too.
- **"Spec wording: 'Commit trailers', 'The body is the run's `summary`' ... git's message clean-up" (TASK-044, planner).** Left. It belongs to TASK-051.
- **"`matches`, `matches_any` and `violating_paths` ... no use case calls them yet" (architecture, Data flow).** Half taken: `matches_any` gets its first caller.
- **"No others available" and the target repo's own Claude Code files (TASK-048).** Left. The pack does not cover them; the spec says so.
- **"Current" still reads "TASK-049 ... (done; commit pending)" though main is at #79.** Corrected at close with the Current line of this task.
- **Every other Later line:** left.
- **Added when this record was saved:** the three "Spec wording" lines of "Spec gaps".
- **To add at close:**
  - "The path pattern lines are held twice, in `app/planner_prompt.py` and `app/context_pack.py`, each tied to the spec by its own conformance test (TASK-050, advisor)".
  - "The instructions of the context pack were not tried on a real implementer run; look at them at the first real `run` (TASK-050, planner)".

## Open questions
All answered by the human on 2026-10-14 ("do as the advisor says"); the criteria above are written for these answers.

1. **Where the module and the hash live.** Answer: `app/context_pack.py` with `build_context_pack`; `context_hash` stays in `app/planner_prompt.py` and is not moved. The module imports it only if its own code calls it, which it does not; the test and, later, the run use case import it from `planner_prompt`.
2. **Criteria of a named requirement.** Answer: only the criteria the contract names are shown under their requirement.
3. **The form of the contract in the text.** Answer: `contract.model_dump_json(indent=2)` under a "Task contract" heading.
4. **Path pattern syntax in the pack.** Answer: included, as the pack's own text with its own conformance test; no constant shared with the planner prompt and no change to `planner_prompt.py` (the advisor's alternative; the planner proposed a shared constant).
5. **Order of the spec items.** Answer: the stored set's order, by filtering `spec.requirements`, each requirement's `acceptance_criteria` and `spec.adrs` (the advisor's alternative; the planner proposed the contract's order). No test fixes the order beyond "equal arguments give equal text".

## Outcome
Built `build_context_pack(contract, spec, tracked_files) -> ContextPack` in the new `src/openfactory/app/context_pack.py`: pure, importing only `openfactory.domain`. The text has the instructions (with the spec's "Path patterns" sentence and six bullets as the module's own text), the contract as `model_dump_json(indent=2)`, the named requirements with only the named criteria, the bodies of the ADRs they are constrained by, and the tracked file names that match `allowed_paths`, each part in the stored set's order or the order given, `(none)` when empty. The module does not import `context_hash`; `app/planner_prompt.py` is unchanged.

- Tests: new `tests/unit/test_context_pack.py` (10 tests) and one conformance test in `tests/unit/test_spec_conformance.py`.
- Deviations from the plan: none.
- Test edits: none; no existing test changed and no test-writer test edited.
- Checks: 1207 tests pass; ruff, pyright and `check_docs` clean.
- Follow-ups (Later lines in `docs/progress.md`): the path pattern lines held in two modules; the instructions untried on a real implementer run; the TASK-043 and TASK-031 lines reworded to the run use case task; the commit message is TASK-051.
