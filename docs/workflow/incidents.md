# Workflow incidents

Things that went wrong in the workflow itself, not in the product. Newest first.

## 2026-10-08 · TASK-004 · Test typo hidden by a collection failure

- **Category:** test-writer
- **What happened:** A test-writer test read `v.id` on a `SpecViolation`, which has no such field (it is `v.subject`). The session stopped and waited for the human to approve a one-word fix.
- **How caught:** On the first test run during implementation, as an `AttributeError`.
- **Root cause:** When the tests were written, the test file failed at collection because the module under test did not exist yet, so no test body ran and the typo could not show. The rule at the time forbade any edit to a test-writer test.
- **Fix:** Mechanical errors may now be fixed without asking if the assertion's intent is unchanged; each fix is reported in the task record's Outcome and checked by the reviewer (`CLAUDE.md`, `/next-task` step 3).

## 2026-10-08 · TASK-003, TASK-004 · docs-keeper inaccuracies

- **Category:** docs-keeper
- **What happened:** The docs-keeper wrote statements into the living docs that did not match the code: three in TASK-003 and one in TASK-004 (wording in `docs/architecture.md`).
- **How caught:** Reading the docs diff at review, before the commit.
- **Root cause:** Hypothesis: haiku summarised loosely; testing by moving docs-keeper to sonnet.
- **Fix:** The docs-keeper now runs on `sonnet`.

## 2026-10-08 · TASK-002 · CI import-order mismatch between local and CI

- **Category:** CI
- **What happened:** `ruff check` passed locally but failed in CI on the import order of `tests/unit/test_event_store_port.py`.
- **How caught:** CI on the pull request.
- **Root cause:** ruff was not told which packages are first-party, so it sorted `openfactory` imports differently in the two environments. The stop hook also ran fewer checks than CI (no `ruff format --check`).
- **Fix:** `src` and `known-first-party` set in `pyproject.toml`; the stop hook aligned with CI; `scripts/ci_local.sh` runs the same checks as CI and is called by the pre-push hook.

## 2026-10-08 · TASK-001 · Reviewer noise

- **Category:** reviewer
- **What happened:** The task took 2h 11m, 6 review rounds and 230 tests. Each round the reviewer raised a new blocking finding about an input nobody will produce (lone surrogates in a payload, integers of about 4300 digits, datetimes at the edge of the range), and each was fixed with more code and tests. One blocker was real, three were noise.
- **How caught:** By the human, from the duration and the number of rounds.
- **Root cause:** The reviewer had no definition of "blocking" and no limit on rounds, and nothing told the session to keep a task proportionate.
- **Fix:** Workflow tuning (#5): `reviewer.md` defines blocking and makes exotic inputs non-blocking notes; `/next-task` re-runs the reviewer at most twice; `CLAUDE.md` says to keep tasks proportionate.
