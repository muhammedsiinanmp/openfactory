"""TASK-058 AC4 (projector parts) and AC5: TaskResolved is validated and writes nothing;
tasks.cost_usd exists (docs/tasks/TASK-058-task-resolved-cost-column-and-gates-removal.md)."""

import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from openfactory.adapters.sqlite_projector import SqliteProjector
from openfactory.adapters.sqlite_store import SqliteEventStore
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import PlanCreatedPayload

HASH = "a" * 64


def contract(task_id, depends_on=()):
    return TaskContract(
        task_id=task_id,
        objective="Do the work",
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


def make_event(stream, type, payload, actor="orchestrator"):
    return Event(
        event_id=uuid4(),
        stream=stream,
        type=type,
        payload=payload,
        actor=actor,
        created_at=datetime.now(UTC),
    )


def plan_created():
    payload = PlanCreatedPayload(
        plan_id="plan_01",
        spec_version="sv_01",
        policy_hash=HASH,
        run_id="run_0001",
        tasks=[contract("AUTH-001"), contract("AUTH-002", ["AUTH-001"])],
    ).model_dump(mode="json")
    return make_event("plan:plan_01", EventType.PlanCreated, payload)


def task_resolved(decision="abandon"):
    return make_event(
        "task:AUTH-002",
        EventType["TaskResolved"],
        {"task_id": "AUTH-002", "decision": decision},
        actor="human",
    )


def snapshot(conn):
    """Every row of every table, by table name."""
    names = [
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
    ]
    return {n: conn.execute(f"SELECT * FROM {n} ORDER BY 1, 2").fetchall() for n in names}


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


# AC4: the projector validates TaskResolved and changes no row


def test_ac4_abandon_after_plan_created_changes_no_table(conn, projector, store):
    projector.apply(store.append(plan_created()))
    before = snapshot(conn)
    assert before["tasks"]
    projector.apply(store.append(task_resolved("abandon")))
    assert snapshot(conn) == before


def test_ac4_rejected_payload_raises_and_changes_nothing(conn, projector, store):
    projector.apply(store.append(plan_created()))
    before = snapshot(conn)
    bad = task_resolved("retry")
    bad.payload["decision"] = "skip"
    with pytest.raises(ValidationError):
        projector.apply(store.append(bad))
    assert snapshot(conn) == before


# AC5: tasks.cost_usd


def test_ac5_cost_usd_is_the_last_tasks_column_real_not_null_default_zero(conn, projector):
    cid, name, ctype, notnull, default, pk = conn.execute("PRAGMA table_info(tasks)").fetchall()[-1]
    assert name == "cost_usd"
    assert ctype.upper() == "REAL"
    assert notnull == 1
    assert float(default) == 0


def test_ac5_plan_created_rows_have_cost_usd_zero(conn, projector, store):
    projector.apply(store.append(plan_created()))
    rows = conn.execute("SELECT id, cost_usd FROM tasks ORDER BY id").fetchall()
    assert rows == [("AUTH-001", 0.0), ("AUTH-002", 0.0)]
