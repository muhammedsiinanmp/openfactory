"""Stats use case: the figures per task, per plan and per role, and the run latency.

See docs/spec/phase1-spec.md ("Metrics"; "CLI commands", "Output") and ADR-020. The task
and plan figures are those of `attribute_costs`; the role figures cover every run of that
role. Each group comes in ascending key order as strings. p50 and p95 are nearest-rank over
the `duration_s` of the runs with `exit: ok`, None when there is none. Runs and events are
only read; the use case records nothing, returns data and prints nothing.
"""

import math
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from openfactory.app.cost import Figures, attribute_costs, sum_figures
from openfactory.domain.agent_run import RunRecord
from openfactory.ports.event_store import EventStore
from openfactory.ports.runs import Runs


class StatsReport(BaseModel):
    """The three figure groups, each sorted by key as strings, and the two percentiles."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tasks: list[tuple[str, Figures]]
    plans: list[tuple[str, Figures]]
    roles: list[tuple[str, Figures]]
    p50: float | None
    p95: float | None


def nearest_rank(values: Sequence[float], percent: int) -> float:
    """The value at 1-based rank ceil(percent/100 x N) of the sorted values; never interpolated."""
    ordered = sorted(values)
    rank = math.ceil(percent / 100 * len(ordered))
    return ordered[max(rank, 1) - 1]


def run_stats(*, runs: Runs, events: EventStore) -> StatsReport:
    records = runs.all_runs()
    attribution = attribute_costs(runs=runs, events=events)

    role_runs: dict[str, list[RunRecord]] = {}
    for run in records:
        role_runs.setdefault(run.role, []).append(run)

    ok = [run.duration_s for run in records if run.exit == "ok" and run.duration_s is not None]
    return StatsReport(
        tasks=sorted(attribution.tasks.items()),
        plans=sorted(attribution.plans.items()),
        roles=sorted((role, sum_figures(group)) for role, group in role_runs.items()),
        p50=nearest_rank(ok, 50) if ok else None,
        p95=nearest_rank(ok, 95) if ok else None,
    )
