"""Approve spec use case: run the validate use case, then record `SpecApproved` or say why not.

See docs/spec/phase1-spec.md ("Spec input format": "Spec versions", "Policies"; "Domain
model and storage": "Streams and actors", "Event payloads"). `approve_spec` does not rely
on an earlier `validate`: it calls the validate use case itself, so `SpecValidated` is
recorded before `SpecApproved`. Events are recorded through the `EventRecorder` port
(ADR-001). The use case returns data and prints nothing; policy problems are returned and
never block the approval.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from openfactory.app.validate import Outcome, validate
from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import SpecApprovedPayload
from openfactory.domain.spec_validation import SpecViolation
from openfactory.ports.event_recorder import EventRecorder
from openfactory.ports.spec_files import SpecFiles
from openfactory.ports.spec_versions import SpecVersions


class ApproveOutcome(StrEnum):
    unloadable = "unloadable"
    nothing_to_approve = "nothing_to_approve"
    refused = "refused"
    approved = "approved"


class ApproveResult(BaseModel):
    """What one `approve spec` run found and recorded.

    `spec_version` is the version approved or refused, the latest approved version when
    there is nothing to approve, and `None` when the spec files cannot be loaded.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: ApproveOutcome
    spec_version: str | None = None
    violations: list[SpecViolation] = []
    policy_problems: list[SpecViolation] = []


def approve_spec(
    files: SpecFiles, versions: SpecVersions, recorder: EventRecorder
) -> ApproveResult:
    validated = validate(files, versions, recorder)
    if validated.outcome is Outcome.unloadable:
        return ApproveResult(
            outcome=ApproveOutcome.unloadable,
            violations=validated.violations,
            policy_problems=validated.policy_problems,
        )
    if validated.outcome is Outcome.matches_approved:
        return ApproveResult(
            outcome=ApproveOutcome.nothing_to_approve,
            spec_version=validated.spec_version,
            policy_problems=validated.policy_problems,
        )
    if validated.violations:
        return ApproveResult(
            outcome=ApproveOutcome.refused,
            spec_version=validated.spec_version,
            violations=validated.violations,
            policy_problems=validated.policy_problems,
        )

    version, spec_hash = validated.spec_version, validated.hash
    # Set whenever a `SpecValidated` was recorded.
    assert version is not None and spec_hash is not None
    assert validated.validated_event_id is not None
    recorder.record(
        Event.new(
            stream=f"spec:{version}",
            type=EventType.SpecApproved,
            payload=SpecApprovedPayload(spec_version=version, hash=spec_hash).model_dump(
                mode="json"
            ),
            actor="human",
            causation_id=validated.validated_event_id,
        )
    )
    return ApproveResult(
        outcome=ApproveOutcome.approved,
        spec_version=version,
        policy_problems=validated.policy_problems,
    )
