# ADR-019: M6 impact, `ImpactComputed`, replan and plan supersession

- Status: proposed
- Date: 2026-10-24

## Context
M6 builds the structural diff, the classifier, the traversal, `impact`, `replan` and
partial re-execution. Spec v1.17 gave these a few sentences: `impact` "diffs the latest
two spec versions", "the payload of `ImpactComputed` is defined when its milestone is
planned", and "on `openfactory replan`, impacted tasks move to `invalidated`" (audit
`docs/spec-audits/2026-10-23-M6.md`, F-1 to F-20). The code built so far works on one
approved plan: `run`'s promotion rule, `<base>` and `status` read the tasks of
`Plans.approved()` only. [ADR-007](ADR-007-event-payloads-as-stable-contracts.md) left
the `ImpactComputed` payload to be defined. Spec v1.18 (SC-158 to SC-177) settles all of it.

## Decision
- **One approved plan.** `replan` records a draft `PlanCreated` holding only the new
  tasks; `PlanCreated` gets no new field. A `PlanApproved` applied while another plan is
  `approved` marks that plan `superseded` and moves every one of its tasks, whatever its
  state, into the new plan (`tasks.plan_id`), before it inserts the new `contract` links.
  The rule reads only the projections, as ADR-018 allows. `<base>` stays the chain tip,
  which still holds the invalidated work (SC-158, SC-159).
- **`ImpactComputed`.** `impact` compares the approved plan's spec version (`from`) with
  the latest approved one (`to`) and records `ImpactComputed` on `spec:<to_version>`,
  actor `orchestrator`, changing no projection. Its payload is `from_version`,
  `to_version`, `run_id` (the accepted classifier run, or null), `requirements` (`id`,
  `change`, `kind`, `rationale`, `obsolete_criteria`, `new_work`), `adrs` (`id`, `change`),
  `tasks`, `downstream`, `files` and `tests`, all sorted; `rationale` is null and the two
  lists `[]` unless `change` is `modified`. `change` and `kind` are closed sets (SC-160).
- **Classifier.** At most one call per `impact`, as a planner call with role
  `classifier`; reply `{"changes": [ChangeClass]}` with `extra="forbid"`; the checks
  `schema`, `unknown-requirement`, `duplicate-requirement`, `missing-requirement`,
  `unknown-criterion` and `cosmetic-with-work`; one retry. ADR changes and newly
  deprecated requirements are decided by rules, not by the model (SC-161, SC-167,
  SC-169, SC-171, SC-172).
- **Invalidation at approval.** `replan` invalidates nothing. `approve plan` of a replan
  draft reads the latest matching `ImpactComputed` recorded before the draft's
  `PlanCreated`, records `PlanApproved`, invalidates the listed tasks that can be, then
  readies every `pending` task whose dependencies have passed (SC-163, SC-165, SC-174).
- **Plan checks.** In a replan `unknown-dependency` accepts untouched tasks that are not
  `abandoned`, and `uncovered` counts untouched tasks that are not `invalidated`. A new
  rule for every plan, `task-id-in-use` (SC-163).
- **Ports.** No new port: `Traces` gains the traversal, `ImpactComputed` is read through
  `EventStore`, the diff reads `SpecVersions`, the classifier goes through `LLMProvider`
  (SC-168).
- **Deferred.** The human override of a classification moves to the Deferred column of
  Scope (SC-160).

## Alternatives considered
- **`PlanCreated.replaces`, and only live tasks move.** A payload change under ADR-007,
  and the invalidated commits would leave the plan, so `<base>` could fall back to an
  older commit.
- **`impact` records nothing; `replan` classifies again.** A second call that can
  disagree with the report the human read.
- **Invalidate at `replan`.** A second `replan` would then find nothing to invalidate,
  and a rejected draft would leave tasks invalidated with no plan to replace them.
- **One classifier call per modified requirement.** Simpler checks, more calls.
- **A new `Impacts` port and projection table.** More code for a read `EventStore`
  already gives.
- **Downstream tasks reported but not invalidated.** More precise, but a downstream task
  could break under the rewritten upstream with no way to fix it.

## Consequences
- The human accepts this ADR before spec v1.18 is applied.
- The premise of the 2026-10-11 TASK-025 decision ("only one approved plan can exist
  before `replan`") is retired; at most one plan is ever `approved`.
- `run`, `status`, `resolve`, `SqlitePlans` and the `<base>` rule need no change;
  `approve_plan.py` gains the impact read, the invalidations and the `pending` readies,
  and the projector's `PlanApproved` branch gains the move.
- `ImpactComputed` gets its payload model, so the projector tests that use it as the
  type without a model need another (Later, TASK-040).
- No database is discarded: no `ImpactComputed` is stored yet and no table changes.
- After the move `tasks.plan_id` is no longer the plan a task came from; per-plan cost
  for `stats` and `report` comes from `PlanCreated.tasks`, decided before M7.
- New tasks start from a tree that still holds the obsolete code and tests; the replan
  prompt tells the planner to rewrite or delete them, and the gates catch a plan that
  does not.
