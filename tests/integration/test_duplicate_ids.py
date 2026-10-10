"""TASK-015 AC1..AC5: duplicated ids (docs/tasks/TASK-015-projector-duplicate-ids.md).

The projector keeps the first item with an id and skips the others (SC-12). OpenFactory's
own tests carry no `req` markers.
"""

import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from openfactory.adapters.filesystem_spec_files import FilesystemSpecFiles
from openfactory.adapters.sqlite_projector import SqliteProjector
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.adapters.sqlite_spec_versions import SqliteSpecVersions
from openfactory.adapters.sqlite_store import SqliteEventStore
from openfactory.app.approve_spec import ApproveOutcome, approve_spec
from openfactory.app.validate import Outcome, validate
from openfactory.domain.events import Event, EventType
from openfactory.domain.models import (
    AcceptanceCriterion,
    Adr,
    AdrStatus,
    Priority,
    Requirement,
    SpecSet,
)
from openfactory.domain.payloads import SpecImportedPayload, SpecValidatedPayload
from openfactory.domain.spec_hash import content_hash

HASH_1 = "a" * 64
HASH_2 = "b" * 64

TABLES = ("spec_versions", "requirements", "adrs")
ORDER = {
    "spec_versions": "id",
    "requirements": "spec_version, id",
    "adrs": "spec_version, id",
}


def req(id, title):
    return Requirement(
        id=id,
        title=title,
        statement="Users can do it.",
        priority=Priority.must,
        components=["auth"],
        acceptance_criteria=[AcceptanceCriterion(id="AC1", text="It works")],
    )


REQ_A = req("REQ-AUTH-001", "First title")
REQ_B = req("REQ-AUTH-001", "Second title")
REQ_C = req("REQ-AUTH-002", "Other")
ADR_X = Adr(id="ADR-001", status=AdrStatus.accepted, body="Body X.")
ADR_Y = Adr(id="ADR-001", status=AdrStatus.proposed, body="Body Y.")


def spec_set(requirements=(REQ_A, REQ_C), adrs=(ADR_X,), components=("auth",)):
    return SpecSet(components=list(components), requirements=list(requirements), adrs=list(adrs))


def imported(version="sv_01", digest=HASH_1, spec=None):
    payload = SpecImportedPayload(
        spec_version=version, hash=digest, spec=spec or spec_set()
    ).model_dump(mode="json")
    return Event(
        event_id=uuid4(),
        stream=f"spec:{version}",
        type=EventType.SpecImported,
        payload=payload,
        actor="orchestrator",
        created_at=datetime.now(UTC),
    )


def validated(version="sv_01"):
    payload = SpecValidatedPayload.model_validate(
        {"spec_version": version, "hash": HASH_1, "violations": [], "warnings": []}
    ).model_dump(mode="json")
    return Event(
        event_id=uuid4(),
        stream=f"spec:{version}",
        type=EventType.SpecValidated,
        payload=payload,
        actor="orchestrator",
        created_at=datetime.now(UTC),
    )


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


@pytest.fixture
def projection(tmp_path):
    """A bare projector over its own connection, and a store to make StoredEvents."""
    connection = sqlite3.connect(tmp_path / "projections.db")
    projector = SqliteProjector(connection)
    projector.create_tables()
    store = SqliteEventStore(tmp_path / "events.db")
    yield connection, projector, store
    store.close()
    connection.close()


# AC1: two requirements with one id


def test_ac1_first_requirement_with_an_id_is_kept_and_the_others_are_skipped(projection):
    connection, projector, store = projection
    spec = spec_set(requirements=[REQ_A, REQ_B, REQ_C])
    projector.apply(store.append(imported(spec=spec)))
    rows = connection.execute(
        "SELECT id, title, hash FROM requirements WHERE spec_version = 'sv_01' ORDER BY id"
    ).fetchall()
    assert rows == [
        ("REQ-AUTH-001", "First title", content_hash(REQ_A)),
        ("REQ-AUTH-002", "Other", content_hash(REQ_C)),
    ]
    assert connection.execute("SELECT id, hash, status FROM spec_versions").fetchall() == [
        ("sv_01", HASH_1, "draft")
    ]


def test_ac1_kept_requirement_follows_the_payload_order(projection):
    connection, projector, store = projection
    spec = spec_set(requirements=[REQ_B, REQ_A, REQ_C])
    projector.apply(store.append(imported(spec=spec)))
    rows = connection.execute("SELECT id, title, hash FROM requirements ORDER BY id").fetchall()
    assert rows == [
        ("REQ-AUTH-001", "Second title", content_hash(REQ_B)),
        ("REQ-AUTH-002", "Other", content_hash(REQ_C)),
    ]


# AC2: two ADRs with one id


