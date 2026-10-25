"""TASK-108: cost attribution of runs to tasks and plans."""

import pytest

from openfactory.app.cost import CostAttribution, Figures, attribute_costs, sum_figures
from openfactory.domain.agent_run import RunRecord
from openfactory.domain.contracts import REQUIRED_GATES, Limits, TaskContract
from openfactory.domain.events import Event, EventType, StoredEvent
from openfactory.domain.payloads import (
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    ImpactComputedPayload,
    PlanApprovedPayload,
    PlanCreatedPayload,
    TaskResolvedPayload,
)

HASH = "a" * 64


def rec(
    run_id, role="implementer", task_id=None, tin=None, tout=None, cost=None, dur=None, exit="ok"
):
    if dur is None and tin is None and cost is None:
        exit = None if exit == "ok" else exit
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


def fin(run_id, tin=10, tout=5, cost=0.5, dur=2.0):
    return rec(run_id, tin=tin, tout=tout, cost=cost, dur=dur)


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


def ev(stream, type_, payload, cause: StoredEvent | None = None):
    return Event.new(
        stream=stream,
        type=type_,
        payload=payload.model_dump(mode="json"),
        actor="orchestrator",
        causation_id=cause.event_id if cause else None,
    )


def call(log: FakeEvents, run_ids, role="planner", cause: StoredEvent | None = None):
    """Record started/finished pairs, each chained to the one before; return the last event."""
    last = cause
    for run_id in run_ids:
        started = AgentRunStartedPayload(
            run_id=run_id, task_id=None, role=role, runtime="claude-code", context_hash=HASH
        )
        last = log.add(ev(f"run:{run_id}", EventType.AgentRunStarted, started, last))
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
        last = log.add(ev(f"run:{run_id}", EventType.AgentRunFinished, done, last))
    return last


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


def plan_approved(log, plan_id):
    return log.add(
        ev(f"plan:{plan_id}", EventType.PlanApproved, PlanApprovedPayload(plan_id=plan_id))
    )


def impact(log, cause=None):
    payload = ImpactComputedPayload(
        from_version="sv_01",
        to_version="sv_02",
        run_id=None,
        requirements=[],
        adrs=[],
        tasks=[],
        downstream=[],
        files=[],
        tests=[],
    )
    return log.add(ev("spec:sv_02", EventType.ImpactComputed, payload, cause))


def run_all(records, log):
    return attribute_costs(runs=FakeRuns(records), events=log)


# AC1


def test_ac1_sum_figures_adds_each_figure():
    got = sum_figures(
        [
            rec("run_0001", tin=100, tout=50, cost=0.25, dur=3.5),
            rec("run_0002", tin=7, tout=3, cost=0.5, dur=9.0),
        ]
    )
    assert got == Figures(runs=2, tokens_in=107, tokens_out=53, cost_usd=0.75, duration_s=12.5)


def test_ac1_null_figures_count_as_zero_on_a_finished_run():
    got = sum_figures([rec("run_0001", tin=None, tout=None, cost=None, dur=2.0, exit="error")])
    assert got == Figures(runs=1, tokens_in=0, tokens_out=0, cost_usd=0.0, duration_s=2.0)


def test_ac1_unfinished_run_counts_as_a_run_and_adds_nothing():
    unfinished = rec("run_0002")
    assert unfinished.exit is None
    got = sum_figures([fin("run_0001", 10, 5, 0.5, 2.0), unfinished])
    assert got == Figures(runs=2, tokens_in=10, tokens_out=5, cost_usd=0.5, duration_s=2.0)


def test_ac1_no_runs_gives_all_zeros():
    assert sum_figures([]) == Figures(runs=0, tokens_in=0, tokens_out=0, cost_usd=0, duration_s=0)


# AC2


