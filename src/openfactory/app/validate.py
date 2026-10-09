"""Validate use case: load and hash the spec set, import it if it changed, run the rules.

See docs/spec/phase1-spec.md ("Spec input format": "Spec versions", "Policies"; "Domain
model and storage": "Streams and actors", "Event payloads"). Events are recorded through
the `EventRecorder` port and spec versions are read through `SpecVersions` (ADR-001).
The use case returns data and prints nothing; policy problems are returned, never recorded.
"""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from openfactory.app.spec_loader import load_policy, load_spec
from openfactory.domain.events import Event, EventType, StoredEvent
from openfactory.domain.models import SpecSet
from openfactory.domain.payloads import (
    RecordedViolation,
    SpecImportedPayload,
    SpecValidatedPayload,
)
from openfactory.domain.spec_hash import canonical_json, content_hash
from openfactory.domain.spec_validation import SpecViolation, validate_spec
from openfactory.ports.event_recorder import EventRecorder
from openfactory.ports.spec_files import SpecFiles
from openfactory.ports.spec_versions import SpecVersions


class Outcome(StrEnum):
    unloadable = "unloadable"
    matches_approved = "matches_approved"
    validated = "validated"


class ValidateResult(BaseModel):
    """What one `validate` run found and recorded.

    `hash` and `validated_event_id` are set only when a `SpecValidated` was recorded.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: Outcome
    spec_version: str | None = None
    violations: list[SpecViolation] = []
    policy_problems: list[SpecViolation] = []
    hash: str | None = None
    validated_event_id: UUID | None = None


def _spec_event(
    version: str, type: EventType, payload: BaseModel, causation_id: UUID | None
) -> Event:
    return Event.new(
        stream=f"spec:{version}",
        type=type,
        payload=payload.model_dump(mode="json"),
        actor="orchestrator",
        causation_id=causation_id,
    )


def validate(files: SpecFiles, versions: SpecVersions, recorder: EventRecorder) -> ValidateResult:
    policy_problems = load_policy(files).violations
    loaded = load_spec(files)
    if loaded.spec is None:
        return ValidateResult(
            outcome=Outcome.unloadable,
            violations=loaded.violations,
            policy_problems=policy_problems,
        )
    spec = loaded.spec
    spec_hash = content_hash(spec)

    approved = versions.latest_approved()
    if approved is not None and approved.hash == spec_hash:
        return ValidateResult(
            outcome=Outcome.matches_approved,
            spec_version=approved.id,
            policy_problems=policy_problems,
        )

    draft = versions.current_draft()
    # An existing draft keeps its id; its content is replaced unless the hash is the same.
    version = draft.id if draft is not None else versions.next_id()
    imported: StoredEvent | None = None
    if draft is None or draft.hash != spec_hash:
        imported = recorder.record(
            _spec_event(
                version,
                EventType.SpecImported,
                SpecImportedPayload(
                    spec_version=version,
                    hash=spec_hash,
                    # Canonical order: sorted as for hashing.
                    spec=SpecSet.model_validate_json(canonical_json(spec)),
                ),
                None,
            )
        )

    violations = validate_spec(spec)
    validated = recorder.record(
        _spec_event(
            version,
            EventType.SpecValidated,
            SpecValidatedPayload(
                spec_version=version,
                hash=spec_hash,
                violations=[
                    RecordedViolation(rule=v.rule.value, subject=v.subject, message=v.message)
                    for v in violations
                ],
                warnings=[],
            ),
            imported.event_id if imported is not None else None,
        )
    )
    return ValidateResult(
        outcome=Outcome.validated,
        spec_version=version,
        violations=violations,
        policy_problems=policy_problems,
        hash=spec_hash,
        validated_event_id=validated.event_id,
    )
