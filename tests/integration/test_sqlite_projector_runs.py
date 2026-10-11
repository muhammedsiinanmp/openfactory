"""TASK-023 AC1..AC6: the projector for agent_runs
(docs/tasks/TASK-023-projector-agent-runs.md)."""

import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from openfactory.adapters.sqlite_projector import SqliteProjector
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.adapters.sqlite_store import SqliteEventStore
from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import AgentRunFinishedPayload, AgentRunStartedPayload

HASH = "a" * 64
T0 = datetime(2026, 10, 11, 9, 0, 0, tzinfo=UTC)
T1 = T0 + timedelta(minutes=5)
T2 = T0 + timedelta(minutes=9)

ALL_TABLES = {
    "spec_versions",
    "requirements",
    "adrs",
    "plans",
    "tasks",
    "task_deps",
    "agent_runs",
}


def make_event(stream, type, payload, created_at, actor="orchestrator"):
    return Event(
        event_id=uuid4(),
        stream=stream,
        type=type,
        payload=payload,
        actor=actor,
        created_at=created_at,
    )


def run_started(run_id, task_id, role, created_at, runtime="claude-code"):
    payload = AgentRunStartedPayload(
        run_id=run_id, task_id=task_id, role=role, runtime=runtime, context_hash=HASH
    ).model_dump(mode="json")
    return make_event(f"run:{run_id}", EventType.AgentRunStarted, payload, created_at)


def run_finished(run_id, created_at, **fields):
    values = {
        "exit": "ok",
        "model": "claude-sonnet",
        "tokens_in": 1200,
        "tokens_out": 300,
        "cost_usd": 0.0421,
        "duration_s": 12.5,
        "error": None,
    }
    values.update(fields)
    payload = AgentRunFinishedPayload(run_id=run_id, **values).model_dump(mode="json")
    return make_event(f"run:{run_id}", EventType.AgentRunFinished, payload, created_at)


def snapshot(conn):
    """Every row of agent_runs, in id order."""
    return conn.execute("SELECT * FROM agent_runs ORDER BY id").fetchall()


def rows_by_id(conn):
    conn.row_factory = None
    cols = [r[1] for r in conn.execute("PRAGMA table_info(agent_runs)")]
    return {r[0]: dict(zip(cols, r, strict=True)) for r in snapshot(conn)}


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


# AC1: table exists, no FK or CHECK, create_tables is idempotent


def test_ac1_agent_runs_exists_next_to_the_other_six_tables(conn, projector):
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert names >= ALL_TABLES


def test_ac1_no_foreign_key_and_no_check_constraint(conn, projector):
    assert conn.execute("PRAGMA table_info(agent_runs)").fetchall()
    assert conn.execute("PRAGMA foreign_key_list(agent_runs)").fetchall() == []
    sql = " ".join(r[0] for r in conn.execute("SELECT sql FROM sqlite_master WHERE type='table'"))
    assert "CHECK" not in sql.upper()


def test_ac1_create_tables_twice_changes_no_row(conn, projector, store):
    projector.apply(store.append(run_started("run_0001", None, "planner", T0)))
    before = snapshot(conn)
    assert before
    projector.create_tables()
    assert snapshot(conn) == before


# AC2: AgentRunStarted inserts one row, the finish columns stay null


def test_ac2_started_without_task_writes_one_row_with_null_finish_columns(conn, projector, store):
    projector.apply(store.append(run_started("run_0001", None, "planner", T0)))
    assert rows_by_id(conn) == {
        "run_0001": {
            "id": "run_0001",
            "task_id": None,
            "role": "planner",
            "runtime": "claude-code",
            "model": None,
            "started_at": T0.isoformat(),
            "ended_at": None,
            "exit": None,
            "tokens_in": None,
            "tokens_out": None,
            "cost_usd": None,
            "duration_s": None,
            "context_hash": HASH,
        }
    }
    assert T0.isoformat().endswith("+00:00")


def test_ac2_second_started_adds_a_row_and_leaves_the_first(conn, projector, store):
    projector.apply(store.append(run_started("run_0001", None, "planner", T0)))
    first = snapshot(conn)
    projector.apply(store.append(run_started("run_0002", "AUTH-002", "implementer", T1)))
    rows = rows_by_id(conn)
    assert snapshot(conn)[0] == first[0]
    assert rows["run_0002"]["task_id"] == "AUTH-002"
    assert rows["run_0002"]["role"] == "implementer"
    assert rows["run_0002"]["started_at"] == T1.isoformat()
    assert len(rows) == 2


