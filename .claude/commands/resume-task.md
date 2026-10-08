---
description: Find where an interrupted task stopped and continue the /next-task loop from there
---
Resume the task in progress. Read only until I give the go-ahead: no edits, no staging,
no commits, no branch switches, no subagents.

Notify markers: the same as in /next-task. Whenever you stop because you need me, end
the message with exactly one marker on its own line, as the very last line:
- [[notify:approval]] — the resume report, a plan, or the final diff + reviewer verdict
  is ready for approval
- [[notify:question]] — an open question or spec gap needs my answer
- [[notify:pr-ready]] — the commit is done and the push/PR commands are printed
Never emit a marker when waiting for a subagent or continuing work.

1. Find the current task.
   - If the branch is task/<TASK-ID>-<slug>, the task is <TASK-ID>.
   - Otherwise take the newest record in docs/tasks/ (highest task number, template
     excluded) whose Status is not done.
   - If neither gives a task, or the branch and the newest open record name different
     tasks, say so and stop with [[notify:question]].
2. Look at the state, without changing it:
   - `git status --short --branch`
   - `git diff --staged --stat` and `git diff --stat`, then the full diffs where the
     summary is not enough
   - `git log --oneline main..HEAD`
   - the task record: Status, Tests, ADR, acceptance criteria, Plan, Outcome
   - docs/progress.md, "Current" and "Blockers"
3. Work out which /next-task step we are at. Read .claude/commands/next-task.md for the
   steps and use this evidence:
   - step 1: the record is Status: planned and the branch task/<TASK-ID>-<slug> does not
     exist. The plan may still be waiting for my approval; ask, don't assume.
   - step 2: the branch exists and the tests the Tests field asks for are missing.
     Test-writer tests are staged once they are written and seen to fail.
   - step 3: the tests exist and tests, ruff, pyright or check_docs are not all green.
     Run them to find out; they change nothing.
   - step 4: the checks are green and the living docs, the record's Outcome or
     docs/progress.md do not yet describe the change.
   - step 5: docs are updated and nothing is committed. I cannot tell from the files
     whether the reviewer ran or what it said, so say that and plan to run it again.
   - step 6: a commit for the task is on the branch. Check its trailers and whether
     docs/workflow/metrics.md is part of it.
   If the evidence fits two steps, name the earlier one and say why.
4. Report, briefly:
   - the task id, title, branch and record Status
   - the step we are at, with the evidence for it
   - what is done, and what is left, as the remaining /next-task steps in order
   - anything that looks wrong: edits outside the record's "Files expected to change",
     changes under `git diff -- tests/` to staged test-writer tests, work on main, a
     record that disagrees with the diff
   ⏸ Wait for my go-ahead. End with [[notify:approval]], or with [[notify:question]] if
   something in the report needs my answer first.
5. After my go-ahead, continue with the remaining /next-task steps from the step
   reported, exactly as .claude/commands/next-task.md words them, including every ⏸ and
   its notify marker. Do not repeat a step that is finished, and do not run step 0: the
   branch already exists.

Extra instructions from me (may be empty): $ARGUMENTS
