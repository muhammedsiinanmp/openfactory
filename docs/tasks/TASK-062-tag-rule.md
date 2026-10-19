# TASK-062: The pytest tag rule and its `no tagged test in a changed file` lines

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-015 (accepted). Its "Ports and adapters" section says "The use case writes `text` through `RunFiles` and applies the pytest tag rule itself". Its "How accepted ADRs are read from now on" section says ADR-003's tag rule means "for each requirement of the contract, a collected test carrying its marker is in a file the task changed". ADR-006 covers the layers. Nothing here triggers a new ADR: no port, adapter, dependency, event, payload or storage change, and no new convention. The choices below become rows in `docs/decisions.md`.
- Spec impact: wording. Three items, none blocks (see "Spec gaps").
- Spec sections (spec v1.16; SC-85, SC-109, SC-123):
  - "Gates and remediation", the gate table, `pytest` row, "Blocks on": "a requirement of the task with no tagged test in a changed file".
  - "Gates and remediation" › "The pytest gate and `req` markers": "or when, for a requirement in the contract, no collected test that carries its `req` marker is in a file among the path check's changed paths. When the tag rule fails, also when `pytest tests/` itself failed, the use case adds one line per uncovered requirement, `no tagged test in a changed file: <requirement id>`, to the gate's text before writing it."
  - "Traceability": "for each requirement of the contract, a collected test carrying its marker must be in a file the task changed (see Gates and remediation)".

## Outline item
M4 outline item 3. It depends on TASK-059 (`MarkerLine`) and on TASK-039 (changed paths, `violating_paths` as the pattern to follow). Outline item 7 is its first caller.

## Objective
Give the run use case a pure function that names the contract's requirements with no tagged test in a changed file, and one that turns them into the gate's `no tagged test in a changed file: <id>` lines.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/domain/tag_rule.py` (new). It is pure and imports only `openfactory.domain` (`TaskContract`, `MarkerLine`) and the standard library.
  - `uncovered_requirements(marker_lines, changed_paths, contract) -> list[str]`. It returns the ids in `contract.requirements` for which no `MarkerLine` has the id in its `req` and a `file` equal, as a string, to one of `changed_paths`. The result is in contract order, each id once at its first position. No argument is changed.
  - `tag_rule_lines(uncovered) -> list[str]`. One line per id, `no tagged test in a changed file: <id>`, with no line break, in the order given. It returns `[]` for an empty list.
- Tests: a new `tests/unit/test_tag_rule.py`, plus one conformance test in `tests/unit/test_spec_conformance.py` that ties the line's wording to the spec sentence.

Out:
- Adding the lines to `GateOutput.text`, deciding `passed` for the `pytest` gate (adapter result and tag rule), writing the file through `RunFiles`, and any call from `app/run.py`. All of this is outline item 7; the order and form of the added text are Open question 2, recorded for item 7.
- Any change to `domain/gates.py`, `ports/`, `adapters/`, `app/`, `cli.py` or the prompts (item 6).
- Normalising paths. `file` is already relative to the worktree root in POSIX form (TASK-061 decision of 2026-10-19), and git gives changed paths in the same form. The match is exact string equality, with no hardening.

## Acceptance criteria
- [ ] **AC1** ("The pytest gate and `req` markers": "a collected test that carries its `req` marker is in a file among the path check's changed paths"). A requirement is covered, and absent from `uncovered_requirements`, when at least one `MarkerLine` has its id in `req` and a `file` that is one of `changed_paths`. A marker line whose `req` holds several ids covers each of them. Marker lines for ids outside the contract change nothing.
- [ ] **AC2** (gate table, `pytest` row: "a requirement of the task with no tagged test in a changed file"). A requirement is uncovered when:
  - its only tagged tests are in files that are not among `changed_paths`; or
  - the only tests in changed files carry no marker for it (`req` `[]`, or other ids); or
  - `marker_lines` is empty.
  With no marker lines, every requirement of the contract is uncovered.
- [ ] **AC3** ("for a requirement in the contract"; "Traceability": "for each requirement of the contract"). Every requirement of the contract is checked, not just one: with two requirements, one covered and one not, only the uncovered one is returned. The result is in contract order, each id once at its first position: a contract listing an uncovered id twice gives it once. The inputs are not changed.
- [ ] **AC4** ("adds one line per uncovered requirement, `no tagged test in a changed file: <requirement id>`"). `tag_rule_lines(["REQ-A-001", "REQ-B-002"])` gives exactly `["no tagged test in a changed file: REQ-A-001", "no tagged test in a changed file: REQ-B-002"]`, and `tag_rule_lines([])` gives `[]`.
- [ ] **AC5** (same sentence; "Tech stack and repo layout", `domain/` is pure). A conformance test finds the sentence's literal `no tagged test in a changed file: <requirement id>` in the spec and checks that `tag_rule_lines` builds the same text, with the id in place of `<requirement id>`. `domain/tag_rule.py` imports from `openfactory` only `openfactory.domain` modules (checked with `ast`).

## Architecture rules that apply
- `domain/` stays pure: no I/O, and no import from `ports`, `adapters` or `app`.
- No event, projection or port change. No new dependency.
- No hardening beyond the spec: paths are compared as given.

## Plan
1. Create branch `task/TASK-062-tag-rule` from an up-to-date main and commit this record.
2. Get the human's answers to Open questions 1 to 3. Record them here and as rows in `docs/decisions.md`, then adjust AC3 and the names before any test is written.
3. Test-writer: write failing tests for AC1 to AC4 in `tests/unit/test_tag_rule.py` (new) and the AC5 conformance test in `tests/unit/test_spec_conformance.py`. No existing test is changed.
4. Add `src/openfactory/domain/tag_rule.py`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
6. Update the living docs and the Outcome. Commit `feat(domain): add the pytest tag rule and its lines` with the trailers `Task: TASK-062` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/domain/tag_rule.py` (new, about 35 lines)
- `tests/unit/test_tag_rule.py` (new, about 140 lines)
- `tests/unit/test_spec_conformance.py` (about +15 lines, one test)
- `docs/architecture.md`: a new section "Tag rule" after "Path patterns and the path check". The Data flow line notes that nothing calls it yet.
- `docs/progress.md`: Current, Done, outline item 3 removed, and the Spec wording Later lines below.
- `docs/decisions.md`: rows for the answers.
- `docs/tasks/TASK-062-tag-rule.md` (this record; Outcome at close).

