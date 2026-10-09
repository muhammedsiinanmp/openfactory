"""TASK-010 AC1..AC6: SqliteEventRecorder (docs/tasks/TASK-010-event-recorder-sqlite.md)."""

import ast
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.adapters.sqlite_store import SqliteEventStore
from openfactory.domain.events import Event, EventType
from openfactory.domain.models import (
    AcceptanceCriterion,
    Adr,
    AdrStatus,
    Priority,
    Requirement,
    SpecSet,
)
from openfactory.domain.payloads import (
    SpecApprovedPayload,
    SpecImportedPayload,
    SpecValidatedPayload,
)
from openfactory.domain.spec_hash import content_hash
from openfactory.ports.event_store import EventConflictError

HASH_1 = "a" * 64
HASH_2 = "b" * 64
HASH_3 = "c" * 64

TABLES = ("spec_versions", "requirements", "adrs")
ORDER = {
    "spec_versions": "id",
    "requirements": "spec_version, id",
    "adrs": "spec_version, id",
}
ADAPTERS_DIR = Path(__file__).parents[2] / "src" / "openfactory" / "adapters"
RECORDER_SOURCE = ADAPTERS_DIR / "sqlite_recorder.py"

REQ_AUTH = Requirement(
    id="REQ-AUTH-001",
    title="Login",
    statement="Users can log in.",
    priority=Priority.must,
    constrained_by=["ADR-001"],
    components=["auth"],
    acceptance_criteria=[AcceptanceCriterion(id="AC1", text="Valid login succeeds")],
)
REQ_OLD = Requirement(
    id="REQ-AUTH-002",
    title="Legacy",
    statement="Old behaviour.",
    priority=Priority.could,
    deprecated=True,
    components=["auth"],
)
ADR_1 = Adr(id="ADR-001", status=AdrStatus.accepted, body="Use sessions.")


def spec_set(requirements=(REQ_AUTH, REQ_OLD), adrs=(ADR_1,), components=("auth",)):
    return SpecSet(components=list(components), requirements=list(requirements), adrs=list(adrs))


def make_event(version, type, payload, created_at=None, actor="orchestrator", event_id=None):
    return Event(
        event_id=event_id or uuid4(),
        stream=f"spec:{version}",
        type=type,
        payload=payload,
        actor=actor,
        created_at=created_at or datetime.now(UTC),
    )


def imported(version="sv_01", digest=HASH_1, spec=None, event_id=None):
    payload = SpecImportedPayload(
        spec_version=version, hash=digest, spec=spec or spec_set()
    ).model_dump(mode="json")
    return make_event(version, EventType.SpecImported, payload, event_id=event_id)


def imported_changed(version="sv_01"):
    changed = spec_set(requirements=[REQ_AUTH], components=("auth", "ui"))
    return imported(version=version, digest=HASH_2, spec=changed)


def validated(version="sv_01"):
    payload = SpecValidatedPayload.model_validate(
        {"spec_version": version, "hash": HASH_1, "violations": [], "warnings": []}
    ).model_dump(mode="json")
    return make_event(version, EventType.SpecValidated, payload)


def approved(version="sv_01", digest=HASH_1, created_at=None):
    payload = SpecApprovedPayload(spec_version=version, hash=digest).model_dump(mode="json")
    return make_event(version, EventType.SpecApproved, payload, created_at, actor="human")


def bad_approved():
    return make_event(
        "sv_01", EventType.SpecApproved, {"spec_version": "v1", "hash": HASH_1}, actor="human"
    )


def import_without_hash():
    payload = {k: v for k, v in imported().payload.items() if k != "hash"}
    return make_event("sv_01", EventType.SpecImported, payload)


def task_event():
    return Event.new(
        stream="task:AUTH-002",
        type=EventType.TaskStateChanged,
        payload={"task_id": "AUTH-002", "from": "pending", "to": "ready", "reason": None},
        actor="orchestrator",
    )


