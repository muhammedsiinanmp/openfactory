"""TASK-091: structural diff of two spec sets."""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from openfactory.domain.models import (
    AcceptanceCriterion,
    Adr,
    AdrStatus,
    Priority,
    Requirement,
    SpecSet,
)
from openfactory.domain.spec_diff import (
    AdrDiff,
    CriterionDiff,
    RequirementDiff,
    SpecDiff,
    diff_specs,
)


def crit(n: int, text: str = "text") -> AcceptanceCriterion:
    return AcceptanceCriterion(id=f"AC-AUTH-001-{n}", text=text)


def req(rid: str = "REQ-AUTH-001", **kw) -> Requirement:
    fields = {
        "id": rid,
        "title": "Login",
        "statement": "Users log in.",
        "priority": Priority.must,
        "acceptance_criteria": [crit(1)],
    }
    fields.update(kw)
    return Requirement(**fields)


def adr(aid: str = "ADR-001", status=AdrStatus.accepted, body: str = "body") -> Adr:
    return Adr(id=aid, status=status, body=body)


def spec(reqs=(), adrs=()) -> SpecSet:
    return SpecSet(requirements=list(reqs), adrs=list(adrs))


def req_change(diff: SpecDiff, rid: str = "REQ-AUTH-001") -> str:
    return next(r.change for r in diff.requirements if r.id == rid)


def req_diff(diff: SpecDiff, rid: str = "REQ-AUTH-001") -> RequirementDiff:
    return next(r for r in diff.requirements if r.id == rid)


# AC1


def test_task091_ac1_added_removed_unchanged():
    old = spec([req("REQ-AUTH-001"), req("REQ-AUTH-002")])
    new = spec([req("REQ-AUTH-001"), req("REQ-AUTH-003")])
    d = diff_specs(old, new)
    assert [(r.id, r.change) for r in d.requirements] == [
        ("REQ-AUTH-001", "unchanged"),
        ("REQ-AUTH-002", "removed"),
        ("REQ-AUTH-003", "added"),
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"title": "Other"},
        {"statement": "Other."},
        {"priority": Priority.should},
        {"acceptance_criteria": [crit(1, "changed")]},
        {"constrained_by": ["ADR-001"]},
        {"components": ["api"]},
    ],
)
def test_task091_ac1_any_field_change_is_modified(change):
    d = diff_specs(spec([req()]), spec([req(**change)]))
    assert req_change(d) == "modified"


def test_task091_ac1_reordering_is_unchanged_and_output_sorted():
    a, b = req("REQ-AUTH-002"), req("REQ-AUTH-001")
    d = diff_specs(spec([b, a]), spec([a, b]))
    assert [(r.id, r.change) for r in d.requirements] == [
        ("REQ-AUTH-001", "unchanged"),
        ("REQ-AUTH-002", "unchanged"),
    ]


# AC2


def test_task091_ac2_adr_changes():
    old = spec(adrs=[adr("ADR-001"), adr("ADR-002"), adr("ADR-003"), adr("ADR-004")])
    new = spec(
        adrs=[
            adr("ADR-001"),
            adr("ADR-002", status=AdrStatus.superseded),
            adr("ADR-003", body="new body"),
            adr("ADR-005"),
        ]
    )
    d = diff_specs(old, new)
    assert [(a.id, a.change) for a in d.adrs] == [
        ("ADR-001", "unchanged"),
        ("ADR-002", "modified"),
        ("ADR-003", "modified"),
        ("ADR-004", "removed"),
        ("ADR-005", "added"),
    ]


# AC3


def test_task091_ac3_criteria_changes_sorted():
    old = spec([req(acceptance_criteria=[crit(1), crit(2, "old"), crit(3)])])
    new = spec([req(acceptance_criteria=[crit(4), crit(2, "new"), crit(1)])])
    r = req_diff(diff_specs(old, new))
    assert r.change == "modified"
    assert [(c.id, c.change) for c in r.criteria] == [
        ("AC-AUTH-001-1", "unchanged"),
        ("AC-AUTH-001-2", "modified"),
        ("AC-AUTH-001-3", "removed"),
        ("AC-AUTH-001-4", "added"),
    ]


def test_task091_ac3_added_and_removed_requirements_diff_against_empty():
    two = [crit(1), crit(2)]
    only = spec([req(acceptance_criteria=two)])
    added = req_diff(diff_specs(spec(), only))
    removed = req_diff(diff_specs(only, spec()))
    assert [(c.id, c.change) for c in added.criteria] == [
        ("AC-AUTH-001-1", "added"),
        ("AC-AUTH-001-2", "added"),
    ]
    assert [c.change for c in removed.criteria] == ["removed", "removed"]


