"""TASK-065 AC1..AC5: the projector keeps tasks.cost_usd and resets it on a retry
(docs/tasks/TASK-065-projector-task-cost-and-retry-reset.md)."""

import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from openfactory.adapters.sqlite_projector import SqliteProjector
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.adapters.sqlite_store import SqliteEventStore
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import (
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    PlanCreatedPayload,
)

HASH = "a" * 64
T0 = datetime(2026, 10, 20, 9, 0, 0, tzinfo=UTC)


def at(n):
    return T0 + timedelta(minutes=n)


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


def make_event(stream, type, payload, created_at, actor="orchestrator"):
    return Event(
        event_id=uuid4(),
        stream=stream,
        type=type,
        payload=payload,
        actor=actor,
        created_at=created_at,
    )


def plan_created():
    payload = PlanCreatedPayload(
        plan_id="plan_01",
        spec_version="sv_01",
        policy_hash=HASH,
        run_id="run_0001",
        tasks=[contract("AUTH-001"), contract("AUTH-002", ["AUTH-001"])],
    ).model_dump(mode="json")
    return make_event("plan:plan_01", EventType.PlanCreated, payload, at(0))


def to_running(task_id, n):
    return make_event(
        f"task:{task_id}",
        EventType.TaskStateChanged,
        {"task_id": task_id, "from": "ready", "to": "running", "reason": None},
        at(n),
    )


def run_started(run_id, task_id, n, role="implementer"):
    payload = AgentRunStartedPayload(
        run_id=run_id, task_id=task_id, role=role, runtime="claude-code", context_hash=HASH
    ).model_dump(mode="json")
    return make_event(f"run:{run_id}", EventType.AgentRunStarted, payload, at(n))


def run_finished(run_id, cost_usd, n):
    payload = AgentRunFinishedPayload(
        run_id=run_id,
        exit="ok",
        model="claude-sonnet",
        tokens_in=10,
        tokens_out=5,
        cost_usd=cost_usd,
        duration_s=1.0,
        error=None,
    ).model_dump(mode="json")
    return make_event(f"run:{run_id}", EventType.AgentRunFinished, payload, at(n))


def task_resolved(task_id, decision, n):
    return make_event(
        f"task:{task_id}",
        EventType.TaskResolved,
        {"task_id": task_id, "decision": decision},
        at(n),
        actor="human",
    )


def finished_run(run_id, task_id, cost_usd, n, role="implementer"):
    return [run_started(run_id, task_id, n, role), run_finished(run_id, cost_usd, n + 1)]


def setup_events():
    """AUTH-001: attempt 1, cost 0.75. AUTH-002: attempt 2, cost 0.375."""
    return [
        plan_created(),
        to_running("AUTH-001", 1),
        *finished_run("run_0002", "AUTH-001", 0.25, 2),
        *finished_run("run_0003", "AUTH-001", 0.5, 4),
        to_running("AUTH-002", 6),
        to_running("AUTH-002", 7),
        *finished_run("run_0004", "AUTH-002", 0.25, 8),
        *finished_run("run_0005", "AUTH-002", 0.125, 10),
    ]


def tasks_by_id(conn):
    cur = conn.execute("SELECT * FROM tasks ORDER BY id")
    cols = [d[0] for d in cur.description]
    return {r[0]: dict(zip(cols, r, strict=True)) for r in cur.fetchall()}


def snapshot(conn):
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


def apply_all(projector, store, events):
    for event in events:
        projector.apply(store.append(event))


# AC1: finished runs add their cost to the run's task


def test_ac1_two_runs_sum_on_their_task_and_change_no_other_column(conn, projector, store):
    apply_all(projector, store, [plan_created()])
    before = tasks_by_id(conn)
    apply_all(
        projector,
        store,
        [
            *finished_run("run_0002", "AUTH-001", 0.25, 1),
            *finished_run("run_0003", "AUTH-001", 0.5, 3),
        ],
    )
    after = tasks_by_id(conn)
    assert after["AUTH-001"] == {**before["AUTH-001"], "cost_usd": 0.75}
    assert after["AUTH-002"] == before["AUTH-002"]
    assert after["AUTH-002"]["cost_usd"] == 0


