# ADR-018: M5 trace links, `TestsCollected` and the `Traces` port

- Status: proposed
- Date: 2026-10-22

## Context
M5 builds `trace`, `why`, `coverage`, the `trace_links` projection and the rebuild of
links from git trailers. Spec v1.16 named `trace_links` and its five `source` values and
nothing else (audit `docs/spec-audits/2026-10-22-M5.md`, F-1 to F-18).
[ADR-003](ADR-003-deterministic-traceability.md) (accepted) left one question open for M5
(gap G14): requirement ids repeat across spec versions while links carry no version. The
test → requirement links had no event to come from: the `req` marker lines lived only in
`GateOutput` and were dropped after the tag rule. Spec v1.17 settles these (decisions
SC-126 to SC-134, SC-137 and SC-142).

## Decision
- **Storage.** `trace_links(from_kind, from_id, to_kind, to_id, source)`, with every
  column in the primary key. The kinds are `requirement`, `adr`, `task`, `run`, `commit`,
  `file` and `test`. Each link is stored once, in one direction: requirement → ADR
  (`spec`), requirement → task and task → the task it depends on (`contract`), task → run
  and run → commit (`trailer`), commit → file (`diff`), test → requirement and test → file
  (`test_tag`).
- **Writing events.** `SpecApproved` replaces the `spec` rows with those of the version it
  approves. `PlanApproved` writes the `contract` rows of the plan's tasks. `CommitRecorded`
  writes the `trailer` and `diff` rows. `TestsCollected` replaces every `test_tag` row. The
  projector reads the projections built by earlier events (`requirements`, `tasks`,
  `task_deps`), as it already did for `tasks.cost_usd`.
- **Versions (G14).** Node ids carry no spec version. `spec` rows are those of the latest
  approved version. No row is removed when a task is invalidated or abandoned.
- **New event `TestsCollected`** `{run_id, task_id, tests: [{node_id, file, req}]}`,
  stream `task:<task id>`, actor `orchestrator`. It holds every test the `pytest` gate
  collected, untagged ones included, and is recorded after the git commit is made, just
  before `CommitRecorded`. A database made before M5 is discarded.
- **Plugin.** The `openfactory_req` line gains `node_id` and is
  `{"node_id", "file", "req"}`. The plugin imports only `pytest`, `json` and `os`.
- **Ports.** A read-only `Traces` port (adapter `sqlite_traces`) serves the queries.
  `GitProvider` also lists the commits reachable from `openfactory/*`, with their trailers
  and changed paths.
- **Rebuild from git.** A function, not a command, returns the links that the trailers
  and the commits' diffs (`--no-renames`) give: requirement → task, task → run,
  run → commit and commit → file. It never writes `trace_links`. M5 is met when that set
  equals those rows for the tasks that have a `CommitRecorded`, apart from a commit made
  without its `CommitRecorded` that is still on its task's branch because the task was not
  retried.

This amends ADR-002: the projector uses the data in the event and the projections built by
earlier events, and a projection added later is not filled by a rebuild of an existing
database, which is discarded instead (as for M4). It amends ADR-003: the "commit → file" row reads "the `files` of `CommitRecorded`", and
the Consequence "The graph can be rebuilt from git trailers alone" reads "the links of
platform commits". It also amends ADR-015: the plugin's line and its imports are as above.

## Alternatives considered
- **A `spec_version` column on `trace_links`.** It keeps every version's links, but every
  query then needs a version filter, and neither M5 nor M6 needs historical links.
- **task → run written at `AgentRunStarted`.** It would link failed attempts and reviewer
  runs too, so the table would no longer equal what the trailers give.
- **The collection recorded with every `pytest` `GateEvaluated`.** The projector would not
  know yet whether the attempt passes, and an attempt that fails would replace the links
  of the committed suite.
- **A test identified by its file only.** Simpler, but it cannot count tests, and the
  impact report counts them.
- **Writing rebuilt links into `trace_links`.** It breaks
  [ADR-002](ADR-002-event-sourcing-as-the-core.md): projections are written only by
  applying a stored event.
- **The trace queries on `Plans`.** One fewer port, but it mixes unrelated reads and
  changes every `Plans` fake.

## Consequences
- The human accepts this ADR before spec v1.17 is applied.
- `trace`, `why` and `coverage` are queries over one table, and M6's traversal uses the
  same links.
- A database made before M5 is discarded, as for M4.
- A crash between the commit and `CommitRecorded` leaves the collection in `trace_links`
  until the next task passes.
- The plugin, `MarkerLine` and every `GateRunner` fake gain `node_id`.
