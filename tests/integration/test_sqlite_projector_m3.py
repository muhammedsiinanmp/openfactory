"""TASK-041 AC1..AC6: the projector for gate_results, commits and tasks.attempt
(docs/tasks/TASK-041-projector-gate-results-commits-attempt.md)."""

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
    CommitRecordedPayload,
    GateEvaluatedPayload,
    PlanApprovedPayload,
    PlanCreatedPayload,
    TaskStateChangedPayload,
)

HASH = "a" * 64
SHA = "b" * 40
SHA_2 = "c" * 40

NINE_TABLES = {
    "spec_versions",
    "requirements",
    "adrs",
    "plans",
    "tasks",
    "task_deps",
    "agent_runs",
    "gate_results",
    "commits",
}
ORDER = {"tasks": "id", "gate_results": "run_id, gate", "commits": "sha"}


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
        tasks=[AUTH_001, AUTH_002],
    ).model_dump(mode="json")
    return make_event("plan:plan_01", EventType.PlanCreated, payload)


def plan_approved():
    payload = PlanApprovedPayload(plan_id="plan_01").model_dump(mode="json")
    return make_event("plan:plan_01", EventType.PlanApproved, payload, actor="human")


def state_changed(task_id, from_, to):
    payload = TaskStateChangedPayload.model_validate(
        {"task_id": task_id, "from": from_, "to": to, "reason": None}
    ).model_dump(mode="json")
    return make_event(f"task:{task_id}", EventType.TaskStateChanged, payload)


def gate_evaluated(run_id, task_id, passed, output_path, gate="path_check"):
    payload = GateEvaluatedPayload(
        run_id=run_id, task_id=task_id, gate=gate, passed=passed, output_path=output_path
    ).model_dump(mode="json")
    return make_event(f"task:{task_id}", EventType.GateEvaluated, payload)


def commit_recorded(sha=SHA, task_id="AUTH-002", run_id="run_0002"):
    payload = CommitRecordedPayload(
        sha=sha,
        task_id=task_id,
        run_id=run_id,
        branch=f"openfactory/{task_id}",
        spec_version="sv_01",
        files=["app/auth/login.py", "tests/auth/test_login.py"],
    ).model_dump(mode="json")
    return make_event(f"task:{task_id}", EventType.CommitRecorded, payload)


def snapshot(conn):
    """Every row of tasks, gate_results and commits, in primary-key order."""
    return {
        table: conn.execute(f"SELECT * FROM {table} ORDER BY {ORDER[table]}").fetchall()
        for table in ORDER
    }


