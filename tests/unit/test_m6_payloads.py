"""TASK-090 AC1..AC4: the ImpactComputed payload model
(docs/tasks/TASK-090-impact-computed-payload.md)."""

import importlib

import pytest
from pydantic import ValidationError

from openfactory.domain.events import EventType

MODIFIED = {
    "id": "REQ-AUTH-001",
    "change": "modified",
    "kind": "behavioral",
    "rationale": "login now needs a second factor",
    "obsolete_criteria": ["AC-AUTH-001-2"],
    "new_work": ["add a second factor step"],
}
ADDED = {
    "id": "REQ-AUTH-002",
    "change": "added",
    "kind": None,
    "rationale": None,
    "obsolete_criteria": [],
    "new_work": [],
}
DEPRECATED = {**ADDED, "id": "REQ-AUTH-003", "change": "deprecated"}
ADR = {"id": "ADR-001", "change": "modified"}
FULL = {
    "from_version": "sv_01",
    "to_version": "sv_02",
    "run_id": "run_0007",
    "requirements": [MODIFIED, ADDED],
    "adrs": [ADR],
    "tasks": ["AUTH-001"],
    "downstream": ["AUTH-002"],
    "files": ["a.py", "b.py"],
    "tests": ["tests/test_a.py::test_x"],
}
NO_CALL = {
    **FULL,
    "run_id": None,
    "requirements": [ADDED, DEPRECATED],
    "adrs": [{"id": "ADR-002", "change": "added"}],
}
TOP_FIELDS = [
    "from_version",
    "to_version",
    "run_id",
    "requirements",
    "adrs",
    "tasks",
    "downstream",
    "files",
    "tests",
]


def payloads():
    return importlib.import_module("openfactory.domain.payloads")


def drop(data: dict, key: str) -> dict:
    return {k: v for k, v in data.items() if k != key}


# AC1


def test_task090_ac1_payload_has_exactly_the_spec_fields_and_round_trips() -> None:
    p = payloads()
    assert list(p.ImpactComputedPayload.model_fields) == TOP_FIELDS
    assert list(p.RequirementImpact.model_fields) == list(MODIFIED)
    assert list(p.AdrImpact.model_fields) == ["id", "change"]
    for data in (FULL, NO_CALL):
        assert p.ImpactComputedPayload.model_validate(data).model_dump(mode="json") == data


@pytest.mark.parametrize(
    "data",
    [
        *[drop(FULL, k) for k in TOP_FIELDS],
        {**FULL, "extra": 1},
        {**FULL, "requirements": [drop(MODIFIED, "kind")]},
        {**FULL, "requirements": [drop(MODIFIED, "rationale")]},
        {**FULL, "requirements": [drop(MODIFIED, "new_work")]},
        {**FULL, "requirements": [{**MODIFIED, "extra": 1}]},
        {**FULL, "adrs": [drop(ADR, "change")]},
        {**FULL, "adrs": [{**ADR, "extra": 1}]},
    ],
)
def test_task090_ac1_payload_rejects_a_missing_or_unknown_field(data) -> None:
    with pytest.raises(ValidationError):
        payloads().ImpactComputedPayload.model_validate(data)


def test_task090_ac1_payload_and_items_are_frozen() -> None:
    p = payloads().ImpactComputedPayload.model_validate(FULL)
    with pytest.raises(ValidationError):
        p.run_id = None
    with pytest.raises(ValidationError):
        p.requirements[0].change = "added"
    with pytest.raises(ValidationError):
        p.adrs[0].change = "added"


# AC2


@pytest.mark.parametrize("change", ["added", "removed", "modified", "deprecated"])
def test_task090_ac2_every_requirement_change_validates(change) -> None:
    item = MODIFIED if change == "modified" else {**ADDED, "change": change}
    payloads().RequirementImpact.model_validate(item)


@pytest.mark.parametrize("change", ["added", "removed", "modified"])
def test_task090_ac2_every_adr_change_validates(change) -> None:
    payloads().AdrImpact.model_validate({"id": "ADR-001", "change": change})


@pytest.mark.parametrize("kind", ["cosmetic", "behavioral", "replacement"])
def test_task090_ac2_every_kind_validates(kind) -> None:
    payloads().RequirementImpact.model_validate({**MODIFIED, "kind": kind})


def test_task090_ac2_stored_payloads_of_every_closed_set_value_still_validate() -> None:
    changes = ["added", "removed", "deprecated"]  # `modified` is stored once per kind below
    kinds = ["cosmetic", "behavioral", "replacement"]
    reqs = [{**ADDED, "id": f"REQ-A-{i:03d}", "change": c} for i, c in enumerate(changes)]
    reqs += [{**MODIFIED, "id": f"REQ-B-{i:03d}", "kind": k} for i, k in enumerate(kinds)]
    adrs = [
        {"id": f"ADR-{i:03d}", "change": c} for i, c in enumerate(["added", "removed", "modified"])
    ]
    stored = {**FULL, "requirements": reqs, "adrs": adrs}
    assert payloads().ImpactComputedPayload.model_validate(stored).model_dump(mode="json") == stored


@pytest.mark.parametrize(
    "data",
    [
        {**FULL, "adrs": [{"id": "ADR-001", "change": "deprecated"}]},
        {**FULL, "requirements": [{**ADDED, "change": "unchanged"}]},
        {**FULL, "requirements": [{**MODIFIED, "kind": "minor"}]},
        {**FULL, "run_id": "run_7"},
        {**FULL, "tasks": ["auth-2"]},
        {**FULL, "downstream": ["auth-2"]},
    ],
    ids=[
        "adr-deprecated",
        "req-unchanged",
        "kind-minor",
        "run_7",
        "tasks-auth-2",
        "downstream-auth-2",
    ],
)
def test_task090_ac2_a_value_outside_the_closed_set_or_id_form_is_rejected(data) -> None:
    with pytest.raises(ValidationError):
        payloads().ImpactComputedPayload.model_validate(data)


# AC3


@pytest.mark.parametrize("field", ["kind", "rationale"])
def test_task090_ac3_a_modified_requirement_needs_kind_and_rationale(field) -> None:
    with pytest.raises(ValidationError):
        payloads().RequirementImpact.model_validate({**MODIFIED, field: None})


@pytest.mark.parametrize("change", ["added", "removed", "deprecated"])
@pytest.mark.parametrize(
    "extra",
    [
        {"kind": "cosmetic"},
        {"rationale": "why"},
        {"obsolete_criteria": ["AC-1"]},
        {"new_work": ["work"]},
    ],
    ids=["kind", "rationale", "obsolete_criteria", "new_work"],
)
def test_task090_ac3_an_unmodified_requirement_carries_no_classification(change, extra) -> None:
    with pytest.raises(ValidationError):
        payloads().RequirementImpact.model_validate({**ADDED, "change": change, **extra})


def test_task090_ac3_a_modified_requirement_with_empty_lists_validates() -> None:
    item = {**MODIFIED, "obsolete_criteria": [], "new_work": []}
    assert payloads().RequirementImpact.model_validate(item).new_work == []


# AC4


def test_task090_ac4_payload_models_registers_impact_computed() -> None:
    p = payloads()
    assert p.PAYLOAD_MODELS[EventType.ImpactComputed] is p.ImpactComputedPayload


def test_task090_ac4_payload_models_has_one_entry_per_event_type() -> None:
    assert set(payloads().PAYLOAD_MODELS) == set(EventType)
    assert len(payloads().PAYLOAD_MODELS) == 13
