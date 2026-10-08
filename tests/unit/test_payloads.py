"""TASK-005: payload models for the spec events.

Each test names the acceptance criterion it covers (AC1..AC6 in
docs/tasks/TASK-005-spec-event-payloads.md).
"""

import ast
import importlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from openfactory.domain.events import Event, EventType
from openfactory.domain.models import SpecSet
from openfactory.domain.spec_hash import content_hash
from openfactory.domain.spec_validation import Rule, validate_spec

HASH = "a" * 64
SPEC_DICT = {
    "components": ["auth", "web"],
    "requirements": [
        {
            "id": "REQ-AUTH-001",
            "title": "Login",
            "statement": "Users can log in.",
            "priority": "must",
            "components": ["auth"],
            "constrained_by": ["ADR-001"],
            "deprecated": True,
            "acceptance_criteria": [
                {"id": "AC-AUTH-001-1", "text": "valid login works"},
                {"id": "AC-AUTH-001-2", "text": "bad password fails"},
            ],
        },
        {
            "id": "REQ-WEB-001",
            "title": "Home",
            "statement": "Home page loads.",
            "priority": "should",
            "acceptance_criteria": [{"id": "AC-WEB-001-1", "text": "returns 200"}],
        },
    ],
    "adrs": [{"id": "ADR-001", "status": "accepted", "body": "Use sessions.\n\nCafé ≥ 1 ✓\n"}],
}


def payloads():
    return importlib.import_module("openfactory.domain.payloads")


def example_spec():
    return SpecSet.model_validate(SPEC_DICT)


def broken_spec():
    return SpecSet.model_validate(
        {
            "components": ["auth"],
            "requirements": [
                {
                    "id": "bad-id",
                    "title": "t",
                    "statement": "s",
                    "priority": "must",
                    "components": ["nope"],
                    "acceptance_criteria": [],
                }
            ],
            "adrs": [],
        }
    )


def recorded_violations():
    p = payloads()
    found = validate_spec(broken_spec())
    return found, [
        p.RecordedViolation(rule=v.rule.value, subject=v.subject, message=v.message) for v in found
    ]


def kwargs_for(name, **overrides):
    base = {
        "SpecImportedPayload": {"spec_version": "sv_01", "hash": HASH, "spec": SPEC_DICT},
        "SpecValidatedPayload": {
            "spec_version": "sv_01",
            "hash": HASH,
            "violations": [],
            "warnings": [],
        },
        "SpecApprovedPayload": {"spec_version": "sv_01", "hash": HASH},
    }[name]
    return {**base, **overrides}


MODEL_NAMES = ["SpecImportedPayload", "SpecValidatedPayload", "SpecApprovedPayload"]
EVENT_FOR = {
    "SpecImportedPayload": EventType.SpecImported,
    "SpecValidatedPayload": EventType.SpecValidated,
    "SpecApprovedPayload": EventType.SpecApproved,
}


# ---------------------------------------------------------------- AC1


def test_ac1_payload_models_map_from_event_types_with_no_other_keys():
    p = payloads()
    assert {
        EventType.SpecImported: p.SpecImportedPayload,
        EventType.SpecValidated: p.SpecValidatedPayload,
        EventType.SpecApproved: p.SpecApprovedPayload,
    } == p.PAYLOAD_MODELS


def test_ac1_payloads_module_respects_domain_boundary():
    tree = ast.parse(Path(payloads().__file__).read_text())
    forbidden = ("openfactory.adapters", "openfactory.app", "openfactory.ports")
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        for name in names:
            assert not name.startswith(forbidden), name


# ---------------------------------------------------------------- AC2


def test_ac2_spec_imported_from_dict_exposes_equal_spec_set():
    payload = payloads().SpecImportedPayload.model_validate(kwargs_for("SpecImportedPayload"))
    assert isinstance(payload.spec, SpecSet)
    assert payload.spec == example_spec()
    assert payload.spec.requirements[0].deprecated is True
    assert payload.spec.adrs[0].body == SPEC_DICT["adrs"][0]["body"]


def test_ac2_spec_imported_accepts_spec_set_instance():
    payload = payloads().SpecImportedPayload(spec_version="sv_01", hash=HASH, spec=example_spec())
    assert payload.spec == example_spec()


@pytest.mark.parametrize("missing", ["spec_version", "hash", "spec"])
def test_ac2_spec_imported_requires_every_field(missing):
    data = kwargs_for("SpecImportedPayload")
    del data[missing]
    with pytest.raises(ValidationError):
        payloads().SpecImportedPayload.model_validate(data)


# ---------------------------------------------------------------- AC3


def test_ac3_violations_from_validate_spec_keep_values_and_order():
    found, recorded = recorded_violations()
    assert len(found) >= 2
    assert len({v.rule for v in found}) >= 2
    p = payloads()
    payload = p.SpecValidatedPayload(
        spec_version="sv_01", hash=HASH, violations=recorded, warnings=[]
    )
    assert len(payload.violations) == len(found)
    for got, src in zip(payload.violations, found, strict=True):
        assert isinstance(got, p.RecordedViolation)
        assert isinstance(got.rule, str)
        assert not isinstance(got.rule, Rule)
        assert (got.rule, got.subject, got.message) == (src.rule.value, src.subject, src.message)


@pytest.mark.parametrize("rule", ["schema", "some-renamed-rule"])
def test_ac3_rule_outside_rule_enum_is_accepted(rule):
    payload = payloads().SpecValidatedPayload.model_validate(
        kwargs_for(
            "SpecValidatedPayload",
            violations=[{"rule": rule, "subject": "x", "message": "m"}],
        )
    )
    assert payload.violations[0].rule == rule


