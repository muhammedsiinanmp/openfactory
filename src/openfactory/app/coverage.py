"""Coverage use case: the untested requirements of the latest approved spec version.

See docs/spec/phase1-spec.md ("Traceability", "Queries"; "CLI commands", "Output") and
ADR-018. The ids are those `Traces.untested_requirements` gives, already sorted as strings
by the adapter. With no approved spec version the use case refuses. It records no events,
does not repair the plan, returns data and prints nothing.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from openfactory.ports.spec_versions import SpecVersions
from openfactory.ports.traces import Traces


class CoverageRefusal(StrEnum):
    no_approved_spec = "no_approved_spec"


class CoverageReport(BaseModel):
    """What one `coverage` run found: a refusal, or the untested requirement ids."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    refusal: CoverageRefusal | None = None
    untested: list[str] = []


def requirement_coverage(*, versions: SpecVersions, traces: Traces) -> CoverageReport:
    ref = versions.latest_approved()
    if ref is None:
        return CoverageReport(refusal=CoverageRefusal.no_approved_spec)
    return CoverageReport(untested=traces.untested_requirements(ref.id))
