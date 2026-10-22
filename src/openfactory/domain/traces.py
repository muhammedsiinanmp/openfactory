"""Requirement trace: what the `Traces` port's `requirement_trace` returns.

See "Traceability" ("Queries") and "CLI commands" ("Output", `trace`) in
docs/spec/phase1-spec.md and ADR-018. `TracedTask` is a task linked to the requirement
with its current state; `TracedCommit` is a commit of such a task; `TracedTest` is a test
tagged with the requirement (`tagged`) or one whose file a traced commit changed.
"""

from pydantic import BaseModel, ConfigDict

from openfactory.domain.payloads import CommitSha, TaskId
from openfactory.domain.states import TaskState


class TracedTask(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: TaskId
    state: TaskState


class TracedCommit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sha: CommitSha
    task_id: TaskId


class TracedTest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str
    tagged: bool


class RequirementTrace(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tasks: list[TracedTask]
    commits: list[TracedCommit]
    files: list[str]
    tests: list[TracedTest]
