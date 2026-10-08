"""TASK-009 AC1..AC6: SqliteProjector (docs/tasks/TASK-009-sqlite-projector.md)."""

import ast
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from openfactory.adapters.sqlite_projector import SqliteProjector
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

HASH_1 = "a" * 64
HASH_2 = "b" * 64
HASH_3 = "c" * 64

TABLES = ("spec_versions", "requirements", "adrs")
ORDER = {
    "spec_versions": "id",
    "requirements": "spec_version, id",
    "adrs": "spec_version, id",
}
COLUMNS = {
    "spec_versions": ["id", "hash", "status", "components", "approved_at"],
    "requirements": [
        "id",
        "spec_version",
        "title",
        "statement",
        "priority",
        "deprecated",
        "components",
        "constrained_by",
        "acceptance_criteria",
        "hash",
    ],
    "adrs": ["id", "spec_version", "status", "body", "hash"],
}
PROJECTOR_SOURCE = (
    Path(__file__).parents[2] / "src" / "openfactory" / "adapters" / "sqlite_projector.py"
)

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


def imported(version="sv_01", digest=HASH_1, spec=None, created_at=None):
    payload = SpecImportedPayload(
        spec_version=version, hash=digest, spec=spec or spec_set()
    ).model_dump(mode="json")
    return make_event(version, EventType.SpecImported, payload, created_at)


def validated(version="sv_01", violations=()):
    payload = SpecValidatedPayload.model_validate(
        {
            "spec_version": version,
            "hash": HASH_1,
            "violations": list(violations),
            "warnings": [],
        }
    ).model_dump(mode="json")
    return make_event(version, EventType.SpecValidated, payload)


def approved(version="sv_01", digest=HASH_1, created_at=None):
    payload = SpecApprovedPayload(spec_version=version, hash=digest).model_dump(mode="json")
    return make_event(version, EventType.SpecApproved, payload, created_at, actor="human")


def make_event(version, type, payload, created_at=None, actor="orchestrator"):
    return Event(
        event_id=uuid4(),
        stream=f"spec:{version}",
        type=type,
        payload=payload,
        actor=actor,
        created_at=created_at or datetime.now(UTC),
    )


def snapshot(conn):
    """Every row of the three tables, in primary-key order."""
    return {
        table: conn.execute(f"SELECT * FROM {table} ORDER BY {ORDER[table]}").fetchall()
        for table in TABLES
    }


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


def stored(store, event):
    return store.append(event)


# AC1: tables, columns, keys, no FK/CHECK, idempotent, no app import


def test_ac1_creates_exactly_the_m1_tables_with_spec_columns_and_keys(conn, projector):
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert names == set(TABLES)
    for table, columns in COLUMNS.items():
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        assert [row[1] for row in info] == columns
    keys = {
        table: [
            r[1]
            for r in sorted(conn.execute(f"PRAGMA table_info({table})"), key=lambda r: r[5])
            if r[5]
        ]
        for table in TABLES
    }
    assert keys == {
        "spec_versions": ["id"],
        "requirements": ["spec_version", "id"],
        "adrs": ["spec_version", "id"],
    }


def test_ac1_no_foreign_key_and_no_check_constraint(conn, projector):
    for table in TABLES:
        assert conn.execute(f"PRAGMA foreign_key_list({table})").fetchall() == []
    sql = " ".join(r[0] for r in conn.execute("SELECT sql FROM sqlite_master WHERE type='table'"))
    assert "CHECK" not in sql.upper()


def test_ac1_create_tables_twice_changes_nothing(conn, projector):
    projector.apply(imported())
    before = snapshot(conn)
    projector.create_tables()
    assert snapshot(conn) == before


def test_ac1_projector_module_imports_nothing_from_app():
    tree = ast.parse(PROJECTOR_SOURCE.read_text())
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
    assert not [m for m in modules if m.startswith("openfactory.app")]


# AC2: SpecImported projects the version, requirements and ADR rows


