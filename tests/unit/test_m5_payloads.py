"""TASK-079 AC3: the TestsCollected payload model (docs/tasks/TASK-079-tests-collected.md)."""

import importlib

import pytest
from pydantic import ValidationError

from openfactory.domain.events import EventType

ITEM = {"node_id": "tests/test_a.py::test_x", "file": "tests/test_a.py", "req": ["REQ-A-001"]}
DATA = {"run_id": "run_0002", "task_id": "AUTH-002", "tests": [ITEM]}


def payloads():
    return importlib.import_module("openfactory.domain.payloads")


def test_task079_ac3_payload_has_exactly_the_spec_fields_and_round_trips() -> None:
    model = payloads().TestsCollectedPayload
    assert list(model.model_fields) == ["run_id", "task_id", "tests"]
    assert list(payloads().CollectedTest.model_fields) == ["node_id", "file", "req"]
    assert model.model_validate(DATA).model_dump(mode="json") == DATA
    empty = {**DATA, "tests": []}
    assert model.model_validate(empty).tests == []


@pytest.mark.parametrize(
    "data",
    [
        {k: v for k, v in DATA.items() if k != "tests"},
        {k: v for k, v in DATA.items() if k != "run_id"},
        {**DATA, "extra": 1},
        {**DATA, "tests": [{k: v for k, v in ITEM.items() if k != "req"}]},
        {**DATA, "tests": [{k: v for k, v in ITEM.items() if k != "node_id"}]},
        {**DATA, "tests": [{**ITEM, "extra": 1}]},
    ],
    ids=["no-tests", "no-run_id", "unknown-key", "item-no-req", "item-no-node_id", "item-unknown"],
)
def test_task079_ac3_payload_rejects_a_missing_or_unknown_field(data) -> None:
    with pytest.raises(ValidationError):
        payloads().TestsCollectedPayload.model_validate(data)


def test_task079_ac3_payload_is_frozen() -> None:
    p = payloads().TestsCollectedPayload.model_validate(DATA)
    with pytest.raises(ValidationError):
        p.run_id = "run_0003"
    with pytest.raises(ValidationError):
        p.tests[0].file = "x.py"


def test_task079_ac3_payload_models_registers_tests_collected_with_twelve_entries() -> None:
    p = payloads()
    assert p.PAYLOAD_MODELS[EventType.TestsCollected] is p.TestsCollectedPayload
    assert len(p.PAYLOAD_MODELS) == 12
    assert EventType.ImpactComputed not in p.PAYLOAD_MODELS
