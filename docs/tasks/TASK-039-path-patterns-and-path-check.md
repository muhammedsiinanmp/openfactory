# TASK-039: Path patterns and the path check in the domain

- Milestone: M3
- Status: done
- Tests: acceptance
- ADR: ADR-014. It is accepted and decides both halves: "Path patterns (SC-59). One syntax for `allowed_paths` and `forbidden_paths` ... It is a small hand-written matcher in the domain, with no new dependency" and "The path check is a pure function in the domain". No new port, adapter, dependency, event type, payload or storage change. The module name, the function names and the prompt wording are rows in `docs/decisions.md` (Open questions 2 to 4).
- Spec impact: wording. Two items, neither stops the task (see "Spec gaps"): whether `*` can match no characters, and the order of the violating paths. No criterion depends on the first; the second is Open question 2.
- Spec sections (spec v1.12): "Task contract" › "Path patterns" (the opening sentence and the six bullets); "Task contract" › "Planning" ("The prompt states the path pattern syntax"); "Spec input format" › "Policies" ("It uses the same glob syntax as the paths in a task contract"); "Execution" › "The path check" ("A path is a violation when it matches a `forbidden_paths` pattern or matches no `allowed_paths` pattern"); "Gates and remediation" (the `path_check` row of the table); "Tech stack and repo layout" / "Domain model and storage" (the M3 paragraph: the path check is in the domain, `gates/` removed)

## Outline item
M3 outline item 1, whole. Items 2 to 13 are left.

## Objective
Add a pure path pattern matcher and a pure function that gives the violating paths of a list of changed paths against a task contract, and make the planner prompt state the pattern syntax.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings.

## Scope
In (names per Open question 3):
- `src/openfactory/domain/path_patterns.py` (new), pure, standard library only:
  - `matches(pattern: str, path: str) -> bool`: one pattern against one path relative to the repo root.
  - `matches_any(patterns: Sequence[str], path: str) -> bool`: used by the path check here and by the context pack later (outline item 9).
  - `violating_paths(changed_paths: Sequence[str], contract: TaskContract) -> list[str]`: the paths that match a `forbidden_paths` pattern or match no `allowed_paths` pattern.
- `src/openfactory/app/planner_prompt.py`: the instructions state the pattern syntax (Open question 4). Nothing else in the prompt changes.

