"""Why use case: a file's commits, tasks, requirements and ADRs.

See docs/spec/phase1-spec.md ("Traceability", "Queries"; "CLI commands", "Output") and
ADR-018. The trace is the one `Traces.file_trace` gives for PATH compared as a string,
already ordered by the adapter. When no commit changed PATH the read gives `None` and the
use case refuses. It records no events, does not repair the plan, returns data and prints
nothing.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from openfactory.domain.traces import FileTrace
from openfactory.ports.traces import Traces


class WhyRefusal(StrEnum):
    no_commit_changed = "no_commit_changed"


class WhyReport(BaseModel):
    """What one `why` run found: a refusal, or the file's trace."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    refusal: WhyRefusal | None = None
    trace: FileTrace | None = None


def why_file(path: str, *, traces: Traces) -> WhyReport:
    trace = traces.file_trace(path)
    if trace is None:
        return WhyReport(refusal=WhyRefusal.no_commit_changed)
    return WhyReport(trace=trace)