def test_ac1_a_reviewer_run_counts_like_an_implementer_run(conn, projector, store):
    apply_all(
        projector,
        store,
        [
            plan_created(),
            *finished_run("run_0002", "AUTH-001", 0.25, 1),
            *finished_run("run_0003", "AUTH-001", 0.125, 3, role="reviewer"),
        ],
    )
    assert tasks_by_id(conn)["AUTH-001"]["cost_usd"] == 0.375


# AC2: a null cost adds 0, a run with no task adds nothing


def test_ac2_null_cost_leaves_the_task_cost_unchanged(conn, projector, store):
    apply_all(projector, store, [plan_created(), *finished_run("run_0002", "AUTH-001", 0.25, 1)])
    before = tasks_by_id(conn)
    apply_all(projector, store, finished_run("run_0003", "AUTH-001", None, 3))
    assert tasks_by_id(conn) == before
    assert before["AUTH-001"]["cost_usd"] == 0.25


def test_ac2_a_planner_run_without_a_task_changes_no_tasks_row(conn, projector, store):
    apply_all(projector, store, [plan_created()])
    before = tasks_by_id(conn)
    apply_all(projector, store, finished_run("run_0002", None, 0.5, 1, role="planner"))
    assert tasks_by_id(conn) == before


# AC3: retry resets attempt and cost of its task only


def test_ac3_retry_resets_attempt_and_cost_of_its_task_only(conn, projector, store):
    apply_all(projector, store, setup_events())
    before = tasks_by_id(conn)
    assert before["AUTH-002"]["attempt"] == 2
    assert before["AUTH-002"]["cost_usd"] == 0.375
    apply_all(projector, store, [task_resolved("AUTH-002", "retry", 20)])
    after = tasks_by_id(conn)
    assert after["AUTH-002"] == {**before["AUTH-002"], "attempt": 0, "cost_usd": 0}
    assert after["AUTH-001"] == before["AUTH-001"]


def test_ac3_after_a_retry_the_next_attempt_and_run_start_from_zero(conn, projector, store):
    apply_all(projector, store, setup_events())
    apply_all(
        projector,
        store,
        [
            task_resolved("AUTH-002", "retry", 20),
            to_running("AUTH-002", 21),
            *finished_run("run_0006", "AUTH-002", 0.25, 22),
        ],
    )
    row = tasks_by_id(conn)["AUTH-002"]
    assert row["attempt"] == 1
    assert row["cost_usd"] == 0.25


# AC4: abandon changes no row


def test_ac4_abandon_after_runs_and_attempts_changes_no_table(conn, projector, store):
    apply_all(projector, store, setup_events())
    before = snapshot(conn)
    assert before["tasks"]
    apply_all(projector, store, [task_resolved("AUTH-002", "abandon", 20)])
    assert snapshot(conn) == before
    assert tasks_by_id(conn)["AUTH-002"]["cost_usd"] == 0.375


# AC5: rebuild is identical


def full_log():
    return [
        *setup_events(),
        *finished_run("run_0006", None, 0.5, 12, role="planner"),
        *finished_run("run_0007", "AUTH-001", None, 14),
        task_resolved("AUTH-002", "retry", 20),
        to_running("AUTH-002", 21),
        *finished_run("run_0008", "AUTH-002", 0.25, 22),
        *finished_run("run_0009", "AUTH-001", 0.125, 24),
    ]


def test_ac5_rebuild_gives_the_same_tasks_rows(conn, projector, store):
    apply_all(projector, store, full_log())
    before = [conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()][0]
    assert tasks_by_id(conn)["AUTH-002"]["cost_usd"] == 0.25
    assert tasks_by_id(conn)["AUTH-001"]["cost_usd"] == 0.875
    projector.rebuild(store.read())
    assert conn.execute("SELECT * FROM tasks ORDER BY id").fetchall() == before


def test_ac5_recorder_projects_the_same_tasks_rows_and_its_rebuild_keeps_them(
    conn, projector, store, tmp_path
):
    apply_all(projector, store, full_log())
    expected = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
    assert [row[-1] for row in expected] == [0.875, 0.25]

    db = tmp_path / "recorded.db"
    recorder = SqliteEventRecorder(db)
    try:
        for event in full_log():
            recorder.record(event)
        other = sqlite3.connect(db)
        try:
            query = "SELECT * FROM tasks ORDER BY id"
            assert other.execute(query).fetchall() == expected
            recorder.rebuild()
            assert other.execute(query).fetchall() == expected
        finally:
            other.close()
    finally:
        recorder.close()