def test_ac2_import_writes_version_requirement_and_adr_rows(conn, projector):
    projector.apply(imported())
    version = conn.execute("SELECT * FROM spec_versions").fetchall()
    assert len(version) == 1
    vid, vhash, status, components, approved_at = version[0]
    assert (vid, vhash, status, approved_at) == ("sv_01", HASH_1, "draft", None)
    assert json.loads(components) == ["auth"]

    rows = conn.execute(
        "SELECT id, spec_version, title, statement, priority, deprecated, components,"
        " constrained_by, acceptance_criteria, hash FROM requirements ORDER BY id"
    ).fetchall()
    assert [r[0] for r in rows] == ["REQ-AUTH-001", "REQ-AUTH-002"]
    for row, req, deprecated in zip(rows, (REQ_AUTH, REQ_OLD), (0, 1), strict=True):
        assert row[1:6] == (
            "sv_01",
            req.title,
            req.statement,
            req.priority.value,
            deprecated,
        )
        assert json.loads(row[6]) == req.components
        assert json.loads(row[7]) == req.constrained_by
        assert json.loads(row[8]) == [c.model_dump() for c in req.acceptance_criteria]
        assert row[9] == content_hash(req)

    adrs = conn.execute("SELECT id, spec_version, status, body, hash FROM adrs").fetchall()
    assert adrs == [("ADR-001", "sv_01", "accepted", "Use sessions.", content_hash(ADR_1))]


# AC3: re-importing a draft replaces its content


def test_ac3_second_import_replaces_draft_content(conn, projector):
    projector.apply(imported())
    changed_req = REQ_AUTH.model_copy(update={"statement": "Users can sign in."})
    changed_adr = ADR_1.model_copy(update={"body": "Use tokens."})
    projector.apply(
        imported(
            digest=HASH_2,
            spec=spec_set(
                requirements=[changed_req], adrs=[changed_adr], components=("auth", "ui")
            ),
        )
    )
    versions = conn.execute("SELECT id, hash, status, components FROM spec_versions").fetchall()
    assert len(versions) == 1
    assert versions[0][:3] == ("sv_01", HASH_2, "draft")
    assert json.loads(versions[0][3]) == ["auth", "ui"]

    reqs = conn.execute("SELECT id, statement, hash FROM requirements").fetchall()
    assert reqs == [("REQ-AUTH-001", "Users can sign in.", content_hash(changed_req))]
    adrs = conn.execute("SELECT id, body, hash FROM adrs").fetchall()
    assert adrs == [("ADR-001", "Use tokens.", content_hash(changed_adr))]


# AC4: approval, later drafts and validation events


def test_ac4_approval_sets_status_and_approved_at_only(conn, projector):
    projector.apply(imported())
    before = snapshot(conn)
    when = datetime(2026, 10, 9, 12, 30, 15, tzinfo=UTC)
    projector.apply(approved(created_at=when))
    after = snapshot(conn)
    assert after["requirements"] == before["requirements"]
    assert after["adrs"] == before["adrs"]
    old, new = before["spec_versions"][0], after["spec_versions"][0]
    assert new[0] == old[0] and new[1] == old[1] and new[3] == old[3]
    assert new[2] == "approved"
    assert new[4] == when.isoformat()


def test_ac4_import_of_next_version_leaves_approved_version_unchanged(conn, projector):
    projector.apply(imported())
    projector.apply(approved())
    approved_rows = snapshot(conn)
    projector.apply(imported(version="sv_02", digest=HASH_2))
    after = snapshot(conn)
    for table in TABLES:
        key = 0 if table == "spec_versions" else 1
        assert [r for r in after[table] if r[key] == "sv_01"] == approved_rows[table]
    assert [r for r in after["spec_versions"] if r[0] == "sv_02"][0][2] == "draft"
    assert {r[1] for r in after["requirements"]} == {"sv_01", "sv_02"}
    assert {r[1] for r in after["adrs"]} == {"sv_01", "sv_02"}


