"""Payload models for events, one per event type.

Implements "Event payloads" under "Domain model and storage" in
docs/spec/phase1-spec.md. Event payloads are built and checked through these
models.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from openfactory.domain.contracts import TaskContract
from openfactory.domain.events import EventType
from openfactory.domain.models import SpecSet
from openfactory.domain.states import TaskState

SpecVersionId = Annotated[str, StringConstraints(pattern=r"^sv_\d{2,}$")]
ContentHash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
PlanId = Annotated[str, StringConstraints(pattern=r"^plan_\d{2,}$")]
RunId = Annotated[str, StringConstraints(pattern=r"^run_\d{4,}$")]
TaskId = Annotated[str, StringConstraints(pattern=r"^[A-Z]+-\d{3}$")]
RunRole = Literal["planner", "implementer", "reviewer", "classifier"]
RunExit = Literal["ok", "error", "timeout"]
GateName = Literal["path_check", "ruff", "pytest", "gitleaks", "review"]
ResolveDecision = Literal["retry", "abandon"]
CommitSha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]


class RecordedViolation(BaseModel):
    """A violation as stored in an event; `rule` is a plain string so old events always replay."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule: str
    subject: str
    message: str


class SpecWarning(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    check: str
    subject: str
    message: str


class SpecImportedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: SpecVersionId
    hash: ContentHash
    spec: SpecSet


class SpecValidatedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: SpecVersionId
    hash: ContentHash
    violations: list[RecordedViolation]
    warnings: list[SpecWarning]


class SpecApprovedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: SpecVersionId
    hash: ContentHash


class PlanCreatedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_id: PlanId
    spec_version: SpecVersionId
    policy_hash: ContentHash
    run_id: RunId
    tasks: list[TaskContract]


class PlanApprovedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_id: PlanId


class TaskStateChangedPayload(BaseModel):
    """`from` is a Python keyword: the field is `from_`, and a plain dump writes `from`."""

    model_config = ConfigDict(
        frozen=True, extra="forbid", serialize_by_alias=True, validate_by_name=True
    )

    task_id: TaskId
    from_: TaskState = Field(alias="from")
    to: TaskState
    reason: str | None

    @model_validator(mode="after")
    def _invalidated_has_a_reason(self) -> Self:
        if self.to is TaskState.invalidated and self.reason is None:
            raise ValueError("reason is required when to is invalidated")
        return self


class AgentRunStartedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: RunId
    task_id: TaskId | None
    role: RunRole
    runtime: str
    context_hash: ContentHash


class AgentRunFinishedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: RunId
    exit: RunExit
    model: str | None
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float | None
    duration_s: float
    error: str | None


class GateEvaluatedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: RunId
    task_id: TaskId
    gate: GateName
    passed: bool
    output_path: str | None


class CommitRecordedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sha: CommitSha
    task_id: TaskId
    run_id: RunId
    branch: str
    spec_version: SpecVersionId
    files: list[str]


class TaskResolvedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: TaskId
    decision: ResolveDecision


PAYLOAD_MODELS: dict[EventType, type[BaseModel]] = {
    EventType.SpecImported: SpecImportedPayload,
    EventType.SpecValidated: SpecValidatedPayload,
    EventType.SpecApproved: SpecApprovedPayload,
    EventType.PlanCreated: PlanCreatedPayload,
    EventType.PlanApproved: PlanApprovedPayload,
    EventType.TaskStateChanged: TaskStateChangedPayload,
    EventType.AgentRunStarted: AgentRunStartedPayload,
    EventType.AgentRunFinished: AgentRunFinishedPayload,
    EventType.GateEvaluated: GateEvaluatedPayload,
    EventType.CommitRecorded: CommitRecordedPayload,
    EventType.TaskResolved: TaskResolvedPayload,
}
