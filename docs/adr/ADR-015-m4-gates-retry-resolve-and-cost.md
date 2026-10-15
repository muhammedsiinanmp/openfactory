# ADR-015: M4 gates, retry, `resolve` and the cost limit

- Status: accepted
- Date: 2026-10-15

## Context
M4 builds the gates that start a process, the reviewer, the retry with failure context,
`resolve`, `status` and the cost limit. Spec v1.13 named them and did not define them
(audit `docs/spec-audits/2026-10-15-M4.md`, 8 blockers). Spec v1.14 settles them
(decisions SC-84 to SC-104), and several of those decisions are ADR triggers under
`CLAUDE.md`:

- a new port and adapter (`GateRunner`, `process_gates`), and new operations on
  `GitProvider`, `RunFiles` and `Plans`;
- a new event type (`TaskResolved`) and a storage change (`tasks.cost_usd`);
- a new convention (the `openfactory_req` pytest plugin and `OPENFACTORY_REQ_OUT`);
- changes to how accepted ADR-003 and ADR-005 are read.

[ADR-014](ADR-014-m3-execution-ports-events-and-conventions.md) left "the port for the
gates that start a process (ruff, pytest, gitleaks)" to M4.

## Decision

**Ports and adapters (SC-84, SC-87, SC-89, SC-92).**

- `GateRunner`, adapter `process_gates`: `run(gate, worktree, timeout_s) -> GateOutput`,
  with `passed` (every command exited 0), `text` (each command line, then its standard
  output, then its standard error) and, for `pytest`, the collected marker lines. `ruff`
  and `pytest` run through `uv run` in the worktree, `gitleaks` from `PATH`. A command that
  cannot start or runs past `timeout_s` (the contract's `max_runtime_s`) fails its gate.
  The use case writes `text` through `RunFiles` and applies the pytest tag rule itself.
- `run` refuses before any event with `<tool> not found` when `uv` or `gitleaks` is not on
  `PATH`.
- `GitProvider` gains the text of `git diff --cached <base>` in a worktree, for the reviewer.
- `RunFiles` gains a read of a run file by the path `write` returned, for the failure
  report.
- `Plans` gains the last gate result of a task, for `status`. It stays read-only
  ([ADR-012](ADR-012-plans-and-runs-read-ports.md)).
- The failure report reads the task's last `failed` reason and its gate results from the
  task's stream through the existing `EventStore` port. ADR-012 rejected `EventStore.read`
  for projection reads; a lookup in one stream, of a field no projection holds
  (`TaskStateChanged.reason`), is not that case.

**The pytest plugin (SC-85, SC-86).** OpenFactory ships `openfactory_req`, one file under
`adapters/pytest_plugin/` that imports only pytest. The adapter puts its directory on
`PYTHONPATH`, so it loads in the target repo's environment. It registers the `req` marker
and, during collection, writes one JSON line `{"file", "req"}` per collected test to the
file named by `OPENFACTORY_REQ_OUT`, a temporary file outside the worktree. The gate runs
`pytest --collect-only -q -p openfactory_req tests/`, whose lines are read, then
`pytest -p openfactory_req tests/`. No OpenFactory module imports the plugin.

**Events and tables (SC-90, SC-91).**

- `TaskResolved { task_id, decision: "retry" | "abandon" }`, stream `task:<task id>`, actor
  `human`, followed by the orchestrator's `TaskStateChanged` pointing at it. `decision` is a
  closed set that may be widened, never narrowed
  ([ADR-007](ADR-007-event-payloads-as-stable-contracts.md)).
- `tasks.cost_usd REAL NOT NULL DEFAULT 0`: the projector adds each `AgentRunFinished`'s
  `cost_usd` (null as 0) to the run's task, found through `agent_runs.task_id`. A
  `TaskResolved` with `retry` sets `attempt` and `cost_usd` to 0. Both use only event data,
  so a rebuild stays identical.

**Gates and retry (SC-88, SC-89).** A `path_check` failure ends the gating; otherwise
`ruff`, `pytest` and `gitleaks` all run, and `review` only when all three passed. A gitleaks
finding (exit 1) gives `secret found` on both the `failed` and the `escalated` event. Every
other failure retries while `attempt < max_attempts`, in the same command; Restart settles
`failed` tasks, escalating those whose last `failed` reason escalates at once.

**How accepted ADRs are read from now on (SC-85, SC-87, SC-100).** These readings need the
human's acceptance with this ADR, before spec v1.14 is applied:

- [ADR-003](ADR-003-deterministic-traceability.md): "the pytest gate fails if a task
  produces no test tagged with its requirements" means that, for each requirement of the
  contract, a collected test carrying its marker is in a file the task changed. Markers
  are still "collected with `pytest --collect-only`", by the plugin above.
- [ADR-005](ADR-005-claude-code-as-the-single-llm-runtime.md) names the reviewer among the
  agents that run in a worktree. The reviewer is instead one `LLMProvider` call with no
  tools, set up as a planner call, replying `ReviewVerdict`. A failed reviewer process
  fails the `review` gate and `run` goes on, an exception to the rule that a failed
  process makes the command exit 1.
- [ADR-008](ADR-008-code-and-the-orchestrator-own-safety.md)'s "a gitleaks finding
  escalates at once" is kept as written: only exit status 1 of gitleaks is a finding.

## Alternatives considered
- **Executables first on `PATH`** for ruff and pytest, with the human activating the
  target repo's environment. Less to state, but the gates would run in whatever
  environment happens to be active.
- **Failing the gate when a tool is missing**, with no refusal. It spends a retry on a
  machine problem, and a missing gitleaks would read as a secret.
- **Reading markers during the test run**, with one `pytest` command. It amends ADR-003's
  "collected with `pytest --collect-only`".
- **The reviewer as an `AgentExecutor` run** in the worktree, as ADR-005 reads. More tools,
  more cost, and no structured verdict.
- **Stopping at the first failed gate.** The single retry would not hear about the other
  failures.
- **A human-actor `TaskStateChanged` for `resolve`.** It breaks "only the orchestrator
  moves a task".
- **A `Runs` read that sums the cost.** No schema change, but the fresh budget after
  `resolve` would need the sum ordered against `TaskResolved`.

## Consequences
- `app` gets the gate, retry, `resolve` and `status` use cases with no I/O of their own;
  `process_gates` ends with its `TYPE_CHECKING` assertion
  ([ADR-006](ADR-006-ports-and-adapters-with-type-checked-conformance.md)).
- Every caller and fake of `GitProvider`, `RunFiles` and `Plans` changes when the methods
  are added.
- The new event type and the `tasks` DDL land in code together with spec v1.14
  (TASK-058, committed on `spec/v1.14`), since `tests/unit/test_spec_conformance.py` holds
  both exactly and neither can come first; the M3 close test, which passes a task on
  `path_check` alone, is rewritten.
- The target repo must be a uv project with ruff and pytest as development dependencies,
  and pass both at the starting commit; gitleaks 8.30 or later is a required tool.
- Each worktree builds its own `.venv` through `uv run`, which costs time per attempt.
- The planner prompt changes (SC-93), so later planner runs have a new `context_hash`.
- ADR-005, ADR-007 and ADR-008 still lag the spec in the places listed under "Later"; their
  amendment stays the human's.
