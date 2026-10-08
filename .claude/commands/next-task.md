---
description: Run the full plan → test → build → document → review loop for one task
---
Run one task end to end. Stop and wait for me at each ⏸.

0. Run `git switch main && git pull`.
1. Use the planner subagent to plan the next task. Save its output as
   docs/tasks/<TASK-ID>-<slug>.md with Status: planned.
   ⏸ Show me the plan and wait for approval.
   After approval, create the branch task/<TASK-ID>-<slug>.
2. Check the task record's Tests field:
   - acceptance: use the test-writer subagent to write failing tests. Show me the failures.
   - integration-only: write one integration test yourself, confirm it fails, continue.
   - none: skip this step.
3. Implement the minimum code to make the tests pass. Follow CLAUDE.md rules.
   Never modify tests written by the test-writer; if one seems wrong, stop and ask me.
   Run tests, ruff and check_docs until all are green.
4. Use the docs-keeper subagent to update living docs.
5. Use the reviewer subagent. Fix blocking issues and re-run the reviewer, at most twice.
   If it still requests changes after that, stop and show me the remaining issues; I decide.
   Don't apply non-blocking notes unless I ask.
   ⏸ Show me the final diff summary and the reviewer verdict.
6. After my approval, commit with a Conventional Commit subject and the trailers from
   CLAUDE.md. Then print the exact commands for me to push and open the PR, with a
   PR description filled in from .github/pull_request_template.md.

Extra instructions from me (may be empty): $ARGUMENTS