"""TASK-028: the `schema` plan rule (parse_reply and PlannerReply).

Each test names the acceptance criterion it covers (AC1..AC5 in
docs/tasks/TASK-028-plan-reply-schema-rule.md).
"""

import importlib
from typing import Any

import pytest

from openfactory.domain.contracts import PlannedTask


def planned_example(**kw: Any) -> dict[str, Any]:
    return {
        "task_id": "AUTH-002",
        "objective": "Implement login endpoint using membership number",
        "requirements": ["REQ-AUTH-001", "REQ-AUTH-002"],
        "acceptance_criteria": ["AC-AUTH-001-2", "AC-AUTH-001-1"],
        "depends_on": ["AUTH-001"],
        "components": ["auth"],
        "role": "implementer",
        "allowed_paths": ["tests/auth/**", "app/auth/**"],
        "forbidden_paths": [],
        **kw,
    }


def second(**kw: Any) -> dict[str, Any]:
    return planned_example(task_id="AUTH-003", **kw)


def without(task: dict[str, Any], key: str) -> dict[str, Any]:
    return {k: v for k, v in task.items() if k != key}


def parse(structured: object | None) -> Any:
    # Imported lazily so the failure is the missing function, not the import.
    return importlib.import_module("openfactory.domain.plan_checks").parse_reply(structured)


def test_ac1_valid_reply_gives_the_tasks_in_order() -> None:
    first, other = planned_example(), second()
    parsed = parse({"tasks": [first, other]})
    assert parsed.rejections == []
    assert parsed.tasks == [PlannedTask.model_validate(first), PlannedTask.model_validate(other)]


def test_ac1_planner_reply_has_exactly_one_field() -> None:
    reply = importlib.import_module("openfactory.domain.contracts").PlannerReply
    assert list(reply.model_fields) == ["tasks"]


def test_ac1_empty_task_list_is_not_a_schema_rejection() -> None:
    parsed = parse({"tasks": []})
    assert parsed.tasks == []
    assert parsed.rejections == []


def test_ac2_missing_field_is_one_rejection_with_path() -> None:
    parsed = parse({"tasks": [planned_example(), without(second(), "objective")]})
    assert len(parsed.rejections) == 1
    rejection = parsed.rejections[0]
    assert (rejection.rule, rejection.subject) == ("schema", "AUTH-003")
    assert "tasks.1.objective" in rejection.message


def test_ac2_two_errors_in_one_task_give_two_rejections() -> None:
    bad = without(planned_example(role="reviewer"), "objective")
    parsed = parse({"tasks": [bad]})
    assert len(parsed.rejections) == 2
    assert {r.subject for r in parsed.rejections} == {"AUTH-002"}
    messages = " ".join(r.message for r in parsed.rejections)
    assert "tasks.0.objective" in messages
    assert "tasks.0.role" in messages


def test_ac2_one_error_in_each_of_two_tasks_uses_each_task_id() -> None:
    parsed = parse(
        {"tasks": [without(planned_example(), "objective"), without(second(), "objective")]}
    )
    assert sorted(r.subject for r in parsed.rejections) == ["AUTH-002", "AUTH-003"]
    assert len(parsed.rejections) == 2


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("required_gates", ["pytest"]),
        ("limits", {"max_runtime_s": 1, "max_attempts": 1, "max_cost_usd": 1.0}),
    ],
)
def test_ac2_orchestrator_fields_in_a_task_are_rejected(key: str, value: object) -> None:
    parsed = parse({"tasks": [planned_example(**{key: value})]})
    assert len(parsed.rejections) == 1
    assert f"tasks.0.{key}" in parsed.rejections[0].message


def test_ac3_string_task_id_rejected_by_the_pattern_is_the_subject() -> None:
    parsed = parse({"tasks": [planned_example(task_id="auth-1")]})
    assert parsed.rejections
    assert {r.subject for r in parsed.rejections} == {"auth-1"}


@pytest.mark.parametrize(
    "task", [planned_example(task_id=7), without(planned_example(), "task_id")]
)
def test_ac3_task_id_that_is_not_a_string_gives_subject_reply(task: dict[str, Any]) -> None:
    parsed = parse({"tasks": [task]})
    assert parsed.rejections
    assert {r.subject for r in parsed.rejections} == {"reply"}


@pytest.mark.parametrize("structured", [{}, {"tasks": "x"}])
def test_ac3_error_outside_any_task_gives_subject_reply(structured: object) -> None:
    parsed = parse(structured)
    assert len(parsed.rejections) == 1
    assert parsed.rejections[0].subject == "reply"
    assert "tasks" in parsed.rejections[0].message


def test_ac4_missing_structured_result_is_one_schema_rejection() -> None:
    parsed = parse(None)
    assert len(parsed.rejections) == 1
    rejection = parsed.rejections[0]
    assert (rejection.rule, rejection.subject) == ("schema", "reply")
    assert rejection.message == "no structured result"


@pytest.mark.parametrize(
    "structured",
    [
        None,
        {},
        {"tasks": "x"},
        {"tasks": [without(planned_example(), "objective")]},
        {"tasks": [planned_example(limits={})]},
        {"tasks": [planned_example(required_gates=[])]},
        {"tasks": [without(planned_example(role="reviewer"), "objective")]},
        {"tasks": [without(planned_example(), "objective"), second(role="reviewer")]},
        {"tasks": [planned_example(task_id="auth-1")]},
        {"tasks": [planned_example(task_id=7)]},
        {"tasks": [without(planned_example(), "task_id")]},
    ],
)
def test_ac5_a_rejected_reply_has_no_tasks_and_only_schema_rules(structured: object) -> None:
    parsed = parse(structured)
    assert parsed.tasks is None
    assert parsed.rejections
    assert {r.rule for r in parsed.rejections} == {"schema"}


def test_ac5_one_invalid_task_rejects_the_whole_reply() -> None:
    parsed = parse({"tasks": [planned_example(), without(second(), "objective")]})
    assert parsed.tasks is None
    assert {r.rule for r in parsed.rejections} == {"schema"}