# AC4


def test_task091_ac4_newly_deprecated_even_with_other_change_and_criteria_diffed():
    old = spec([req(acceptance_criteria=[crit(1), crit(2)])])
    new = spec([req(deprecated=True, title="Other", acceptance_criteria=[crit(1)])])
    r = req_diff(diff_specs(old, new))
    assert r.change == "deprecated"
    assert [(c.id, c.change) for c in r.criteria] == [
        ("AC-AUTH-001-1", "unchanged"),
        ("AC-AUTH-001-2", "removed"),
    ]


def test_task091_ac4_newly_deprecated_with_nothing_else_changed():
    d = diff_specs(spec([req()]), spec([req(deprecated=True)]))
    assert req_change(d) == "deprecated"


def test_task091_ac4_deprecated_in_both_is_unchanged():
    d = diff_specs(spec([req(deprecated=True)]), spec([req(deprecated=True)]))
    assert req_change(d) == "unchanged"


def test_task091_ac4_undeprecated_is_modified():
    d = diff_specs(spec([req(deprecated=True)]), spec([req()]))
    assert req_change(d) == "modified"


def test_task091_ac4_absent_from_old_and_deprecated_in_new_is_deprecated():
    d = diff_specs(spec(), spec([req(deprecated=True)]))
    assert req_change(d) == "deprecated"


# AC5


@pytest.mark.parametrize("which", ["modified", "added", "removed"])
def test_task091_ac5_changed_adr_modifies_constrained_requirement(which):
    r = req(constrained_by=["ADR-001"])
    base = adr("ADR-001")
    old_adrs = [] if which == "added" else [base]
    new_adrs = (
        []
        if which == "removed"
        else [adr("ADR-001", body="changed") if which == "modified" else base]
    )
    d = diff_specs(spec([r], old_adrs), spec([r], new_adrs))
    assert req_change(d) == "modified"
    assert {c.change for c in req_diff(d).criteria} == {"unchanged"}


def test_task091_ac5_unnamed_adr_change_leaves_requirement_unchanged():
    r = req(constrained_by=["ADR-001"])
    old = spec([r], [adr("ADR-001"), adr("ADR-002")])
    new = spec([r], [adr("ADR-001"), adr("ADR-002", body="changed")])
    assert req_change(diff_specs(old, new)) == "unchanged"


def test_task091_ac5_rule_does_not_override_added_removed_deprecated():
    r = req(constrained_by=["ADR-001"])
    rd = req(constrained_by=["ADR-001"], deprecated=True)
    old_adrs = [adr("ADR-001")]
    new_adrs = [adr("ADR-001", body="changed")]
    added = diff_specs(spec([], old_adrs), spec([r], new_adrs))
    removed = diff_specs(spec([r], old_adrs), spec([], new_adrs))
    deprecated = diff_specs(spec([r], old_adrs), spec([rd], new_adrs))
    assert req_change(added) == "added"
    assert req_change(removed) == "removed"
    assert req_change(deprecated) == "deprecated"


# AC6


def test_task091_ac6_imports_only_domain():
    path = Path(__file__).parents[2] / "src/openfactory/domain/spec_diff.py"
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        for n in names:
            if n.split(".")[0] == "openfactory":
                assert n.startswith("openfactory.domain"), n


@pytest.mark.parametrize(
    "model",
    [
        CriterionDiff(id="x", change="added"),
        RequirementDiff(id="x", change="added", criteria=[]),
        AdrDiff(id="x", change="added"),
        SpecDiff(requirements=[], adrs=[]),
    ],
)
def test_task091_ac6_models_frozen_and_forbid_extra(model):
    with pytest.raises(ValidationError):
        setattr(model, "id" if hasattr(model, "id") else "adrs", None)
    with pytest.raises(ValidationError):
        type(model).model_validate({**model.model_dump(), "bogus": 1})


def test_task091_ac6_deterministic_and_inputs_untouched():
    old = spec([req(), req("REQ-AUTH-002")], [adr()])
    new = spec([req(title="x"), req("REQ-AUTH-003")], [adr(body="y")])
    old_before, new_before = old.model_copy(deep=True), new.model_copy(deep=True)
    assert diff_specs(old, new) == diff_specs(old, new)
    assert old == old_before
    assert new == new_before
