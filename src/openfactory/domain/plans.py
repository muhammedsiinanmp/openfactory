"""Plan and task references: what the `Plans` port returns.

See "Projections" under "Domain model and storage" and "Planning" under "Task contract"
in docs/spec/phase1-spec.md. `PlanRef` is the current draft plan or the approved plan;
`Task` is one row of the `tasks` projection with its dependencies; `CommitRef` is the
latest commit of a plan with its task id.
"""

from pydantic import BaseModel, ConfigDict

from openfactory.domain.contracts import TaskContract
from openfactory.domain.payloads import CommitSha, PlanId, SpecVersionId, TaskId
from openfactory.domain.states import TaskState


class PlanRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: PlanId
    spec_version: SpecVersionId


class Task(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: TaskId
    plan_id: PlanId
    state: TaskState
    attempt: int
    contract: TaskContract
    # From the `task_deps` projection, in ascending id order.
    depends_on: list[TaskId]


class CommitRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sha: CommitSha
    task_id: TaskId