def test_ac2_task_figures_cover_all_its_runs_including_before_a_retry():
    log = FakeEvents()
    plan_created(log, "plan_01", ["TASK-001", "TASK-002"])
    plan_approved(log, "plan_01")
    log.add(
        ev(
            "task:TASK-001",
            EventType.TaskResolved,
            TaskResolvedPayload(task_id="TASK-001", decision="retry"),
        )
    )
    records = [
        rec("run_0002", task_id="TASK-001", tin=1, tout=1, cost=0.1, dur=1.0, exit="error"),
        rec("run_0003", "reviewer", "TASK-001", 2, 2, 0.2, 2.0),
        rec("run_0004", task_id="TASK-001", tin=4, tout=4, cost=0.4, dur=4.0),
        rec("run_0005", task_id="TASK-002", tin=8, tout=8, cost=0.8, dur=8.0),
    ]
    got = run_all(records, log)
    assert isinstance(got, CostAttribution)
    assert got.tasks["TASK-001"].model_dump() == {
        "runs": 3,
        "tokens_in": 7,
        "tokens_out": 7,
        "cost_usd": pytest.approx(0.7),
        "duration_s": 7.0,
    }
    assert got.tasks["TASK-002"].runs == 1


def test_ac2_planner_and_classifier_runs_are_in_no_task_entry():
    log = FakeEvents()
    records = [
        rec("run_0001", "planner", None, 1, 1, 0.1, 1.0),
        rec("run_0002", "classifier", None, 1, 1, 0.1, 1.0),
        rec("run_0003", "implementer", "TASK-001", 1, 1, 0.1, 1.0),
    ]
    assert set(run_all(records, log).tasks) == {"TASK-001"}


# AC3


def test_ac3_every_created_plan_has_an_entry_and_one_without_runs_is_zero():
    log = FakeEvents()
    plan_created(log, "plan_01", ["TASK-001"])
    plan_created(log, "plan_02", ["TASK-002"])
    got = run_all([rec("run_0002", task_id="TASK-001", tin=3, tout=2, cost=0.3, dur=1.0)], log)
    assert set(got.plans) == {"plan_01", "plan_02"}
    assert got.plans["plan_01"].runs == 1
    assert got.plans["plan_02"] == Figures(
        runs=0, tokens_in=0, tokens_out=0, cost_usd=0, duration_s=0
    )


def test_ac3_task_counts_only_for_the_latest_plan_that_lists_it():
    log = FakeEvents()
    plan_created(log, "plan_01", ["TASK-001", "TASK-002"])
    plan_created(log, "plan_02", ["TASK-001"])
    records = [
        rec("run_0002", task_id="TASK-001", tin=3, tout=2, cost=0.3, dur=1.0),
        rec("run_0003", task_id="TASK-002", tin=5, tout=5, cost=0.5, dur=2.0),
    ]
    got = run_all(records, log)
    assert got.plans["plan_02"].runs == 1
    assert got.plans["plan_02"].tokens_in == 3
    assert got.plans["plan_01"].runs == 1
    assert got.plans["plan_01"].tokens_in == 5


# AC4


def test_ac4_plan_includes_the_planner_runs_on_its_chain_including_a_retry():
    log = FakeEvents()
    last = call(log, ["run_0001", "run_0002"], "planner")
    plan_created(log, "plan_01", ["TASK-001"], cause=last, run_id="run_0002")
    records = [
        rec("run_0001", "planner", None, 10, 1, 0.1, 1.0),
        rec("run_0002", "planner", None, 20, 2, 0.2, 2.0),
        rec("run_0003", "implementer", "TASK-001", 40, 4, 0.4, 4.0),
    ]
    got = run_all(records, log).plans["plan_01"]
    assert got.runs == 3
    assert got.tokens_in == 70
    assert got.cost_usd == pytest.approx(0.7)


def test_ac4_planner_runs_of_a_command_with_no_plan_created_are_in_no_plan():
    log = FakeEvents()
    call(log, ["run_0001"], "planner")  # rejected: no PlanCreated
    last = call(log, ["run_0002"], "planner")
    plan_created(log, "plan_01", [], cause=last, run_id="run_0002")
    records = [
        rec("run_0001", "planner", None, 10, 1, 0.1, 1.0),
        rec("run_0002", "planner", None, 20, 2, 0.2, 2.0),
    ]
    got = run_all(records, log)
    assert got.plans["plan_01"].runs == 1
    assert got.plans["plan_01"].tokens_in == 20


