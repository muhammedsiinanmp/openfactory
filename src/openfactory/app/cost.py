"""Cost attribution: the figures of each task and each plan.

See docs/spec/phase1-spec.md ("Metrics"; "CLI commands", "Output") and ADR-020. A task's
figures cover all its runs. A plan's figures cover the runs of the tasks whose latest
`PlanCreated` is that plan's, the planner runs on its `PlanCreated`'s `causation_id` chain
and, for a replan (a `PlanCreated` after some `PlanApproved`), the classifier runs on the
chain of the latest `ImpactComputed` before it. Runs and events are only read; the use
case records nothing, returns data and prints nothing.
"""

from collections.abc import Iterable
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from openfactory.domain.agent_run import RunRecord
from openfactory.domain.events import EventType, StoredEvent
from openfactory.domain.payloads import (
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    PlanCreatedPayload,
)
from openfactory.ports.event_store import EventStore
from openfactory.ports.runs import Runs


class Figures(BaseModel):
    """Number of runs and the sums of their figures, a null counting as 0."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runs: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    duration_s: float


class CostAttribution(BaseModel):
    """Figures keyed by task id (tasks with a run) and by plan id (plans with a `PlanCreated`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tasks: dict[str, Figures]
    plans: dict[str, Figures]


def sum_figures(runs: Iterable[RunRecord]) -> Figures:
    records = list(runs)
    return Figures(
        runs=len(records),
        tokens_in=sum(run.tokens_in or 0 for run in records),
        tokens_out=sum(run.tokens_out or 0 for run in records),
        cost_usd=sum(run.cost_usd or 0.0 for run in records),
        duration_s=sum(run.duration_s or 0.0 for run in records),
    )


def _chain_runs(start: UUID | None, by_id: dict[UUID, StoredEvent]) -> set[str]:
    """The run ids of the `AgentRunStarted` and `AgentRunFinished` events on the chain."""
    run_ids: set[str] = set()
    event_id = start
    while event_id is not None and event_id in by_id:
        event = by_id[event_id]
        if event.type is EventType.AgentRunStarted:
            run_ids.add(AgentRunStartedPayload.model_validate(event.payload).run_id)
        elif event.type is EventType.AgentRunFinished:
            run_ids.add(AgentRunFinishedPayload.model_validate(event.payload).run_id)
        event_id = event.causation_id
    return run_ids


def attribute_costs(*, runs: Runs, events: EventStore) -> CostAttribution:
    log = events.read()
    by_id = {event.event_id: event for event in log}
    records = runs.all_runs()
    by_run = {run.id: run for run in records}

    task_runs: dict[str, list[RunRecord]] = {}
    for run in records:
        if run.task_id is not None:
            task_runs.setdefault(run.task_id, []).append(run)

    # In ascending `seq`, so a later `PlanCreated` overwrites a task's earlier plan.
    plan_of_task: dict[str, str] = {}
    plan_run_ids: dict[str, set[str]] = {}
    approved = False
    latest_impact: StoredEvent | None = None
    for event in log:
        if event.type is EventType.PlanApproved:
            approved = True
        elif event.type is EventType.ImpactComputed:
            latest_impact = event
        elif event.type is EventType.PlanCreated:
            payload = PlanCreatedPayload.model_validate(event.payload)
            for contract in payload.tasks:
                plan_of_task[contract.task_id] = payload.plan_id
            run_ids = _chain_runs(event.causation_id, by_id)
            if approved and latest_impact is not None:
                run_ids |= _chain_runs(latest_impact.causation_id, by_id)
            plan_run_ids[payload.plan_id] = run_ids

    plans: dict[str, Figures] = {}
    for plan_id, run_ids in plan_run_ids.items():
        plan_records = [by_run[run_id] for run_id in run_ids if run_id in by_run]
        for task_id, plan in plan_of_task.items():
            if plan == plan_id:
                plan_records.extend(task_runs.get(task_id, []))
        plans[plan_id] = sum_figures(plan_records)

    return CostAttribution(
        tasks={task_id: sum_figures(task) for task_id, task in task_runs.items()},
        plans=plans,
    )
