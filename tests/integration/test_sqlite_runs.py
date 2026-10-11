"""TASK-024 AC2, AC3, AC6 (Runs half): SqliteRuns
(docs/tasks/TASK-024-runs-port-and-stored-spec-set.md)."""

import sqlite3

import pytest

from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.adapters.sqlite_runs import SqliteRuns
from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import AgentRunFinishedPayload, AgentRunStartedPayload

HASH = "a" * 64
TABLES = ("events", "agent_runs", "projection_state")


def started(run_id):
    payload = AgentRunStartedPayload(
        run_id=run_id, task_id=None, role="planner", runtime="claude-code", context_hash=HASH
    )
    return Event.new(
        stream=f"run:{run_id}",
        type=EventType.AgentRunStarted,
        payload=payload.model_dump(mode="json"),
        actor="orchestrator",
    )


def finished(run_id):
    payload = AgentRunFinishedPayload(
        run_id=run_id,
        exit="ok",
        model="claude-sonnet",
        tokens_in=10,
        tokens_out=5,
        cost_usd=0.01,
        duration_s=1.5,
        error=None,
    )
    return Event.new(
        stream=f"run:{run_id}",
        type=EventType.AgentRunFinished,
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
def runs(db, recorder):
    adapter = SqliteRuns(db)
    yield adapter
    adapter.close()


def test_ac2_empty_log_gives_run_0001(runs):
    assert runs.next_id() == "run_0001"


@pytest.mark.parametrize("record_finish", [False, True], ids=["started-only", "finished"])
def test_ac2_next_id_follows_a_started_run(recorder, runs, record_finish):
    recorder.record(started("run_0001"))
    if record_finish:
        recorder.record(finished("run_0001"))
    assert runs.next_id() == "run_0002"


def test_ac2_next_id_is_one_more_than_the_highest_not_the_count(recorder, runs):
    recorder.record(started("run_0001"))
    recorder.record(started("run_0007"))
    assert runs.next_id() == "run_0008"


def test_ac2_ids_widen_past_four_digits(recorder, runs):
    recorder.record(started("run_9999"))
    assert runs.next_id() == "run_10000"


def test_ac3_adapter_opened_early_sees_later_events(recorder, runs):
    assert runs.next_id() == "run_0001"
    recorder.record(started("run_0001"))
    recorder.record(finished("run_0001"))
    assert runs.next_id() == "run_0002"


def test_ac6_next_id_changes_no_row(db, recorder):
    recorder.record(started("run_0001"))
    recorder.record(finished("run_0001"))
    recorder.record(started("run_0002"))

    def snapshot():
        conn = sqlite3.connect(db)
        try:
            return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall() for t in TABLES}
        finally:
            conn.close()

    before = snapshot()
    adapter = SqliteRuns(db)
    adapter.next_id()
    adapter.close()
    assert snapshot() == before