Not expected to change: `domain/gates.py`, `ports/`, `adapters/`, `app/`, `cli.py`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, and every existing test except the one test added to the conformance file.

Expected size: about 190 lines with tests, about 35 of them in `src/`.

## Spec gaps
Spec impact is "wording". None of the three items blocks, because each concerns the form of the result and not whether the gate fails. Each has an Open question below, and no answer is assumed.

1. **"Gates and remediation" › "The pytest gate and `req` markers"**, "one line per uncovered requirement".
   - Unclear: the order of the lines is not given, and neither is what happens when the contract lists a requirement id twice. `PlannedTask.requirements` is not deduplicated by `complete_contract`.
   - Why it does not block: the gate fails whatever the order, and the lines are hints for the retry (SC-123). → Open question 1.
2. **Same sentence**, "adds ... to the gate's text before writing it".
   - Unclear: the spec does not say where the lines go in the text (after the adapter's text is the natural reading), how they are separated, or whether the last one ends in a line break. TASK-060's layout ends every non-empty part in `\n`.
   - Why it does not block this task: the joining is outline item 7's. This task returns the lines without line breaks. → Open question 2, recorded now so item 7 inherits an answer.
3. **Same section**: the spec names no function, module or argument shape for the tag rule. Its "file among the path check's changed paths" is read as exact string equality, since both sides are relative to the worktree root in POSIX form (TASK-061 decision of 2026-10-19).
   - Why it does not block: this is a code layout choice. → Open question 3.

Readings, not gaps:
- "a collected test" counts every `MarkerLine` the `--collect-only` command gave, whatever `pytest tests/` did. SC-123 says the lines are added "also when `pytest tests/` itself failed".
- A test file that is changed and matches no `allowed_paths` pattern cannot reach the gate: `path_check` fails first and no other gate runs.

## Open questions
1. **Order and duplicates of the uncovered ids.**
   - Proposed: contract order, each id once (at its first position). This follows `complete_contract`'s "each id at its first position" for `depends_on`.
   - Alternative (a): contract order with duplicates kept, as written.
   - Alternative (b): sorted as strings.
2. **How item 7 adds the lines to the text** (recorded now, built in item 7).
   - Proposed: after the adapter's text, each line followed by `\n`, nothing between the adapter's text and the first line. The adapter's text already ends in `\n` when not empty (TASK-060 layout).
   - Alternative: one empty line between the adapter's text and the tag-rule lines.
3. **Module and names.**
   - Proposed: `domain/tag_rule.py` with `uncovered_requirements(marker_lines, changed_paths, contract)` and `tag_rule_lines(uncovered)`. The contract goes last, as in `violating_paths(changed_paths, contract)`.
   - Alternative: put both functions in `domain/gates.py`, next to `MarkerLine`.

## Answers (2026-10-19, the human approved the proposed answers; advisor AGREE on all three)
1. Contract order, each id once at its first position.
2. Item 7 appends the lines right after the adapter's text, each ending in `\n`, with nothing between.
3. `domain/tag_rule.py` with `uncovered_requirements(marker_lines, changed_paths, contract)` and `tag_rule_lines(uncovered)`.

## Later lines in `docs/progress.md`
- Taken: none.
- Added: the three "Spec wording" lines, with the answers.

## Outcome
Added `src/openfactory/domain/tag_rule.py` with `uncovered_requirements` and `tag_rule_lines`, `tests/unit/test_tag_rule.py` (12 tests, AC1 to AC4) and one conformance test in `tests/unit/test_spec_conformance.py` (AC5). Behaviour follows the answers of 2026-10-19: contract order, each id once; the module imports only `openfactory.domain` and the standard library. Nothing calls the functions yet; outline item 7 is the first caller and appends the lines after the adapter's text, each ending in `\n`.

Test edits: `ruff format` reformatted one parametrize line in `tests/unit/test_tag_rule.py` (E501, layout only, assertion unchanged). No other test was changed.

Living docs: `docs/architecture.md` ("Tag rule" section and a data-flow paragraph), `docs/progress.md` (Current, Done, outline item 3 removed, three Spec wording Later lines), `docs/decisions.md` (three rows), all in this task's commit. Plan step 1's separate record commit was skipped: the record goes in the same commit.

Reviewer notes: the AC5 `ast` check ignores relative imports; left as is, since the domain uses absolute imports. Item 7 must apply the tag rule also when `pytest tests/` itself failed (SC-123); noted on outline item 7.
