"""Structural diff of two stored spec sets.

Implements "Step 1: structural diff (deterministic)" under "Spec diff and impact
analysis" in docs/spec/phase1-spec.md and ADR-019. Items are compared by id and
`content_hash`. A requirement deprecated in both sets is `unchanged`, whatever its hash
or ADRs; one deprecated in the old set and present and not deprecated in the new one is
`added`, its criteria diffed against an empty side. A requirement deprecated in the new
set and not deprecated (or absent) in the old one is `deprecated`; an otherwise
`unchanged` requirement is `modified` when an ADR in its `constrained_by` changed. The
criteria of a requirement deprecated in both are still diffed by id and hash. Every list
holds `unchanged` items too and is sorted by id.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from openfactory.domain.models import AcceptanceCriterion, Requirement, SpecSet
from openfactory.domain.spec_hash import SpecItem, content_hash

ItemChange = Literal["added", "removed", "modified", "unchanged"]
DiffRequirementChange = Literal["added", "removed", "modified", "deprecated", "unchanged"]


class CriterionDiff(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    change: ItemChange


class RequirementDiff(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    change: DiffRequirementChange
    criteria: list[CriterionDiff]


class AdrDiff(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    change: ItemChange


class SpecDiff(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    requirements: list[RequirementDiff]
    adrs: list[AdrDiff]


def _changes[T: SpecItem](old: dict[str, T], new: dict[str, T]) -> dict[str, ItemChange]:
    changes: dict[str, ItemChange] = {}
    for item_id in sorted(old.keys() | new.keys()):
        if item_id not in new:
            changes[item_id] = "removed"
        elif item_id not in old:
            changes[item_id] = "added"
        elif content_hash(old[item_id]) == content_hash(new[item_id]):
            changes[item_id] = "unchanged"
        else:
            changes[item_id] = "modified"
    return changes


def _criteria(old: Requirement | None, new: Requirement | None) -> list[CriterionDiff]:
    def index(requirement: Requirement | None) -> dict[str, AcceptanceCriterion]:
        if requirement is None:
            return {}
        return {criterion.id: criterion for criterion in requirement.acceptance_criteria}

    changes = _changes(index(old), index(new))
    return [CriterionDiff(id=item_id, change=change) for item_id, change in changes.items()]


def diff_specs(old: SpecSet, new: SpecSet) -> SpecDiff:
    old_adrs = {adr.id: adr for adr in old.adrs}
    new_adrs = {adr.id: adr for adr in new.adrs}
    adr_changes = _changes(old_adrs, new_adrs)
    changed_adrs = {item_id for item_id, change in adr_changes.items() if change != "unchanged"}

    old_reqs = {requirement.id: requirement for requirement in old.requirements}
    new_reqs = {requirement.id: requirement for requirement in new.requirements}
    requirements: list[RequirementDiff] = []
    for item_id, item_change in _changes(old_reqs, new_reqs).items():
        before, after = old_reqs.get(item_id), new_reqs.get(item_id)
        change: DiffRequirementChange = item_change
        criteria_before = before
        if before is not None and after is not None and before.deprecated and after.deprecated:
            change = "unchanged"
        elif before is not None and after is not None and before.deprecated:
            change = "added"
            criteria_before = None
        elif after is not None and after.deprecated and (before is None or not before.deprecated):
            change = "deprecated"
        elif (
            change == "unchanged"
            and before is not None
            and after is not None
            and {*before.constrained_by, *after.constrained_by} & changed_adrs
        ):
            change = "modified"
        requirements.append(
            RequirementDiff(id=item_id, change=change, criteria=_criteria(criteria_before, after))
        )

    adrs = [AdrDiff(id=item_id, change=change) for item_id, change in adr_changes.items()]
    return SpecDiff(requirements=requirements, adrs=adrs)