def expected_sv_01(status, approved_at):
    """Every row the default import of `sv_01` must leave, in primary-key order."""
    return {
        "spec_versions": [("sv_01", HASH_1, status, '["auth"]', approved_at)],
        "requirements": [
            (
                "REQ-AUTH-001",
                "sv_01",
                "Login",
                "Users can log in.",
                "must",
                0,
                '["auth"]',
                '["ADR-001"]',
                '[{"id": "AC1", "text": "Valid login succeeds"}]',
                content_hash(REQ_AUTH),
            ),
            (
                "REQ-AUTH-002",
                "sv_01",
                "Legacy",
                "Old behaviour.",
                "could",
                1,
                '["auth"]',
                "[]",
                "[]",
                content_hash(REQ_OLD),
            ),
        ],
        "adrs": [("ADR-001", "sv_01", "accepted", "Use sessions.", content_hash(ADR_1))],
    }


def snapshot(conn):
    """Every row of the three spec projections, in primary-key order."""
    return {
        table: conn.execute(f"SELECT * FROM {table} ORDER BY {ORDER[table]}").fetchall()
        for table in TABLES
    }


def state_rows(conn):
    return conn.execute("SELECT id, last_seq FROM projection_state").fetchall()


def read_all(path):
    store = SqliteEventStore(path)
    try:
        return store.read()
    finally:
        store.close()


def append_only(path, events):
    store = SqliteEventStore(path)
    try:
        return [store.append(e) for e in events]
    finally:
        store.close()


@pytest.fixture
def db(tmp_path):
    return tmp_path / "factory.db"


@pytest.fixture
def conn(db):
    """A second connection that sees only committed data; opened lazily after the recorder."""
    connections = []

    def open_conn():
        c = sqlite3.connect(db)
        connections.append(c)
        return c

    yield open_conn
    for c in connections:
        c.close()


@pytest.fixture
def recorder(db):
    r = SqliteEventRecorder(db)
    yield r
    r.close()


# AC1: port, creation, imports, shared SQL


def test_ac1_open_creates_file_tables_wal_and_the_single_state_row(db, conn):
    SqliteEventRecorder(db).close()
    c = conn()
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"events", "spec_versions", "requirements", "adrs", "projection_state"} <= names
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    columns = [r[1] for r in c.execute("PRAGMA table_info(projection_state)")]
    assert columns == ["id", "last_seq"]
    assert state_rows(c) == [(1, 0)]


def test_ac1_opening_a_second_time_changes_no_row(db, conn, recorder):
    recorder.record(imported())
    c = conn()
    before = (snapshot(c), state_rows(c), read_all(db))
    SqliteEventRecorder(db).close()
    assert (snapshot(c), state_rows(c), read_all(db)) == before


def test_ac1_recorder_module_imports_nothing_from_app():
    tree = ast.parse(RECORDER_SOURCE.read_text())
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
    assert not [m for m in modules if m.startswith("openfactory.app")]


@pytest.mark.parametrize("text", ["CREATE TABLE IF NOT EXISTS events", "INSERT INTO events"])
def test_ac1_events_sql_lives_only_in_sqlite_events(text):
    holders = [p.name for p in ADAPTERS_DIR.glob("*.py") if text in p.read_text()]
    assert holders == ["sqlite_events.py"]


# AC2: record returns a StoredEvent, stores and projects


