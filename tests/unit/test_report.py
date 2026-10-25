"""TASK-110: the report use case (docs/tasks/TASK-110-report-use-case.md)."""

import ast
from pathlib import Path

import pytest

from openfactory.app.cost import Figures, attribute_costs
from openfactory.app.report import CostRow, Report, ReportRefusal, build_report
from openfactory.domain.agent_run import RunRecord
from openfactory.domain.contracts import REQUIRED_GATES, Limits, TaskContract
from openfactory.domain.events import Event, EventType, StoredEvent
from openfactory.domain.models import Priority, Requirement, SpecSet
from openfactory.domain.payloads import (
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    ImpactComputedPayload,
    PlanApprovedPayload,
    PlanCreatedPayload,
)
from openfactory.domain.plans import PlanRef
from openfactory.domain.spec_versions import SpecVersionRef
from openfactory.domain.traces import RequirementTrace, TracedCommit, TracedTask, TracedTest

HASH = "a" * 64
SHA = "b" * 40
PLAN_01 = PlanRef(id="plan_01", spec_version="sv_01")
EMPTY = RequirementTrace(tasks=[], commits=[], files=[], tests=[])


def rec(run_id, role="implementer", task_id=None, tin=10, tout=5, cost=0.5, dur=2.0):
    return RunRecord(
        id=run_id,
        task_id=task_id,
        role=role,
        exit="ok",
        tokens_in=tin,
        tokens_out=tout,
        cost_usd=cost,
        duration_s=dur,
    )


class FakeRuns:
    def __init__(self, records):
        self.records = records
        self.calls = []

    def next_id(self):
        raise AssertionError("next_id must not be called")

    def unfinished_run(self, task_id):
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


class FakePlans:
    def __init__(self, approved):
        self._approved = approved
        self.calls = []

    def approved(self):
        self.calls.append("approved")
        return self._approved

    def __getattr__(self, name):
        raise AssertionError(f"Plans.{name} must not be called")


class FakeVersions:
    def __init__(self, latest, sets=None):
        self.latest = latest
        self.sets = sets or {}
        self.calls = []

    def latest_approved(self):
        self.calls.append("latest_approved")
        return self.latest

    def spec_set(self, version_id):
        self.calls.append("spec_set")
        return self.sets.get(version_id)

    def __getattr__(self, name):
        raise AssertionError(f"SpecVersions.{name} must not be called")


class FakeTraces:
    def __init__(self, traces=None):
        self.traces = traces or {}
        self.calls = []

    def requirement_trace(self, requirement_id):
        self.calls.append(("requirement_trace", requirement_id))
        return self.traces.get(requirement_id, EMPTY)

    def __getattr__(self, name):
        raise AssertionError(f"Traces.{name} must not be called")


def req(req_id, title="T", deprecated=False):
    return Requirement(
        id=req_id, title=title, statement="s", priority=Priority.must, deprecated=deprecated
    )


def ev(stream, type_, payload, cause=None):
    return Event.new(
        stream=stream,
        type=type_,
        payload=payload.model_dump(mode="json"),
        actor="orchestrator",
        causation_id=cause.event_id if cause else None,
    )


def call(log, run_ids, role="planner", cause=None):
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


def planner(run_id, tin=10):
    return rec(run_id, "planner", None, tin, 1, 0.1, 1.0)


def classifier(run_id, tin=100):
    return rec(run_id, "classifier", None, tin, 1, 1.0, 1.0)


def report(
    *,
    approved=PLAN_01,
    latest="sv_01",
    requirements=(),
    traces=None,
    records=(),
    log=None,
):
    log = log if log is not None else FakeEvents()
    versions = FakeVersions(
        SpecVersionRef(id=latest, hash=HASH) if latest else None,
        {latest: SpecSet(requirements=list(requirements))} if latest else {},
    )
    fakes = {
        "plans": FakePlans(approved),
        "versions": versions,
        "traces": FakeTraces(traces),
        "runs": FakeRuns(list(records)),
        "events": log,
    }
    return build_report(**fakes), fakes


