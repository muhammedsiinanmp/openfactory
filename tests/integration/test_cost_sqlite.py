"""TASK-108 AC6: attribute_costs on real SQLite gives the figures of a build and a replan."""

import pytest

from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.adapters.sqlite_runs import SqliteRuns
from openfactory.adapters.sqlite_store import SqliteEventStore
from openfactory.app.cost import attribute_costs
from openfactory.domain.contracts import REQUIRED_GATES, Limits, TaskContract
from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import (
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    ImpactComputedPayload,
    PlanApprovedPayload,
    PlanCreatedPayload,
)

HASH = "a" * 64


def event(stream, type_, payload, cause=None):
    return Event.new(
        stream=stream,
        type=type_,
        payload=payload.model_dump(mode="json"),
        actor="orchestrator",
        causation_id=cause.event_id if cause else None,
    )


def run(rec, run_id, role, task_id=None, cause=None, tin=10):
    started = rec.record(
        event(
            f"run:{run_id}",
            EventType.AgentRunStarted,
            AgentRunStartedPayload(
                run_id=run_id, task_id=task_id, role=role, runtime="claude-code", context_hash=HASH
            ),
            cause,
        )
    )
    return rec.record(
        event(
            f"run:{run_id}",
            EventType.AgentRunFinished,
            AgentRunFinishedPayload(
                run_id=run_id,
                exit="ok",
                model=None,
                tokens_in=tin,
                tokens_out=1,
                cost_usd=0.5,
                duration_s=2.0,
                error=None,
            ),
            started,
        )
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


def plan(rec, plan_id, task_ids, cause, run_id):
    return rec.record(
        event(
            f"plan:{plan_id}",
            EventType.PlanCreated,
            PlanCreatedPayload(
                plan_id=plan_id,
                spec_version="sv_01",
                policy_hash=HASH,
                run_id=run_id,
                tasks=[contract(t) for t in task_ids],
            ),
            cause,
        )
    )


def test_ac6_real_sqlite_gives_the_figures_of_one_build_and_one_replan(tmp_path):
    db = tmp_path / "openfactory.db"
    rec = SqliteEventRecorder(db)
    store = SqliteEventStore(db)
    runs = SqliteRuns(db)
    try:
        last = run(rec, "run_0001", "planner", tin=1)
        plan(rec, "plan_01", ["TASK-001"], last, "run_0001")
        rec.record(
            event("plan:plan_01", EventType.PlanApproved, PlanApprovedPayload(plan_id="plan_01"))
        )
        run(rec, "run_0002", "implementer", "TASK-001", tin=2)
        run(rec, "run_0003", "reviewer", "TASK-001", tin=4)
        cls = run(rec, "run_0004", "classifier", tin=8)
        rec.record(
            event(
                "spec:sv_02",
                EventType.ImpactComputed,
                ImpactComputedPayload(
                    from_version="sv_01",
                    to_version="sv_02",
                    run_id="run_0004",
                    requirements=[],
                    adrs=[],
                    tasks=[],
                    downstream=[],
                    files=[],
                    tests=[],
                ),
                cls,
            )
        )
        last = run(rec, "run_0005", "planner", tin=16)
        plan(rec, "plan_02", ["TASK-002"], last, "run_0005")
        run(rec, "run_0006", "implementer", "TASK-002", tin=32)

        got = attribute_costs(runs=runs, events=store)
    finally:
        runs.close()
        rec.close()

    assert got.tasks["TASK-001"].model_dump() == {
        "runs": 2,
        "tokens_in": 6,
        "tokens_out": 2,
        "cost_usd": pytest.approx(1.0),
        "duration_s": 4.0,
    }
    assert got.plans["plan_01"].runs == 3
    assert got.plans["plan_01"].tokens_in == 7
    assert got.plans["plan_02"].runs == 3
    assert got.plans["plan_02"].tokens_in == 8 + 16 + 32
