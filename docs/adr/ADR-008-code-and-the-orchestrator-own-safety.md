# ADR-008: Code and the orchestrator own safety

- Status: accepted
- Date: 2026-10-09

## Context
A task contract carries three things that bound what an agent may do: the paths it may
not write, the gates its result must pass, and its limits on runtime, attempts and cost.
Two inputs could set them: the planner, which is an LLM, and `specs/policies.yaml`,
which is a file a human edits.

Earlier spec versions left room for both to weaken the bounds.

- The planner emitted `required_gates` and `limits`, and nothing said whether it may
  leave out a gate or raise its own attempt limit (gap G23). Gap G15 notes that "an LLM
  setting its own cost ceiling is odd".
- In spec v1.5 the four protected paths were only the default of the policy's
  `forbidden_paths`, so a policy that set the key dropped the protection of `.env` and
  `specs/**` unless it repeated them.

## Decision
The bounds are set by code and the orchestrator. The planner cannot weaken any of them,
and the policy file cannot remove the baseline paths or a gate.

- Four baseline paths are always forbidden: `specs/**`, `.openfactory/**`, `.env` and
  `.env.*`. They are defined in code (`BASELINE_FORBIDDEN_PATHS` in `domain/policy.py`),
  not in the policy file, so no policy can remove them.
- The policy's `forbidden_paths` adds to the baseline and never replaces it. It defaults
  to `[]`.
- The planner emits a `PlannedTask`, which has neither `required_gates` nor `limits`. A
  reply that contains either fails validation.
- The orchestrator completes each task into a `TaskContract`:
  - `forbidden_paths` is the baseline, then the policy's list, then the planner's,
    without duplicates;
  - `required_gates` is `[path_check, ruff, pytest, gitleaks, review]`;
  - `limits` comes from the policy's `max_runtime_s`, `max_attempts` and `max_cost_usd`,
    each of which must be greater than zero.
- The policy file has five keys and rejects unknown ones, so it has no key for gates.
  `openfactory plan` refuses to run while the policy is invalid.

The spec sums it up: "the planner can never widen access past the baseline and the
policy, drop a gate, or raise a limit."

The same split holds at execution. The orchestrator, not the agent, decides whether a
result is accepted. After the agent exits it checks every changed path against the
contract, and any violation fails the run, whatever the agent claims. The agent never
commits. The reviewer agent's verdict is recorded but cannot override a failed
deterministic gate. A path violation or a gitleaks finding escalates at once, with no
retry.

## Alternatives considered
- **The planner keeps `max_runtime_s` and `max_cost_usd`**, and its `max_attempts` is
  only lowered to the policy's ceiling. This was the proposal in gap G23. The human
  chose to put all three limits in the policy, so the planner chooses none of them.
- **Trust the planner for gates and limits** and only merge forbidden paths, as the spec
  then literally said (gap G23).
- **Defaults on `Limits`**, so the planner may omit them (gap G28). `Limits` has three
  required fields with no defaults, set by the orchestrator.
- **The four paths as the default value of the policy's `forbidden_paths`**, as in spec
  v1.5. A policy that set the key dropped the protection unless it repeated them.
- **Merge the baseline into the `Policy` model.** `Policy.forbidden_paths` holds only
  the policy file's list as written; merging belongs to the M2 task contract (decisions
  log, TASK-008).
- **Four required gates, without `review`**, as first proposed in gap G23. `review` was
  added to the fixed gates; its verdict still cannot override a failed deterministic
  gate.

## Consequences
Easier:
- The safety of a run does not depend on what the planner replied or on how the policy
  file was edited.
- The completed contract is what `PlanCreated` and `tasks.contract` hold, so the bounds
  in force for a task are reconstructable from the log.
- A policy file needs to list only the project's own additions.

Harder:
- Gates are not configurable: every task has the same five.
- Limits are the same for every task in a plan; the planner cannot give a larger task
  more runtime or cost.
- Changing the baseline paths or the gate list is a code change.
- In Phase 1 the path check after the run is the real enforcement. Claude Code's own
  permission settings are defence in depth, and running the agent in a container with
  only the worktree mounted is a stretch goal, not a requirement.