def build_then_replan_log():
    """plan_01 (build) approved; impact + classifier; plan_02 (replan) approved."""
    log = FakeEvents()
    plan_created(log, "plan_01", ["TASK-001"], cause=call(log, ["run_0001"]))
    plan_approved(log, "plan_01")
    impact(log, call(log, ["run_0002"], "classifier"))
    plan_created(log, "plan_02", ["TASK-002"], cause=call(log, ["run_0003"]), run_id="run_0003")
    plan_approved(log, "plan_02")
    records = [
        planner("run_0001"),
        rec("run_0010", task_id="TASK-001", tin=1000),
        classifier("run_0002"),
        planner("run_0003", 20),
        rec("run_0011", task_id="TASK-002", tin=7),
    ]
    return log, records


# AC1


def test_ac1_no_approved_plan_refuses_with_every_other_field_default():
    log = FakeEvents()
    plan_created(log, "plan_01", ["TASK-001"])
    got, fakes = report(
        approved=None,
        requirements=[req("REQ-A-001")],
        records=[rec("run_0001", task_id="TASK-001")],
        log=log,
    )
    assert got == Report(refusal=ReportRefusal.no_approved_plan)
    assert got.plan_id is None and got.total is None
    assert got.requirements == [] and got.costs == []
    assert "append" not in log.calls


# AC2


def test_ac2_plan_and_spec_version_are_reported_even_when_they_differ():
    plan = PlanRef(id="plan_01", spec_version="sv_01")
    got, _ = report(approved=plan, latest="sv_02")
    assert got.refusal is None
    assert got.plan_id == "plan_01"
    assert got.spec_version == "sv_02"


# AC3


def test_ac3_requirements_sorted_as_strings_with_title_deprecated_and_trace():
    tr = RequirementTrace(
        tasks=[
            TracedTask(task_id="TASK-002", state="passed"),
            TracedTask(task_id="TASK-001", state="passed"),
        ],
        commits=[TracedCommit(sha=SHA, task_id="TASK-001")],
        files=["z.py", "a.py"],
        tests=[TracedTest(node_id="t::b", tagged=True), TracedTest(node_id="t::a", tagged=False)],
    )
    got, fakes = report(
        requirements=[
            req("REQ-AUTH-010", "Ten"),
            req("REQ-AUTH-002", "Two", deprecated=True),
            req("REQ-AUTH-003", "Three"),
        ],
        traces={"REQ-AUTH-002": tr},
    )
    assert [r.id for r in got.requirements] == ["REQ-AUTH-002", "REQ-AUTH-003", "REQ-AUTH-010"]
    first, second, third = got.requirements
    assert (first.title, first.deprecated) == ("Two", True)
    assert (third.title, third.deprecated) == ("Ten", False)
    assert first.trace == tr
    assert first.trace.tasks[0].task_id == "TASK-002"  # adapter order kept
    assert second.trace == EMPTY
    assert third.trace.tasks == [] and third.trace.commits == []
    assert third.trace.files == [] and third.trace.tests == []


def test_ac3_only_the_latest_approved_version_is_listed():
    log = FakeEvents()
    versions = FakeVersions(
        SpecVersionRef(id="sv_02", hash=HASH),
        {
            "sv_01": SpecSet(requirements=[req("REQ-OLD-001"), req("REQ-A-001")]),
            "sv_02": SpecSet(requirements=[req("REQ-A-001")]),
        },
    )
    got = build_report(
        plans=FakePlans(PlanRef(id="plan_01", spec_version="sv_01")),
        versions=versions,
        traces=FakeTraces(),
        runs=FakeRuns([]),
        events=log,
    )
    assert [r.id for r in got.requirements] == ["REQ-A-001"]


# AC4


def test_ac4_build_then_replan_rows_hold_their_own_runs():
    log, records = build_then_replan_log()
    got, _ = report(approved=PlanRef(id="plan_02", spec_version="sv_01"), records=records, log=log)
    assert [(c.plan_id, c.kind) for c in got.costs] == [("plan_01", "build"), ("plan_02", "replan")]
    build, replan = got.costs
    assert build.figures.runs == 2
    assert build.figures.tokens_in == 1010
    assert replan.figures.runs == 3  # its planner, the classifier, its new task
    assert replan.figures.tokens_in == 127
    attribution = attribute_costs(runs=FakeRuns(records), events=log)
    for row in got.costs:
        assert isinstance(row, CostRow)
        assert row.figures == attribution.plans[row.plan_id]


