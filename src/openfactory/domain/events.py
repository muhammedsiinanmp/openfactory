"""Event envelope and the Phase 1 event types.

Mirrors the `events` table in docs/spec/phase1-spec.md ("Domain model and storage").
"""

import math
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID, uuid4

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
)

ACTOR_PATTERN = r"^(human|orchestrator|agent:[a-z][a-z-]*)$"
# Pydantic's JSON reader refuses integers of about 4300 digits; smaller ones round-trip.
_INT_LIMIT = 10**4299


class EventType(StrEnum):
    SpecImported = "SpecImported"
    SpecValidated = "SpecValidated"
    SpecApproved = "SpecApproved"
    PlanCreated = "PlanCreated"
    PlanApproved = "PlanApproved"
    TaskStateChanged = "TaskStateChanged"
    AgentRunStarted = "AgentRunStarted"
    AgentRunFinished = "AgentRunFinished"
    GateEvaluated = "GateEvaluated"
    CommitRecorded = "CommitRecorded"
    ImpactComputed = "ImpactComputed"


def _datetime_or_iso(value: object) -> datetime:
    """Pydantic would otherwise read a number as a Unix timestamp."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise ValueError("created_at must be a datetime or an ISO 8601 string")


def _to_utc(value: datetime) -> datetime:
    try:
        return value.astimezone(UTC)
    except OverflowError as exc:
        raise ValueError("created_at is out of range when converted to UTC") from exc


def _check_text(value: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("payload strings must be valid Unicode (no lone surrogates)") from exc


def _reject_non_json(value: JsonValue) -> JsonValue:
    """Reject what JsonValue lets through but JSON text cannot carry faithfully.

    NaN and Infinity would serialise as null; a lone surrogate cannot be encoded;
    a huge integer is written but cannot be read back.
    """
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("payload must not contain NaN or Infinity")
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) >= _INT_LIMIT:
        raise ValueError("payload integers must have fewer than 4300 digits")
    if isinstance(value, str):
        _check_text(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_text(key)
            _reject_non_json(item)
    elif isinstance(value, list):
        for item in value:
            _reject_non_json(item)
    return value


UtcDatetime = Annotated[AwareDatetime, BeforeValidator(_datetime_or_iso), AfterValidator(_to_utc)]
JsonObject = Annotated[dict[str, JsonValue], AfterValidator(_reject_non_json)]


class Event(BaseModel):
    """A new event, not yet assigned a `seq` by the store."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    stream: str = Field(min_length=1)
    type: EventType
    payload: JsonObject
    actor: str = Field(pattern=ACTOR_PATTERN)
    causation_id: UUID | None = None
    created_at: UtcDatetime

    @classmethod
    def new(
        cls,
        *,
        stream: str,
        type: EventType,
        payload: dict[str, JsonValue],
        actor: str,
        causation_id: UUID | None = None,
    ) -> Self:
        """Build an event with a generated UUID4 `event_id` and the current UTC time."""
        return cls(
            event_id=uuid4(),
            stream=stream,
            type=type,
            payload=payload,
            actor=actor,
            causation_id=causation_id,
            created_at=datetime.now(UTC),
        )


class StoredEvent(Event):
    """An event read back from the store; only these are replayed."""

    seq: int = Field(strict=True, ge=1)
