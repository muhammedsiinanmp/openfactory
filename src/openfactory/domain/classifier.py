"""The change classifier's reply, its checks and the criteria a requirement lost.

Implements "Step 2: change classification (LLM, validated)" and "Classifier checks" under
"Spec diff and impact analysis" in docs/spec/phase1-spec.md, and ADR-019.
`parse_classifier_reply` is the `schema` rule; `check_classification` runs the five
content rules on entries that already loaded and never returns `schema`. There is one
rejection per rule, subject and offending id, as for the plan checks.
`add_lost_criteria` adds every criterion `to` lost to its requirement's
`obsolete_criteria`, whatever the classifier said.

Everything is read from the `SpecDiff`: the modified requirements are those with change
`modified`, a requirement's `from` criteria are its criteria not `added`, the ones it
lost are those `removed` and the ones it gained are those `added`.
"""

from collections import Counter
from collections.abc import Sequence
from enum import StrEnum
from typing import cast

from pydantic import BaseModel, ConfigDict, ValidationError

from openfactory.domain.payloads import ChangeKind
from openfactory.domain.spec_diff import RequirementDiff, SpecDiff


class ChangeClass(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    req_id: str
    kind: ChangeKind
    rationale: str
    obsolete_criteria: list[str]
    new_work: list[str]


class ClassifierReply(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    changes: list[ChangeClass]


class ClassifierRule(StrEnum):
    SCHEMA = "schema"
    UNKNOWN_REQUIREMENT = "unknown-requirement"
    DUPLICATE_REQUIREMENT = "duplicate-requirement"
    MISSING_REQUIREMENT = "missing-requirement"
    UNKNOWN_CRITERION = "unknown-criterion"
    COSMETIC_WITH_WORK = "cosmetic-with-work"


class ClassifierRejection(BaseModel):
    """One broken rule; `subject` is the requirement id it concerns, or `reply`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule: ClassifierRule
    subject: str
    message: str


class ParsedClassification(BaseModel):
    """A classifier reply after the `schema` rule: the entries, or the rejections and none."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    changes: list[ChangeClass] | None
    rejections: list[ClassifierRejection]


def _schema_subject(structured: object, loc: tuple[int | str, ...]) -> str:
    """The `req_id` of the entry the error lies in when that value is a string, else `reply`."""
    if isinstance(structured, dict) and len(loc) >= 2 and loc[0] == "changes":
        changes = cast("dict[object, object]", structured).get("changes")
        index = loc[1]
        if isinstance(changes, list) and isinstance(index, int):
            items = cast("list[object]", changes)
            if index < len(items) and isinstance(change := items[index], dict):
                req_id = cast("dict[object, object]", change).get("req_id")
                if isinstance(req_id, str):
                    return req_id
    return "reply"


def parse_classifier_reply(structured: object | None) -> ParsedClassification:
    """Load a classifier's structured result, or return its `schema` rejections.

    `None` is a missing structured result. There is one rejection per Pydantic error, with
    the field path in its message.
    """
    if structured is None:
        return ParsedClassification(
            changes=None,
            rejections=[
                ClassifierRejection(
                    rule=ClassifierRule.SCHEMA, subject="reply", message="no structured result"
                )
            ],
        )
    try:
        reply = ClassifierReply.model_validate(structured)
    except ValidationError as error:
        rejections: list[ClassifierRejection] = []
        for detail in error.errors():
            loc = detail["loc"]
            field_path = ".".join(str(part) for part in loc)
            rejections.append(
                ClassifierRejection(
                    rule=ClassifierRule.SCHEMA,
                    subject=_schema_subject(structured, loc),
                    message=f"{field_path}: {detail['msg']}" if field_path else detail["msg"],
                )
            )
        return ParsedClassification(changes=None, rejections=rejections)
    return ParsedClassification(changes=list(reply.changes), rejections=[])


def _modified(diff: SpecDiff) -> dict[str, RequirementDiff]:
    return {r.id: r for r in diff.requirements if r.change == "modified"}


def _lost(requirement: RequirementDiff) -> list[str]:
    return [c.id for c in requirement.criteria if c.change == "removed"]


def _gained(requirement: RequirementDiff) -> list[str]:
    return [c.id for c in requirement.criteria if c.change == "added"]


def _unknown_requirement(
    changes: Sequence[ChangeClass], modified: dict[str, RequirementDiff]
) -> list[ClassifierRejection]:
    return [
        ClassifierRejection(
            rule=ClassifierRule.UNKNOWN_REQUIREMENT,
            subject=req_id,
            message=f"entry {req_id!r} is not a modified requirement",
        )
        for req_id in dict.fromkeys(c.req_id for c in changes)
        if req_id not in modified
    ]


def _duplicate_requirement(changes: Sequence[ChangeClass]) -> list[ClassifierRejection]:
    counts = Counter(c.req_id for c in changes)
    return [
        ClassifierRejection(
            rule=ClassifierRule.DUPLICATE_REQUIREMENT,
            subject=req_id,
            message=f"requirement {req_id!r} has {count} entries",
        )
        for req_id, count in counts.items()
        if count > 1
    ]


def _missing_requirement(
    changes: Sequence[ChangeClass], modified: dict[str, RequirementDiff]
) -> list[ClassifierRejection]:
    classified = {c.req_id for c in changes}
    return [
        ClassifierRejection(
            rule=ClassifierRule.MISSING_REQUIREMENT,
            subject=req_id,
            message=f"modified requirement {req_id!r} has no entry",
        )
        for req_id in modified
        if req_id not in classified
    ]


def _unknown_criterion(changes: Sequence[ChangeClass], diff: SpecDiff) -> list[ClassifierRejection]:
    # Read against every requirement of the diff, not only the modified ones: an entry for
    # an unchanged or removed requirement may name a real `from` criterion of it.
    requirements = {r.id: r for r in diff.requirements}
    offending: dict[tuple[str, str], None] = {}
    for c in changes:
        requirement = requirements.get(c.req_id)
        known = (
            {cr.id for cr in requirement.criteria if cr.change != "added"}
            if requirement
            else set[str]()
        )
        for ac_id in c.obsolete_criteria:
            if ac_id not in known:
                offending[(c.req_id, ac_id)] = None
    return [
        ClassifierRejection(
            rule=ClassifierRule.UNKNOWN_CRITERION,
            subject=req_id,
            message=(
                f"entry {req_id!r} lists obsolete criterion {ac_id!r}, "
                "which is not a criterion of its from version"
            ),
        )
        for req_id, ac_id in offending
    ]


def _cosmetic_with_work(
    changes: Sequence[ChangeClass], modified: dict[str, RequirementDiff]
) -> list[ClassifierRejection]:
    # Only modified requirements on purpose, unlike `unknown-criterion`: an entry for any
    # other requirement is already `unknown-requirement`.
    offending: dict[str, None] = {}
    for c in changes:
        requirement = modified.get(c.req_id)
        lost_or_gained = bool(requirement and (_lost(requirement) or _gained(requirement)))
        if c.kind == "cosmetic" and (c.obsolete_criteria or c.new_work or lost_or_gained):
            offending[c.req_id] = None
    return [
        ClassifierRejection(
            rule=ClassifierRule.COSMETIC_WITH_WORK,
            subject=req_id,
            message=(
                f"entry {req_id!r} is cosmetic but has obsolete criteria, new work "
                "or a lost or gained criterion"
            ),
        )
        for req_id in offending
    ]


def check_classification(
    changes: Sequence[ChangeClass], diff: SpecDiff
) -> list[ClassifierRejection]:
    """The rejections of the content rules, in rule-table order; empty when the reply passes."""
    modified = _modified(diff)
    return [
        *_unknown_requirement(changes, modified),
        *_duplicate_requirement(changes),
        *_missing_requirement(changes, modified),
        *_unknown_criterion(changes, diff),
        *_cosmetic_with_work(changes, modified),
    ]


def add_lost_criteria(changes: Sequence[ChangeClass], diff: SpecDiff) -> list[ChangeClass]:
    """Each entry with the criteria its requirement lost added to `obsolete_criteria`.

    `obsolete_criteria` becomes each id once, sorted as strings; nothing else changes.
    """
    modified = _modified(diff)
    result: list[ChangeClass] = []
    for c in changes:
        requirement = modified.get(c.req_id)
        lost = _lost(requirement) if requirement else []
        obsolete = sorted({*c.obsolete_criteria, *lost})
        result.append(c.model_copy(update={"obsolete_criteria": obsolete}))
    return result
