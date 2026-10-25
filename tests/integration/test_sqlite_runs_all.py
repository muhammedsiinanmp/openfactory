"""TASK-107 AC3, AC4, AC5: SqliteRuns.all_runs (docs/tasks/TASK-107-runs-all-runs.md)."""

import pytest

from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.adapters.sqlite_runs import SqliteRuns
from openfactory.domain.agent_run import RunRecord
from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import (
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    TaskResolvedPayload,
)

HASH = "a" * 64


def started(run_id, role="planner", task_id=None):
    payload = AgentRunStartedPayload(
        run_id=run_id, task_id=task_id, role=role, runtime="claude-code", context_hash=HASH
    )
    return Event.new(
        stream=f"run:{run_id}",
        type=EventType.AgentRunStarted,
        payload=payload.model_dump(mode="json"),
        actor="orchestrator",
    )


def finished(run_id, exit="ok", tokens_in=10, tokens_out=5, cost_usd=0.01, duration_s=1.5):
    payload = AgentRunFinishedPayload(
        run_id=run_id,
        exit=exit,
        model="claude-sonnet",
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        duration_s=duration_s,
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


def test_ac3_finished_runs_carry_started_and_finished_values(recorder, runs):
    recorder.record(started("run_0001", "planner"))
    recorder.record(finished("run_0001", "ok", 100, 50, 0.25, 3.5))
    recorder.record(started("run_0002", "implementer", "TASK-001"))
    recorder.record(finished("run_0002", "error", 7, 3, 0.5, 9.0))
    recorder.record(started("run_0003", "classifier"))
    recorder.record(finished("run_0003", "ok", 1, 1, 0.01, 0.5))
    recorder.record(started("run_0004", "reviewer", "TASK-001"))
    recorder.record(finished("run_0004", "timeout", 2, 2, 0.02, 1.0))
    assert runs.all_runs() == [
        RunRecord(
            id="run_0001",
            task_id=None,
            role="planner",
            exit="ok",
            tokens_in=100,
            tokens_out=50,
            cost_usd=0.25,
            duration_s=3.5,
        ),
        RunRecord(
            id="run_0002",
            task_id="TASK-001",
            role="implementer",
            exit="error",
            tokens_in=7,
            tokens_out=3,
            cost_usd=0.5,
            duration_s=9.0,
        ),
        RunRecord(
            id="run_0003",
            task_id=None,
            role="classifier",
            exit="ok",
            tokens_in=1,
            tokens_out=1,
            cost_usd=0.01,
            duration_s=0.5,
        ),
        RunRecord(
            id="run_0004",
            task_id="TASK-001",
            role="reviewer",
            exit="timeout",
            tokens_in=2,
            tokens_out=2,
            cost_usd=0.02,
            duration_s=1.0,
        ),
    ]


def test_ac3_unreported_tokens_and_cost_are_none_not_zero(recorder, runs):
    recorder.record(started("run_0001", "implementer", "TASK-001"))
    recorder.record(finished("run_0001", "error", None, None, None, 2.0))
    (rec,) = runs.all_runs()
    assert rec.tokens_in is None
    assert rec.tokens_out is None
    assert rec.cost_usd is None
    assert rec.duration_s == 2.0
    assert rec.exit == "error"


def test_ac4_started_only_run_is_listed_with_null_figures(recorder, runs):
    recorder.record(started("run_0001", "reviewer", "TASK-002"))
    assert runs.all_runs() == [
        RunRecord(
            id="run_0001",
            task_id="TASK-002",
            role="reviewer",
            exit=None,
            tokens_in=None,
            tokens_out=None,
            cost_usd=None,
            duration_s=None,
        )
    ]


def test_ac5_order_is_by_integer_run_number(recorder, runs):
    for rid in ("run_10000", "run_0002", "run_9999"):
        recorder.record(started(rid))
    assert [r.id for r in runs.all_runs()] == ["run_0002", "run_9999", "run_10000"]


def test_ac5_runs_before_a_retry_resolution_are_still_listed(recorder, runs):
    recorder.record(started("run_0001", "implementer", "TASK-001"))
    recorder.record(finished("run_0001", "error"))
    resolved = TaskResolvedPayload(task_id="TASK-001", decision="retry")
    recorder.record(
        Event.new(
            stream="task:TASK-001",
            type=EventType.TaskResolved,
            payload=resolved.model_dump(mode="json"),
            actor="human",
        )
    )
    recorder.record(started("run_0002", "implementer", "TASK-001"))
    assert [r.id for r in runs.all_runs()] == ["run_0001", "run_0002"]


def test_ac5_empty_log_gives_empty_list(runs):
    assert runs.all_runs() == []


def test_ac5_later_run_shows_on_next_call(recorder, runs):
    recorder.record(started("run_0001"))
    assert [r.id for r in runs.all_runs()] == ["run_0001"]
    recorder.record(started("run_0002"))
    recorder.record(finished("run_0002"))
    assert [r.id for r in runs.all_runs()] == ["run_0001", "run_0002"]
