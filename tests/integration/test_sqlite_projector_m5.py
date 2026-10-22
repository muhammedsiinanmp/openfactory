"""TASK-079 AC3: recording a TestsCollected validates it and writes no projection row."""

import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.domain.events import Event, EventType

GOOD = {
    "run_id": "run_0002",
    "task_id": "AUTH-002",
    "tests": [{"node_id": "tests/test_a.py::test_x", "file": "tests/test_a.py", "req": []}],
}


def make_event(payload: dict) -> Event:
    return Event(
        event_id=uuid4(),
        stream="task:AUTH-002",
        type=EventType.TestsCollected,
        payload=payload,
        actor="orchestrator",
        created_at=datetime.now(UTC),
    )


def all_rows(db) -> dict[str, list]:
    conn = sqlite3.connect(db)
    try:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        return {
            n: conn.execute(f'SELECT * FROM "{n}"').fetchall()
            for n in names
            if n not in ("events", "projection_state", "sqlite_sequence")
        }
    finally:
        conn.close()


def test_task079_ac3_a_tests_collected_event_is_recorded_and_changes_no_projection(
    tmp_path,
) -> None:
    db = tmp_path / "events.db"
    recorder = SqliteEventRecorder(db)
    try:
        before = all_rows(db)
        stored = recorder.record(make_event(GOOD))
        assert stored.type == "TestsCollected"
        assert all_rows(db) == before
    finally:
        recorder.close()


@pytest.mark.parametrize(
    "bad",
    [{k: v for k, v in GOOD.items() if k != "tests"}, {**GOOD, "extra": 1}],
    ids=["missing-tests", "unknown-key"],
)
def test_task079_ac3_a_payload_the_model_rejects_raises(tmp_path, bad) -> None:
    recorder = SqliteEventRecorder(tmp_path / "events.db")
    try:
        with pytest.raises(ValidationError):
            recorder.record(make_event(bad))
    finally:
        recorder.close()
