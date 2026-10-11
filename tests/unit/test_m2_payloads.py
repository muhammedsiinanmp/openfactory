"""TASK-021: payload models for the plan, task and agent run events.

Each test names the acceptance criterion it covers (AC1..AC6 in
docs/tasks/TASK-021-m2-event-payloads.md).
"""

import importlib

import pytest
from pydantic import ValidationError

from openfactory.domain.events import Event, EventType

HASH = "a" * 64

CONTRACT_1 = {
    "task_id": "AUTH-002",
    "objective": "Implement login endpoint using membership number",
    "requirements": ["REQ-AUTH-001"],
    "acceptance_criteria": ["AC-AUTH-001-1", "AC-AUTH-001-2"],
    "depends_on": ["AUTH-001"],
    "components": ["auth"],
    "role": "implementer",
    "allowed_paths": ["app/auth/**", "tests/auth/**"],
    "forbidden_paths": ["specs/**", ".openfactory/**", ".env", ".env.*"],
    "required_gates": ["path_check", "ruff", "pytest", "gitleaks", "review"],
    "limits": {"max_runtime_s": 1200, "max_attempts": 2, "max_cost_usd": 1.5},
}
CONTRACT_2 = {
    "task_id": "WEB-001",
    "objective": "Add the home page",
    "requirements": ["REQ-WEB-002", "REQ-WEB-001"],
    "acceptance_criteria": ["AC-WEB-001-2", "AC-WEB-001-1"],
    "depends_on": [],
    "components": ["web", "auth"],
    "role": "implementer",
    "allowed_paths": ["web/**", "app/**"],
    "forbidden_paths": [],
    "required_gates": ["review", "path_check", "pytest"],
    "limits": {"max_runtime_s": 600, "max_attempts": 3, "max_cost_usd": 0.5},
}

BASE = {
    "PlanCreatedPayload": {
        "plan_id": "plan_01",
        "spec_version": "sv_01",
        "policy_hash": HASH,
        "run_id": "run_0001",
        "tasks": [CONTRACT_1, CONTRACT_2],
    },
    "PlanApprovedPayload": {"plan_id": "plan_01"},
    "TaskStateChangedPayload": {
        "task_id": "AUTH-002",
        "from": "pending",
        "to": "ready",
        "reason": None,
    },
    "AgentRunStartedPayload": {
        "run_id": "run_0001",
        "task_id": None,
        "role": "planner",
        "runtime": "claude-code",
        "context_hash": HASH,
    },
    "AgentRunFinishedPayload": {
        "run_id": "run_0001",
        "exit": "ok",
        "model": "claude-sonnet",
        "tokens_in": 100,
        "tokens_out": 50,
        "cost_usd": 0.25,
        "duration_s": 12.5,
        "error": None,
    },
}
MODEL_NAMES = list(BASE)
EVENT_FOR = {
    "PlanCreatedPayload": EventType.PlanCreated,
    "PlanApprovedPayload": EventType.PlanApproved,
    "TaskStateChangedPayload": EventType.TaskStateChanged,
    "AgentRunStartedPayload": EventType.AgentRunStarted,
    "AgentRunFinishedPayload": EventType.AgentRunFinished,
}


def payloads():
    return importlib.import_module("openfactory.domain.payloads")


def data_for(name, **overrides):
    return {**BASE[name], **overrides}


def validate(name, **overrides):
    return getattr(payloads(), name).model_validate(data_for(name, **overrides))


# ---------------------------------------------------------------- AC1


def test_ac1_payload_models_has_exactly_the_eight_spec_events():
    p = payloads()
    assert {
        EventType.SpecImported: p.SpecImportedPayload,
        EventType.SpecValidated: p.SpecValidatedPayload,
        EventType.SpecApproved: p.SpecApprovedPayload,
        EventType.PlanCreated: p.PlanCreatedPayload,
        EventType.PlanApproved: p.PlanApprovedPayload,
        EventType.TaskStateChanged: p.TaskStateChangedPayload,
        EventType.AgentRunStarted: p.AgentRunStartedPayload,
        EventType.AgentRunFinished: p.AgentRunFinishedPayload,
    } == p.PAYLOAD_MODELS


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


# ---------------------------------------------------------------- AC2


def test_ac2_plan_created_keeps_both_contracts_and_their_order():
    p = payloads()
    payload = validate("PlanCreatedPayload")
    assert all(isinstance(t, p.TaskContract) for t in payload.tasks)
    assert payload.model_dump(mode="json") == BASE["PlanCreatedPayload"]


@pytest.mark.parametrize("missing", ["required_gates", "limits"])
def test_ac2_plan_created_rejects_a_planned_task_shape(missing):
    partial = {k: v for k, v in CONTRACT_1.items() if k != missing}
    with pytest.raises(ValidationError):
        validate("PlanCreatedPayload", tasks=[partial])


@pytest.mark.parametrize(
    "field, good, bad",
    [
        ("plan_id", ["plan_01", "plan_100"], ["plan_1", "Plan_01", ""]),
        ("run_id", ["run_0001", "run_12345"], ["run_001", "run_1"]),
        ("policy_hash", [HASH], ["a" * 63, "A" + "a" * 63]),
    ],
)
def test_ac2_plan_created_id_and_hash_forms(field, good, bad):
    for value in good:
        assert getattr(validate("PlanCreatedPayload", **{field: value}), field) == value
    for value in bad:
        with pytest.raises(ValidationError):
            validate("PlanCreatedPayload", **{field: value})


def test_ac2_plan_approved_has_exactly_plan_id():
    cls = payloads().PlanApprovedPayload
    assert set(cls.model_fields) == {"plan_id"}
    assert cls.model_validate({"plan_id": "plan_01"}).plan_id == "plan_01"


