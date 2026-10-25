"""TASK-109: the stats use case (docs/tasks/TASK-109-stats.md)."""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from openfactory.app.cost import Figures
from openfactory.app.stats import StatsReport, nearest_rank, run_stats
from openfactory.domain.agent_run import RunRecord
from openfactory.domain.contracts import REQUIRED_GATES, Limits, TaskContract
from openfactory.domain.events import Event, EventType, StoredEvent
from openfactory.domain.payloads import (
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    PlanCreatedPayload,
)

HASH = "a" * 64


def rec(
    run_id, role="implementer", task_id=None, tin=None, tout=None, cost=None, dur=None, exit=None
):
    return RunRecord(
        id=run_id,
        task_id=task_id,
        role=role,
        exit=exit,
        tokens_in=tin,
        tokens_out=tout,
        cost_usd=cost,
        duration_s=dur,
    )


def fin(run_id, role="implementer", task_id=None, tin=10, tout=5, cost=0.5, dur=2.0, exit="ok"):
    return rec(run_id, role, task_id, tin, tout, cost, dur, exit)


class FakeRuns:
    def __init__(self, records):
        self.records = records
        self.calls = []

    def next_id(self):
        self.calls.append("next_id")
        raise AssertionError("next_id must not be called")

    def unfinished_run(self, task_id):
        self.calls.append("unfinished_run")
        raise AssertionError("unfinished_run must not be called")

    def all_runs(self):
        self.calls.append("all_runs")
        return list(self.records)


class FakeEvents:
    def __init__(self):
        self.events: list[StoredEvent] = []
        self.calls = []

    def add(self, event: Event) -> StoredEvent:
        stored = StoredEvent(**event.model_dump(), seq=len(self.events) + 1)
        self.events.append(stored)
        return stored

    def append(self, event):
        self.calls.append("append")
        raise AssertionError("append must not be called")

    def read(self, stream=None):
        self.calls.append("read")
        return [e for e in self.events if stream is None or e.stream == stream]


def ev(stream, type_, payload, cause=None):
    return Event.new(
        stream=stream,
        type=type_,
        payload=payload.model_dump(mode="json"),
        actor="orchestrator",
        causation_id=cause.event_id if cause else None,
    )


def contract(task_id):
    return TaskContract(
        task_id=task_id,
        objective="x",
        requirements=["REQ-A-001"],
        acceptance_criteria=["AC-A-001-1"],
        components=["a"],
        role="implementer",
        allowed_paths=["src/**"],
        required_gates=list(REQUIRED_GATES),
        limits=Limits(max_runtime_s=1, max_attempts=1, max_cost_usd=1),
    )


def plan_created(log, plan_id, task_ids, cause=None, run_id="run_0001"):
    payload = PlanCreatedPayload(
        plan_id=plan_id,
        spec_version="sv_01",
        policy_hash=HASH,
        run_id=run_id,
        tasks=[contract(t) for t in task_ids],
    )
    return log.add(ev(f"plan:{plan_id}", EventType.PlanCreated, payload, cause))


def planner_call(log, run_id):
    started = AgentRunStartedPayload(
        run_id=run_id, task_id=None, role="planner", runtime="claude-code", context_hash=HASH
    )
    s = log.add(ev(f"run:{run_id}", EventType.AgentRunStarted, started))
    done = AgentRunFinishedPayload(
        run_id=run_id,
        exit="ok",
        model=None,
        tokens_in=1,
        tokens_out=1,
        cost_usd=0.1,
        duration_s=1.0,
        error=None,
    )
    return log.add(ev(f"run:{run_id}", EventType.AgentRunFinished, done, s))


def stats(records, log=None):
    return run_stats(runs=FakeRuns(records), events=log or FakeEvents())


# AC1


def test_ac1_task_figures_sorted_as_strings_with_nulls_and_unfinished_counted():
    got = stats(
        [
            fin("run_0001", task_id="AUTH-010", tin=7, tout=3, cost=0.25, dur=1.5),
            fin("run_0002", "reviewer", "AUTH-002", tin=10, tout=5, cost=0.5, dur=2.0),
            rec("run_0003", task_id="AUTH-002"),  # unfinished
            rec("run_0004", task_id="AUTH-002", dur=1.0, exit="error"),  # nulls
        ]
    )
    assert isinstance(got, StatsReport)
    assert [k for k, _ in got.tasks] == ["AUTH-002", "AUTH-010"]
    assert got.tasks[0][1] == Figures(
        runs=3, tokens_in=10, tokens_out=5, cost_usd=0.5, duration_s=3.0
    )
    assert got.tasks[1][1].runs == 1