def test_ac2_record_returns_stored_events_and_projects_each_one(db, conn, recorder):
    events = [
        imported(),
        validated(),
        approved(created_at=datetime(2026, 10, 9, 12, 0, tzinfo=UTC)),
    ]
    approved_at = events[2].created_at.isoformat()
    expected = [
        expected_sv_01("draft", None),
        expected_sv_01("draft", None),
        expected_sv_01("approved", approved_at),
    ]
    c = conn()
    previous_seq = 0
    for i, event in enumerate(events, start=1):
        result = recorder.record(event)
        assert result.seq > previous_seq
        previous_seq = result.seq
        assert (result.event_id, result.stream, result.type) == (
            event.event_id,
            event.stream,
            event.type,
        )
        assert (result.payload, result.actor, result.created_at) == (
            event.payload,
            event.actor,
            event.created_at,
        )
        assert [e.event_id for e in read_all(db)] == [e.event_id for e in events[:i]]
        assert snapshot(c) == expected[i - 1]


def test_ac2_event_type_without_projection_is_stored_and_moves_last_seq(db, conn, recorder):
    recorder.record(imported())
    c = conn()
    before = snapshot(c)
    result = recorder.record(task_event())
    assert snapshot(c) == before
    assert state_rows(c) == [(1, result.seq)]
    assert read_all(db)[-1].event_id == result.event_id


# AC3: a rejected payload leaves nothing behind


def test_ac3_invalid_payload_raises_and_leaves_events_projections_and_last_seq(db, conn, recorder):
    first = recorder.record(imported())
    c = conn()
    before = (snapshot(c), state_rows(c), read_all(db))
    bad = import_without_hash()
    with pytest.raises(ValidationError):
        recorder.record(bad)
    assert (snapshot(c), state_rows(c), read_all(db)) == before
    assert bad.event_id not in {e.event_id for e in read_all(db)}
    assert state_rows(c) == [(1, first.seq)]


def test_ac3_a_valid_event_recorded_after_a_failure_is_stored_and_projected(db, conn, recorder):
    recorder.record(imported())
    with pytest.raises(ValidationError):
        recorder.record(import_without_hash())
    result = recorder.record(approved())
    c = conn()
    assert state_rows(c) == [(1, result.seq)]
    assert c.execute("SELECT status FROM spec_versions").fetchall() == [("approved",)]
    assert result.event_id in {e.event_id for e in read_all(db)}


# AC4: a repeated event_id


def test_ac4_same_event_again_returns_the_stored_event_and_applies_nothing(db, conn, recorder):
    a = imported()
    b = imported_changed()
    first_a = recorder.record(a)
    second_b = recorder.record(b)
    c = conn()
    before = (snapshot(c), read_all(db))
    again = recorder.record(a)
    assert again == first_a
    assert again.seq == first_a.seq
    assert (snapshot(c), read_all(db)) == before
    assert snapshot(c)["spec_versions"][0][1] == HASH_2
    assert state_rows(c) == [(1, second_b.seq)]


def test_ac4_same_event_id_with_different_content_raises_and_changes_nothing(db, conn, recorder):
    a = imported()
    recorder.record(a)
    second_b = recorder.record(imported_changed())
    c = conn()
    before = (snapshot(c), state_rows(c), read_all(db))
    clash = imported(digest=HASH_3, event_id=a.event_id)
    with pytest.raises(EventConflictError):
        recorder.record(clash)
    assert (snapshot(c), state_rows(c), read_all(db)) == before
    assert state_rows(c) == [(1, second_b.seq)]


# AC5: last_seq bookkeeping and catch-up


def test_ac5_last_seq_follows_every_record_in_a_single_row(conn, recorder):
    c = conn()
    for event in (imported(), validated(), task_event(), approved()):
        result = recorder.record(event)
        assert state_rows(c) == [(1, result.seq)]


