"""Deterministic validation rules for a spec set.

Implements the "Validation rules" under "Spec input format" in docs/spec/phase1-spec.md.
`validate_spec` runs the first four on a spec set alone. The fifth (deleted requirements)
also needs the approved spec set and the tasks, which the validate use case reads through
ports: `deleted_requirements` and `deleted_requirement_violation` are its pure parts.

`Rule.schema` is the rule the spec loader reports a file under when it cannot be loaded
into the models; `validate_spec` returns neither it nor `Rule.deleted_requirement`.
"""

import re
from collections import Counter
from collections.abc import Iterable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from openfactory.domain.models import AdrStatus, SpecSet

REQUIREMENT_ID = re.compile(r"REQ-[A-Z]+-\d{3}")
ADR_ID = re.compile(r"ADR-\d{3}")
CRITERION_ID = re.compile(r"AC-[A-Z]+-\d{3}-\d+")


class Rule(StrEnum):
    id_format = "id-format"
    id_unique = "id-unique"
    missing_acceptance_criteria = "missing-acceptance-criteria"
    constrained_by = "constrained-by"
    undeclared_component = "undeclared-component"
    deleted_requirement = "deleted-requirement"
    schema = "schema"


class SpecViolation(BaseModel):
    """One broken rule; `subject` is the ID it concerns."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule: Rule
    subject: str
    message: str


def _criterion_ids(spec: SpecSet) -> list[str]:
    return [ac.id for r in spec.requirements for ac in r.acceptance_criteria]


def _id_format(spec: SpecSet) -> list[SpecViolation]:
    groups = [
        ("requirement", REQUIREMENT_ID, [r.id for r in spec.requirements]),
        ("ADR", ADR_ID, [a.id for a in spec.adrs]),
        ("acceptance criterion", CRITERION_ID, _criterion_ids(spec)),
    ]
    return [
        SpecViolation(
            rule=Rule.id_format,
            subject=id_,
            message=f"{kind} id {id_!r} does not match {pattern.pattern}",
        )
        for kind, pattern, ids in groups
        for id_ in ids
        if not pattern.fullmatch(id_)
    ]


def _duplicates(ids: Iterable[str]) -> list[str]:
    """Each repeated id once, in order of first appearance."""
    return [id_ for id_, count in Counter(ids).items() if count > 1]


def _id_unique(spec: SpecSet) -> list[SpecViolation]:
    groups = [
        ("requirement", [r.id for r in spec.requirements]),
        ("ADR", [a.id for a in spec.adrs]),
        ("acceptance criterion", _criterion_ids(spec)),
    ]
    return [
        SpecViolation(
            rule=Rule.id_unique,
            subject=id_,
            message=f"{kind} id {id_!r} is used more than once",
        )
        for kind, ids in groups
        for id_ in _duplicates(ids)
    ]


def _missing_acceptance_criteria(spec: SpecSet) -> list[SpecViolation]:
    return [
        SpecViolation(
            rule=Rule.missing_acceptance_criteria,
            subject=r.id,
            message=f"requirement {r.id!r} has no acceptance criteria",
        )
        for r in spec.requirements
        if not r.acceptance_criteria
    ]


def _constrained_by(spec: SpecSet) -> list[SpecViolation]:
    known = {a.id for a in spec.adrs}
    accepted = {a.id for a in spec.adrs if a.status is AdrStatus.accepted}
    return [
        SpecViolation(
            rule=Rule.constrained_by,
            subject=r.id,
            message=(
                f"requirement {r.id!r} is constrained by {adr_id!r}, which is not accepted"
                if adr_id in known
                else f"requirement {r.id!r} is constrained by {adr_id!r}, which does not exist"
            ),
        )
        for r in spec.requirements
        for adr_id in r.constrained_by
        if adr_id not in accepted
    ]


def _undeclared_component(spec: SpecSet) -> list[SpecViolation]:
    declared = set(spec.components)
    return [
        SpecViolation(
            rule=Rule.undeclared_component,
            subject=r.id,
            message=f"requirement {r.id!r} names undeclared component {component!r}",
        )
        for r in spec.requirements
        for component in r.components
        if component not in declared
    ]


def validate_spec(spec: SpecSet) -> list[SpecViolation]:
    """Return every violation in the spec set, in a fixed rule order."""
    return [
        *_id_format(spec),
        *_id_unique(spec),
        *_missing_acceptance_criteria(spec),
        *_constrained_by(spec),
        *_undeclared_component(spec),
    ]


def deleted_requirements(approved: SpecSet, spec: SpecSet) -> list[str]:
    """The ids of the requirements in `approved` that are absent from `spec`, ascending."""
    present = {r.id for r in spec.requirements}
    return sorted({r.id for r in approved.requirements} - present)


def deleted_requirement_violation(requirement_id: str, task_ids: list[str]) -> SpecViolation:
    return SpecViolation(
        rule=Rule.deleted_requirement,
        subject=requirement_id,
        message=(
            f"requirement {requirement_id!r} is deleted but tasks still reference it: "
            f"{', '.join(sorted(task_ids))}"
        ),
    )
