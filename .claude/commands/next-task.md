---
description: Run the full plan → test → build → document → review loop for one task
---
Run one task end to end. Stop and wait for me at each ⏸.

Notify markers: whenever you stop because you need me, end the message with exactly
one marker on its own line, as the very last line:
- [[notify:approval]] — a plan, or the final diff + reviewer verdict, is ready for approval
- [[notify:question]] — an open question or spec gap needs my answer
- [[notify:pr-ready]] — the commit is done and the push/PR commands are printed
Never emit a marker when waiting for a subagent or continuing work.

0. Run `git switch main && git pull`.
1. Use the planner subagent to plan the next task. Save its output as
   docs/tasks/<TASK-ID>-<slug>.md with Status: planned.
   ⏸ Show me the plan and wait for approval. End with [[notify:approval]].
   If the plan has open questions or hits a spec gap, end with [[notify:question]] instead.
   After approval, create the branch task/<TASK-ID>-<slug>.
2. Check the task record's Tests field:
   - acceptance: use the test-writer subagent to write failing tests. Show me the failures.
   - integration-only: write one integration test yourself, confirm it fails, continue.
   - none: skip this step.
3. Implement the minimum code to make the tests pass. Follow CLAUDE.md rules.
   Tests from the test-writer are fixed. Never weaken, skip or delete a test to make it
   pass. Exception: mechanical errors (wrong attribute or import name, syntax) may be fixed
   if the assertion's intent is unchanged; report each fix in the task record's Outcome.
   The reviewer checks every test edit.
   If a test seems wrong for any other reason, stop and ask me, ending with
   [[notify:question]].
   Run tests, ruff, pyright and check_docs until all are green.
4. Use the docs-keeper subagent to update living docs.
5. Use the reviewer subagent. Fix blocking issues and re-run the reviewer, at most twice.
   If it still requests changes after that, stop and show me the remaining issues; I decide.
   End that message with [[notify:question]].
   Don't apply non-blocking notes unless I ask.
   ⏸ Show me the final diff summary and the reviewer verdict. End with [[notify:approval]].
6. After my approval, run `uv run python scripts/workflow_metrics.py` so the updated
   docs/workflow/metrics.md is part of the task's commit. Then commit with a Conventional
   Commit subject and the trailers from CLAUDE.md. Then print the exact commands for me to push and open the PR, with a
   PR description filled in from .github/pull_request_template.md.
   End with [[notify:pr-ready]].

Extra instructions from me (may be empty): $ARGUMENTS
