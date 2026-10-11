"""TASK-025 AC2 to AC6: SqlitePlans (docs/tasks/TASK-025-plans-port-sqlite.md)."""

import sqlite3

import pytest

from openfactory.adapters.sqlite_plans import SqlitePlans
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import (
    PlanApprovedPayload,
    PlanCreatedPayload,
    TaskStateChangedPayload,
)
from openfactory.domain.plans import PlanRef, Task
from openfactory.domain.states import TaskState

HASH = "a" * 64
TABLES = ("events", "plans", "tasks", "task_deps", "projection_state")


def contract(task_id, requirements=("REQ-AUTH-001",), depends_on=()):
    return TaskContract(
        task_id=task_id,
        objective=f"Do {task_id}",
        requirements=list(requirements),
        acceptance_criteria=["AC-AUTH-001-1"],
        depends_on=list(depends_on),
        components=["auth"],
        role="implementer",
        allowed_paths=["app/auth/**"],
        forbidden_paths=["specs/**"],
        required_gates=["path_check", "ruff", "pytest", "gitleaks", "review"],
        limits=Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.5),
    )


AUTH_001 = contract("AUTH-001")
AUTH_002 = contract("AUTH-002", depends_on=["AUTH-001"])
AUTH_003 = contract("AUTH-003", depends_on=["AUTH-001", "AUTH-002"])


def plan_created(plan_id="plan_01", tasks=(AUTH_001,), spec_version="sv_01"):
    payload = PlanCreatedPayload(
        plan_id=plan_id,
        spec_version=spec_version,
        policy_hash=HASH,
        run_id="run_0001",
        tasks=list(tasks),
    )
    return Event.new(
        stream=f"plan:{plan_id}",
        type=EventType.PlanCreated,
        payload=payload.model_dump(mode="json"),
        actor="orchestrator",
    )


def plan_approved(plan_id="plan_01"):
    payload = PlanApprovedPayload(plan_id=plan_id)
    return Event.new(
        stream=f"plan:{plan_id}",
        type=EventType.PlanApproved,
        payload=payload.model_dump(mode="json"),
        actor="human",
    )


def state_changed(task_id, from_, to, reason=None):
    payload = TaskStateChangedPayload.model_validate(
        {"task_id": task_id, "from": from_, "to": to, "reason": reason}
    )
    return Event.new(
        stream=f"task:{task_id}",
        type=EventType.TaskStateChanged,
        payload=payload.model_dump(mode="json"),
        actor="orchestrator",
    )


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


# AC2: next plan id


def test_ac2_empty_log_gives_plan_01(plans):
    assert plans.next_id() == "plan_01"


def test_ac2_next_id_counts_superseded_plans(recorder, plans):
    recorder.record(plan_created("plan_01"))
    assert plans.next_id() == "plan_02"
    recorder.record(plan_created("plan_02"))
    assert plans.next_id() == "plan_03"
    recorder.record(plan_approved("plan_02"))
    assert plans.next_id() == "plan_03"


def test_ac2_ids_widen_past_two_digits(recorder, plans):
    recorder.record(plan_created("plan_99"))
    assert plans.next_id() == "plan_100"


# AC3: current draft and approved plan


def test_ac3_empty_log_has_no_draft_and_no_approved(plans):
    assert plans.current_draft() is None
    assert plans.approved() is None


def test_ac3_created_plan_is_the_draft(recorder, plans):
    recorder.record(plan_created("plan_01"))
    assert plans.current_draft() == PlanRef(id="plan_01", spec_version="sv_01")
    assert plans.approved() is None


def test_ac3_a_second_plan_supersedes_the_first(recorder, plans):
    recorder.record(plan_created("plan_01"))
    recorder.record(plan_created("plan_02"))
    assert plans.current_draft() == PlanRef(id="plan_02", spec_version="sv_01")
    assert plans.approved() is None


def test_ac3_approval_moves_the_draft_to_approved(recorder, plans):
    recorder.record(plan_created("plan_01"))
    recorder.record(plan_created("plan_02"))
    recorder.record(plan_approved("plan_02"))
    assert plans.current_draft() is None
    assert plans.approved() == PlanRef(id="plan_02", spec_version="sv_01")


# AC4: tasks of a plan