def test_ac3_empty_violations_and_warnings_are_valid():
    payload = payloads().SpecValidatedPayload.model_validate(kwargs_for("SpecValidatedPayload"))
    assert payload.violations == []
    assert payload.warnings == []


def test_ac3_warning_entry_is_exposed_as_spec_warning():
    p = payloads()
    payload = p.SpecValidatedPayload.model_validate(
        kwargs_for(
            "SpecValidatedPayload",
            warnings=[{"check": "c", "subject": "REQ-A-001", "message": "m"}],
        )
    )
    warning = payload.warnings[0]
    assert isinstance(warning, p.SpecWarning)
    assert (warning.check, warning.subject, warning.message) == ("c", "REQ-A-001", "m")


@pytest.mark.parametrize("missing", ["spec_version", "hash", "violations", "warnings"])
def test_ac3_spec_validated_requires_every_field(missing):
    data = kwargs_for("SpecValidatedPayload")
    del data[missing]
    with pytest.raises(ValidationError):
        payloads().SpecValidatedPayload.model_validate(data)


# ---------------------------------------------------------------- AC4


def test_ac4_spec_approved_has_exactly_two_fields_and_validates():
    cls = payloads().SpecApprovedPayload
    assert set(cls.model_fields) == {"spec_version", "hash"}
    payload = cls.model_validate({"spec_version": "sv_02", "hash": HASH})
    assert (payload.spec_version, payload.hash) == ("sv_02", HASH)


@pytest.mark.parametrize("missing", ["spec_version", "hash"])
def test_ac4_spec_approved_requires_both_fields(missing):
    data = kwargs_for("SpecApprovedPayload")
    del data[missing]
    with pytest.raises(ValidationError):
        payloads().SpecApprovedPayload.model_validate(data)


# ---------------------------------------------------------------- AC5


@pytest.mark.parametrize(
    "name, extra",
    [
        ("SpecImportedPayload", {"approved_by": "human"}),
        ("SpecValidatedPayload", {"violation": []}),
        ("SpecApprovedPayload", {"approved_by": "human"}),
    ],
)
def test_ac5_payload_models_forbid_unknown_fields(name, extra):
    with pytest.raises(ValidationError):
        getattr(payloads(), name).model_validate(kwargs_for(name, **extra))


@pytest.mark.parametrize(
    "name, data",
    [
        ("RecordedViolation", {"rule": "r", "subject": "s", "message": "m"}),
        ("SpecWarning", {"check": "c", "subject": "s", "message": "m"}),
    ],
)
def test_ac5_entry_models_forbid_unknown_fields(name, data):
    cls = getattr(payloads(), name)
    cls.model_validate(data)
    with pytest.raises(ValidationError):
        cls.model_validate({**data, "extra": "x"})


@pytest.mark.parametrize("name", MODEL_NAMES)
@pytest.mark.parametrize("version", ["sv_01", "sv_12", "sv_100"])
def test_ac5_spec_version_accepts_two_or_more_digits(name, version):
    model = getattr(payloads(), name).model_validate(kwargs_for(name, spec_version=version))
    assert model.spec_version == version


@pytest.mark.parametrize("name", MODEL_NAMES)
@pytest.mark.parametrize("version", ["sv_1", "v_01", "SV_01", ""])
def test_ac5_spec_version_rejects_other_forms(name, version):
    with pytest.raises(ValidationError):
        getattr(payloads(), name).model_validate(kwargs_for(name, spec_version=version))


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_ac5_hash_accepts_content_hash_of_a_spec_set(name):
    h = content_hash(example_spec())
    assert getattr(payloads(), name).model_validate(kwargs_for(name, hash=h)).hash == h


@pytest.mark.parametrize("name", MODEL_NAMES)
@pytest.mark.parametrize(
    "bad",
    ["a" * 63, "A" + "a" * 63, "g" + "a" * 63],
    ids=["too-short", "uppercase", "non-hex"],
)
def test_ac5_hash_rejects_bad_forms(name, bad):
    with pytest.raises(ValidationError):
        getattr(payloads(), name).model_validate(kwargs_for(name, hash=bad))


# ---------------------------------------------------------------- AC6


def _round_trip(model):
    p = payloads()
    event_type = EVENT_FOR[type(model).__name__]
    event = Event.new(
        stream="spec", type=event_type, payload=model.model_dump(mode="json"), actor="human"
    )
    stored = Event.model_validate_json(event.model_dump_json())
    return stored, p.PAYLOAD_MODELS[stored.type].model_validate(stored.payload)


def test_ac6_spec_imported_round_trips_and_keeps_the_spec_hash():
    p = payloads()
    spec = example_spec()
    model = p.SpecImportedPayload(spec_version="sv_01", hash=content_hash(spec), spec=spec)
    stored, back = _round_trip(model)
    assert stored.type is EventType.SpecImported
    assert back == model
    assert content_hash(back.spec) == content_hash(spec)


def test_ac6_spec_validated_round_trips_with_violations():
    p = payloads()
    _, recorded = recorded_violations()
    assert recorded
    model = p.SpecValidatedPayload(
        spec_version="sv_01", hash=HASH, violations=recorded, warnings=[]
    )
    stored, back = _round_trip(model)
    assert stored.type is EventType.SpecValidated
    assert back == model


def test_ac6_spec_approved_round_trips():
    model = payloads().SpecApprovedPayload(spec_version="sv_02", hash=HASH)
    stored, back = _round_trip(model)
    assert stored.type is EventType.SpecApproved
    assert back == model
