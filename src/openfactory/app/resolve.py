"""Resolve use case: record a human's decision on an escalated task, or say why not.

See docs/spec/phase1-spec.md ("CLI commands": "Output"; "Domain model and storage":
"Streams and actors", "Projection rules"; "Task state machine"). The task is refused,
before any event, when there is no approved plan, when the approved plan has no such task
and when the task is not `escalated`. Otherwise `TaskResolved` is recorded as the human's,
with no causation, then the orchestrator's `TaskStateChanged` (`escalated` to `ready` for
`retry`, to `abandoned` for `abandon`, null reason) pointing at it. The transition is
checked against `TRANSITIONS` before either event is recorded (ADR-015). The use case does
not run the task, returns data and prints nothing.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import (
    ResolveDecision,
    TaskResolvedPayload,
    TaskStateChangedPayload,
)
from openfactory.domain.states import TRANSITIONS, TaskState
from openfactory.ports.event_recorder import EventRecorder
from openfactory.ports.plans import Plans


class ResolveRefusal(StrEnum):
    no_approved_plan = "no_approved_plan"
    unknown_task = "unknown_task"
    not_escalated = "not_escalated"


class ResolveResult(BaseModel):
    """What one `resolve` run found and recorded.

    `detail` is the task's current state for `not_escalated`, else `None`. `state` is the
    task's new state after a resolve, and `None` on a refusal.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    refusal: ResolveRefusal | None = None
    detail: str | None = None
    state: TaskState | None = None


def resolve_task(
    task_id: str, decision: ResolveDecision, *, plans: Plans, recorder: EventRecorder
) -> ResolveResult:
    plan = plans.approved()
    if plan is None:
        return ResolveResult(refusal=ResolveRefusal.no_approved_plan)
    task = next((t for t in plans.tasks(plan.id) if t.id == task_id), None)
    if task is None:
        return ResolveResult(refusal=ResolveRefusal.unknown_task)
    if task.state is not TaskState.escalated:
        return ResolveResult(refusal=ResolveRefusal.not_escalated, detail=task.state.value)

    to = TaskState.ready if decision == "retry" else TaskState.abandoned
    if to not in TRANSITIONS[task.state]:
        raise ValueError(f"{task_id}: no transition from {task.state} to {to}")

    resolved = recorder.record(
        Event.new(
            stream=f"task:{task_id}",
            type=EventType.TaskResolved,
            payload=TaskResolvedPayload(task_id=task_id, decision=decision).model_dump(mode="json"),
            actor="human",
        )
    )
    # Built from a dict: `from` is a Python keyword, and pyright rejects `from_=`.
    changed = TaskStateChangedPayload.model_validate(
        {"task_id": task_id, "from": task.state, "to": to, "reason": None}
    )
    recorder.record(
        Event.new(
            stream=f"task:{task_id}",
            type=EventType.TaskStateChanged,
            payload=changed.model_dump(mode="json"),
            actor="orchestrator",
            causation_id=resolved.event_id,
        )
    )
    return ResolveResult(state=to)
