"""TASK-075 AC4: resolve_task against the real SqliteEventRecorder and SqlitePlans
(docs/tasks/TASK-075-resolve-use-case.md)."""

import pytest

from openfactory.adapters.sqlite_plans import SqlitePlans
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.app.resolve import resolve_task
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import (
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    PlanApprovedPayload,
    PlanCreatedPayload,
)
from openfactory.domain.states import TaskState

HASH = "a" * 64


def _contract(task_id):
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


def _ev(stream, type_, payload, actor="orchestrator"):
    return Event.new(stream=stream, type=type_, payload=payload, actor=actor)


def _move(task_id, from_, to, reason=None):
    return _ev(
        f"task:{task_id}",
        EventType.TaskStateChanged,
        {"task_id": task_id, "from": from_, "to": to, "reason": reason},
    )


@pytest.fixture
def recorder(tmp_path):
    r = SqliteEventRecorder(tmp_path / "of.db")
    yield r
    r.close()


@pytest.fixture
def plans(recorder, tmp_path):
    return SqlitePlans(tmp_path / "of.db")


def _escalate(recorder, task_id, reason):
    """Plan with `task_id` approved, run once at cost 0.75, failed, then escalated."""
    created = PlanCreatedPayload(
        plan_id="plan_01",
        spec_version="sv_01",
        policy_hash=HASH,
        run_id="run_0001",
        tasks=[_contract(task_id)],
    ).model_dump(mode="json")
    recorder.record(_ev("plan:plan_01", EventType.PlanCreated, created))
    recorder.record(
        _ev(
            "plan:plan_01",
            EventType.PlanApproved,
            PlanApprovedPayload(plan_id="plan_01").model_dump(mode="json"),
            actor="human",
        )
    )
    recorder.record(_move(task_id, "pending", "ready"))
    recorder.record(_move(task_id, "ready", "running"))
    started = AgentRunStartedPayload(
        run_id="run_0002",
        task_id=task_id,
        role="implementer",
        runtime="claude-code",
        context_hash=HASH,
    ).model_dump(mode="json")
    finished = AgentRunFinishedPayload(
        run_id="run_0002",
        exit="ok",
        model="m",
        tokens_in=1,
        tokens_out=1,
        cost_usd=0.75,
        duration_s=1.0,
        error=None,
    ).model_dump(mode="json")
    recorder.record(_ev("run:run_0002", EventType.AgentRunStarted, started))
    recorder.record(_ev("run:run_0002", EventType.AgentRunFinished, finished))
    recorder.record(_move(task_id, "running", "failed"))
    recorder.record(_move(task_id, "failed", "escalated", reason))


def _only(plans):
    (task,) = plans.tasks("plan_01")
    return task


def test_ac4_retry_of_a_path_violation_escalation_resets_attempt_and_cost(recorder, plans):
    _escalate(recorder, "AUTH-001", "path violation")
    before = _only(plans)
    assert (before.state, before.attempt, before.cost_usd) == (TaskState.escalated, 1, 0.75)

    result = resolve_task("AUTH-001", "retry", plans=plans, recorder=recorder)

    assert result.refusal is None
    after = _only(plans)
    assert after.state is TaskState.ready
    assert after.attempt == 0
    assert after.cost_usd == 0


def test_ac4_abandon_of_a_secret_escalation_keeps_attempt_and_cost(recorder, plans):
    _escalate(recorder, "AUTH-001", "secret found")

    result = resolve_task("AUTH-001", "abandon", plans=plans, recorder=recorder)

    assert result.refusal is None
    after = _only(plans)
    assert after.state is TaskState.abandoned
    assert after.attempt == 1
    assert after.cost_usd == 0.75
