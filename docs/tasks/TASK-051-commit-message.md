# TASK-051: Commit message of a passed task

- Milestone: M3
- Status: done
- Tests: acceptance
- ADR: ADR-003 (accepted): "The orchestrator writes the commit trailers (`Task`, `Requirements`, `Acceptance-Criteria`, `Agent-Run`, `Spec-Version`)"; ADR-014 (accepted), "Execution (SC-56, SC-58, SC-60, SC-62, SC-65)". No new port, adapter, dependency, event type, payload or storage change, and no new convention: the message form is the spec's. The module name, the function's signature and the answers to the open questions are rows in `docs/decisions.md`.
- Spec impact: wording. Two items, neither stops the task (see "Spec gaps").
- Spec sections (spec v1.12, SC-65): "Traceability" › "Commit trailers"; "Execution" › "Per-task sequence" (step 6), "The commit", "Adapter interface" (the `summary` sentence)

## Outline item
M3 outline item 1, second of two pieces (the context pack, SC-64, was TASK-050). This task finishes item 1. Items 2 to 5 are left.

## Objective
Give the run use case one pure function that builds the commit message of a passed task (subject, body and trailers) from the task contract, the run's `summary`, the implementer run's id and the plan's spec version.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings and to SC-65.

## Prerequisite
None. No `claude` call and no git call.

## Scope
In:
- `src/openfactory/domain/commit_message.py` (new), pure, no I/O (Open question 1):
  - `build_commit_message(contract: TaskContract, summary: str, run_id: str, spec_version: str) -> str`.
  - Subject: `f"{contract.task_id}: {contract.objective}"[:72]`.
  - Body: the summary with leading and trailing whitespace removed, otherwise unchanged; no body paragraph when nothing is left (Open question 2).
  - Trailers, the last paragraph, in the spec's order: `Task`, `Requirements`, `Acceptance-Criteria`, `Agent-Run`, `Spec-Version`. The two id lists are `", ".join(...)` of the contract's lists as they stand.
  - Paragraphs are separated by one empty line; the message ends with one `\n` after the last trailer.
- Tests: a new unit file, and one conformance test for the spec's example block.

Out (not this task):
- Any caller: `GitProvider.commit(worktree, message)`, `CommitRecorded`, the branch name `openfactory/<task id>` (outline item 2).
- Reading trailers back from git, and `trace_links` (M5).
- Any change to `GitCli.commit`, including a `--cleanup` flag (decided in TASK-044).
- Any test that runs git. TASK-044 covers a trailer message on real git, and the M3 close test covers the built one.
- Hardening:
  - an objective with a line break (Open question 3);
  - a summary that holds trailer-like lines, `#` lines or `---`;
  - an id that holds `, `;
  - a cut that ends in a space.
  No test covers any of these.
- Checking `run_id` or `spec_version` against their id patterns. They arrive from `Runs.next_id` and the plan's row.

## Acceptance criteria
All quoted text is from "Traceability" › "Commit trailers" unless another heading is named.

Terms:
- **The sample contract** is a `TaskContract` for `AUTH-002` with objective `Implement login endpoint using membership number`, `requirements` `["REQ-AUTH-002", "REQ-AUTH-001"]` and `acceptance_criteria` `["AC-AUTH-002-1", "AC-AUTH-001-2", "AC-AUTH-001-1"]`. Neither list is sorted.
- **The sample call** is `build_commit_message(<sample contract>, "Added the login endpoint.\n\nTests cover both paths.", "run_0091", "sv_01")`.
- **The last paragraph** of a message is `message.rstrip("\n").split("\n\n")[-1]`.

- [x] AC1 ("The subject is `<task id>: <objective>`, cut to 72 characters"; SC-65):
  - The first line of the sample call's message is `AUTH-002: Implement login endpoint using membership number`, and the second line is empty.
  - With an objective of 100 `x`, the first line is `("AUTH-002: " + "x" * 100)[:72]`, 72 characters long. The task id and `: ` count towards the 72, and nothing is added at the cut.
  - A subject of exactly 72 characters is unchanged.
- [x] AC2 ("The body is the run's `summary`"; "Execution" › "Adapter interface": "`summary` is the agent's final message ... and is used only as the body of the commit"; SC-65):
  - The sample call's message holds the summary unchanged, its empty line included, between the subject and the trailers, with one empty line before it and one after it.
  - A summary of `"\n  Added it.\n\n"` gives the same message as `"Added it."` (Open question 2).
