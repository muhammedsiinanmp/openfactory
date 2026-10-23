"""TASK-092: the classifier reply, its checks and the lost criteria."""

import ast
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from openfactory.domain.classifier import (
    ChangeClass,
    ClassifierRejection,
    ClassifierReply,
    ClassifierRule,
    add_lost_criteria,
    check_classification,
    parse_classifier_reply,
)
from openfactory.domain.plan_checks import rejection_lines
from openfactory.domain.spec_diff import CriterionDiff, RequirementDiff, SpecDiff


def crit(id: str, change: str) -> CriterionDiff:
    return CriterionDiff(id=id, change=change)  # type: ignore[arg-type]


def make_diff() -> SpecDiff:
    return SpecDiff(
        requirements=[
            RequirementDiff(
                id="REQ-AUTH-001",
                change="modified",
                criteria=[
                    crit("AC-AUTH-001-1", "removed"),
                    crit("AC-AUTH-001-2", "modified"),
                    crit("AC-AUTH-001-3", "added"),
                    crit("AC-AUTH-001-4", "unchanged"),
                ],
            ),
            RequirementDiff(id="REQ-AUTH-002", change="unchanged", criteria=[]),
            RequirementDiff(id="REQ-AUTH-003", change="added", criteria=[]),
            RequirementDiff(id="REQ-AUTH-004", change="removed", criteria=[]),
            RequirementDiff(id="REQ-AUTH-005", change="deprecated", criteria=[]),
        ],
        adrs=[],
    )


def entry(
    req_id: str = "REQ-AUTH-001",
    kind: str = "behavioral",
    obsolete: list[str] | None = None,
    work: list[str] | None = None,
) -> ChangeClass:
    return ChangeClass(
        req_id=req_id,
        kind=kind,  # type: ignore[arg-type]
        rationale="r",
        obsolete_criteria=obsolete or [],
        new_work=["w"] if work is None else work,
    )


def raw(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "req_id": "REQ-AUTH-001",
        "kind": "behavioral",
        "rationale": "r",
        "obsolete_criteria": [],
        "new_work": [],
    }
    return base | over


def rules(rejections: list[ClassifierRejection]) -> list[tuple[str, str]]:
    return sorted((r.rule.value, r.subject) for r in rejections)


# AC1


def test_task092_ac1_fields_are_exact_and_required() -> None:
    assert list(ChangeClass.model_fields) == [
        "req_id",
        "kind",
        "rationale",
        "obsolete_criteria",
        "new_work",
    ]
    assert list(ClassifierReply.model_fields) == ["changes"]
    with pytest.raises(ValidationError):
        ChangeClass.model_validate({"req_id": "REQ-AUTH-001"})


def test_task092_ac1_frozen_and_forbid_extra() -> None:
    with pytest.raises(ValidationError):
        ChangeClass.model_validate(raw(extra=1))
    with pytest.raises(ValidationError):
        ClassifierReply.model_validate({"changes": [], "extra": 1})
    with pytest.raises(ValidationError):
        entry().req_id = "x"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        ClassifierReply(changes=[]).changes = []  # type: ignore[misc]


@pytest.mark.parametrize("kind", ["cosmetic", "behavioral", "replacement"])
def test_task092_ac1_kind_accepts_the_three_values(kind: str) -> None:
    assert ChangeClass.model_validate(raw(kind=kind)).kind == kind


def test_task092_ac1_kind_rejects_other_values() -> None:
    with pytest.raises(ValidationError):
        ChangeClass.model_validate(raw(kind="major"))


# AC2


def test_task092_ac2_no_structured_result() -> None:
    parsed = parse_classifier_reply(None)
    assert parsed.changes is None
    assert len(parsed.rejections) == 1
    only = parsed.rejections[0]
    assert (only.rule, only.subject, only.message) == (
        ClassifierRule.SCHEMA,
        "reply",
        "no structured result",
    )


def test_task092_ac2_valid_reply_gives_changes() -> None:
    parsed = parse_classifier_reply({"changes": [raw()]})
    assert parsed.rejections == []
    assert parsed.changes == [ChangeClass.model_validate(raw())]


