"""TASK-011 AC2..AC6: SqliteSpecVersions (docs/tasks/TASK-011-spec-versions-port-sqlite.md)."""

import sqlite3

import pytest

from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.adapters.sqlite_spec_versions import SqliteSpecVersions
from openfactory.domain.events import Event, EventType
from openfactory.domain.models import SpecSet
from openfactory.domain.payloads import SpecApprovedPayload, SpecImportedPayload
from openfactory.domain.spec_versions import SpecVersionRef

TABLES = ("events", "spec_versions", "requirements", "adrs", "projection_state")


def hash_of(n, salt=0):
    return format(n * 10 + salt, "064x")


def imported(n, salt=0):
    version = f"sv_{n:02d}"
    payload = SpecImportedPayload(
        spec_version=version, hash=hash_of(n, salt), spec=SpecSet(components=["core"])
    )
    return Event.new(
        stream=f"spec:{version}",
        type=EventType.SpecImported,
        payload=payload.model_dump(mode="json"),
        actor="orchestrator",
    )


def approved(n):
    version = f"sv_{n:02d}"
    payload = SpecApprovedPayload(spec_version=version, hash=hash_of(n))
    return Event.new(
        stream=f"spec:{version}",
        type=EventType.SpecApproved,
        payload=payload.model_dump(mode="json"),
        actor="human",
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
def versions(db, recorder):
    adapter = SqliteSpecVersions(db)
    yield adapter
    adapter.close()


def ref(n, salt=0):
    return SpecVersionRef(id=f"sv_{n:02d}", hash=hash_of(n, salt))


def test_ac2_empty_database_has_nothing_and_next_id_is_sv_01(versions):
    assert versions.latest_approved() is None
    assert versions.current_draft() is None
    assert versions.next_id() == "sv_01"


def test_ac3_import_makes_a_draft_and_next_id_moves_on(recorder, versions):
    recorder.record(imported(1))
    assert versions.current_draft() == ref(1)
    assert versions.latest_approved() is None
    assert versions.next_id() == "sv_02"


def test_ac3_second_import_replaces_the_draft_hash_and_keeps_its_id(recorder, versions):
    recorder.record(imported(1))
    recorder.record(imported(1, salt=1))
    assert versions.current_draft() == ref(1, salt=1)
    assert versions.next_id() == "sv_02"


def test_ac4_approve_import_approve_sequence(recorder, versions):
    recorder.record(imported(1))
    recorder.record(approved(1))
    assert versions.latest_approved() == ref(1)
    assert versions.current_draft() is None
    assert versions.next_id() == "sv_02"

    recorder.record(imported(2))
    assert versions.current_draft() == ref(2)
    assert versions.latest_approved() == ref(1)
    assert versions.next_id() == "sv_03"

    recorder.record(approved(2))
    assert versions.latest_approved() == ref(2)
    assert versions.current_draft() is None


def test_ac5_next_id_after_sv_09_is_sv_10(recorder, versions):
    for n in range(1, 10):
        recorder.record(imported(n))
        recorder.record(approved(n))
    assert versions.next_id() == "sv_10"


def test_ac5_ids_widen_past_two_digits(recorder, versions):
    for n in range(1, 101):
        recorder.record(imported(n))
        recorder.record(approved(n))
    assert versions.latest_approved() == SpecVersionRef(id="sv_100", hash=hash_of(100))
    assert versions.next_id() == "sv_101"


def test_ac6_adapter_sees_events_recorded_after_it_was_opened(recorder, versions):
    assert versions.current_draft() is None
    recorder.record(imported(1))
    assert versions.current_draft() == ref(1)
    recorder.record(approved(1))
    assert versions.latest_approved() == ref(1)


def test_ac6_reading_changes_no_row(db, recorder):
    recorder.record(imported(1))
    recorder.record(approved(1))
    recorder.record(imported(2))

    def snapshot():
        conn = sqlite3.connect(db)
        try:
            return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall() for t in TABLES}
        finally:
            conn.close()

    before = snapshot()
    adapter = SqliteSpecVersions(db)
    adapter.latest_approved()
    adapter.current_draft()
    adapter.next_id()
    adapter.close()
    assert snapshot() == before