def test_ac4_plans_without_approval_have_no_row_and_superseded_approved_keeps_one():
    log = FakeEvents()
    plan_created(log, "plan_01", ["TASK-001"])  # draft replaced before approval
    plan_created(log, "plan_02", ["TASK-001"])
    plan_approved(log, "plan_02")
    plan_created(log, "plan_03", ["TASK-002"])
    plan_approved(log, "plan_03")
    plan_created(log, "plan_04", ["TASK-003"])  # replan draft not yet approved
    got, _ = report(approved=PlanRef(id="plan_03", spec_version="sv_01"), log=log)
    assert [(c.plan_id, c.kind) for c in got.costs] == [
        ("plan_02", "build"),
        ("plan_03", "replan"),
    ]


def test_ac4_rows_sorted_as_strings_not_by_approval_order():
    log = FakeEvents()
    plan_created(log, "plan_02", [])
    plan_created(log, "plan_01", [])
    plan_approved(log, "plan_02")
    plan_approved(log, "plan_01")
    got, _ = report(log=log)
    assert [c.plan_id for c in got.costs] == ["plan_01", "plan_02"]
    assert got.costs[0].kind == "build"


# AC5


def test_ac5_total_sums_rows_and_leaves_out_unattributed_runs():
    log, records = build_then_replan_log()
    call(log, ["run_0004", "run_0005"])  # twice-rejected plan: no PlanCreated
    plan_created(log, "plan_03", [], cause=call(log, ["run_0006"]))  # unapproved draft
    records += [planner("run_0004", 500), planner("run_0005", 500), planner("run_0006", 500)]
    got, _ = report(approved=PlanRef(id="plan_02", spec_version="sv_01"), records=records, log=log)
    assert got.total is not None
    assert got.total.runs == sum(c.figures.runs for c in got.costs) == 5
    assert got.total.tokens_in == sum(c.figures.tokens_in for c in got.costs) == 1137
    assert got.total.tokens_out == sum(c.figures.tokens_out for c in got.costs)
    assert got.total.cost_usd == pytest.approx(sum(c.figures.cost_usd for c in got.costs))
    assert got.total.duration_s == pytest.approx(sum(c.figures.duration_s for c in got.costs))


def test_ac5_approved_plan_with_no_runs_has_a_zero_total():
    log = FakeEvents()
    plan_created(log, "plan_01", [])
    plan_approved(log, "plan_01")
    got, _ = report(log=log)
    assert got.total == Figures(runs=0, tokens_in=0, tokens_out=0, cost_usd=0, duration_s=0)


# AC6


def test_ac6_only_read_methods_are_called_and_nothing_is_recorded():
    log, records = build_then_replan_log()
    before = len(log.events)
    got, fakes = report(
        approved=PlanRef(id="plan_02", spec_version="sv_01"),
        requirements=[req("REQ-A-001")],
        records=records,
        log=log,
    )
    assert got.refusal is None
    assert set(fakes["plans"].calls) == {"approved"}
    assert set(fakes["versions"].calls) <= {"latest_approved", "spec_set"}
    assert {c[0] for c in fakes["traces"].calls} == {"requirement_trace"}
    assert set(fakes["runs"].calls) == {"all_runs"}
    assert set(log.calls) == {"read"}
    assert len(log.events) == before


def test_ac6_report_module_imports_only_domain_ports_and_cost():
    import openfactory.app.report as mod

    tree = ast.parse(Path(mod.__file__).read_text())
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(a.name for a in node.names)
    own = [m for m in modules if m.startswith("openfactory")]
    assert own
    allowed = ("openfactory.domain", "openfactory.ports", "openfactory.app.cost")
    assert all(m.startswith(allowed) for m in own)
