"""TASK-022 AC1..AC6: the projector for plans, tasks and task_deps
(docs/tasks/TASK-022-projector-plan-task-tables.md)."""

import json
import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from openfactory.adapters.sqlite_projector import SqliteProjector
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.adapters.sqlite_store import SqliteEventStore
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import (
    PlanApprovedPayload,
    PlanCreatedPayload,
    TaskStateChangedPayload,
)

HASH = "a" * 64

M2_TABLES = ("plans", "tasks", "task_deps")
ORDER = {"plans": "id", "tasks": "id", "task_deps": "task_id, depends_on"}


def contract(task_id, objective="Do the work", depends_on=()):
    return TaskContract(
        task_id=task_id,
        objective=objective,
        requirements=["REQ-AUTH-001"],
        acceptance_criteria=["AC-AUTH-001-1", "AC-AUTH-001-2"],
        depends_on=list(depends_on),
        components=["auth"],
        role="implementer",
        allowed_paths=["app/auth/**", "tests/auth/**"],
        forbidden_paths=["specs/**", ".env"],
        required_gates=["path_check", "ruff", "pytest", "gitleaks", "review"],
        limits=Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.5),
    )


AUTH_001 = contract("AUTH-001", "Create the user model")
AUTH_002 = contract("AUTH-002", "Implement login endpoint", ["AUTH-001"])
AUTH_002_NEW = contract("AUTH-002", "Implement login with tokens")
AUTH_003 = contract("AUTH-003", "Add logout", ["AUTH-002"])


def plan_payload(plan_id, tasks):
    return PlanCreatedPayload(
        plan_id=plan_id, spec_version="sv_01", policy_hash=HASH, run_id="run_0001", tasks=tasks
    ).model_dump(mode="json")


def make_event(stream, type, payload, actor="orchestrator"):
    return Event(
        event_id=uuid4(),
        stream=stream,
        type=type,
        payload=payload,
        actor=actor,
        created_at=datetime.now(UTC),
    )


def plan_created(plan_id="plan_01", tasks=(AUTH_001, AUTH_002)):
    payload = plan_payload(plan_id, list(tasks))
    return make_event(f"plan:{plan_id}", EventType.PlanCreated, payload)


def plan_approved(plan_id="plan_01"):
    payload = PlanApprovedPayload(plan_id=plan_id).model_dump(mode="json")
    return make_event(f"plan:{plan_id}", EventType.PlanApproved, payload, actor="human")


def state_changed(task_id, from_, to):
    payload = TaskStateChangedPayload.model_validate(
        {"task_id": task_id, "from": from_, "to": to, "reason": None}
    ).model_dump(mode="json")
    return make_event(f"task:{task_id}", EventType.TaskStateChanged, payload)


def snapshot(conn):
    """Every row of the three tables, in primary-key order."""
    return {
        table: conn.execute(f"SELECT * FROM {table} ORDER BY {ORDER[table]}").fetchall()
        for table in M2_TABLES
    }


@pytest.fixture
def conn(tmp_path):
    connection = sqlite3.connect(tmp_path / "projections.db")
    yield connection
    connection.close()


@pytest.fixture
def projector(conn):
    p = SqliteProjector(conn)
    p.create_tables()
    return p


@pytest.fixture
def store(tmp_path):
    s = SqliteEventStore(tmp_path / "events.db")
    yield s
    s.close()


# AC1: tables exist, no FK or CHECK, create_tables is idempotent


def test_ac1_creates_the_plan_and_task_tables_next_to_the_m1_tables(conn, projector, store):
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"spec_versions", "requirements", "adrs", *M2_TABLES} <= names


def test_ac1_no_foreign_key_and_no_check_constraint(conn, projector, store):
    for table in M2_TABLES:
        assert conn.execute(f"PRAGMA table_info({table})").fetchall()
        assert conn.execute(f"PRAGMA foreign_key_list({table})").fetchall() == []
    sql = " ".join(r[0] for r in conn.execute("SELECT sql FROM sqlite_master WHERE type='table'"))
    assert "CHECK" not in sql.upper()


def test_ac1_create_tables_twice_changes_no_row(conn, projector, store):
    projector.apply(store.append(plan_created()))
    before = snapshot(conn)
    assert before["tasks"]
    projector.create_tables()
    assert snapshot(conn) == before


# AC2: PlanCreated projects the plan, its tasks and their dependencies


def test_ac2_plan_created_writes_plan_task_and_dependency_rows(conn, projector, store):
    projector.apply(store.append(plan_created()))
    assert conn.execute("SELECT * FROM plans").fetchall() == [("plan_01", "sv_01", "draft")]

    rows = conn.execute(
        "SELECT id, plan_id, state, objective, attempt, contract FROM tasks ORDER BY id"
    ).fetchall()
    assert [r[:5] for r in rows] == [
        ("AUTH-001", "plan_01", "pending", AUTH_001.objective, 0),
        ("AUTH-002", "plan_01", "pending", AUTH_002.objective, 0),
    ]
    for row, expected in zip(rows, (AUTH_001, AUTH_002), strict=True):
        assert json.loads(row[5]) == expected.model_dump(mode="json")

    assert conn.execute("SELECT task_id, depends_on FROM task_deps").fetchall() == [
        ("AUTH-002", "AUTH-001")
    ]


# AC3: a new draft supersedes the earlier one