def test_task092_ac2_error_in_an_entry_uses_its_req_id_and_field_path() -> None:
    parsed = parse_classifier_reply({"changes": [raw(kind="major", rationale=3)]})
    assert parsed.changes is None
    assert len(parsed.rejections) == 2
    for r in parsed.rejections:
        assert r.rule == ClassifierRule.SCHEMA
        assert r.subject == "REQ-AUTH-001"
    messages = sorted(r.message for r in parsed.rejections)
    assert messages[0].startswith("changes.0.kind: ")
    assert messages[1].startswith("changes.0.rationale: ")


@pytest.mark.parametrize(
    "structured",
    [
        {},
        {"changes": "x"},
        {"changes": ["nope"]},
        {"changes": [raw(req_id=7, kind="x")]},
    ],
)
def test_task092_ac2_other_errors_have_subject_reply(structured: object) -> None:
    parsed = parse_classifier_reply(structured)
    assert parsed.changes is None
    assert parsed.rejections
    assert {r.subject for r in parsed.rejections} == {"reply"}
    assert {r.rule for r in parsed.rejections} == {ClassifierRule.SCHEMA}


# AC3


def test_task092_ac3_valid_entries_have_no_rejections() -> None:
    assert check_classification([entry(obsolete=["AC-AUTH-001-1"])], make_diff()) == []
    assert check_classification([], SpecDiff(requirements=[], adrs=[])) == []


@pytest.mark.parametrize(
    "req_id",
    ["REQ-NOPE-001", "REQ-AUTH-002", "REQ-AUTH-003", "REQ-AUTH-004", "REQ-AUTH-005"],
)
def test_task092_ac3_unknown_requirement(req_id: str) -> None:
    got = check_classification([entry(), entry(req_id=req_id)], make_diff())
    assert rules(got) == [("unknown-requirement", req_id)]


def test_task092_ac3_duplicate_requirement_once_per_id() -> None:
    got = check_classification([entry(), entry(), entry()], make_diff())
    assert rules(got) == [("duplicate-requirement", "REQ-AUTH-001")]


def test_task092_ac3_missing_requirement() -> None:
    got = check_classification([], make_diff())
    assert rules(got) == [("missing-requirement", "REQ-AUTH-001")]


# AC4


@pytest.mark.parametrize("unknown", ["AC-AUTH-001-3", "AC-AUTH-001-9"])
def test_task092_ac4_unknown_criterion(unknown: str) -> None:
    got = check_classification([entry(obsolete=[unknown])], make_diff())
    assert rules(got) == [("unknown-criterion", "REQ-AUTH-001")]
    assert unknown in got[0].message


def test_task092_ac4_from_criteria_of_a_requirement_not_modified_are_accepted() -> None:
    """An unchanged requirement's entry naming its real criterion gets only unknown-requirement."""
    diff = SpecDiff(
        requirements=[
            *make_diff().requirements,
            RequirementDiff(
                id="REQ-AUTH-006", change="unchanged", criteria=[crit("AC-AUTH-006-1", "unchanged")]
            ),
        ],
        adrs=[],
    )
    got = check_classification(
        [entry(), entry(req_id="REQ-AUTH-006", obsolete=["AC-AUTH-006-1"])], diff
    )
    assert rules(got) == [("unknown-requirement", "REQ-AUTH-006")]


def test_task092_ac4_known_criteria_are_accepted() -> None:
    ids = ["AC-AUTH-001-1", "AC-AUTH-001-2", "AC-AUTH-001-4"]
    assert check_classification([entry(obsolete=ids)], make_diff()) == []


@pytest.mark.parametrize(
    "bad",
    [
        entry(kind="cosmetic", obsolete=["AC-AUTH-001-2"], work=[]),
        entry(kind="cosmetic", work=["do it"]),
        # the requirement has a removed criterion, so cosmetic is wrong even with no work
        entry(kind="cosmetic", work=[]),
    ],
)
def test_task092_ac4_cosmetic_with_work(bad: ChangeClass) -> None:
    got = check_classification([bad], make_diff())
    assert ("cosmetic-with-work", "REQ-AUTH-001") in rules(got)


def test_task092_ac4_cosmetic_without_work_is_fine_when_nothing_was_lost() -> None:
    diff = SpecDiff(
        requirements=[
            RequirementDiff(
                id="REQ-AUTH-001", change="modified", criteria=[crit("AC-AUTH-001-1", "modified")]
            )
        ],
        adrs=[],
    )
    assert check_classification([entry(kind="cosmetic", work=[])], diff) == []


@pytest.mark.parametrize("kind", ["behavioral", "replacement"])
def test_task092_ac4_work_is_fine_for_other_kinds(kind: str) -> None:
    got = check_classification([entry(kind=kind, obsolete=["AC-AUTH-001-2"])], make_diff())
    assert got == []


