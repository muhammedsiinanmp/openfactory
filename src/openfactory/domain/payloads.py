"""Payload models for events, one per event type.

Implements "Event payloads" under "Domain model and storage" in
docs/spec/phase1-spec.md for the M1 spec events. Event payloads are built
and checked through these models.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from openfactory.domain.events import EventType
from openfactory.domain.models import SpecSet

SpecVersionId = Annotated[str, StringConstraints(pattern=r"^sv_\d{2,}$")]
ContentHash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


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


PAYLOAD_MODELS: dict[EventType, type[BaseModel]] = {
    EventType.SpecImported: SpecImportedPayload,
    EventType.SpecValidated: SpecValidatedPayload,
    EventType.SpecApproved: SpecApprovedPayload,
}
