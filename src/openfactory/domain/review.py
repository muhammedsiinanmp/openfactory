"""The reviewer's reply: `ReviewVerdict`, its `schema` rejections and the review gate's file.

Implements "The review gate" under "Gates and remediation" in docs/spec/phase1-spec.md. A
reviewer reply is parsed as a planner reply is: `None` is a missing structured result, and
each Pydantic error is one `schema` rejection with subject `reply`, printed by
`plan_checks.rejection_lines`.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from openfactory.domain.plan_checks import PlanRejection, PlanRule


class ReviewVerdict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: Literal["approve", "reject"]
    comments: str


class ParsedReview(BaseModel):
    """A reviewer reply after the `schema` rule: the verdict, or the rejections and none."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: ReviewVerdict | None
    rejections: list[PlanRejection]


def parse_review_reply(structured: object | None) -> ParsedReview:
    """Load a reviewer's structured result, or return its `schema` rejections."""
    if structured is None:
        return ParsedReview(
            verdict=None,
            rejections=[
                PlanRejection(rule=PlanRule.schema, subject="reply", message="no structured result")
            ],
        )
    try:
        verdict = ReviewVerdict.model_validate(structured)
    except ValidationError as error:
        rejections: list[PlanRejection] = []
        for detail in error.errors():
            field_path = ".".join(str(part) for part in detail["loc"])
            rejections.append(
                PlanRejection(
                    rule=PlanRule.schema,
                    subject="reply",
                    message=f"{field_path}: {detail['msg']}" if field_path else detail["msg"],
                )
            )
        return ParsedReview(verdict=None, rejections=rejections)
    return ParsedReview(verdict=verdict, rejections=[])


def _line_ended(text: str) -> str:
    return text if text.endswith("\n") else text + "\n"


def review_file_text(verdict: ReviewVerdict | None, error: str | None) -> str:
    """`verdict: <word>` then the comments; with no verdict, the run's `error`.

    The text ends in a line break, added when the comments or the error lack one.
    """
    if verdict is not None:
        return f"verdict: {verdict.verdict}\n{_line_ended(verdict.comments)}"
    return _line_ended(error or "")
