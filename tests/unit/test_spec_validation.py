"""TASK-003: spec domain models and deterministic validation rules.

Each test names the acceptance criterion it covers (AC1..AC6 in
docs/tasks/TASK-003-spec-models-validation.md).
"""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from openfactory.domain.models import AcceptanceCriterion, Adr, Requirement, SpecSet
from openfactory.domain.spec_validation import SpecViolation, validate_spec

DOMAIN_DIR = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "domain"

EXAMPLE = {
    "components": ["auth"],
    "requirements": [
        {
            "id": "REQ-AUTH-001",
            "title": "Login with membership number",
            "statement": "Users authenticate using their membership number and password.",
            "priority": "must",
            "constrained_by": ["ADR-001"],
            "acceptance_criteria": [
                {
                    "id": "AC-AUTH-001-1",
                    "text": "Valid membership number and password returns a JWT.",
                },
                {"id": "AC-AUTH-001-2", "text": "Unknown membership number returns 401."},
            ],
        }
    ],
    "adrs": [{"id": "ADR-001", "status": "accepted"}],
}


def req(id="REQ-AUTH-001", **kw):
    data = {
        "id": id,
        "title": "t",
        "statement": "s",
        "priority": "must",
        "acceptance_criteria": [{"id": "AC-AUTH-001-1", "text": "x"}],
    }
    data.update(kw)
    return data


def spec(requirements=None, adrs=None, components=("auth",)):
    return SpecSet.model_validate(
        {
            "components": list(components),
            "requirements": [req()] if requirements is None else requirements,
            "adrs": [] if adrs is None else adrs,
        }
    )


def hits(spec_set, rule):
    return [v for v in validate_spec(spec_set) if v.rule == rule]


def subjects(spec_set, rule):
    return [v.subject for v in hits(spec_set, rule)]


# AC1


def test_ac1_example_spec_parses_and_validates_clean():
    s = SpecSet.model_validate(EXAMPLE)
    assert s.components == ["auth"]
    r = s.requirements[0]
    assert isinstance(r, Requirement)
    assert (r.id, r.title, r.priority, r.constrained_by) == (
        "REQ-AUTH-001",
        "Login with membership number",
        "must",
        ["ADR-001"],
    )
    assert r.components == []
    assert isinstance(r.acceptance_criteria[0], AcceptanceCriterion)
    assert r.acceptance_criteria[1].id == "AC-AUTH-001-2"
    assert isinstance(s.adrs[0], Adr)
    assert validate_spec(s) == []


def test_ac1_optional_lists_default_to_empty():
    r = Requirement.model_validate(
        {"id": "REQ-AUTH-001", "title": "t", "statement": "s", "priority": "must"}
    )
    assert r.constrained_by == []
    assert r.components == []
    assert r.acceptance_criteria == []


@pytest.mark.parametrize("priority", ["must", "should", "could"])
def test_ac1_priority_accepts_closed_set(priority):
    assert Requirement.model_validate(req(priority=priority)).priority == priority


def test_ac1_priority_outside_set_raises():
    with pytest.raises(ValidationError):
        Requirement.model_validate(req(priority="urgent"))


@pytest.mark.parametrize("status", ["proposed", "accepted", "superseded"])
def test_ac1_adr_status_accepts_closed_set(status):
    assert Adr.model_validate({"id": "ADR-001", "status": status}).status == status


def test_ac1_adr_status_outside_set_raises():
    with pytest.raises(ValidationError):
        Adr.model_validate({"id": "ADR-001", "status": "rejected"})


@pytest.mark.parametrize("module", ["models.py", "spec_validation.py"])
def test_ac1_domain_modules_import_no_outer_layers(module):
    tree = ast.parse((DOMAIN_DIR / module).read_text())
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    for forbidden in ("adapters", "app", "ports"):
        assert not any(m.startswith(f"openfactory.{forbidden}") for m in imported)


# AC2


@pytest.mark.parametrize("bad", ["REQ-auth-001", "REQ-AUTH-1", "AUTH-001", "REQ-AUTH-0011"])
def test_ac2_bad_requirement_id(bad):
    s = spec([req(id=bad)])
    assert bad in subjects(s, "id-format")


def test_ac2_bad_adr_id():
    s = spec(adrs=[{"id": "ADR-1", "status": "accepted"}])
    assert subjects(s, "id-format") == ["ADR-1"]


