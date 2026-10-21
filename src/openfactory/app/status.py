"""Status use case: the tasks of the approved plan with their state, attempts and last gate.

See docs/spec/phase1-spec.md ("CLI commands": "Output"; "Domain model and storage": "Ids",
"Projection rules"). The tasks come in ascending id order as strings, each with its
projected `attempt`, its contract's `limits.max_attempts` and `Plans.last_gate_result`.
With no approved plan the use case refuses. It records no events, does not repair the plan,
returns data and prints nothing.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from openfactory.domain.plans import GateResultRef
from openfactory.domain.states import TaskState
from openfactory.ports.plans import Plans


class StatusRefusal(StrEnum):
    no_approved_plan = "no_approved_plan"


class TaskStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    state: TaskState
    attempt: int
    max_attempts: int
    gate: GateResultRef | None


class StatusReport(BaseModel):
    """What one `status` run found: a refusal, or the tasks of the approved plan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    refusal: StatusRefusal | None = None
    tasks: list[TaskStatus] = []


def plan_status(*, plans: Plans) -> StatusReport:
    plan = plans.approved()
    if plan is None:
        return StatusReport(refusal=StatusRefusal.no_approved_plan)
    return StatusReport(
        tasks=[
            TaskStatus(
                task_id=task.id,
                state=task.state,
                attempt=task.attempt,
                max_attempts=task.contract.limits.max_attempts,
                gate=plans.last_gate_result(task.id),
            )
            for task in sorted(plans.tasks(plan.id), key=lambda t: t.id)
        ]
    )
