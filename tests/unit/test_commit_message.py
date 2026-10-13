"""TASK-051: the commit message of a passed task.

Each test names the acceptance criterion it covers (AC1..AC6 in
docs/tasks/TASK-051-commit-message.md; AC5 is in test_spec_conformance.py).
"""

import ast
from pathlib import Path

import pytest

from openfactory.domain import commit_message
from openfactory.domain.commit_message import build_commit_message
from openfactory.domain.contracts import REQUIRED_GATES, Limits, TaskContract

OBJECTIVE = "Implement login endpoint using membership number"
SUMMARY = "Added the login endpoint.\n\nTests cover both paths."
TRAILERS = (
    "Task: AUTH-002\n"
    "Requirements: REQ-AUTH-002, REQ-AUTH-001\n"
    "Acceptance-Criteria: AC-AUTH-002-1, AC-AUTH-001-2, AC-AUTH-001-1\n"
    "Agent-Run: run_0091\n"
    "Spec-Version: sv_01"
)


def sample_contract(
    objective: str = OBJECTIVE,
    requirements: list[str] | None = None,
) -> TaskContract:
    return TaskContract(
        task_id="AUTH-002",
        objective=objective,
        requirements=requirements or ["REQ-AUTH-002", "REQ-AUTH-001"],
        acceptance_criteria=["AC-AUTH-002-1", "AC-AUTH-001-2", "AC-AUTH-001-1"],
        depends_on=["AUTH-001"],
        components=["auth"],
        role="implementer",
        allowed_paths=["app/auth/**"],
        required_gates=list(REQUIRED_GATES),
        limits=Limits(max_runtime_s=600, max_attempts=3, max_cost_usd=2.0),
    )


def message(summary: str = SUMMARY, contract: TaskContract | None = None) -> str:
    return build_commit_message(contract or sample_contract(), summary, "run_0091", "sv_01")


def last_paragraph(text: str) -> str:
    return text.rstrip("\n").split("\n\n")[-1]


def test_ac1_subject_is_task_id_and_objective_then_an_empty_line() -> None:
    lines = message().split("\n")
    assert lines[0] == f"AUTH-002: {OBJECTIVE}"
    assert lines[1] == ""


def test_ac1_subject_is_cut_to_72_characters_counting_the_task_id() -> None:
    first = message(contract=sample_contract(objective="x" * 100)).split("\n")[0]
    assert first == ("AUTH-002: " + "x" * 100)[:72]
    assert len(first) == 72


def test_ac1_subject_of_exactly_72_characters_is_unchanged() -> None:
    objective = "y" * (72 - len("AUTH-002: "))
    first = message(contract=sample_contract(objective=objective)).split("\n")[0]
    assert first == f"AUTH-002: {objective}"


def test_ac2_body_is_the_summary_between_subject_and_trailers() -> None:
    expected = f"AUTH-002: {OBJECTIVE}\n\n{SUMMARY}\n\n{TRAILERS}\n"
    assert message() == expected


def test_ac2_summary_whitespace_around_the_text_is_removed() -> None:
    assert message("\n  Added it.\n\n") == message("Added it.")


def test_ac3_last_paragraph_is_the_five_trailers_in_order() -> None:
    assert last_paragraph(message()) == TRAILERS


def test_ac3_one_requirement_has_no_comma() -> None:
    text = message(contract=sample_contract(requirements=["REQ-AUTH-001"]))
    assert "Requirements: REQ-AUTH-001\n" in text


def test_ac3_summary_with_trailer_like_last_paragraph_does_not_change_trailers() -> None:
    assert last_paragraph(message("Done.\n\nTask: OTHER-001")) == TRAILERS


@pytest.mark.parametrize("summary", ["", " \n"])
def test_ac4_empty_summary_gives_subject_one_empty_line_and_trailers(summary: str) -> None:
    text = message(summary)
    assert text == f"AUTH-002: {OBJECTIVE}\n\n{TRAILERS}\n"
    assert "\n\n\n" not in text


def test_ac6_result_is_text_and_the_same_for_equal_arguments() -> None:
    first, second = message(), message()
    assert isinstance(first, str)
    assert first == second


def test_ac6_module_imports_only_domain_and_standard_library() -> None:
    tree = ast.parse(Path(commit_message.__file__).read_text())
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
    for name in modules:
        if name.startswith("openfactory"):
            assert name.startswith("openfactory.domain")
