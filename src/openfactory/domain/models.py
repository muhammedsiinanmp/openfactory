"""Spec set models: requirements, acceptance criteria, ADRs and declared components.

Mirrors "Spec input format" in docs/spec/phase1-spec.md. The models hold structure
only; the ID and cross-reference rules live in `spec_validation`.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Priority(StrEnum):
    must = "must"
    should = "should"
    could = "could"


class AdrStatus(StrEnum):
    proposed = "proposed"
    accepted = "accepted"
    superseded = "superseded"


class AcceptanceCriterion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    text: str


class Requirement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str
    statement: str
    priority: Priority
    constrained_by: list[str] = []
    components: list[str] = []
    acceptance_criteria: list[AcceptanceCriterion] = []
    deprecated: bool = False


class Adr(BaseModel):
    # ADR front matter normally carries more than `id` and `status` (title, date).
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str
    status: AdrStatus
    body: str = ""


class SpecSet(BaseModel):
    """Everything `openfactory validate` checks together."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    components: list[str] = []
    requirements: list[Requirement] = []
    adrs: list[Adr] = []
