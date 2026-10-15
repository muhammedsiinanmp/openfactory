"""TASK-058: the TaskResolved event type and its payload model
(docs/tasks/TASK-058-task-resolved-cost-column-and-gates-removal.md, AC1..AC4)."""

import importlib

import pytest
from pydantic import ValidationError

from openfactory.domain.events import Event, EventType

TWELVE = {
    "SpecImported",
    "SpecValidated",
    "SpecApproved",
    "PlanCreated",
    "PlanApproved",
    "TaskStateChanged",
    "AgentRunStarted",
    "AgentRunFinished",
    "GateEvaluated",
    "CommitRecorded",
    "TaskResolved",
    "ImpactComputed",
}
ELEVEN_MODEL_KEYS = TWELVE - {"ImpactComputed"}

RETRY = {"task_id": "AUTH-002", "decision": "retry"}
ABANDON = {"task_id": "AUTH-002", "decision": "abandon"}


def payloads():
    return importlib.import_module("openfactory.domain.payloads")


def model():
    return payloads().TaskResolvedPayload


# ---------------------------------------------------------------- AC1


def test_ac1_event_type_has_exactly_the_twelve_values():
    assert {m.value for m in EventType} == TWELVE
    assert len(list(EventType)) == 12


# ---------------------------------------------------------------- AC2


@pytest.mark.parametrize("data", [RETRY, ABANDON], ids=["retry", "abandon"])
def test_ac2_task_resolved_validates_and_dumps_what_it_was_given(data):
    assert model().model_validate(data).model_dump(mode="json") == data


@pytest.mark.parametrize(
    "data",
    [
        {"decision": "retry"},
        {"task_id": "AUTH-002"},
        {**RETRY, "surprise": 1},
        {**RETRY, "decision": "skip"},
        {**RETRY, "task_id": "auth-2"},
    ],
    ids=["no_task_id", "no_decision", "unknown_key", "bad_decision", "bad_task_id"],
)
def test_ac2_task_resolved_rejects_bad_payloads(data):
    with pytest.raises(ValidationError):
        model().model_validate(data)


def test_ac2_task_resolved_is_frozen():
    payload = model().model_validate(RETRY)
    with pytest.raises(ValidationError):
        payload.decision = "abandon"


def test_ac2_payload_models_has_exactly_the_eleven_keys():
    p = payloads()
    assert {k.value for k in p.PAYLOAD_MODELS} == ELEVEN_MODEL_KEYS
    assert EventType.ImpactComputed not in p.PAYLOAD_MODELS
    assert p.PAYLOAD_MODELS[EventType["TaskResolved"]] is p.TaskResolvedPayload


# ---------------------------------------------------------------- AC3
# Literal stored values: renaming or narrowing the decision set must fail here.

STORED_TASK_RESOLVED = [
    {"task_id": "AUTH-002", "decision": "retry"},
    {"task_id": "AUTH-002", "decision": "abandon"},
]


@pytest.mark.parametrize("stored", STORED_TASK_RESOLVED, ids=lambda p: p["decision"])
def test_ac3_stored_decisions_still_validate(stored):
    payloads().PAYLOAD_MODELS[EventType["TaskResolved"]].model_validate(stored)


# ---------------------------------------------------------------- AC4


@pytest.mark.parametrize("data", [RETRY, ABANDON], ids=["retry", "abandon"])
def test_ac4_dumped_payload_is_accepted_by_the_event_envelope(data):
    event = Event.new(
        stream="task:AUTH-002",
        type=EventType["TaskResolved"],
        payload=model().model_validate(data).model_dump(mode="json"),
        actor="human",
    )
    assert event.payload == data


@pytest.mark.parametrize("data", [RETRY, ABANDON], ids=["retry", "abandon"])
def test_ac4_payload_survives_the_event_round_trip(data):
    original = model().model_validate(data)
    event = Event.new(
        stream="task:AUTH-002",
        type=EventType["TaskResolved"],
        payload=original.model_dump(mode="json"),
        actor="human",
    )
    stored = Event.model_validate_json(event.model_dump_json())
    assert stored.type is EventType["TaskResolved"]
    assert (
        model().model_validate_json(model().model_validate(stored.payload).model_dump_json())
        == original
    )
    assert model().model_validate(stored.payload) == original