@pytest.mark.parametrize("bad", ["AUTH-001-1", "AC-AUTH-001", "AC-auth-001-1", "AC-AUTH-1-1"])
def test_ac2_bad_criterion_id(bad):
    s = spec([req(acceptance_criteria=[{"id": bad, "text": "x"}])])
    assert subjects(s, "id-format") == [bad]


def test_ac2_valid_ids_give_no_id_format_violation():
    s = spec(
        [
            req(
                acceptance_criteria=[
                    {"id": "AC-AUTH-001-1", "text": "x"},
                    {"id": "AC-AUTH-001-12", "text": "y"},
                ]
            )
        ],
        adrs=[{"id": "ADR-001", "status": "accepted"}],
    )
    assert hits(s, "id-format") == []


# AC3


def test_ac3_duplicate_requirement_id():
    s = spec([req(), req()])
    assert "REQ-AUTH-001" in subjects(s, "id-unique")


def test_ac3_duplicate_adr_id():
    s = spec(
        adrs=[{"id": "ADR-001", "status": "accepted"}, {"id": "ADR-001", "status": "proposed"}]
    )
    assert subjects(s, "id-unique") == ["ADR-001"]


def test_ac3_duplicate_criterion_id_in_same_requirement():
    ac = {"id": "AC-AUTH-001-1", "text": "x"}
    s = spec([req(acceptance_criteria=[ac, ac])])
    assert subjects(s, "id-unique") == ["AC-AUTH-001-1"]


def test_ac3_duplicate_criterion_id_across_requirements():
    ac = {"id": "AC-AUTH-001-1", "text": "x"}
    s = spec([req(acceptance_criteria=[ac]), req(id="REQ-AUTH-002", acceptance_criteria=[ac])])
    assert subjects(s, "id-unique") == ["AC-AUTH-001-1"]


# AC4


@pytest.mark.parametrize("omit", [True, False])
def test_ac4_no_acceptance_criteria(omit):
    data = req()
    if omit:
        del data["acceptance_criteria"]
    else:
        data["acceptance_criteria"] = []
    s = spec([data])
    assert subjects(s, "missing-acceptance-criteria") == ["REQ-AUTH-001"]


def test_ac4_requirement_with_criteria_not_flagged():
    assert hits(spec(), "missing-acceptance-criteria") == []


# AC5


def test_ac5_unknown_adr():
    s = spec([req(constrained_by=["ADR-009"])], adrs=[{"id": "ADR-001", "status": "accepted"}])
    assert subjects(s, "constrained-by") == ["REQ-AUTH-001"]


@pytest.mark.parametrize("status", ["proposed", "superseded"])
def test_ac5_non_accepted_adr(status):
    s = spec([req(constrained_by=["ADR-001"])], adrs=[{"id": "ADR-001", "status": status}])
    assert subjects(s, "constrained-by") == ["REQ-AUTH-001"]


def test_ac5_accepted_adr_and_empty_constrained_by_are_fine():
    s = spec(
        [
            req(constrained_by=["ADR-001"]),
            req(id="REQ-AUTH-002", acceptance_criteria=[{"id": "AC-AUTH-002-1", "text": "x"}]),
        ],
        adrs=[{"id": "ADR-001", "status": "accepted"}],
    )
    assert hits(s, "constrained-by") == []


# AC6


def test_ac6_undeclared_component():
    s = spec([req(components=["auth", "billing"])])
    assert subjects(s, "undeclared-component") == ["REQ-AUTH-001"]


def test_ac6_declared_component_is_fine():
    assert hits(spec([req(components=["auth"])]), "undeclared-component") == []


def test_ac6_violations_have_rule_subject_and_message():
    s = spec([req(id="bad", components=["nope"], acceptance_criteria=[])])
    violations = validate_spec(s)
    assert violations
    for v in violations:
        assert isinstance(v, SpecViolation)
        assert v.rule and v.subject
        assert isinstance(v.message, str) and v.message


def test_ac6_all_violations_in_one_run_and_deterministic():
    s = spec(
        [
            req(id="REQ-auth-001", components=["nope"], constrained_by=["ADR-009"]),
            req(id="REQ-AUTH-002", acceptance_criteria=[]),
            req(id="REQ-AUTH-002", acceptance_criteria=[]),
        ],
        adrs=[{"id": "ADR-1", "status": "accepted"}],
    )
    first = validate_spec(s)
    assert {v.rule for v in first} == {
        "id-format",
        "id-unique",
        "missing-acceptance-criteria",
        "constrained-by",
        "undeclared-component",
    }
    assert validate_spec(s) == first
