# ADR-020: M7 cost attribution per plan and the run reads

- Status: accepted
- Date: 2026-10-25

## Context
`stats` prints totals per task, per plan and per role, and `report` compares the cost of
the initial build with that of the replan ("Metrics"). ADR-019 moves every task of the
superseded plan into the new one at a replan, so `tasks.plan_id` no longer names the plan
a task came from; its Consequences leave per-plan cost to `PlanCreated.tasks`, "decided
before M7". Planner runs carry no plan, classifier runs carry none either, and `Runs`
gives only the next run id and a task's unfinished run. Spec v1.20 (SC-204, SC-209)
settles both.

## Decision
- A task's runs count for the latest `PlanCreated` that lists the task. Ids are reused
  only from a superseded draft, whose tasks never ran, so this is the plan the task ran
  under.
- A plan also gets the planner runs of the command that recorded its `PlanCreated`, found
  through that event's `causation_id` chain.
- A plan whose `PlanCreated` was recorded while another plan was approved (a replan) also
  gets the classifier runs of the latest `ImpactComputed` recorded before that
  `PlanCreated`, found through that event's chain. So the replan's cost includes the
  `impact` it rests on.
- The planner runs of a command that recorded no `PlanCreated`, and classifier runs no
  replan used, belong to no plan and count only in the role figures.
- No new port. `Runs` also gives every run with its task id, role, exit, tokens, cost and
  `duration_s`. `PlanCreated`, `PlanApproved` and `ImpactComputed` events and their
  chains are read through `EventStore`; `report` reads the links through `Traces`.

## Alternatives considered
- **Classifier runs belong to no plan.** Simpler, but the replan's figure in `report`
  would leave out the `impact` call it needed, and so overstate the saving.
- **Attribute through `tasks.plan_id`.** Wrong after a replan: the invalidated and
  untouched tasks of the first plan would count as the replan's.
- **Add a plan id to `AgentRunStarted`.** A payload change (ADR-007) for a figure the
  event log already gives through `PlanCreated.tasks` and `causation_id`.
- **A new `Metrics` read port.** More code and another adapter; `Runs` and `EventStore`
  cover the reads.

## Consequences
- `stats` and `report` need no new event, table or column, and no database is discarded.
- `SqliteRuns` gains one read; the use cases follow the `causation_id` chains of events
  read through `EventStore`.
- Two replan drafts in a row share one `ImpactComputed`, so its classifier runs show on
  both drafts' `stats` lines; `report` lists approved plans only, so its rows do not
  double-count.