def test_ac5_catch_up_applies_events_appended_behind_the_recorders_back(tmp_path, conn):
    caught_up_db = tmp_path / "caught_up.db"
    reference_db = tmp_path / "reference.db"
    tail = [validated(), approved(), imported(version="sv_02", digest=HASH_2)]
    first = imported()

    recorder = SqliteEventRecorder(caught_up_db)
    recorder.record(first)
    recorder.close()
    append_only(caught_up_db, tail)

    reference = SqliteEventRecorder(reference_db)
    for event in (first, *tail):
        reference.record(event)
    reference.close()

    SqliteEventRecorder(caught_up_db).close()
    c = sqlite3.connect(caught_up_db)
    r = sqlite3.connect(reference_db)
    try:
        assert snapshot(c) == snapshot(r)
        assert state_rows(c) == [(1, max(e.seq for e in read_all(caught_up_db)))]
        before = (snapshot(c), state_rows(c))
        SqliteEventRecorder(caught_up_db).close()
        assert (snapshot(c), state_rows(c)) == before
    finally:
        c.close()
        r.close()


def test_ac5_catch_up_builds_projections_for_a_database_with_only_an_events_table(
    tmp_path, db, conn
):
    events = [imported(), validated(), approved()]
    append_only(db, events)
    reference_db = tmp_path / "reference.db"
    reference = SqliteEventRecorder(reference_db)
    for event in events:
        reference.record(event)
    reference.close()

    SqliteEventRecorder(db).close()
    c = conn()
    r = sqlite3.connect(reference_db)
    try:
        assert snapshot(c) == snapshot(r)
        assert state_rows(c) == [(1, max(e.seq for e in read_all(db)))]
    finally:
        r.close()


def test_ac5_bad_stored_payload_fails_the_open_naming_seq_and_applies_nothing(db, conn):
    recorder = SqliteEventRecorder(db)
    recorder.record(imported())
    recorder.close()
    c = conn()
    before = (snapshot(c), state_rows(c))
    _, bad = append_only(db, [validated(), bad_approved()])
    with pytest.raises(ValidationError) as error:
        SqliteEventRecorder(db)
    assert f"seq {bad.seq}" in str(error.value)
    assert (snapshot(c), state_rows(c)) == before


def test_ac5_stored_event_the_projector_cannot_write_fails_the_open_naming_seq_and_model(db, conn):
    recorder = SqliteEventRecorder(db)
    recorder.record(imported())
    recorder.close()
    c = conn()
    before = (snapshot(c), state_rows(c))
    twice = spec_set(requirements=[REQ_AUTH, REQ_AUTH])
    _, bad = append_only(db, [validated(), imported(version="sv_02", digest=HASH_2, spec=twice)])
    with pytest.raises(sqlite3.IntegrityError) as error:
        SqliteEventRecorder(db)
    assert f"seq {bad.seq}" in str(error.value)
    assert "SpecImportedPayload" in str(error.value)
    assert isinstance(error.value.__cause__, sqlite3.IntegrityError)
    assert (snapshot(c), state_rows(c)) == before


# AC6: rebuild


def record_log(recorder):
    log = [
        imported(),
        validated(),
        imported_changed(),
        validated(),
        approved(digest=HASH_2),
        task_event(),
        imported(version="sv_02", digest=HASH_3),
        validated(version="sv_02"),
    ]
    return [recorder.record(e) for e in log]


def test_ac6_rebuild_gives_identical_rows_drops_strays_and_keeps_last_seq(db, conn, recorder):
    stored = record_log(recorder)
    c = conn()
    before = snapshot(c)
    assert before["spec_versions"]
    c.execute(
        "INSERT INTO requirements VALUES ('REQ-X-001', 'sv_09', 't', 's', 'must', 0,"
        " '[]', '[]', '[]', 'h')"
    )
    c.commit()
    recorder.rebuild()
    assert snapshot(c) == before
    assert state_rows(c) == [(1, stored[-1].seq)]
    assert state_rows(c) == [(1, max(e.seq for e in read_all(db)))]


def test_ac6_failed_rebuild_raises_and_rolls_everything_back(db, conn, recorder):
    record_log(recorder)
    c = conn()
    before = (snapshot(c), state_rows(c))
    append_only(db, [bad_approved()])
    with pytest.raises(ValidationError):
        recorder.rebuild()
    assert (snapshot(c), state_rows(c)) == before
