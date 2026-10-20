"""TASK-069: ReviewVerdict, parse_review_reply and review_file_text (AC1, AC2, AC3, AC6)."""

import pytest
from pydantic import ValidationError

from openfactory.domain.plan_checks import PlanRule, rejection_lines
from openfactory.domain.review import ReviewVerdict, parse_review_reply, review_file_text


def test_ac1_review_verdict_has_exactly_two_required_fields() -> None:
    assert set(ReviewVerdict.model_fields) == {"verdict", "comments"}
    assert all(f.is_required() for f in ReviewVerdict.model_fields.values())
    assert ReviewVerdict(verdict="approve", comments="ok").verdict == "approve"


@pytest.mark.parametrize(
    "data",
    [
        {"verdict": "approve", "comments": "ok", "extra": 1},
        {"verdict": "maybe", "comments": "ok"},
        {"verdict": "approve"},
        {"comments": "ok"},
    ],
)
def test_ac1_extra_key_bad_verdict_or_missing_field_is_rejected(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ReviewVerdict.model_validate(data)


def test_ac2_missing_structured_result() -> None:
    parsed = parse_review_reply(None)
    assert parsed.verdict is None
    assert rejection_lines(parsed.rejections) == ["schema  reply  no structured result"]


def test_ac2_invalid_result_gives_one_schema_rejection_per_error_with_field_path() -> None:
    parsed = parse_review_reply({"verdict": "approve", "comments": "ok", "extra": 1})
    assert parsed.verdict is None
    assert len(parsed.rejections) == 1
    rejection = parsed.rejections[0]
    assert rejection.rule is PlanRule.schema
    assert rejection.subject == "reply"
    assert rejection.message.startswith("extra: ")


def test_ac2_error_without_field_path_has_only_the_message() -> None:
    parsed = parse_review_reply("not an object")
    assert parsed.verdict is None
    assert len(parsed.rejections) == 1
    assert parsed.rejections[0].subject == "reply"
    assert not parsed.rejections[0].message.startswith(": ")
    assert ": " not in parsed.rejections[0].message.split(" ")[0]


def test_ac2_valid_result_gives_verdict_and_no_rejections() -> None:
    parsed = parse_review_reply({"verdict": "reject", "comments": "missing test"})
    assert parsed.verdict == ReviewVerdict(verdict="reject", comments="missing test")
    assert parsed.rejections == []


def test_ac3_several_errors_are_sorted_as_strings() -> None:
    parsed = parse_review_reply({"verdict": "maybe"})
    lines = rejection_lines(parsed.rejections)
    assert len(lines) == 2
    assert lines == sorted(lines)
    assert any("comments" in line for line in lines)
    assert any("verdict" in line for line in lines)
    assert all(line.startswith("schema  reply  ") for line in lines)


@pytest.mark.parametrize(
    ("comments", "expected"),
    [
        ("looks good", "verdict: approve\nlooks good\n"),
        ("looks good\n", "verdict: approve\nlooks good\n"),
    ],
)
def test_ac6_file_text_with_verdict(comments: str, expected: str) -> None:
    verdict = ReviewVerdict(verdict="approve", comments=comments)
    assert review_file_text(verdict, None) == expected


def test_ac6_file_text_for_reject() -> None:
    verdict = ReviewVerdict(verdict="reject", comments="no tests")
    assert review_file_text(verdict, None) == "verdict: reject\nno tests\n"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("schema  reply  no structured result", "schema  reply  no structured result\n"),
        ("a\nb\n", "a\nb\n"),
    ],
)
def test_ac6_file_text_without_verdict_is_the_error(error: str, expected: str) -> None:
    assert review_file_text(None, error) == expected
