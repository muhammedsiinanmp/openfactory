"""TASK-064 AC2 to AC5: SqlitePlans.last_gate_result
(docs/tasks/TASK-064-plans-last-gate-result.md)."""

import sqlite3

import pytest

from openfactory.adapters.sqlite_plans import SqlitePlans
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import (
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    GateEvaluatedPayload,
    PlanApprovedPayload,
    PlanCreatedPayload,
)

HASH = "a" * 64
GATES = ["path_check", "ruff", "pytest", "gitleaks", "review"]
TABLES = (
    "events",
    "plans",
    "tasks",
    "task_deps",
    "commits",
    "agent_runs",
    "gate_results",
    "projection_state",
)


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
        required_gates=GATES,
        limits=Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.5),
    )


def ev(stream, type_, payload, actor="orchestrator"):
    return Event.new(
        stream=stream, type=type_, payload=payload.model_dump(mode="json"), actor=actor
    )


def plan_created():
    payload = PlanCreatedPayload(
        plan_id="plan_01",
        spec_version="sv_01",
        policy_hash=HASH,
        run_id="run_0001",
        tasks=[contract("AUTH-001"), contract("AUTH-002")],
    )
    return ev("plan:plan_01", EventType.PlanCreated, payload)


def started(run_id, task_id="AUTH-001", role="implementer"):
    payload = AgentRunStartedPayload(
        run_id=run_id, task_id=task_id, role=role, runtime="claude-code", context_hash=HASH
    )
    return ev(f"run:{run_id}", EventType.AgentRunStarted, payload)


def finished(run_id, exit_="ok"):
    payload = AgentRunFinishedPayload(
        run_id=run_id,
        exit=exit_,
        model="claude-sonnet",
        tokens_in=10,
        tokens_out=5,
        cost_usd=0.01,
        duration_s=1.5,
        error=None if exit_ == "ok" else "boom",
    )
    return ev(f"run:{run_id}", EventType.AgentRunFinished, payload)


def gate(run_id, name, passed, task_id="AUTH-001"):
    payload = GateEvaluatedPayload(
        run_id=run_id, task_id=task_id, gate=name, passed=passed, output_path=None
    )
    return ev(f"task:{task_id}", EventType.GateEvaluated, payload)


def ref(name, passed):
    from openfactory.domain.plans import GateResultRef

    return GateResultRef(gate=name, passed=passed)


@pytest.fixture
def db(tmp_path):
    return tmp_path / "openfactory.db"


@pytest.fixture
def recorder(db):
    rec = SqliteEventRecorder(db)
    yield rec
    rec.close()


@pytest.fixture
def plans(db, recorder):
    adapter = SqlitePlans(db)
    yield adapter
    adapter.close()


@pytest.fixture
def planned(recorder):
    recorder.record(plan_created())
    recorder.record(
        ev("plan:plan_01", EventType.PlanApproved, PlanApprovedPayload(plan_id="plan_01"), "human")
    )


def record_run(recorder, run_id, results, task_id="AUTH-001"):
    recorder.record(started(run_id, task_id))
    recorder.record(finished(run_id))
    for name, passed in results:
        recorder.record(gate(run_id, name, passed, task_id))


# AC2: None cases


def test_ac2_task_without_an_implementer_run_gives_none(planned, plans):
    assert plans.last_gate_result("AUTH-001") is None


def test_ac2_runs_without_a_gate_result_give_none(planned, recorder, plans):
    recorder.record(started("run_0002"))
    recorder.record(finished("run_0002", "error"))
    recorder.record(started("run_0003"))
    assert plans.last_gate_result("AUTH-001") is None


def test_ac2_task_id_without_a_tasks_row_gives_none(planned, recorder, plans):
    record_run(recorder, "run_0002", [("pytest", True)], task_id="GHOST-001")
    assert plans.last_gate_result("GHOST-001") is None


# AC3: last gate in required_gates order


@pytest.mark.parametrize(
    ("results", "expected"),
    [
        ([("path_check", False)], ("path_check", False)),
        (
            [("path_check", True), ("ruff", True), ("pytest", True), ("gitleaks", False)],
            ("gitleaks", False),
        ),
        ([(g, True) for g in GATES], ("review", True)),
    ],
)
def test_ac3_result_is_the_latest_evaluated_gate(planned, recorder, plans, results, expected):
    record_run(recorder, "run_0002", results)
    assert plans.last_gate_result("AUTH-001") == ref(*expected)


def test_ac3_event_order_does_not_matter(planned, recorder, plans):
    record_run(
        recorder,
        "run_0002",
        [("gitleaks", False), ("path_check", True), ("pytest", True), ("ruff", True)],
    )
    assert plans.last_gate_result("AUTH-001") == ref("gitleaks", False)


# AC4: latest implementer run with a gate result


def test_ac4_latest_run_with_results_wins(planned, recorder, plans):
    record_run(recorder, "run_0002", [("path_check", True), ("review", True)])
    record_run(recorder, "run_0003", [("path_check", False)])
    assert plans.last_gate_result("AUTH-001") == ref("path_check", False)


def test_ac4_run_numbers_compare_as_numbers(planned, recorder, plans):
    record_run(recorder, "run_0009", [("review", True)])
    record_run(recorder, "run_0010", [("ruff", False)])
    assert plans.last_gate_result("AUTH-001") == ref("ruff", False)


def test_ac4_later_run_without_results_does_not_hide_earlier(planned, recorder, plans):
    record_run(recorder, "run_0002", [("pytest", True)])
    recorder.record(started("run_0003"))
    recorder.record(finished("run_0003", "error"))
    assert plans.last_gate_result("AUTH-001") == ref("pytest", True)


def test_ac4_other_tasks_runs_never_count(planned, recorder, plans):
    record_run(recorder, "run_0002", [("ruff", True)])
    record_run(recorder, "run_0003", [("review", False)], task_id="AUTH-002")
    assert plans.last_gate_result("AUTH-001") == ref("ruff", True)
    assert plans.last_gate_result("AUTH-002") == ref("review", False)


# AC5: read-only, sees later events


def test_ac5_adapter_opened_early_sees_later_events(planned, recorder, plans):
    assert plans.last_gate_result("AUTH-001") is None
    record_run(recorder, "run_0002", [("path_check", True)])
    assert plans.last_gate_result("AUTH-001") == ref("path_check", True)


def test_ac5_the_read_changes_no_row(db, planned, recorder):
    record_run(recorder, "run_0002", [("path_check", True), ("ruff", False)])

    def snapshot():
        conn = sqlite3.connect(db)
        try:
            return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall() for t in TABLES}
        finally:
            conn.close()

    before = snapshot()
    adapter = SqlitePlans(db)
    adapter.last_gate_result("AUTH-001")
    adapter.close()
    assert snapshot() == before
