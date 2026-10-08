"""TASK-002 AC2..AC6: SqliteEventStore (docs/tasks/TASK-002-event-store-sqlite.md)."""

import json
import sqlite3
from datetime import datetime

import pytest

from openfactory.adapters.sqlite_store import SqliteEventStore
from openfactory.domain.events import Event, EventType, StoredEvent
from openfactory.ports.event_store import EventConflictError

COLUMNS = ["seq", "event_id", "stream", "type", "payload", "actor", "causation_id", "created_at"]


def make_event(stream="task:AUTH-002", **overrides):
    kwargs = {
        "stream": stream,
        "type": EventType.TaskStateChanged,
        "payload": {"to": "ready"},
        "actor": "orchestrator",
    }
    kwargs.update(overrides)
    return Event.new(**kwargs)


def envelope(event):
    return event.model_dump(exclude={"seq"})


def raw_rows(path, sql="SELECT * FROM events ORDER BY seq", args=()):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def count_rows(path, event):
    sql = "SELECT 1 FROM events WHERE event_id = ?"
    return len(raw_rows(path, sql, (str(event.event_id),)))


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "openfactory.db"


@pytest.fixture
def store(db_path):
    s = SqliteEventStore(db_path)
    yield s
    s.close()


def test_ac2_open_creates_events_table_with_exact_columns(db_path, store):
    assert db_path.is_file()
    rows = raw_rows(db_path, "PRAGMA table_info(events)")
    assert [r[1] for r in rows] == COLUMNS


def test_ac2_database_is_in_wal_mode(db_path, store):
    assert raw_rows(db_path, "PRAGMA journal_mode") == [("wal",)]


def test_ac3_append_returns_stored_event_with_same_envelope_and_seq_1(store):
    event = make_event(causation_id=make_event().event_id)
    stored = store.append(event)
    assert isinstance(stored, StoredEvent)
    assert stored.seq == 1
    assert envelope(stored) == envelope(event)


def test_ac3_later_appends_get_larger_seq(store):
    seqs = [store.append(make_event()).seq for _ in range(3)]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == 3


def test_ac4_same_event_again_is_a_noop_returning_original_seq(db_path, store):
    event = make_event()
    first = store.append(event)
    store.append(make_event())
    again = store.append(event)
    assert again == first
    assert again.seq == first.seq
    assert count_rows(db_path, event) == 1
    assert len(raw_rows(db_path)) == 2


def test_ac4_same_event_id_different_content_raises_and_row_unchanged(db_path, store):
    event = make_event()
    first = store.append(event)
    changed = event.model_copy(update={"payload": {"to": "done"}})
    with pytest.raises(EventConflictError):
        store.append(changed)
    assert store.read() == [first]
    assert count_rows(db_path, event) == 1


@pytest.mark.parametrize(
    "update",
    [{"stream": "task:OTHER"}, {"actor": "agent:coder"}, {"type": EventType.PlanCreated}],
)
def test_ac4_conflict_on_non_payload_field_raises_and_row_unchanged(db_path, store, update):
    event = make_event()
    first = store.append(event)
    changed = event.model_copy(update=update)
    with pytest.raises(EventConflictError):
        store.append(changed)
    assert store.read() == [first]
    assert count_rows(db_path, event) == 1


@pytest.mark.parametrize(("changed_value", "expected_type"), [(1.0, float), (True, bool)])
def test_ac4_payload_value_of_different_json_type_is_a_conflict(
    db_path, store, changed_value, expected_type
):
    event = make_event(payload={"a": 1})
    first = store.append(event)
    changed = event.model_copy(update={"payload": {"a": changed_value}})
    assert type(changed.payload["a"]) is expected_type
    with pytest.raises(EventConflictError):
        store.append(changed)
    assert store.read() == [first]
    assert count_rows(db_path, event) == 1


def test_ac5_read_returns_all_stored_events_in_seq_order(store):
    appended = [store.append(make_event(stream=s)) for s in ("task:A", "task:B", "task:A")]
    result = store.read()
    assert result == appended
    assert all(isinstance(e, StoredEvent) for e in result)
    assert [e.seq for e in result] == sorted(e.seq for e in result)


def test_ac5_read_with_stream_filters_and_keeps_order(store):
    a1 = store.append(make_event(stream="task:AUTH-002"))
    store.append(make_event(stream="task:OTHER"))
    a2 = store.append(make_event(stream="task:AUTH-002"))
    assert store.read(stream="task:AUTH-002") == [a1, a2]


def test_ac5_unknown_stream_and_new_database_give_empty_list(store):
    assert store.read() == []
    store.append(make_event())
    assert store.read(stream="task:NONE") == []


def test_ac6_events_survive_close_and_reopen(db_path):
    first = SqliteEventStore(db_path)
    parent = first.append(make_event())
    child = first.append(
        make_event(
            payload={"a": {"b": [1, 2.5, None, True, "x"]}, "n": "é"},
            causation_id=parent.event_id,
        )
    )
    first.close()

    second = SqliteEventStore(db_path)
    try:
        assert second.read() == [parent, child]
        assert second.read()[1].created_at == child.created_at
    finally:
        second.close()


def test_ac6_raw_row_has_iso_utc_created_at_and_json_payload(db_path, store):
    event = make_event(payload={"a": {"b": [1, "x"]}})
    store.append(event)
    created_at, payload = raw_rows(db_path, "SELECT created_at, payload FROM events")[0]
    assert isinstance(created_at, str)
    assert created_at.endswith(("Z", "+00:00"))
    assert datetime.fromisoformat(created_at) == event.created_at
    assert isinstance(payload, str)
    assert json.loads(payload) == {"a": {"b": [1, "x"]}}
