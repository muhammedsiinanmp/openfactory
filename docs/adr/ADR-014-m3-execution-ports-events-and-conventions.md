# ADR-014: M3 execution: ports, events, path patterns and the context pack

- Status: proposed
- Date: 2026-10-13

## Context
M3 builds `run`: one task end to end in a git worktree, with the path check and a commit
with trailers. Spec v1.11 named the pieces and did not define them (audit
`docs/spec-audits/2026-10-12-M3.md`, 6 blockers). Spec v1.12 settles them (decisions
SC-54 to SC-80), and several of those decisions are ADR triggers under `CLAUDE.md`:

- new ports and adapters (`WorkspaceManager`, `AgentExecutor`, `RunFiles`, and more
  methods on `GitProvider`, `Plans` and `Runs`);
- two event payloads and two projection tables (`GateEvaluated`, `CommitRecorded`,
  `gate_results`, `commits`);
- a convention other code must follow (the path pattern syntax);
- changes to what the spec means (the context pack holds no file contents; "the agent
  never commits"; the failed-process cases).

The `run` use case lives in `app`, which may depend on the domain and the ports only
([ADR-006](ADR-006-ports-and-adapters-with-type-checked-conformance.md)), so every git
command, every file it writes and every projection it reads needs a port.

## Decision

**Ports and adapters (SC-63, SC-68).**

- `WorkspaceManager`, adapter `git_worktree`: creates and removes a task's worktree
  (`.openfactory/worktrees/<task id>`) and branch (`openfactory/<task id>`).
- `GitProvider`, adapter `git_cli`, gains: the commit `HEAD` points at, the tracked files
  of a worktree, staging the changes of a worktree and listing the paths that differ from
  a commit, a soft reset of a branch, and making a commit. These take the worktree's
  path. This is "the rest" that
  [ADR-012](ADR-012-plans-and-runs-read-ports.md) left to M3.
- `AgentExecutor`, adapter `claude_code_executor`:
  `run(contract, context, workdir, output_dir) -> RunResult`. The adapter writes the
  runtime's result envelope to `<output_dir>/transcript.json`.
- `RunFiles`, adapter `filesystem_run_files`: writes a file of a run under
  `.openfactory/runs/<run id>/` and returns its path relative to the repo. Gate output
  goes through it.
- `Plans` gains the latest commit of a plan with its task id; `Runs` gains the unfinished
  run of a task. Both stay read-only (ADR-012).
- The path check is a pure function in the domain. The package `gates/` is removed from
  the layout, which closes its conflict with the four layers of ADR-006. The port for
  the gates that start a process (ruff, pytest, gitleaks) is decided in M4.

**Events and tables (SC-57, SC-61).**

- `GateEvaluated { run_id, task_id, gate, passed, output_path }` and
  `CommitRecorded { sha, task_id, run_id, branch, spec_version, files }`, both on stream
  `task:<task id>` with actor `orchestrator`. `files` is in the payload now so that M5 can
  build the commit to file links by a rebuild
  ([ADR-007](ADR-007-event-payloads-as-stable-contracts.md)).
- Tables `gate_results` and `commits`, with the DDL of spec v1.12.
- The projector adds 1 to `tasks.attempt` for each `TaskStateChanged` whose `to` is
  `running`. No stored payload changes.

**Path patterns (SC-59).** One syntax for `allowed_paths` and `forbidden_paths`, in
contracts and in the policy: `*`, `**` as a whole segment, `?`, a trailing `/`, and a
pattern with no `/` matching in any directory; no negations and no character classes.
It is a small hand-written matcher in the domain, with no new dependency.

**Execution (SC-56, SC-58, SC-60, SC-62, SC-65).** Tasks form a single chain: each
worktree starts from the latest commit of the plan, or from `HEAD`. The orchestrator
never merges and commits only on `openfactory/<task id>` branches, so
`protected_branches` is inert in Phase 1. The path check is `git add -A` followed by
`git diff --cached --name-only -z --no-renames <base>`. `run` starts with a repair made
from the projections, and removes and recreates a task's worktree and branch before each
attempt.

**The context pack (SC-64).** One prompt text with the instructions, the contract, the
spec items it names and the names of the tracked files that match `allowed_paths`. It
holds no file contents, where spec v1.11 said "the current contents of files under
`allowed_paths`". Its SHA-256 is the run's `context_hash`.

**How accepted ADRs are read from now on (SC-66, SC-71, SC-75).** These three readings
need the human's acceptance with this ADR, before spec v1.12 is applied:

- [ADR-003](ADR-003-deterministic-traceability.md) and
  [ADR-008](ADR-008-code-and-the-orchestrator-own-safety.md) say the agent never commits.
  The implementer has `Bash`, approved in advance, so it can run `git commit`. The rule
  now means that no commit of the agent survives: the orchestrator resets the branch to
  `<base>` with the changes kept, and every commit on a task branch is its own.
- `Bash` approved in advance is command execution on the human's machine, outside the
  worktree too. The path check stays the only enforcement
  ([ADR-005](ADR-005-claude-code-as-the-single-llm-runtime.md): Claude Code's permission
  settings are defence in depth).
- ADR-005's amendment lists three failed-process cases. Spec v1.12 has four for every
  call (a `claude` that cannot be started is added) and a fifth for an agent run (an
  envelope that reports an error).

## Alternatives considered
- **A `Gate` port now, keeping `gates/`.** It serves ruff, pytest and gitleaks, which are
  M4, and keeps a fifth package beside the four layers.
- **No `files` in `CommitRecorded`.** Adding a required field in M5 would make every
  stored `CommitRecorded` invalid (ADR-007), so M5 would discard the database.
- **The `pathspec` library with full gitignore rules.** A new runtime dependency for
  rules the examples do not need.
- **File contents in the context pack, with a size limit.** A second rule and a larger
  prompt for what the agent reads with its tools.
- **No `Bash` for the implementer.** The agent could not commit at all, and could not
  run the tests, which costs retries from M4.
- **Checking `protected_branches` against the task branch name.** `run` would read the
  policy, which the spec reads only when a plan is created, for a check that cannot fire.
- **Repair by reading the branch tip's `Task` trailer.** More git reads, and it failed a
  `gating` task that already had its `CommitRecorded`.
- **An integration branch `openfactory/main`.** One more branch update per task for the
  same result as the chain.

## Consequences
- `app` gets the `run` use case with no I/O of its own; each new adapter ends with its
  `TYPE_CHECKING` assertion (ADR-006).
- Every caller and fake of `Plans`, `Runs` and `GitProvider` changes when the methods
  are added.
- Two fixed tests change with the human's approval: the DDL block read by
  `tests/unit/test_spec_conformance.py`, and
  `test_ac5_event_type_without_projection_is_ignored` with `build_log`, because
  `GateEvaluated` gets its model in M3 and not in M4.
- The M3 test that a task passes on `path_check` alone is rewritten in M4.
- `protected_branches` protects nothing until a later phase merges or pushes.
- A target repo that does not ignore tool by-products (`__pycache__/`) will see tasks
  escalate on a path violation.
- ADR-005's amendment lags the spec by the cases above until the human amends it.