def test_ac2_first_adr_with_an_id_is_kept_and_requirements_are_written(projection):
    connection, projector, store = projection
    spec = spec_set(adrs=[ADR_X, ADR_Y])
    projector.apply(store.append(imported(spec=spec)))
    assert connection.execute("SELECT id, status, body, hash FROM adrs").fetchall() == [
        ("ADR-001", "accepted", "Body X.", content_hash(ADR_X))
    ]
    assert connection.execute("SELECT id FROM requirements ORDER BY id").fetchall() == [
        ("REQ-AUTH-001",),
        ("REQ-AUTH-002",),
    ]


def test_ac2_kept_adr_follows_the_payload_order(projection):
    connection, projector, store = projection
    spec = spec_set(adrs=[ADR_Y, ADR_X])
    projector.apply(store.append(imported(spec=spec)))
    assert connection.execute("SELECT id, status, body, hash FROM adrs").fetchall() == [
        ("ADR-001", "proposed", "Body Y.", content_hash(ADR_Y))
    ]


# AC3: the recorder records, rebuilds and replaces


def duplicated_import():
    return imported(spec=spec_set(requirements=[REQ_A, REQ_B, REQ_C], adrs=[ADR_X, ADR_Y]))


def test_ac3_record_stores_both_events_and_rebuild_gives_identical_rows(db, conn, recorder):
    recorder.record(duplicated_import())
    second = recorder.record(validated())
    c = conn()
    before = snapshot(c)
    assert len(before["requirements"]) == 2
    assert len(before["adrs"]) == 1
    assert len(read_all(db)) == 2
    assert state_rows(c) == [(1, second.seq)]
    recorder.rebuild()
    assert snapshot(c) == before
    assert state_rows(c) == [(1, second.seq)]


def test_ac3_a_later_import_without_the_duplicate_replaces_the_content(
    tmp_path, db, conn, recorder
):
    later = imported(digest=HASH_2, spec=spec_set(requirements=[REQ_B, REQ_C], adrs=[ADR_Y]))
    recorder.record(duplicated_import())
    recorder.record(later)
    reference_db = tmp_path / "reference.db"
    reference = SqliteEventRecorder(reference_db)
    reference.record(later)
    reference.close()
    c = conn()
    r = sqlite3.connect(reference_db)
    try:
        assert snapshot(c) == snapshot(r)
        assert snapshot(c)["requirements"][0][2] == "Second title"
    finally:
        r.close()


# AC4: catch-up applies a stored duplicated import


def test_ac4_catch_up_applies_a_stored_import_with_a_duplicated_requirement(tmp_path, db, conn):
    events = [duplicated_import(), validated()]
    SqliteEventRecorder(db).close()
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
        assert len(snapshot(c)["requirements"]) == 2
        assert state_rows(c) == [(1, max(e.seq for e in read_all(db)))]
    finally:
        r.close()


# AC5: validate and approve_spec on files with a duplicated requirement id

REQUIREMENTS_YAML = """\
components: [auth]
requirements:
  - id: REQ-AUTH-001
    title: Login
    statement: Users can log in.
    priority: must
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-001-1
        text: Valid login returns a JWT.
  - id: REQ-AUTH-001
    title: Login again
    statement: Users can log in twice.
    priority: should
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-001-2
        text: Second login works.
"""


def test_ac5_validate_and_approve_spec_report_id_unique_and_never_approve(tmp_path, db, conn):
    specs = tmp_path / "specs"
    (specs / "adrs").mkdir(parents=True)
    (specs / "requirements.yaml").write_text(REQUIREMENTS_YAML)
    (specs / "policies.yaml").write_text("max_attempts: 3\n")
    files = FilesystemSpecFiles(specs)
    recorder = SqliteEventRecorder(db)
    versions = SqliteSpecVersions(db)
    try:
        result = validate(files, versions, recorder)
        assert result.outcome is Outcome.validated
        assert result.spec_version == "sv_01"
        assert [
            (v.rule.value, v.subject) for v in result.violations if v.rule.value == "id-unique"
        ] == [("id-unique", "REQ-AUTH-001")]
        events = read_all(db)
        assert [e.type for e in events] == [EventType.SpecImported, EventType.SpecValidated]
        recorded = events[1].payload["violations"]
        assert any(v["rule"] == "id-unique" and v["subject"] == "REQ-AUTH-001" for v in recorded)

        approval = approve_spec(files, versions, recorder)
        assert approval.outcome is ApproveOutcome.refused
        assert EventType.SpecApproved not in {e.type for e in read_all(db)}
        c = conn()
        assert c.execute("SELECT id, status FROM spec_versions").fetchall() == [("sv_01", "draft")]
    finally:
        versions.close()
        recorder.close()