def test_ac4_tasks_come_back_in_id_order_with_dependencies(recorder, plans):
    recorder.record(plan_created("plan_01", [AUTH_003, AUTH_001, AUTH_002]))
    result = plans.tasks("plan_01")
    assert [t.id for t in result] == ["AUTH-001", "AUTH-002", "AUTH-003"]
    assert all(isinstance(t, Task) for t in result)
    assert all(t.plan_id == "plan_01" for t in result)
    assert all(t.state == TaskState.pending for t in result)
    assert all(t.attempt == 0 for t in result)
    assert [t.contract for t in result] == [AUTH_001, AUTH_002, AUTH_003]
    assert [t.depends_on for t in result] == [[], ["AUTH-001"], ["AUTH-001", "AUTH-002"]]


def test_ac4_tasks_show_the_state_the_projection_holds(recorder, plans):
    recorder.record(plan_created("plan_01", [AUTH_001, AUTH_002, AUTH_003]))
    recorder.record(plan_approved("plan_01"))
    recorder.record(state_changed("AUTH-001", "pending", "ready"))
    states = {t.id: t.state for t in plans.tasks("plan_01")}
    assert states == {
        "AUTH-001": TaskState.ready,
        "AUTH-002": TaskState.pending,
        "AUTH-003": TaskState.pending,
    }


def test_ac4_superseded_and_unknown_plans_have_no_tasks(recorder, plans):
    recorder.record(plan_created("plan_01", [AUTH_001, AUTH_002]))
    recorder.record(plan_created("plan_02", [AUTH_001]))
    assert plans.tasks("plan_01") == []
    assert plans.tasks("plan_07") == []


# AC5: live tasks referencing a requirement

R1 = "REQ-AUTH-001"
R2 = "REQ-AUTH-002"
REF_TASKS = (
    contract("AUTH-002", requirements=[R1]),
    contract("AUTH-003", requirements=[R2]),
    contract("AUTH-001", requirements=[R1]),
)


def test_ac5_draft_and_approved_tasks_count_in_id_order(recorder, plans):
    recorder.record(plan_created("plan_01", REF_TASKS))
    assert plans.live_tasks_referencing(R1) == ["AUTH-001", "AUTH-002"]
    recorder.record(plan_approved("plan_01"))
    assert plans.live_tasks_referencing(R1) == ["AUTH-001", "AUTH-002"]


def test_ac5_invalidated_and_abandoned_tasks_do_not_count(recorder, plans):
    recorder.record(plan_created("plan_01", REF_TASKS))
    recorder.record(plan_approved("plan_01"))
    recorder.record(state_changed("AUTH-001", "pending", "invalidated", reason="req changed"))
    assert plans.live_tasks_referencing(R1) == ["AUTH-002"]
    recorder.record(state_changed("AUTH-002", "pending", "abandoned"))
    assert plans.live_tasks_referencing(R1) == []


def test_ac5_a_requirement_no_task_lists_gives_empty(recorder, plans):
    recorder.record(plan_created("plan_01", REF_TASKS))
    assert plans.live_tasks_referencing("REQ-AUTH-009") == []


def test_ac5_tasks_of_a_superseded_draft_do_not_count(recorder, plans):
    recorder.record(plan_created("plan_01", REF_TASKS))
    recorder.record(plan_created("plan_02", [contract("AUTH-001", requirements=[R2])]))
    assert plans.live_tasks_referencing(R1) == []


# AC6: read-only, and sees later events


def snapshot(db):
    conn = sqlite3.connect(db)
    try:
        return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall() for t in TABLES}
    finally:
        conn.close()


def test_ac6_the_five_reads_change_no_row(db, recorder):
    recorder.record(plan_created("plan_01", [AUTH_001, AUTH_002]))
    recorder.record(plan_created("plan_02", [AUTH_001, AUTH_002]))
    recorder.record(plan_approved("plan_02"))
    recorder.record(state_changed("AUTH-001", "pending", "ready"))
    before = snapshot(db)
    adapter = SqlitePlans(db)
    adapter.current_draft()
    adapter.approved()
    adapter.next_id()
    adapter.tasks("plan_02")
    adapter.live_tasks_referencing(R1)
    adapter.close()
    assert snapshot(db) == before


def test_ac6_adapter_opened_early_sees_later_events(recorder, plans):
    assert plans.next_id() == "plan_01"
    assert plans.current_draft() is None
    recorder.record(plan_created("plan_01"))
    assert plans.next_id() == "plan_02"
    assert plans.current_draft() == PlanRef(id="plan_01", spec_version="sv_01")