def test_ac3_new_draft_supersedes_the_earlier_one_and_removes_its_tasks(conn, projector, store):
    projector.apply(store.append(plan_created()))
    projector.apply(store.append(plan_created("plan_02", [AUTH_002_NEW, AUTH_003])))

    assert conn.execute("SELECT * FROM plans ORDER BY id").fetchall() == [
        ("plan_01", "sv_01", "superseded"),
        ("plan_02", "sv_01", "draft"),
    ]
    rows = conn.execute("SELECT id, plan_id, objective, contract FROM tasks ORDER BY id").fetchall()
    assert [r[:3] for r in rows] == [
        ("AUTH-002", "plan_02", AUTH_002_NEW.objective),
        ("AUTH-003", "plan_02", AUTH_003.objective),
    ]
    assert json.loads(rows[0][3]) == AUTH_002_NEW.model_dump(mode="json")
    assert conn.execute("SELECT task_id, depends_on FROM task_deps").fetchall() == [
        ("AUTH-003", "AUTH-002")
    ]


def test_ac3_new_draft_leaves_an_approved_plan_and_its_tasks(conn, projector, store):
    projector.apply(store.append(plan_created()))
    projector.apply(store.append(plan_approved()))
    before = snapshot(conn)

    projector.apply(store.append(plan_created("plan_02", [AUTH_003])))
    after = snapshot(conn)
    assert after["plans"] == [("plan_01", "sv_01", "approved"), ("plan_02", "sv_01", "draft")]
    assert [r for r in after["tasks"] if r[1] == "plan_01"] == before["tasks"]
    assert ("AUTH-002", "AUTH-001") in after["task_deps"]


# AC4: approval and task state changes


def test_ac4_plan_approved_sets_status_and_touches_no_task(conn, projector, store):
    projector.apply(store.append(plan_created()))
    before = snapshot(conn)
    projector.apply(store.append(plan_approved()))
    after = snapshot(conn)
    assert after["plans"] == [("plan_01", "sv_01", "approved")]
    assert after["tasks"] == before["tasks"]
    assert after["task_deps"] == before["task_deps"]
    assert {r[2] for r in after["tasks"]} == {"pending"}


def test_ac4_task_state_changed_sets_state_and_nothing_else(conn, projector, store):
    projector.apply(store.append(plan_created()))
    projector.apply(store.append(plan_approved()))
    before = {r[0]: r for r in snapshot(conn)["tasks"]}

    projector.apply(store.append(state_changed("AUTH-001", "pending", "ready")))
    rows = {r[0]: r for r in snapshot(conn)["tasks"]}
    assert rows["AUTH-001"] == (*before["AUTH-001"][:2], "ready", *before["AUTH-001"][3:])
    assert rows["AUTH-002"] == before["AUTH-002"]

    projector.apply(store.append(state_changed("AUTH-001", "ready", "running")))
    rows = {r[0]: r for r in snapshot(conn)["tasks"]}
    assert rows["AUTH-001"][2] == "running"
    assert rows["AUTH-001"][5] == 1


# AC5: invalid payloads raise and write nothing


def test_ac5_plan_created_the_model_rejects_raises_and_supersedes_nothing(conn, projector, store):
    projector.apply(store.append(plan_created()))
    before = snapshot(conn)
    bad = plan_created("plan_02", [AUTH_003])
    del bad.payload["tasks"][0]["limits"]
    with pytest.raises(ValidationError):
        projector.apply(store.append(bad))
    assert snapshot(conn) == before
    assert before["plans"] == [("plan_01", "sv_01", "draft")]
    assert len(before["tasks"]) == 2


def test_ac5_plan_approved_the_model_rejects_raises_and_changes_nothing(conn, projector, store):
    projector.apply(store.append(plan_created()))
    before = snapshot(conn)
    bad = make_event("plan:plan_01", EventType.PlanApproved, {"plan_id": "p1"}, actor="human")
    with pytest.raises(ValidationError):
        projector.apply(store.append(bad))
    assert snapshot(conn) == before


# AC6: rebuild is identical, through the projector and through the recorder


def log_events():
    return [
        plan_created(),
        plan_created("plan_02", [AUTH_002_NEW, AUTH_003]),
        plan_approved("plan_02"),
        state_changed("AUTH-002", "pending", "ready"),
        state_changed("AUTH-002", "ready", "running"),
    ]


def test_ac6_rebuild_gives_identical_rows(conn, projector, store):
    for event in log_events():
        projector.apply(store.append(event))
    before = snapshot(conn)
    assert before["plans"] and before["tasks"] and before["task_deps"]
    projector.rebuild(store.read())
    assert snapshot(conn) == before


def test_ac6_rebuild_drops_a_task_row_no_event_produced(conn, projector, store):
    for event in log_events():
        projector.apply(store.append(event))
    conn.execute("INSERT INTO tasks VALUES ('ZZZ-999', 'plan_09', 'pending', 'o', '{}', 0)")
    projector.rebuild(store.read())
    assert conn.execute("SELECT 1 FROM tasks WHERE id = 'ZZZ-999'").fetchall() == []


def test_ac6_recorder_projects_the_same_rows_and_its_rebuild_keeps_them(
    conn, projector, store, tmp_path
):
    for event in log_events():
        projector.apply(store.append(event))
    expected = snapshot(conn)

    db = tmp_path / "recorded.db"
    recorder = SqliteEventRecorder(db)
    try:
        for event in log_events():
            recorder.record(event)
        other = sqlite3.connect(db)
        try:
            assert snapshot(other) == expected
            recorder.rebuild()
            assert snapshot(other) == expected
        finally:
            other.close()
    finally:
        recorder.close()