- [x] AC3 ("The trailers are the last paragraph of the message. `Requirements` and `Acceptance-Criteria` list the contract's ids in contract order, joined by `, `. `Agent-Run` is the implementer run, and `Spec-Version` is the plan's spec version"; SC-65):
  - The last paragraph of the sample call's message is exactly these five lines, in this order:
    `Task: AUTH-002`
    `Requirements: REQ-AUTH-002, REQ-AUTH-001`
    `Acceptance-Criteria: AC-AUTH-002-1, AC-AUTH-001-2, AC-AUTH-001-1`
    `Agent-Run: run_0091`
    `Spec-Version: sv_01`
  - A contract with one requirement gives `Requirements: REQ-AUTH-001`, with no comma.
  - A summary whose own last paragraph is `Task: OTHER-001` does not change the last paragraph of the message.
- [x] AC4 ("The body is the run's `summary`", for an empty summary; Open question 2):
  - With a summary of `""`, and with one of `" \n"`, the message is the subject, one empty line and the five trailer lines. No text `\n\n\n` is in it.
- [x] AC5 (the example block under "**Commit trailers**, written by the orchestrator:"; SC-65):
  - A conformance test in `tests/unit/test_spec_conformance.py` reads the block from the spec.
  - It builds the message for `AUTH-002`, the block's objective, `["REQ-AUTH-001"]`, `["AC-AUTH-001-1", "AC-AUTH-001-2"]`, summary `<the run's summary>`, `run_0091` and `sv_01`.
  - The built message equals the block, compared after `strip()` on both.
- [x] AC6 (CLAUDE.md "Architecture rules": "src/openfactory/domain: pure models and rules. No I/O, no imports from adapters/app"; "Execution" › "Per-task sequence" step 6: "the orchestrator itself commits with trailers"):
  - `build_commit_message` returns a `str`, and two calls with equal arguments give equal text.
  - `domain/commit_message.py` imports only from `openfactory.domain` and the standard library (checked with `ast`, as in `tests/unit/test_context_pack.py`).
  - Every existing test passes unchanged.

## Architecture rules that apply
- `domain` is pure: no I/O, no import from `ports`, `adapters`, `app` or `cli`.
- No event is recorded. `cli.py`, `ports/`, `adapters/` and `app/` are not changed.
- No new dependency. No `req` markers on OpenFactory's own tests.
- Existing tests are fixed: none is edited.
- No hardening beyond what the spec asks.

## Plan
1. Create branch `task/TASK-051-commit-message` from an up-to-date main.
2. Write failing tests:
   - `tests/unit/test_commit_message.py` (new) for AC1 to AC4 and AC6;
   - one test in `tests/unit/test_spec_conformance.py` for AC5.
3. Add `domain/commit_message.py`: a module docstring that names "Commit trailers", then `build_commit_message`. Paragraphs are collected in a list (subject, the stripped summary when not empty, the five trailer lines), joined with `"\n\n"` and ended with `"\n"`.
4. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
5. Update the living docs, the rows in `docs/decisions.md` and the Outcome. Commit `feat(domain): build the commit message of a passed task` with trailers `Task: TASK-051` and `Milestone: M3`.

## Files expected to change
- `src/openfactory/domain/commit_message.py` (new, about 40 lines)
- `tests/unit/test_commit_message.py` (new, about 130 lines)
- `tests/unit/test_spec_conformance.py` (one test added, about 20 lines)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-051-commit-message.md` (this record; Outcome at close)

Not expected to change: `cli.py`, everything under `app/`, `ports/` and `adapters/`, every other file under `domain/`, every existing test, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 200 lines with tests.

## Living docs to update
- `docs/architecture.md`: new section "Commit message" (`domain/commit_message.py`); "Data flow" says `build_commit_message` exists for the run use case and nothing calls it yet.
- `docs/progress.md`: Current, Done, outline item 1 removed (items renumbered, or item 1 marked done), and the Later lines listed below.
- `docs/decisions.md`: rows for the answered open questions and for the message's ending.
- `CHANGELOG.md` and `README.md`: no change (nothing a user sees).

## New dependencies
None.

## Spec gaps
Spec impact is "wording": two items, neither stops the task.

1. "Traceability" › "Commit trailers", "The body is the run's `summary`" (with "Execution" › "Adapter interface", "`summary` is the agent's final message, empty when `exit` is `error` or `timeout`").
   - Unclear: whether the summary goes in byte for byte, leading and trailing whitespace included.
   - Unclear: what the message is when the summary of an `ok` run is empty. The adapter requires the envelope's `result` but not that it has text.
   - Does not block: under both readings the trailers are the last paragraph and the body is the summary's text. Answered by Open question 2.
2. "Traceability" › "Commit trailers", "The subject is `<task id>: <objective>`, cut to 72 characters" (with "Task contract", `objective: str`).
   - Unclear: `objective` is a plain string with no rule against a line break, so the "subject" may span lines.
   - Does not block: the task follows the text as written. Answered by Open question 3.

