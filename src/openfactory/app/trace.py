"""Trace use case: a requirement's tasks, commits, files and tests.

See docs/spec/phase1-spec.md ("Traceability", "Queries"; "CLI commands", "Output") and
ADR-018. The trace is the one `Traces.requirement_trace` gives, already ordered by the
adapter. When no approved spec version has the requirement the read gives `None` and the
use case refuses. It records no events, does not repair the plan, returns data and prints
nothing.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from openfactory.domain.traces import RequirementTrace
from openfactory.ports.traces import Traces


class TraceRefusal(StrEnum):
    unknown_requirement = "unknown_requirement"


class TraceReport(BaseModel):
    """What one `trace` run found: a refusal, or the requirement's trace."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    refusal: TraceRefusal | None = None
    trace: RequirementTrace | None = None


def trace_requirement(requirement_id: str, *, traces: Traces) -> TraceReport:
    trace = traces.requirement_trace(requirement_id)
    if trace is None:
        return TraceReport(refusal=TraceRefusal.unknown_requirement)
    return TraceReport(trace=trace)