# AC3: AgentRunFinished sets the finish columns on its own row only


def test_ac3_finished_ok_sets_six_columns_and_leaves_the_rest(conn, projector, store):
    projector.apply(store.append(run_started("run_0001", None, "planner", T0)))
    projector.apply(store.append(run_started("run_0002", "AUTH-002", "implementer", T1)))
    before = rows_by_id(conn)

    projector.apply(store.append(run_finished("run_0001", T2)))
    after = rows_by_id(conn)

    assert after["run_0002"] == before["run_0002"]
    expected = {
        **before["run_0001"],
        "model": "claude-sonnet",
        "exit": "ok",
        "tokens_in": 1200,
        "tokens_out": 300,
        "cost_usd": 0.0421,
        "duration_s": 12.5,
        "ended_at": T2.isoformat(),
    }
    assert after["run_0001"] == expected


def test_ac3_finished_with_error_leaves_the_nullable_columns_null(conn, projector, store):
    projector.apply(store.append(run_started("run_0001", None, "planner", T0)))
    projector.apply(store.append(run_started("run_0002", "AUTH-002", "implementer", T1)))
    projector.apply(
        store.append(
            run_finished(
                "run_0002",
                T2,
                exit="error",
                error="process failed",
                model=None,
                tokens_in=None,
                tokens_out=None,
                cost_usd=None,
                duration_s=3.0,
            )
        )
    )
    row = rows_by_id(conn)["run_0002"]
    assert row["exit"] == "error"
    assert row["duration_s"] == 3.0
    assert row["ended_at"] == T2.isoformat()
    assert [row[c] for c in ("model", "tokens_in", "tokens_out", "cost_usd")] == [None] * 4


# AC4: invalid payloads raise and change nothing


def test_ac4_started_the_model_rejects_raises_and_writes_nothing(conn, projector, store):
    projector.apply(store.append(run_started("run_0001", None, "planner", T0)))
    before = snapshot(conn)
    bad = run_started("run_0002", None, "planner", T1)
    bad.payload["role"] = "tester"
    with pytest.raises(ValidationError):
        projector.apply(store.append(bad))
    assert snapshot(conn) == before


def test_ac4_finished_the_model_rejects_raises_and_changes_nothing(conn, projector, store):
    projector.apply(store.append(run_started("run_0001", None, "planner", T0)))
    before = snapshot(conn)
    bad = run_finished("run_0001", T2)
    del bad.payload["error"]
    with pytest.raises(ValidationError):
        projector.apply(store.append(bad))
    assert snapshot(conn) == before
    row = rows_by_id(conn)["run_0001"]
    assert row["exit"] is None
    assert row["ended_at"] is None


# AC5: rebuild is identical


def log_events():
    return [
        run_started("run_0001", None, "planner", T0),
        run_finished("run_0001", T1, exit="error", error="rejected reply", cost_usd=0.5),
        run_started("run_0002", None, "planner", T1),
        run_finished("run_0002", T2),
        run_started("run_0003", "AUTH-002", "implementer", T2),
    ]


def test_ac5_log_projects_three_rows(conn, projector, store):
    for event in log_events():
        projector.apply(store.append(event))
    rows = rows_by_id(conn)
    assert list(rows) == ["run_0001", "run_0002", "run_0003"]
    assert rows["run_0001"]["cost_usd"] == 0.5
    assert rows["run_0001"]["exit"] == "error"
    assert rows["run_0003"]["ended_at"] is None
    assert rows["run_0003"]["exit"] is None


def test_ac5_rebuild_gives_identical_rows(conn, projector, store):
    for event in log_events():
        projector.apply(store.append(event))
    before = snapshot(conn)
    assert len(before) == 3
    projector.rebuild(store.read())
    assert snapshot(conn) == before


def test_ac5_rebuild_drops_a_run_row_no_event_produced(conn, projector, store):
    for event in log_events():
        projector.apply(store.append(event))
    conn.execute(
        "INSERT INTO agent_runs (id, role, runtime, started_at, context_hash) "
        "VALUES ('run_9999', 'planner', 'x', 't', 'h')"
    )
    projector.rebuild(store.read())
    assert conn.execute("SELECT 1 FROM agent_runs WHERE id = 'run_9999'").fetchall() == []


# AC6: recorder projects the same rows and its rebuild keeps them


def test_ac6_recorder_projects_the_same_rows_and_its_rebuild_keeps_them(
    conn, projector, store, tmp_path
):
    for event in log_events():
        projector.apply(store.append(event))
    expected = snapshot(conn)
    assert len(expected) == 3

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