Already recorded, not new: the TASK-044 item on git's message clean-up ("The body is the run's `summary`" with "The commit"). It stays open; see the Later lines below.

Readings, not gaps (each follows from the text as written):
- "cut to 72 characters": the first 72 characters of the whole line `<task id>: <objective>`, as Python counts characters; nothing is added at the cut.
- "in contract order": the lists as the contract holds them, with no sorting and no removal of repeats.
- The trailer names and their order: those of the example block.
- "`Agent-Run` is the implementer run": the run id, as `run_0091` in the example.
- The single `\n` at the end of the message: the example block shows no ending; one `\n` is the form of the message in `tests/integration/test_git_cli_commit.py`, and git's clean-up gives the same.

## Later lines in `docs/progress.md`: taken or left
- **"Spec wording: 'Commit trailers', 'The body is the run's `summary`' ... git's message clean-up" (TASK-044, planner).** Left open. Reworded at close: the built message has no blank lines of its own at either end and none doubled between its parts; blank lines doubled inside the summary, and trailing spaces on its lines, are still changed by git's clean-up.
- **"`WorkspaceManager.create` returns the path but not the branch name" (TASK-045, advisor).** Left. The branch is not part of the message; outline item 2.
- **"Spec wording: 'The commit', `--no-verify` ... a `prepare-commit-msg` hook of the target repo can still change the message" (TASK-044).** Left.
- **"Current" still reads "TASK-050 ... (done; commit pending)" though main is at #80.** Corrected at close with the Current line of this task.
- **Every other Later line:** left.
- **To add when this record is saved:** the two "Spec wording" lines of "Spec gaps".
- **To add at close:**
  - "An objective with a line break gives a subject of more than one line; `build_commit_message` follows the text as written, no test (TASK-051, planner)".
  - "Before M5: a summary is the agent's markdown and may hold a `---` line or a last paragraph of `Key: value` lines; whether `git log --format=%(trailers)` still reads only the orchestrator's paragraph was not checked on real git (TASK-051, planner)".

## Open questions
Answered 2026-10-14: the human accepted the proposed answer to each of the three questions (advisor: 3 AGREE). The criteria above stand as written. For question 1 the recorded reason is that the spec fixes the message's form, not the M5 argument (advisor).

1. **Where the function lives.** The outline says "in the app and domain".
   - Proposed: `domain/commit_message.py` only, with `build_commit_message(contract, summary, run_id, spec_version) -> str`, and nothing in `app/`. The message form is a traceability rule with no I/O, and the M5 code that reads trailers back can sit beside it. The run use case calls it directly.
   - Alternative: `app/commit_message.py`, beside `context_pack.py`.
2. **Whitespace around the summary, and an empty summary.**
   - Proposed: the summary's leading and trailing whitespace is removed and the rest is unchanged; when nothing is left, the message is subject, one empty line, trailers. The built message then has exactly one empty line between its parts and does not depend on git's clean-up, which `commit.cleanup` can turn off.
   - Alternative: the summary is used byte for byte and an empty one gives an empty body paragraph, leaving the tidying to git. AC4 is then dropped and AC2 loses its second bullet.
3. **An objective with a line break.**
   - Proposed: follow the text as written (`f"{task_id}: {objective}"[:72]`), with no test and a Later line. The trailers stay the last paragraph either way.
   - Alternative: replace each run of whitespace in the objective with one space before the cut. That changes what "the subject is `<task id>: <objective>`" means and would need a `/spec-change`.

## Outcome
Built `build_commit_message(contract, summary, run_id, spec_version) -> str` in the new `src/openfactory/domain/commit_message.py`: pure, importing only `openfactory.domain`. The subject is `<task id>: <objective>` cut to 72 characters; the body is the summary with leading and trailing whitespace removed, left out when nothing remains; the trailers (`Task`, `Requirements`, `Acceptance-Criteria`, `Agent-Run`, `Spec-Version`) are the last paragraph; paragraphs are separated by one empty line and the message ends with one `\n`. The function is in `domain/` only, nothing in `app/`.

- Tests: new `tests/unit/test_commit_message.py` (12 tests, AC4 parametrized over two summaries) and one conformance test in `tests/unit/test_spec_conformance.py`.
- Deviations from the plan: none.
- Test edits: none; no existing test changed and no test-writer test edited.
- Checks: 1220 tests pass; ruff, pyright and `check_docs` clean.
- Follow-ups (Later lines in `docs/progress.md`): the two "Spec wording" lines of "Spec gaps" (answers recorded in `docs/decisions.md`), the objective with a line break (candidate `/spec-change`), the summary and trailers on real git before M5, and the TASK-044 git clean-up line reworded.