Out (not this task):
- Running git, staging, or reading the changed paths (outline item 5).
- `GateEvaluated`, the gate's output file, the reasons `path_check` and `no changes`, the escalation (items 2, 7, 10). `violating_paths` returns `[]` for an empty list; "a run that changed no path is a failed attempt" is the use case's rule.
- The context pack and its list of tracked files that match `allowed_paths` (item 9).
- Checking pattern syntax in `Policy`, `PlannedTask` or the plan checks. Entries stay plain strings; the spec has no rule that rejects a pattern.
- Odd patterns: an empty string, a leading `/`, `//`, `**` inside a segment. They get no criterion and no special code; what they match follows from the rules (see "Spec gaps", readings).
- Normalising paths (`./`, `\`, a trailing `/`, Unicode forms). Paths come from git as they are.
- Hardening against exotic inputs.

## Acceptance criteria
"Path patterns" and "Planning" are under "Task contract"; "The path check" under "Execution". In AC1 to AC4 every bullet is a call of `matches(pattern, path)`.

- [x] AC1 ("Path patterns": "an entry of `allowed_paths` or `forbidden_paths` is a pattern, matched against a path relative to the repo root, with `/` separators, case-sensitively"; "`*` matches any run of characters except `/`"; "`?` matches one character except `/`"):
  - `app/*.py` matches `app/main.py`. It does not match `app/auth/main.py`, `app/main.pyc` or `src/app/main.py`.
  - `app/mod?.py` matches `app/mod1.py`. It does not match `app/mod.py` or `app/mod12.py`. `a?b` does not match `a/b`.
  - `app/Main.py` does not match `app/main.py`.
- [x] AC2 ("Path patterns": "`**` as a whole segment matches zero or more segments"; the contract example `app/auth/**`):
  - `app/**` matches `app/main.py` and `app/auth/views/login.py`. It does not match `application/main.py` or `src/app/main.py`.
  - `app/**/test_*.py` matches `app/test_a.py` and `app/x/y/test_a.py`. It does not match `app/x/a.py`.
  - `**/conftest.py` matches `conftest.py` and `tests/unit/conftest.py`.
- [x] AC3 ("Path patterns": "A pattern that ends with `/` is the same as that pattern followed by `**`"; "A pattern with no `/` matches a file of that name in any directory, so `.env` and `.env.*` cover every directory, and `*.py` in `allowed_paths` allows a Python file in every directory"):
  - `docs/` matches `docs/a.md` and `docs/x/b.md`. It does not match `src/docs/a.md`.
  - `.env` matches `.env` and `services/api/.env`. It does not match `.envrc`.
  - `.env.*` matches `.env.local` and `deploy/.env.prod`. It does not match `.env`.
  - `*.py` matches `setup.py` and `app/auth/login.py`. It does not match `app/login.pyi`.
- [x] AC4 ("Path patterns": "There are no negations and no character classes: `!` and `[` are literal characters"):
  - `!app/main.py` does not match `app/main.py`. It matches the path `!app/main.py`.
  - `file[1].txt` matches `file[1].txt` and does not match `file1.txt`. `[ab].py` does not match `a.py`.
  - `.env` does not match `xenv` (a `.` is a literal character).
- [x] AC5 ("The path check": "A path is a violation when it matches a `forbidden_paths` pattern or matches no `allowed_paths` pattern"; "Gates and remediation", the `path_check` row: "any changed path of the worktree outside `allowed_paths` or inside `forbidden_paths`"). With a `TaskContract` whose `allowed_paths` is `[app/auth/**, tests/auth/**]` and whose `forbidden_paths` is `[specs/**, .openfactory/**, .env, .env.*, app/auth/secrets/**]`:
  - For the changed paths `app/auth/login.py`, `app/main.py`, `tests/auth/test_login.py`, `specs/requirements.yaml`, `app/auth/secrets/key.pem`, `app/auth/.env`, in that order, `violating_paths` returns `app/main.py`, `specs/requirements.yaml`, `app/auth/secrets/key.pem`, `app/auth/.env` (the order per Open question 2).
  - A path that matches both an allowed and a forbidden pattern is a violation: `app/auth/secrets/key.pem` and `app/auth/.env` above.
  - For `app/auth/login.py` and `tests/auth/test_login.py` alone it returns `[]`. For an empty list it returns `[]`.
  - The contract and the list passed in are unchanged.
- [x] AC6 ("Planning": "The prompt states the path pattern syntax"; "Plan checks": "retried once with the same prompt and the rejection lines added to it"):
  - The text of `build_planner_prompt(spec, policy, tracked_files)` states each of the six rules of "Path patterns" and that a pattern is matched against a path relative to the repo root, case-sensitively (the exact form per Open question 4).
  - The retry prompt (`rejections` given) holds the same statement.
  - Equal arguments still give equal text, and `context_hash` of the prompt is still the SHA-256 of that text as UTF-8.

## Architecture rules that apply
- `domain` stays pure: `path_patterns.py` does no I/O and imports only `openfactory.domain.contracts` and the standard library. Nothing from `ports`, `adapters` or `app`.
- No new dependency (ADR-014 rejected `pathspec`). `fnmatch` and `glob` are not used: `fnmatch` has character classes and lets `*` cross `/`, which the spec rules out.
- One matcher for contracts and the policy (ADR-014: "One syntax ... in contracts and in the policy"). No second matcher is written later; items 9 and 10 call this module.
- `app/planner_prompt.py` keeps importing from `domain` only, and one function builds the first and the retry prompt.
- Tests from the test-writer are fixed. No existing test is expected to change: no test pins the instruction text, and the hash tests compare against the prompt they are given.
- OpenFactory's own tests carry no `req` markers.
- No hardening beyond the spec's rules.

## Plan
1. Create branch `task/TASK-039-path-patterns-and-path-check` from an up-to-date main.
2. Get the human's answers to the Open questions; record them here and as rows in `docs/decisions.md`.
3. Write failing tests:
   - `tests/unit/test_path_patterns.py` (new) for AC1 to AC5, the match cases as `pytest.mark.parametrize` tables of (pattern, path, expected).
   - `tests/unit/test_planner_prompt.py`: tests added for AC6 (and, if Open question 4 is answered as proposed, one conformance test in `tests/unit/test_spec_conformance.py` that reads the bullets under "Path patterns" from the spec file).
4. Write `domain/path_patterns.py`: split pattern and path on `/`; a pattern that ends with `/` gets `**` added; a pattern with no `/` gets `**/` in front; match the segments with `**` taking zero or more path segments; within a segment `*` and `?` are the only special characters.
5. Add `violating_paths`, built on `matches_any`.
6. Add the syntax statement to the planner instructions.
7. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until green.
8. Update the living docs and the Outcome. Commit `feat(domain): add path patterns and the path check` with trailers `Task: TASK-039` and `Milestone: M3`.

## Files expected to change
- `src/openfactory/domain/path_patterns.py` (new, about 60 lines)
- `src/openfactory/app/planner_prompt.py` (about 10 lines)
- `tests/unit/test_path_patterns.py` (new, about 150 lines)
- `tests/unit/test_planner_prompt.py` (about 25 lines added)
- `tests/unit/test_spec_conformance.py` (one test, only if Open question 4 is answered as proposed)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, `CHANGELOG.md`
- `docs/tasks/TASK-039-path-patterns-and-path-check.md`

Not expected to change: everything under `ports/` and `adapters/`, `domain/contracts.py`, `domain/policy.py`, `domain/plan_checks.py`, `cli.py`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, and every existing test's assertions.

Expected size: about 270 lines with tests.

## Living docs to update
- `docs/architecture.md`:
  - A new section "Path patterns and the path check" for `domain/path_patterns.py`.
  - "Planner prompt": the instructions now state the pattern syntax.
  - "Policy model" and "Task contract models": the sentence "their glob syntax is not checked" stays true; add that the matcher is in `path_patterns.py`.
  - "Data flow": the three functions exist and no use case calls them yet.
- `docs/progress.md`: Current, then Done; remove outline item 1 and renumber or keep the "depends on" references correct.
- `docs/decisions.md`: rows for the answered questions.
- `CHANGELOG.md`: the planner prompt states the path pattern syntax (the `context_hash` of new planner runs differs from earlier ones for the same inputs).
- `README.md`: no change expected.

## New dependencies
None.

## Spec gaps
Spec impact is "wording". Neither item stops the task.

1. "Task contract" › "Path patterns", the bullet "`*` matches any run of characters except `/`". The text does not say whether the run can be empty. The next bullet says "zero or more" for `**` and the one after says "one character" for `?`, so the silence stands out. It decides whether `*.py` matches a file named `.py`, or `test_*.py` matches `test_.py`. It does not block: no acceptance criterion uses such a path, and the spec's own examples (`.env.*`, `*.py`, `app/auth/**`) do not depend on it. The code still has to do one or the other, so it is Open question 1 for the human, not an assumption of the task.
2. "Execution" › "The path check", the sentence "the gate's output file lists the violating paths, one per line". The order of the lines is not given. The file is written in outline item 10, but this task's function returns the list it is written from. It does not block: the set of violating paths is fully defined; only AC5's order assertion waits on Open question 2.

Readings, not gaps (each follows from the text as written; none has a criterion of its own unless noted):
- A pattern with a `/` is matched from the repo root ("matched against a path relative to the repo root"), so `app/**` does not match `src/app/main.py` (AC2) and `docs/` does not match `src/docs/a.md` (AC3). The trailing-`/` rule is applied first: `docs/` is `docs/**`, which has a `/`, so the any-directory rule does not apply to it.
- A pattern with no `/` "matches a file of that name": the last segment of the path. `.env` therefore does not match `.env/keys.txt`, a file inside a directory named `.env`. This differs from gitignore; it is what the sentence says.
- "`**` as a whole segment": two `*` inside a segment (`a**b`, `app/**.py`) are two `*`, so they match as one `*` does and do not cross `/`.
- `**` matching zero segments at the end means `specs/**` also matches a file named `specs` at the repo root. No test fixes it.
- The match is of the whole path: `app/*.py` does not match `app/main.pyc` (AC1).
- "Case-sensitively" and "`!` and `[` are literal" are read as: every character other than `*`, `?` and `/` matches itself only.
- A path that matches both lists is a violation: the sentence joins the two conditions with "or" (AC5).
- The policy's `forbidden_paths` need no code here: they are already in the completed contract's `forbidden_paths` (`complete_contract`, TASK-026), so the function takes the contract alone.
- The spec does not give the words of the planner prompt, as for the rest of the prompt (TASK-031). "States the path pattern syntax" is read as: all six rules are stated.

## Later lines in `docs/progress.md`: taken or left
- No Later line is about path patterns or the path check.
- Audit finding F-6 of `docs/spec-audits/2026-10-13-proposal-v1.12.md` (the planner prompt does not state the path pattern syntax; "change the code, in an M3 task") is not a Later line; it is taken here, as AC6.
- "Spec gap (before the M3 run use case is planned)" F-1, F-5, F-7 and the wording items F-2, F-3: left; they concern items 6, 7, 10 and 11.
- "`context_hash` lives in `app/planner_prompt.py` and may need moving" (TASK-031, advisor): left; item 9 meets it first.
- "Look again at including the rejected reply in the retry prompt" (TASK-031): left. This task changes the prompt because the spec asks for it; it does not touch the retry form.
- To add at close, if Open question 1 is not settled by a spec change first: a Later line "Spec wording: whether `*` can match no characters ('Path patterns')", with the answer given.

## Open questions
Question 1 is a spec wording item and is the human's to answer. The others are not spec decisions; each has a proposal.

1. **Can `*` match no characters?** (Spec gaps, item 1.) Proposed: yes, zero or more, as in shell and gitignore globs; record the answer as a decisions row and leave the spec text to a later `/spec-change`. No test is written for it either way. Alternative: one or more.
2. **Order of the violating paths.** Proposed: the order of `changed_paths`, which is git's order; a path given twice is returned twice (git does not give one twice). AC5 asserts that order. Alternative: sorted as strings, without duplicates, so the gate's output file does not depend on git's order.
3. **Module and names.** Proposed: one module `domain/path_patterns.py` with `matches(pattern, path)`, `matches_any(patterns, path)` and `violating_paths(changed_paths, contract)`. Alternative: the matcher there and `violating_paths` in a second module `domain/path_check.py`, which item 10 would then also use for the gate's name and output lines.
4. **How the prompt states the syntax.** Proposed: the instructions get a short block that copies the opening sentence and the six bullets of "Path patterns" word for word, and a conformance test in `tests/unit/test_spec_conformance.py` reads those bullets from the spec file and asserts each is in the prompt, so the prompt cannot drift from the spec. Alternative: the task's own shorter wording, with tests that assert it line by line and a decisions row for the text.

Answers (the human, 2026-10-13, each as proposed and following the advisor; rows in `docs/decisions.md`):
1. `*` matches zero or more characters. No test either way.
2. The order of `changed_paths`, a repeated path returned twice. The line order of the gate's output file is not decided here and stays under "Later".
3. One module `domain/path_patterns.py` with `matches`, `matches_any` and `violating_paths`.
4. The opening sentence and the six bullets copied word for word, Markdown backticks included, with a conformance test in `tests/unit/test_spec_conformance.py` that asserts the opening sentence and each bullet are in the prompt.

## Outcome
Built:
- `src/openfactory/domain/path_patterns.py`: `matches`, `matches_any` and `violating_paths`, as in the plan. No use case calls them yet.
- `src/openfactory/app/planner_prompt.py`: `_INSTRUCTIONS` gains a "Path patterns:" block with the opening sentence and the six bullets of the spec word for word. The `context_hash` of new planner runs differs from earlier ones for the same inputs.
- Tests: `tests/unit/test_path_patterns.py` (new), additions to `tests/unit/test_planner_prompt.py`, and one conformance test in `tests/unit/test_spec_conformance.py` that reads the bullets from the spec.

Deviations from the plan: none.

Test edits: no test-writer test was edited.

Implementation note: two lines of the copied text are wrapped in the source with a backslash continuation to meet the 100-column limit; the prompt text is unchanged.

Outline numbers: this record uses the M3 outline's numbers at planning time (items 1 to 13). `docs/progress.md` removed item 1 at close and renumbered, so every item named here is one lower there (item 10, the run use case for one task, is now item 9).

Follow-ups: the three "Spec wording" lines under "Later" in `docs/progress.md` (whether `*` can match no characters; the order of the gate's output lines; a pattern with no `/` does not cover files inside a directory of that name, reviewer).
