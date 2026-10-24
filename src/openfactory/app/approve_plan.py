"""Approve plan use case: record `PlanApproved` for the draft plan, or say why not.

See docs/spec/phase1-spec.md ("Task contract": "Planning"; "Domain model and storage":
"Streams and actors", "Event payloads"; "Task state machine"; "Spec diff and impact
analysis": "Approving a replan") and ADR-019. The draft is refused when there is none or
when it was made for a spec version that is not the latest approved one. When an approved
plan exists, the latest matching `ImpactComputed` recorded before the draft's `PlanCreated`
is read through `EventStore`, which nothing here appends to, and the draft is refused when
one of its tasks or downstream tasks is `running` or `gating`. Otherwise `PlanApproved` is
recorded, then one `TaskStateChanged` to `invalidated` per impacted or downstream task that
can be, then one `pending` to `ready` per `pending` task whose dependencies have all
passed, each group in ascending task id and pointing at `PlanApproved`. Every transition is
checked against `TRANSITIONS` before anything is recorded. Events are recorded through the
`EventRecorder` port and the projections are read through `SpecVersions` and `Plans`
(ADR-001, ADR-012). The use case returns data and prints nothing.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import (
    ImpactComputedPayload,
    PlanApprovedPayload,
    TaskStateChangedPayload,
)
from openfactory.domain.plans import PlanRef
from openfactory.domain.states import TRANSITIONS, TaskState
from openfactory.ports.event_recorder import EventRecorder
from openfactory.ports.event_store import EventStore
from openfactory.ports.plans import Plans
from openfactory.ports.spec_versions import SpecVersions


class ApprovePlanOutcome(StrEnum):
    no_draft = "no_draft"
    stale_draft = "stale_draft"
    task_busy = "task_busy"
    approved = "approved"


class ApprovePlanResult(BaseModel):
    """What one `approve plan` run found and recorded.

    `plan_id` and `spec_version` are the draft's, and `None` when there is no draft.
    `approved_plan_exists` is set on `stale_draft`; `task_id` and `state` name the lowest
    `running` or `gating` impacted or downstream task on `task_busy`. `invalidated` and
    `ready` hold the ids of the tasks invalidated and made ready, ascending; empty unless
    approved.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: ApprovePlanOutcome
    plan_id: str | None = None
    spec_version: str | None = None
    approved_plan_exists: bool = False
    task_id: str | None = None
    state: TaskState | None = None
    invalidated: list[str] = []
    ready: list[str] = []


_BUSY = (TaskState.running, TaskState.gating)
_SKIPPED = (TaskState.abandoned, TaskState.invalidated)


def _change(
    task_id: str, from_: TaskState, to: TaskState, reason: str | None
) -> TaskStateChangedPayload:
    # Built from a dict: `from` is a Python keyword, and pyright rejects `from_=`.
    return TaskStateChangedPayload.model_validate(
        {"task_id": task_id, "from": from_, "to": to, "reason": reason}
    )


def _latest_impact_before(
    events: EventStore, draft: PlanRef, approved: PlanRef
) -> ImpactComputedPayload | None:
    """The last `ImpactComputed` on `spec:<draft version>` from the approved plan's version
    with a `seq` below the draft's `PlanCreated`."""
    created = next(
        e.seq for e in events.read(f"plan:{draft.id}") if e.type == EventType.PlanCreated
    )
    latest: ImpactComputedPayload | None = None
    for event in events.read(f"spec:{draft.spec_version}"):
        if event.type != EventType.ImpactComputed or event.seq >= created:
            continue
        payload = ImpactComputedPayload.model_validate(event.payload)
        if payload.from_version == approved.spec_version:
            latest = payload
    return latest


def _check(task_id: str, from_: TaskState, to: TaskState) -> None:
    if to not in TRANSITIONS[from_]:
        raise ValueError(f"{task_id}: no transition from {from_} to {to}")


def approve_plan(
    versions: SpecVersions, plans: Plans, recorder: EventRecorder, *, events: EventStore
) -> ApprovePlanResult:
    draft = plans.current_draft()
    if draft is None:
        return ApprovePlanResult(outcome=ApprovePlanOutcome.no_draft)
    latest = versions.latest_approved()
    if latest is None or latest.id != draft.spec_version:
        return ApprovePlanResult(
            outcome=ApprovePlanOutcome.stale_draft,
            plan_id=draft.id,
            spec_version=draft.spec_version,
            approved_plan_exists=plans.approved() is not None,
        )

    tasks = plans.tasks(draft.id)
    listed: list[str] = []
    approved_plan = plans.approved()
    if approved_plan is not None:
        impact = _latest_impact_before(events, draft, approved_plan)
        # A replan draft is only made from a matching `ImpactComputed` (see `replan`).
        assert impact is not None
        tasks = [*tasks, *plans.tasks(approved_plan.id)]
        listed = sorted(set(impact.tasks) | set(impact.downstream))
    states = {task.id: task.state for task in tasks}
    depends_on = {task.id: task.depends_on for task in tasks}

    busy = [task_id for task_id in listed if states.get(task_id) in _BUSY]
    if busy:
        return ApprovePlanResult(
            outcome=ApprovePlanOutcome.task_busy,
            plan_id=draft.id,
            spec_version=draft.spec_version,
            task_id=busy[0],
            state=states[busy[0]],
        )

    reason = f"spec change {draft.spec_version}"
    changes = [
        _change(task_id, states[task_id], TaskState.invalidated, reason)
        for task_id in listed
        if task_id in states and states[task_id] not in _SKIPPED
    ]
    invalidated = [change.task_id for change in changes]
    for task_id in invalidated:
        states[task_id] = TaskState.invalidated
    ready = sorted(
        task_id
        for task_id, state in states.items()
        if state is TaskState.pending
        and all(states.get(dep) is TaskState.passed for dep in depends_on[task_id])
    )
    changes += [_change(task_id, TaskState.pending, TaskState.ready, None) for task_id in ready]
    for change in changes:
        _check(change.task_id, change.from_, change.to)

    approved = recorder.record(
        Event.new(
            stream=f"plan:{draft.id}",
            type=EventType.PlanApproved,
            payload=PlanApprovedPayload(plan_id=draft.id).model_dump(mode="json"),
            actor="human",
        )
    )
    for change in changes:
        recorder.record(
            Event.new(
                stream=f"task:{change.task_id}",
                type=EventType.TaskStateChanged,
                payload=change.model_dump(mode="json"),
                actor="orchestrator",
                causation_id=approved.event_id,
            )
        )
    return ApprovePlanResult(
        outcome=ApprovePlanOutcome.approved,
        plan_id=draft.id,
        spec_version=draft.spec_version,
        invalidated=invalidated,
        ready=ready,
    )
