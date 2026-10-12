"""Approve plan use case: record `PlanApproved` for the draft plan, or say why not.

See docs/spec/phase1-spec.md ("Task contract": "Planning"; "Domain model and storage":
"Streams and actors", "Event payloads"; "Task state machine"). The draft is refused when
there is none or when it was made for a spec version that is not the latest approved one.
Otherwise `PlanApproved` is recorded, then one `TaskStateChanged` (`pending` to `ready`)
per task with no dependencies, in ascending task id, each pointing at `PlanApproved`.
Events are recorded through the `EventRecorder` port and the projections are read through
`SpecVersions` and `Plans` (ADR-001, ADR-012). The use case returns data and prints
nothing.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import PlanApprovedPayload, TaskStateChangedPayload
from openfactory.domain.states import TaskState
from openfactory.ports.event_recorder import EventRecorder
from openfactory.ports.plans import Plans
from openfactory.ports.spec_versions import SpecVersions


class ApprovePlanOutcome(StrEnum):
    no_draft = "no_draft"
    stale_draft = "stale_draft"
    approved = "approved"


class ApprovePlanResult(BaseModel):
    """What one `approve plan` run found and recorded.

    `plan_id` and `spec_version` are the draft's, and `None` when there is no draft.
    `ready` holds the ids of the tasks made ready, ascending; empty unless approved.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: ApprovePlanOutcome
    plan_id: str | None = None
    spec_version: str | None = None
    ready: list[str] = []


def _made_ready(task_id: str) -> TaskStateChangedPayload:
    # Built from a dict: `from` is a Python keyword, and pyright rejects `from_=`.
    return TaskStateChangedPayload.model_validate(
        {"task_id": task_id, "from": TaskState.pending, "to": TaskState.ready, "reason": None}
    )


def approve_plan(
    versions: SpecVersions, plans: Plans, recorder: EventRecorder
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
        )

    approved = recorder.record(
        Event.new(
            stream=f"plan:{draft.id}",
            type=EventType.PlanApproved,
            payload=PlanApprovedPayload(plan_id=draft.id).model_dump(mode="json"),
            actor="human",
        )
    )
    ready = sorted(task.id for task in plans.tasks(draft.id) if not task.depends_on)
    for task_id in ready:
        recorder.record(
            Event.new(
                stream=f"task:{task_id}",
                type=EventType.TaskStateChanged,
                payload=_made_ready(task_id).model_dump(mode="json"),
                actor="orchestrator",
                causation_id=approved.event_id,
            )
        )
    return ApprovePlanResult(
        outcome=ApprovePlanOutcome.approved,
        plan_id=draft.id,
        spec_version=draft.spec_version,
        ready=ready,
    )
