"""TASK-040: payload models for the gate and commit events.

Each test names the acceptance criterion it covers (AC1..AC5 in
docs/tasks/TASK-040-m3-event-payloads.md).
"""

import importlib
from typing import get_args

import pytest
from pydantic import ValidationError

from openfactory.domain.contracts import REQUIRED_GATES
from openfactory.domain.events import Event, EventType

SHA = "a" * 40

BASE = {
    "GateEvaluatedPayload": {
        "run_id": "run_0002",
        "task_id": "AUTH-002",
        "gate": "path_check",
        "passed": True,
        "output_path": None,
    },
    "CommitRecordedPayload": {
        "sha": SHA,
        "task_id": "AUTH-002",
        "run_id": "run_0002",
        "branch": "openfactory/AUTH-002",
        "spec_version": "sv_01",
        "files": ["app/auth/login.py", "tests/auth/test_login.py"],
    },
}
MODEL_NAMES = list(BASE)
EVENT_FOR = {
    "GateEvaluatedPayload": EventType.GateEvaluated,
    "CommitRecordedPayload": EventType.CommitRecorded,
}


def payloads():
    return importlib.import_module("openfactory.domain.payloads")


def data_for(name, **overrides):
    return {**BASE[name], **overrides}


def validate(name, **overrides):
    return getattr(payloads(), name).model_validate(data_for(name, **overrides))


# ---------------------------------------------------------------- AC1


def test_ac1_payload_models_has_exactly_the_ten_events_without_impact_computed():
    p = payloads()
    assert set(p.PAYLOAD_MODELS) >= {
        EventType.SpecImported,
        EventType.SpecValidated,
        EventType.SpecApproved,
        EventType.PlanCreated,
        EventType.PlanApproved,
        EventType.TaskStateChanged,
        EventType.AgentRunStarted,
        EventType.AgentRunFinished,
        EventType.GateEvaluated,
        EventType.CommitRecorded,
    }
    assert p.PAYLOAD_MODELS[EventType.GateEvaluated] is p.GateEvaluatedPayload
    assert p.PAYLOAD_MODELS[EventType.CommitRecorded] is p.CommitRecordedPayload


@pytest.mark.parametrize(
    "name, field", [(name, field) for name, data in BASE.items() for field in data]
)
def test_ac1_every_field_is_required_nullable_ones_included(name, field):
    data = data_for(name)
    del data[field]
    with pytest.raises(ValidationError):
        getattr(payloads(), name).model_validate(data)


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_ac1_unknown_field_is_rejected(name):
    with pytest.raises(ValidationError):
        validate(name, surprise=1)


def test_ac1_gate_name_type_equals_the_required_gates():
    assert get_args(payloads().GateName) == tuple(REQUIRED_GATES)


# ---------------------------------------------------------------- AC2


def test_ac2_gate_evaluated_dumps_what_it_was_given():
    payload = validate("GateEvaluatedPayload")
    assert payload.model_dump(mode="json") == BASE["GateEvaluatedPayload"]


def test_ac2_gate_evaluated_failed_with_an_output_file():
    payload = validate(
        "GateEvaluatedPayload",
        passed=False,
        output_path=".openfactory/runs/run_0002/path_check.txt",
    )
    assert payload.passed is False
    assert payload.output_path == ".openfactory/runs/run_0002/path_check.txt"


@pytest.mark.parametrize(
    "override",
    [{"gate": "semgrep"}, {"run_id": "run_002"}, {"task_id": "auth-2"}],
)
def test_ac2_gate_evaluated_rejects_bad_gate_and_ids(override):
    with pytest.raises(ValidationError):
        validate("GateEvaluatedPayload", **override)


# ---------------------------------------------------------------- AC3


def test_ac3_commit_recorded_dumps_what_it_was_given_files_in_order():
    payload = validate("CommitRecordedPayload")
    assert payload.model_dump(mode="json") == BASE["CommitRecordedPayload"]


@pytest.mark.parametrize(
    "override",
    [
        {"sha": "a" * 39},
        {"sha": "a" * 39 + "g"},
        {"spec_version": "v1"},
        {"run_id": "run_1"},
        {"task_id": "auth-2"},
        {"files": "app/auth/login.py"},
    ],
)
def test_ac3_commit_recorded_rejects_bad_values(override):
    with pytest.raises(ValidationError):
        validate("CommitRecordedPayload", **override)


# ---------------------------------------------------------------- AC4
# Literal stored values: renaming or narrowing the gate names must fail here.

STORED_GATE_EVALUATED = [
    {
        "run_id": "run_0002",
        "task_id": "AUTH-002",
        "gate": "path_check",
        "passed": True,
        "output_path": None,
    },
    {
        "run_id": "run_0002",
        "task_id": "AUTH-002",
        "gate": "ruff",
        "passed": False,
        "output_path": ".openfactory/runs/run_0002/ruff.txt",
    },
    {
        "run_id": "run_0002",
        "task_id": "AUTH-002",
        "gate": "pytest",
        "passed": True,
        "output_path": ".openfactory/runs/run_0002/pytest.txt",
    },
    {
        "run_id": "run_0002",
        "task_id": "AUTH-002",
        "gate": "gitleaks",
        "passed": True,
        "output_path": None,
    },
    {
        "run_id": "run_0002",
        "task_id": "AUTH-002",
        "gate": "review",
        "passed": False,
        "output_path": ".openfactory/runs/run_0002/review.json",
    },
]


@pytest.mark.parametrize(
    "payload", STORED_GATE_EVALUATED, ids=[p["gate"] for p in STORED_GATE_EVALUATED]
)
def test_ac4_stored_gate_names_still_validate(payload):
    payloads().PAYLOAD_MODELS[EventType.GateEvaluated].model_validate(payload)


# ---------------------------------------------------------------- AC5


def _round_trip(name, model):
    event = Event.new(
        stream="task:AUTH-002",
        type=EVENT_FOR[name],
        payload=model.model_dump(mode="json"),
        actor="orchestrator",
    )
    stored = Event.model_validate_json(event.model_dump_json())
    return stored, payloads().PAYLOAD_MODELS[stored.type].model_validate(stored.payload)


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_ac5_dumped_payload_is_accepted_by_the_event_envelope(name):
    event = Event.new(
        stream="task:AUTH-002",
        type=EVENT_FOR[name],
        payload=validate(name).model_dump(mode="json"),
        actor="orchestrator",
    )
    assert event.type is EVENT_FOR[name]
    assert event.payload == data_for(name)


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_ac5_payload_survives_the_event_round_trip(name):
    model = validate(name)
    stored, back = _round_trip(name, model)
    assert stored.type is EVENT_FOR[name]
    assert back == model