# AC5


def replan_log():
    """plan_01 approved; classifier on an ImpactComputed; replan drafts plan_02 and plan_03."""
    log = FakeEvents()
    plan_created(log, "plan_01", ["TASK-001"], cause=call(log, ["run_0001"], "planner"))
    plan_approved(log, "plan_01")
    return log


def cls(run_id, tin=100):
    return rec(run_id, "classifier", None, tin, 1, 1.0, 1.0)


def planner(run_id, tin=10):
    return rec(run_id, "planner", None, tin, 1, 0.1, 1.0)


def test_ac5_replan_gets_the_classifier_runs_of_the_latest_impact_including_a_retry():
    log = replan_log()
    impact(log, call(log, ["run_0002", "run_0003"], "classifier"))
    plan_created(log, "plan_02", [], cause=call(log, ["run_0004"], "planner"))
    records = [planner("run_0001"), cls("run_0002"), cls("run_0003", 200), planner("run_0004", 20)]
    got = run_all(records, log)
    assert got.plans["plan_02"].runs == 3
    assert got.plans["plan_02"].tokens_in == 320
    assert got.plans["plan_01"].runs == 1


def test_ac5_plan_without_an_earlier_approval_gets_no_classifier_runs():
    log = FakeEvents()
    call(log, ["run_0001"], "classifier")
    impact(log, log.events[-1])
    plan_created(log, "plan_01", [], cause=call(log, ["run_0002"], "planner"))
    got = run_all([cls("run_0001"), planner("run_0002")], log)
    assert got.plans["plan_01"].runs == 1


def test_ac5_impact_without_causation_adds_no_runs():
    log = replan_log()
    impact(log, None)
    plan_created(log, "plan_02", [], cause=call(log, ["run_0002"], "planner"))
    got = run_all([planner("run_0001"), planner("run_0002", 20)], log)
    assert got.plans["plan_02"].runs == 1


def test_ac5_classifier_runs_of_an_earlier_unused_impact_are_in_no_plan():
    log = replan_log()
    impact(log, call(log, ["run_0002"], "classifier"))  # superseded, never used
    impact(log, call(log, ["run_0003"], "classifier"))
    plan_created(log, "plan_02", [], cause=call(log, ["run_0004"], "planner"))
    records = [planner("run_0001"), cls("run_0002", 1000), cls("run_0003"), planner("run_0004")]
    got = run_all(records, log)
    assert got.plans["plan_02"].runs == 2
    assert got.plans["plan_02"].tokens_in == 110


def test_ac5_two_drafts_after_the_same_impact_both_get_its_classifier_runs():
    log = replan_log()
    impact(log, call(log, ["run_0002"], "classifier"))
    plan_created(log, "plan_02", [], cause=call(log, ["run_0003"], "planner"))
    plan_created(log, "plan_03", [], cause=call(log, ["run_0004"], "planner"))
    records = [planner("run_0001"), cls("run_0002"), planner("run_0003"), planner("run_0004")]
    got = run_all(records, log)
    assert got.plans["plan_02"].runs == 2
    assert got.plans["plan_03"].runs == 2


# AC6


def test_ac6_attribution_only_reads_all_runs_and_the_event_log():
    log = replan_log()
    runs = FakeRuns([planner("run_0001")])
    before = len(log.events)
    attribute_costs(runs=runs, events=log)
    assert set(runs.calls) == {"all_runs"}
    assert set(log.calls) <= {"read"}
    assert len(log.events) == before


def test_ac6_cost_module_imports_only_domain_and_ports():
    import ast
    from pathlib import Path

    import openfactory.app.cost as cost

    tree = ast.parse(Path(cost.__file__).read_text())
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(a.name for a in node.names)
    own = [m for m in modules if m.startswith("openfactory")]
    assert own
    assert all(m.startswith(("openfactory.domain", "openfactory.ports")) for m in own)