# ---------------------------------------------------------------- AC3


def test_ac3_task_state_changed_dumps_the_key_from():
    payload = validate("TaskStateChangedPayload")
    assert payload.model_dump(mode="json") == BASE["TaskStateChangedPayload"]


def test_ac3_task_state_changed_also_validates_by_field_name():
    cls = payloads().TaskStateChangedPayload
    payload = cls(task_id="AUTH-002", from_="pending", to="ready", reason=None)
    assert payload == validate("TaskStateChangedPayload")


def test_ac3_invalidated_needs_a_text_reason():
    ok = validate("TaskStateChangedPayload", to="invalidated", reason="spec changed")
    assert ok.reason == "spec changed"
    with pytest.raises(ValidationError):
        validate("TaskStateChangedPayload", to="invalidated", reason=None)


def test_ac3_text_reason_is_allowed_with_another_target():
    assert validate("TaskStateChangedPayload", reason="why not").reason == "why not"


@pytest.mark.parametrize("field", ["from", "to"])
def test_ac3_state_outside_the_nine_is_rejected(field):
    with pytest.raises(ValidationError):
        validate("TaskStateChangedPayload", **{field: "done"})


# ---------------------------------------------------------------- AC4


@pytest.mark.parametrize("task_id", [None, "AUTH-002"])
def test_ac4_agent_run_started_with_and_without_a_task(task_id):
    assert validate("AgentRunStartedPayload", task_id=task_id).task_id == task_id


@pytest.mark.parametrize("override", [{"role": "coder"}, {"context_hash": "A" * 64}])
def test_ac4_agent_run_started_rejects_bad_role_and_hash(override):
    with pytest.raises(ValidationError):
        validate("AgentRunStartedPayload", **override)


def test_ac4_agent_run_finished_with_every_value_reported():
    payload = validate("AgentRunFinishedPayload")
    assert (payload.exit, payload.tokens_in, payload.cost_usd) == ("ok", 100, 0.25)


def test_ac4_agent_run_finished_as_a_failed_process_records_it():
    payload = validate(
        "AgentRunFinishedPayload",
        exit="timeout",
        model=None,
        tokens_in=None,
        tokens_out=None,
        cost_usd=None,
        duration_s=30.0,
        error="timed out",
    )
    assert payload.model is None
    assert payload.error == "timed out"


@pytest.mark.parametrize("override", [{"duration_s": None}, {"exit": "failed"}])
def test_ac4_agent_run_finished_rejects_null_duration_and_unknown_exit(override):
    with pytest.raises(ValidationError):
        validate("AgentRunFinishedPayload", **override)


# ---------------------------------------------------------------- AC5
# Literal stored values: renaming or narrowing a closed set must fail here.

STATES = [
    "pending",
    "ready",
    "running",
    "gating",
    "passed",
    "failed",
    "escalated",
    "abandoned",
    "invalidated",
]
GATES = ["path_check", "ruff", "pytest", "gitleaks", "review"]


def stored_payloads():
    rows = []
    for state in STATES:
        reason = "r" if state == "invalidated" else None
        rows.append(
            (
                "TaskStateChanged",
                {"task_id": "AUTH-002", "from": "pending", "to": state, "reason": reason},
            )
        )
        rows.append(
            (
                "TaskStateChanged",
                {"task_id": "AUTH-002", "from": state, "to": "ready", "reason": None},
            )
        )
    for role in ["planner", "implementer", "reviewer", "classifier"]:
        rows.append(("AgentRunStarted", {**BASE["AgentRunStartedPayload"], "role": role}))
    for exit_ in ["ok", "error", "timeout"]:
        rows.append(("AgentRunFinished", {**BASE["AgentRunFinishedPayload"], "exit": exit_}))
    contract = {**CONTRACT_1, "role": "implementer", "required_gates": GATES}
    rows.append(("PlanCreated", {**BASE["PlanCreatedPayload"], "tasks": [contract]}))
    return rows


def test_ac5_the_table_has_the_expected_number_of_rows():
    assert len(stored_payloads()) == 18 + 4 + 3 + 1


@pytest.mark.parametrize(
    "event_type, payload",
    stored_payloads(),
    ids=[f"{t}-{i}" for i, (t, _) in enumerate(stored_payloads())],
)
def test_ac5_stored_closed_values_still_validate(event_type, payload):
    model = payloads().PAYLOAD_MODELS[EventType(event_type)]
    model.model_validate(payload)


# ---------------------------------------------------------------- AC6


def _round_trip(name, model):
    event = Event.new(
        stream="plan:plan_01",
        type=EVENT_FOR[name],
        payload=model.model_dump(mode="json"),
        actor="orchestrator",
    )
    stored = Event.model_validate_json(event.model_dump_json())
    return stored, payloads().PAYLOAD_MODELS[stored.type].model_validate(stored.payload)


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_ac6_dumped_payload_is_accepted_by_the_event_envelope(name):
    model = validate(name)
    event = Event.new(
        stream="plan:plan_01",
        type=EVENT_FOR[name],
        payload=model.model_dump(mode="json"),
        actor="orchestrator",
    )
    assert event.type is EVENT_FOR[name]
    assert event.payload == data_for(name)


@pytest.mark.parametrize(
    "name, overrides",
    [
        ("PlanCreatedPayload", {}),
        ("TaskStateChangedPayload", {}),
        (
            "AgentRunFinishedPayload",
            {"model": None, "tokens_in": None, "tokens_out": None, "cost_usd": None},
        ),
    ],
)
def test_ac6_payload_survives_the_event_round_trip(name, overrides):
    model = validate(name, **overrides)
    stored, back = _round_trip(name, model)
    assert stored.type is EVENT_FOR[name]
    assert back == model
