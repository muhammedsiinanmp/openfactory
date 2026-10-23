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
RequirementChange = Literal["added", "removed", "modified", "deprecated"]
AdrChange = Literal["added", "removed", "modified"]
ChangeKind = Literal["cosmetic", "behavioral", "replacement"]
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


class CollectedTest(BaseModel):
    """One test of a `TestsCollected` payload; kept apart from `MarkerLine` (ADR-007)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str
    file: str
    req: list[str]


class TestsCollectedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: RunId
    task_id: TaskId
    # Every test the pytest gate collected, sorted by `node_id` by the use case.
    tests: list[CollectedTest]


class TaskResolvedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: TaskId
    decision: ResolveDecision


class RequirementImpact(BaseModel):
    """One changed requirement of an `ImpactComputed`; kept apart from `ChangeClass` (ADR-007)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    change: RequirementChange
    kind: ChangeKind | None
    rationale: str | None
    obsolete_criteria: list[str]
    new_work: list[str]

    @model_validator(mode="after")
    def _classified_only_when_modified(self) -> Self:
        if self.change == "modified":
            if self.kind is None or self.rationale is None:
                raise ValueError("kind and rationale are required when change is modified")
        elif (
            self.kind is not None
            or self.rationale is not None
            or self.obsolete_criteria
            or self.new_work
        ):
            raise ValueError(
                "kind and rationale are null, obsolete_criteria and new_work are [],"
                " unless change is modified"
            )
        return self


class AdrImpact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    change: AdrChange


class ImpactComputedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    from_version: SpecVersionId
    to_version: SpecVersionId
    run_id: RunId | None
    # The lists are sorted by the use case; the model checks no order.
    requirements: list[RequirementImpact]
    adrs: list[AdrImpact]
    tasks: list[TaskId]
    downstream: list[TaskId]
    files: list[str]
    tests: list[str]


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
    EventType.TestsCollected: TestsCollectedPayload,
    EventType.CommitRecorded: CommitRecordedPayload,
    EventType.TaskResolved: TaskResolvedPayload,
    EventType.ImpactComputed: ImpactComputedPayload,
}