@pytest.mark.parametrize(
    "violations",
    [[], [{"rule": "R1", "subject": "REQ-AUTH-001", "message": "bad"}]],
)
def test_ac4_validated_changes_no_row(conn, projector, violations):
    projector.apply(imported())
    before = snapshot(conn)
    projector.apply(validated(violations=violations))
    assert snapshot(conn) == before


# AC5: invalid payloads raise and write nothing; unprojected types are ignored


def raw_event(type, payload, version="sv_01"):
    return make_event(version, type, payload)


def good_import_payload():
    return imported().payload


def bad_payloads():
    no_hash = {k: v for k, v in good_import_payload().items() if k != "hash"}
    extra = {**good_import_payload(), "surprise": 1}
    return {
        "import-no-hash": (EventType.SpecImported, no_hash),
        "import-extra-key": (EventType.SpecImported, extra),
        "approved-bad-version": (
            EventType.SpecApproved,
            {"spec_version": "v1", "hash": HASH_1},
        ),
        "validated-no-warnings": (
            EventType.SpecValidated,
            {"spec_version": "sv_01", "hash": HASH_1, "violations": []},
        ),
    }


@pytest.mark.parametrize("case", list(bad_payloads()))
def test_ac5_invalid_payload_raises_validation_error_and_writes_nothing(conn, projector, case):
    projector.apply(imported())
    before = snapshot(conn)
    type, payload = bad_payloads()[case]
    with pytest.raises(ValidationError):
        projector.apply(raw_event(type, payload))
    assert snapshot(conn) == before


def test_ac5_event_type_without_projection_is_ignored(conn, projector, store):
    projector.apply(imported())
    before = snapshot(conn)
    event = stored(
        store,
        Event.new(
            stream="task:AUTH-002",
            type=EventType.TaskStateChanged,
            payload={"to": "ready", "anything": [1, 2]},
            actor="orchestrator",
        ),
    )
    projector.apply(event)
    assert snapshot(conn) == before


# AC6: rebuild is identical


def build_log(store, projector):
    changed = spec_set(requirements=[REQ_AUTH], components=("auth", "ui"))
    events = [
        imported(),
        validated(),
        imported(digest=HASH_2, spec=changed),
        validated(),
        approved(digest=HASH_2),
        Event.new(
            stream="task:AUTH-002",
            type=EventType.TaskStateChanged,
            payload={"to": "ready"},
            actor="orchestrator",
        ),
        imported(version="sv_02", digest=HASH_3),
        validated(version="sv_02"),
    ]
    for event in events:
        projector.apply(stored(store, event))


def test_ac6_rebuild_gives_identical_rows(conn, projector, store):
    build_log(store, projector)
    before = snapshot(conn)
    assert before["spec_versions"]
    projector.rebuild(store.read())
    assert snapshot(conn) == before


def test_ac6_rebuild_applies_events_in_seq_order(conn, projector, store):
    build_log(store, projector)
    before = snapshot(conn)
    projector.rebuild(reversed(store.read()))
    assert snapshot(conn) == before


def test_ac6_rebuild_drops_rows_not_in_the_log(conn, projector, store):
    build_log(store, projector)
    conn.execute(
        "INSERT INTO requirements VALUES ('REQ-X-001', 'sv_09', 't', 's', 'must', 0,"
        " '[]', '[]', '[]', 'h')"
    )
    projector.rebuild(store.read())
    assert conn.execute("SELECT 1 FROM requirements WHERE id = 'REQ-X-001'").fetchall() == []


def test_ac6_rebuild_into_a_second_database_gives_same_rows(conn, projector, store, tmp_path):
    build_log(store, projector)
    other = sqlite3.connect(tmp_path / "second.db")
    try:
        second = SqliteProjector(other)
        second.create_tables()
        second.rebuild(store.read())
        assert snapshot(other) == snapshot(conn)
    finally:
        other.close()