# AC5


def test_task092_ac5_one_rejection_per_subject_and_offending_id() -> None:
    twice = entry(obsolete=["AC-AUTH-001-9", "AC-AUTH-001-9"])
    assert rules(check_classification([twice], make_diff())) == [
        ("unknown-criterion", "REQ-AUTH-001")
    ]
    dup = check_classification([twice, entry(obsolete=["AC-AUTH-001-9"])], make_diff())
    assert [r for r in dup if r.rule == ClassifierRule.UNKNOWN_CRITERION].__len__() == 1
    two = check_classification([entry(obsolete=["AC-AUTH-001-8", "AC-AUTH-001-9"])], make_diff())
    assert len(two) == 2
    assert {"AC-AUTH-001-8", "AC-AUTH-001-9"} == {
        i for i in ("AC-AUTH-001-8", "AC-AUTH-001-9") if any(i in r.message for r in two)
    }


def test_task092_ac5_cosmetic_with_work_once_per_req_id() -> None:
    bad = entry(kind="cosmetic", obsolete=["AC-AUTH-001-2"], work=["x"])
    got = check_classification([bad], make_diff())
    assert [r.rule for r in got].count(ClassifierRule.COSMETIC_WITH_WORK) == 1


def test_task092_ac5_messages_name_the_offending_id() -> None:
    for r in check_classification([entry(), entry(req_id="REQ-AUTH-003")], make_diff()):
        assert "REQ-AUTH-003" in r.message
    for r in check_classification([], make_diff()):
        assert "REQ-AUTH-001" in r.message
    dup = check_classification([entry(), entry()], make_diff())
    assert all("REQ-AUTH-001" in r.message for r in dup)


def test_task092_ac5_rejection_lines_print_and_sort_classifier_rejections() -> None:
    rejections = [
        ClassifierRejection(rule=ClassifierRule.UNKNOWN_CRITERION, subject="B", message="m2"),
        ClassifierRejection(rule=ClassifierRule.DUPLICATE_REQUIREMENT, subject="Z", message="m1"),
        ClassifierRejection(rule=ClassifierRule.UNKNOWN_CRITERION, subject="A", message="m3"),
    ]
    assert rejection_lines(rejections) == [
        "duplicate-requirement  Z  m1",
        "unknown-criterion  A  m3",
        "unknown-criterion  B  m2",
    ]


# AC6


def test_task092_ac6_lost_criteria_are_added_sorted_without_duplicates() -> None:
    given = entry(obsolete=["AC-AUTH-001-4", "AC-AUTH-001-1", "AC-AUTH-001-4"])
    [got] = add_lost_criteria([given], make_diff())
    assert got.obsolete_criteria == ["AC-AUTH-001-1", "AC-AUTH-001-4"]
    [empty] = add_lost_criteria([entry()], make_diff())
    assert empty.obsolete_criteria == ["AC-AUTH-001-1"]


def test_task092_ac6_changes_nothing_else_and_does_not_mutate() -> None:
    original = entry(kind="cosmetic", work=[])
    inputs = [original]
    first = add_lost_criteria(inputs, make_diff())
    assert inputs == [entry(kind="cosmetic", work=[])]
    assert original.obsolete_criteria == []
    assert first == add_lost_criteria(inputs, make_diff())
    assert (first[0].req_id, first[0].kind, first[0].rationale, first[0].new_work) == (
        original.req_id,
        original.kind,
        original.rationale,
        original.new_work,
    )


def test_task092_ac6_requirement_without_lost_criteria_is_left_as_given() -> None:
    diff = SpecDiff(
        requirements=[
            RequirementDiff(
                id="REQ-AUTH-001", change="modified", criteria=[crit("AC-AUTH-001-1", "unchanged")]
            )
        ],
        adrs=[],
    )
    given = entry(obsolete=["AC-AUTH-001-1"])
    assert add_lost_criteria([given], diff) == [given]


def test_task092_ac6_module_imports_only_domain() -> None:
    source = Path(__file__).resolve().parents[2] / "src/openfactory/domain/classifier.py"
    imported: list[str] = []
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(a.name for a in node.names)
    own = [m for m in imported if m == "openfactory" or m.startswith("openfactory.")]
    assert all(m.startswith("openfactory.domain") for m in own), own
