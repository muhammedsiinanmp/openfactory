"""TASK-031: `rejection_lines`, AC4 of the task record."""

from openfactory.domain.plan_checks import PlanRejection, PlanRule, rejection_lines


def rej(rule: PlanRule, subject: str, message: str) -> PlanRejection:
    return PlanRejection(rule=rule, subject=subject, message=message)


def test_ac4_one_schema_rejection_is_one_line_with_two_space_separators() -> None:
    lines = rejection_lines([rej(PlanRule.schema, "reply", "no structured result")])
    assert lines == ["schema  reply  no structured result"]


def test_ac4_lines_sorted_by_rule_then_subject_then_message() -> None:
    given = [
        rej(PlanRule.uncovered, "REQ-AUTH-001", "no task covers it"),
        rej(PlanRule.cycle, "AUTH-002", "in a cycle"),
        rej(PlanRule.cycle, "AUTH-001", "in a cycle"),
        rej(PlanRule.cycle, "AUTH-001", "a cycle, earlier message"),
    ]
    assert rejection_lines(given) == [
        "cycle  AUTH-001  a cycle, earlier message",
        "cycle  AUTH-001  in a cycle",
        "cycle  AUTH-002  in a cycle",
        "uncovered  REQ-AUTH-001  no task covers it",
    ]


def test_ac4_empty_gives_empty_and_input_is_unchanged() -> None:
    assert rejection_lines([]) == []
    given = [
        rej(PlanRule.uncovered, "REQ-AUTH-001", "m"),
        rej(PlanRule.cycle, "AUTH-001", "m"),
    ]
    before = list(given)
    rejection_lines(given)
    assert given == before