def table_names(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


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


def project_plan(projector, store):
    projector.apply(store.append(plan_created()))
    projector.apply(store.append(plan_approved()))


# AC1: tables exist, no FK or CHECK, create_tables is idempotent


def test_ac1_creates_all_nine_tables(conn, projector):
    assert table_names(conn) >= NINE_TABLES


def test_ac1_no_foreign_key_and_no_check_constraint(conn, projector):
    for table in ("gate_results", "commits"):
        assert conn.execute(f"PRAGMA table_info({table})").fetchall()
        assert conn.execute(f"PRAGMA foreign_key_list({table})").fetchall() == []
    sql = " ".join(r[0] for r in conn.execute("SELECT sql FROM sqlite_master WHERE type='table'"))
    assert "CHECK" not in sql.upper()


def test_ac1_create_tables_twice_changes_no_row(conn, projector, store):
    project_plan(projector, store)
    projector.apply(store.append(gate_evaluated("run_0002", "AUTH-002", True, None)))
    projector.apply(store.append(commit_recorded()))
    before = snapshot(conn)
    assert before["gate_results"] and before["commits"]
    projector.create_tables()
    assert snapshot(conn) == before


# AC2: GateEvaluated inserts one gate_results row


def test_ac2_gate_evaluated_inserts_one_row_each(conn, projector, store):
    project_plan(projector, store)
    before = snapshot(conn)

    projector.apply(store.append(gate_evaluated("run_0002", "AUTH-002", True, None)))
    after_first = snapshot(conn)
    assert after_first["gate_results"] == [("run_0002", "path_check", 1, None)]
    assert after_first["tasks"] == before["tasks"]
    assert after_first["commits"] == before["commits"] == []

    path = ".openfactory/runs/run_0003/path_check.txt"
    projector.apply(store.append(gate_evaluated("run_0003", "AUTH-002", False, path)))
    after_second = snapshot(conn)
    assert after_second["gate_results"] == [
        ("run_0002", "path_check", 1, None),
        ("run_0003", "path_check", 0, path),
    ]
    assert after_second["tasks"] == before["tasks"]
    assert after_second["commits"] == []


# AC3: CommitRecorded inserts one commits row


def test_ac3_commit_recorded_inserts_one_row_and_changes_no_task(conn, projector, store):
    project_plan(projector, store)
    before = snapshot(conn)

    projector.apply(store.append(commit_recorded()))
    after = snapshot(conn)
    assert after["commits"] == [(SHA, "AUTH-002", "run_0002", "openfactory/AUTH-002")]
    assert after["tasks"] == before["tasks"]
    assert after["gate_results"] == []


# AC4: attempt counts each change to running


def attempt_and_state(conn, task_id):
    return conn.execute("SELECT state, attempt FROM tasks WHERE id = ?", (task_id,)).fetchone()


def test_ac4_attempt_counts_each_change_to_running(conn, projector, store):
    project_plan(projector, store)

    def move(from_, to):
        projector.apply(store.append(state_changed("AUTH-001", from_, to)))

    move("pending", "ready")
    assert attempt_and_state(conn, "AUTH-001") == ("ready", 0)

    before = {r[0]: r for r in snapshot(conn)["tasks"]}
    move("ready", "running")
    rows = {r[0]: r for r in snapshot(conn)["tasks"]}
    assert rows["AUTH-001"] == (*before["AUTH-001"][:2], "running", *before["AUTH-001"][3:5], 1)
    assert rows["AUTH-002"] == before["AUTH-002"]

    move("running", "gating")
    assert attempt_and_state(conn, "AUTH-001") == ("gating", 1)
    move("gating", "failed")
    assert attempt_and_state(conn, "AUTH-001") == ("failed", 1)
    move("failed", "ready")
    assert attempt_and_state(conn, "AUTH-001") == ("ready", 1)
    move("ready", "running")
    assert attempt_and_state(conn, "AUTH-001") == ("running", 2)


# AC5: payloads the models reject raise and write nothing


def rejected_gate():
    ev = gate_evaluated("run_0002", "AUTH-002", True, None)
    ev.payload["gate"] = "semgrep"
    return ev


def rejected_commit():
    ev = commit_recorded()
    ev.payload["sha"] = SHA[:39]
    return ev


def rejected_state_change():
    ev = state_changed("AUTH-001", "ready", "running")
    del ev.payload["reason"]
    return ev


@pytest.mark.parametrize("bad", [rejected_gate, rejected_commit, rejected_state_change])
def test_ac5_payload_the_model_rejects_raises_and_changes_nothing(conn, projector, store, bad):
    project_plan(projector, store)
    projector.apply(store.append(state_changed("AUTH-001", "pending", "ready")))
    before = snapshot(conn)
    with pytest.raises(ValidationError):
        projector.apply(store.append(bad()))
    assert snapshot(conn) == before
    assert attempt_and_state(conn, "AUTH-001") == ("ready", 0)


# AC6: rebuild is identical, through the projector and through the recorder


def log_events():
    return [
        plan_created(),
        plan_approved(),
        state_changed("AUTH-001", "pending", "ready"),
        state_changed("AUTH-001", "ready", "running"),
        state_changed("AUTH-001", "running", "gating"),
        gate_evaluated("run_0002", "AUTH-001", False, ".openfactory/runs/run_0002/path_check.txt"),
        state_changed("AUTH-001", "gating", "failed"),
        state_changed("AUTH-001", "failed", "ready"),
        state_changed("AUTH-001", "ready", "running"),
        state_changed("AUTH-001", "running", "gating"),
        gate_evaluated("run_0003", "AUTH-001", True, None),
        commit_recorded(SHA, "AUTH-001", "run_0003"),
        state_changed("AUTH-001", "gating", "passed"),
    ]


def test_ac6_rebuild_gives_identical_rows(conn, projector, store):
    for event in log_events():
        projector.apply(store.append(event))
    before = snapshot(conn)
    assert before["gate_results"] and before["commits"]
    assert {r[0]: r for r in before["tasks"]}["AUTH-001"][5] == 2
    projector.rebuild(store.read())
    assert snapshot(conn) == before


def test_ac6_rebuild_drops_rows_no_event_produced(conn, projector, store):
    for event in log_events():
        projector.apply(store.append(event))
    conn.execute("INSERT INTO gate_results VALUES ('run_9999', 'ruff', 1, NULL)")
    conn.execute(
        "INSERT INTO commits VALUES (?, 'ZZZ-999', 'run_9999', 'openfactory/ZZZ-999')", (SHA_2,)
    )
    projector.rebuild(store.read())
    assert conn.execute("SELECT 1 FROM gate_results WHERE run_id = 'run_9999'").fetchall() == []
    assert conn.execute("SELECT 1 FROM commits WHERE sha = ?", (SHA_2,)).fetchall() == []


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
