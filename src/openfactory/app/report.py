"""Report use case: the approved plan, each requirement's trace and the cost per plan.

See docs/spec/phase1-spec.md ("Metrics"; "CLI commands", "Output"), ADR-018 and ADR-020.
The requirements are those of the latest approved spec version in ascending id as strings,
each with the trace `Traces.requirement_trace` gives. The cost rows are the plans with a
`PlanApproved` in ascending id as strings, `build` for the first and `replan` for the
others, with the figures of `attribute_costs`, then their sum. With no approved plan the
use case refuses. It records no events, does not repair the plan, returns data and prints
nothing.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from openfactory.app.cost import Figures, attribute_costs
from openfactory.domain.events import EventType
from openfactory.domain.payloads import PlanApprovedPayload
from openfactory.domain.traces import RequirementTrace
from openfactory.ports.event_store import EventStore
from openfactory.ports.plans import Plans
from openfactory.ports.runs import Runs
from openfactory.ports.spec_versions import SpecVersions
from openfactory.ports.traces import Traces


class ReportRefusal(StrEnum):
    no_approved_plan = "no_approved_plan"


class ReportRequirement(BaseModel):
    """One requirement of the latest approved spec version and its trace."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str
    deprecated: bool
    trace: RequirementTrace


class CostRow(BaseModel):
    """The figures of one plan with a `PlanApproved`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_id: str
    kind: Literal["build", "replan"]
    figures: Figures


class Report(BaseModel):
    """What one `report` run found: a refusal, or the report's data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    refusal: ReportRefusal | None = None
    plan_id: str | None = None
    spec_version: str | None = None
    requirements: list[ReportRequirement] = []
    costs: list[CostRow] = []
    total: Figures | None = None


def build_report(
    *, plans: Plans, versions: SpecVersions, traces: Traces, runs: Runs, events: EventStore
) -> Report:
    plan = plans.approved()
    if plan is None:
        return Report(refusal=ReportRefusal.no_approved_plan)

    version = versions.latest_approved()
    assert version is not None
    spec = versions.spec_set(version.id)
    assert spec is not None

    requirements: list[ReportRequirement] = []
    for requirement in sorted(spec.requirements, key=lambda r: r.id):
        trace = traces.requirement_trace(requirement.id)
        assert trace is not None
        requirements.append(
            ReportRequirement(
                id=requirement.id,
                title=requirement.title,
                deprecated=requirement.deprecated,
                trace=trace,
            )
        )

    # Read before `attribute_costs`, so every approved plan is a key of its `plans`.
    approved_ids = sorted(
        {
            PlanApprovedPayload.model_validate(event.payload).plan_id
            for event in events.read()
            if event.type is EventType.PlanApproved
        }
    )
    attribution = attribute_costs(runs=runs, events=events)
    costs = [
        CostRow(
            plan_id=plan_id,
            kind="build" if index == 0 else "replan",
            figures=attribution.plans[plan_id],
        )
        for index, plan_id in enumerate(approved_ids)
    ]
    total = Figures(
        runs=sum(row.figures.runs for row in costs),
        tokens_in=sum(row.figures.tokens_in for row in costs),
        tokens_out=sum(row.figures.tokens_out for row in costs),
        cost_usd=sum(row.figures.cost_usd for row in costs),
        duration_s=sum(row.figures.duration_s for row in costs),
    )
    return Report(
        refusal=None,
        plan_id=plan.id,
        spec_version=version.id,
        requirements=requirements,
        costs=costs,
        total=total,
    )
