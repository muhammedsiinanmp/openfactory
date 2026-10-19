"""TASK-062: the pytest tag rule and its `no tagged test in a changed file` lines."""

import pytest

from openfactory.domain.contracts import REQUIRED_GATES, Limits, TaskContract
from openfactory.domain.gates import MarkerLine
from openfactory.domain.tag_rule import tag_rule_lines, uncovered_requirements

TEST_FILE = "tests/test_login.py"


def contract(requirements: list[str]) -> TaskContract:
    return TaskContract(
        task_id="AUTH-002",
        objective="x",
        requirements=requirements,
        acceptance_criteria=["AC-AUTH-001-1"],
        components=["auth"],
        role="implementer",
        allowed_paths=["app/**", "tests/**"],
        required_gates=list(REQUIRED_GATES),
        limits=Limits(max_runtime_s=1, max_attempts=1, max_cost_usd=1),
    )


def marker(file: str, *req: str) -> MarkerLine:
    return MarkerLine(file=file, req=list(req))


def test_requirement_with_a_tagged_test_in_a_changed_file_is_covered() -> None:
    lines = [marker(TEST_FILE, "REQ-A-001")]
    assert uncovered_requirements(lines, [TEST_FILE], contract(["REQ-A-001"])) == []


def test_one_marker_line_with_several_ids_covers_each_of_them() -> None:
    lines = [marker(TEST_FILE, "REQ-A-001", "REQ-A-002")]
    result = uncovered_requirements(lines, [TEST_FILE], contract(["REQ-A-001", "REQ-A-002"]))
    assert result == []


def test_marker_lines_for_ids_outside_the_contract_change_nothing() -> None:
    lines = [marker(TEST_FILE, "REQ-Z-009")]
    result = uncovered_requirements(lines, [TEST_FILE], contract(["REQ-A-001"]))
    assert result == ["REQ-A-001"]


@pytest.mark.parametrize(
    ("lines", "changed"),
    [
        pytest.param([marker("tests/test_old.py", "REQ-A-001")], [TEST_FILE], id="unchanged-file"),
        pytest.param(
            [marker(TEST_FILE), marker(TEST_FILE, "REQ-B-002")], [TEST_FILE], id="no-marker"
        ),
        pytest.param([], [TEST_FILE], id="no-marker-lines"),
    ],
)
def test_requirement_is_uncovered(lines: list[MarkerLine], changed: list[str]) -> None:
    assert uncovered_requirements(lines, changed, contract(["REQ-A-001"])) == ["REQ-A-001"]


def test_only_the_uncovered_requirement_is_returned() -> None:
    lines = [marker(TEST_FILE, "REQ-A-001")]
    result = uncovered_requirements(lines, [TEST_FILE], contract(["REQ-A-001", "REQ-B-002"]))
    assert result == ["REQ-B-002"]


def test_with_no_marker_lines_every_requirement_is_uncovered() -> None:
    ids = ["REQ-A-001", "REQ-B-002", "REQ-C-003"]
    assert uncovered_requirements([], [TEST_FILE], contract(ids)) == ids


def test_result_is_in_contract_order_with_each_id_once() -> None:
    ids = ["REQ-B-002", "REQ-A-001", "REQ-B-002"]
    assert uncovered_requirements([], [], contract(ids)) == ["REQ-B-002", "REQ-A-001"]


def test_inputs_are_not_changed() -> None:
    lines = [marker(TEST_FILE, "REQ-A-001")]
    changed = [TEST_FILE]
    the_contract = contract(["REQ-A-001", "REQ-B-002", "REQ-B-002"])
    uncovered_requirements(lines, changed, the_contract)
    assert lines == [marker(TEST_FILE, "REQ-A-001")]
    assert changed == [TEST_FILE]
    assert the_contract.requirements == ["REQ-A-001", "REQ-B-002", "REQ-B-002"]


def test_tag_rule_lines_gives_one_line_per_id_in_order() -> None:
    assert tag_rule_lines(["REQ-A-001", "REQ-B-002"]) == [
        "no tagged test in a changed file: REQ-A-001",
        "no tagged test in a changed file: REQ-B-002",
    ]


def test_tag_rule_lines_gives_nothing_for_no_ids() -> None:
    assert tag_rule_lines([]) == []
