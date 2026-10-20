"""TASK-071 AC4: SqlitePlans.tasks gives each task's cost_usd
(docs/tasks/TASK-071-run-cost-limit.md)."""

import pytest

from openfactory.adapters.sqlite_plans import SqlitePlans
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import (
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    PlanCreatedPayload,
)

HASH = "a" * 64


def contract(task_id):
    return TaskContract(
        task_id=task_id,
        objective=f"Do {task_id}",
        requirements=["REQ-AUTH-001"],
        acceptance_criteria=["AC-AUTH-001-1"],
        depends_on=[],
        components=["auth"],
        role="implementer",
        allowed_paths=["app/auth/**"],
        forbidden_paths=["specs/**"],
        required_gates=["path_check", "ruff", "pytest", "gitleaks", "review"],
        limits=Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.5),
    )


def ev(stream, type_, payload, actor="orchestrator"):
    return Event.new(stream=stream, type=type_, payload=payload, actor=actor)


def plan_created():
    payload = PlanCreatedPayload(
        plan_id="plan_01",
        spec_version="sv_01",
        policy_hash=HASH,
        run_id="run_0001",
        tasks=[contract("AUTH-001"), contract("AUTH-002")],
    ).model_dump(mode="json")
    return ev("plan:plan_01", EventType.PlanCreated, payload)


def run(run_id, task_id, cost):
    started = AgentRunStartedPayload(
        run_id=run_id, task_id=task_id, role="implementer", runtime="claude-code", context_hash=HASH
    ).model_dump(mode="json")
    finished = AgentRunFinishedPayload(
        run_id=run_id,
        exit="ok",
        model="m",
        tokens_in=1,
        tokens_out=1,
        cost_usd=cost,
        duration_s=1.0,
        error=None,
    ).model_dump(mode="json")
    return [
        ev(f"run:{run_id}", EventType.AgentRunStarted, started),
        ev(f"run:{run_id}", EventType.AgentRunFinished, finished),
    ]


@pytest.fixture
def recorder(tmp_path):
    r = SqliteEventRecorder(tmp_path / "of.db")
    yield r
    r.close()


@pytest.fixture
def plans(recorder, tmp_path):
    return SqlitePlans(tmp_path / "of.db")


def costs(plans):
    return {t.id: t.cost_usd for t in plans.tasks("plan_01")}


def test_task071_ac4_a_new_task_has_cost_zero(recorder, plans):
    recorder.record(plan_created())
    assert costs(plans) == {"AUTH-001": 0, "AUTH-002": 0}


def test_task071_ac4_cost_is_the_sum_of_runs_with_nulls_as_zero(recorder, plans):
    recorder.record(plan_created())
    for e in [*run("run_0002", "AUTH-001", 0.25), *run("run_0003", "AUTH-001", None)]:
        recorder.record(e)
    for e in run("run_0004", "AUTH-001", 0.5):
        recorder.record(e)
    assert costs(plans) == {"AUTH-001": 0.75, "AUTH-002": 0}


def test_task071_ac4_a_retry_resets_the_cost_to_zero(recorder, plans):
    recorder.record(plan_created())
    for e in run("run_0002", "AUTH-001", 0.25):
        recorder.record(e)
    recorder.record(
        ev(
            "task:AUTH-001",
            EventType.TaskResolved,
            {"task_id": "AUTH-001", "decision": "retry"},
            actor="human",
        )
    )
    assert costs(plans)["AUTH-001"] == 0