def test_ac1_report_is_frozen_and_forbids_extra_fields():
    got = stats([])
    with pytest.raises(ValidationError):
        got.p50 = 1.0  # type: ignore[misc]
    with pytest.raises(ValidationError):
        StatsReport(tasks=[], plans=[], roles=[], p50=None, p95=None, extra=1)  # type: ignore[call-arg]


# AC2


def test_ac2_plans_sorted_include_every_created_plan_with_attributed_figures():
    log = FakeEvents()
    plan_created(
        log, "plan_02", ["TASK-002"], cause=planner_call(log, "run_0002"), run_id="run_0002"
    )
    plan_created(
        log, "plan_01", ["TASK-001"], cause=planner_call(log, "run_0001"), run_id="run_0001"
    )
    got = stats(
        [
            fin("run_0001", "planner", tin=1, tout=1, cost=0.1, dur=1.0),
            fin("run_0002", "planner", tin=2, tout=2, cost=0.2, dur=1.0),
            fin("run_0003", task_id="TASK-001", tin=10, tout=5, cost=0.5, dur=2.0),
        ],
        log,
    )
    assert [k for k, _ in got.plans] == ["plan_01", "plan_02"]
    assert got.plans[0][1].runs == 2
    assert got.plans[0][1].tokens_in == 11
    assert got.plans[1][1].runs == 1


# AC3


def test_ac3_roles_sorted_only_those_with_runs_and_rejected_planner_in_no_plan():
    log = FakeEvents()
    planner_call(log, "run_0001")  # rejected: no PlanCreated
    plan_created(log, "plan_01", [], cause=planner_call(log, "run_0002"), run_id="run_0002")
    got = stats(
        [
            fin("run_0001", "planner", tin=1, tout=1, cost=0.1, dur=1.0),
            fin("run_0002", "planner", tin=2, tout=2, cost=0.2, dur=1.0),
            fin("run_0003", "reviewer", "TASK-001", tin=4, tout=4, cost=0.4, dur=4.0),
            fin("run_0004", "implementer", "TASK-001", tin=8, tout=8, cost=0.8, dur=8.0),
        ],
        log,
    )
    assert [k for k, _ in got.roles] == ["implementer", "planner", "reviewer"]
    roles = dict(got.roles)
    assert roles["planner"].runs == 2
    assert roles["planner"].tokens_in == 3
    assert dict(got.plans)["plan_01"].runs == 1


# AC4


@pytest.mark.parametrize(
    ("values", "percent", "want"),
    [
        (list(map(float, range(1, 11))), 50, 5.0),
        (list(map(float, range(1, 11))), 95, 10.0),
        ([2.34], 50, 2.34),
        ([2.34], 95, 2.34),
        ([1.0, 2.0, 3.0, 4.0], 50, 2.0),
        ([1.0, 2.0, 3.0, 4.0], 95, 4.0),
        ([4.0, 1.0, 3.0, 2.0], 50, 2.0),
    ],
)
def test_ac4_nearest_rank_is_the_value_at_ceil_rank_never_interpolated(values, percent, want):
    assert nearest_rank(values, percent) == want


def test_ac4_percentiles_use_only_ok_runs_across_roles():
    got = stats(
        [
            fin(f"run_{i:04d}", "reviewer" if i % 2 else "implementer", dur=float(i))
            for i in range(1, 11)
        ]
        + [
            fin("run_0011", dur=500.0, exit="error"),
            fin("run_0012", dur=900.0, exit="timeout"),
            rec("run_0013"),
        ]
    )
    assert (got.p50, got.p95) == (5.0, 10.0)


def test_ac4_percentiles_are_none_without_an_ok_run():
    got = stats([fin("run_0001", dur=3.0, exit="error"), rec("run_0002")])
    assert (got.p50, got.p95) == (None, None)


# AC6


def test_ac6_no_run_gives_empty_groups_and_reads_only():
    runs, log = FakeRuns([]), FakeEvents()
    got = run_stats(runs=runs, events=log)
    assert (got.tasks, got.plans, got.roles) == ([], [], [])
    assert set(runs.calls) == {"all_runs"}
    assert set(log.calls) <= {"read"}


def test_ac6_stats_module_imports_only_domain_ports_and_cost():
    import openfactory.app.stats as stats_mod

    tree = ast.parse(Path(stats_mod.__file__).read_text())
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(a.name for a in node.names)
    own = [m for m in modules if m.startswith("openfactory")]
    assert own
    assert all(
        m.startswith(("openfactory.domain", "openfactory.ports", "openfactory.app.cost"))
        for m in own
    )
