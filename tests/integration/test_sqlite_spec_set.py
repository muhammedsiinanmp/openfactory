"""TASK-024 AC4..AC6: SpecVersions.spec_set
(docs/tasks/TASK-024-runs-port-and-stored-spec-set.md)."""

import sqlite3
from typing import Protocol

import pytest

from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.adapters.sqlite_spec_versions import SqliteSpecVersions
from openfactory.domain.events import Event, EventType
from openfactory.domain.models import AcceptanceCriterion, Adr, Requirement, SpecSet
from openfactory.domain.payloads import SpecApprovedPayload, SpecImportedPayload
from openfactory.domain.spec_hash import content_hash
from openfactory.ports.spec_versions import SpecVersions

TABLES = ("events", "spec_versions", "requirements", "adrs", "agent_runs", "projection_state")


def req(n, **kw):
    fields = {
        "id": f"REQ-{n:03d}",
        "title": f"Title {n}",
        "statement": f"Statement {n}",
        "priority": "must",
    }
    fields.update(kw)
    return Requirement(**fields)


def full_set():
    return SpecSet(
        components=["core", "cli"],
        requirements=[
            req(
                1,
                constrained_by=["ADR-001"],
                components=["core", "cli"],
                acceptance_criteria=[
                    AcceptanceCriterion(id="REQ-001.AC1", text="first"),
                    AcceptanceCriterion(id="REQ-001.AC2", text="second"),
                ],
                deprecated=True,
            ),
            req(2),
        ],
        adrs=[
            Adr(id="ADR-001", status="accepted", body="Line one\nLigne deux: café → 日本\n"),
            Adr(id="ADR-002", status="proposed", body="Short"),
        ],
    )


def imported(n, spec, hash_=None):
    version = f"sv_{n:02d}"
    payload = SpecImportedPayload(spec_version=version, hash=hash_ or content_hash(spec), spec=spec)
    return Event.new(
        stream=f"spec:{version}",
        type=EventType.SpecImported,
        payload=payload.model_dump(mode="json"),
        actor="orchestrator",
    )


def approved(n, spec):
    version = f"sv_{n:02d}"
    payload = SpecApprovedPayload(spec_version=version, hash=content_hash(spec))
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


def test_ac4_protocol_has_exactly_the_four_methods():
    assert issubclass(SpecVersions, Protocol)
    public = {
        name
        for name, value in vars(SpecVersions).items()
        if not name.startswith("_") and callable(value)
    }
    assert public == {"latest_approved", "current_draft", "next_id", "spec_set"}


def test_ac4_spec_set_returns_the_imported_set(recorder, versions):
    spec = full_set()
    recorder.record(imported(1, spec))
    assert versions.spec_set("sv_01") == spec


def test_ac4_content_hash_matches_the_draft_hash(recorder, versions):
    spec = full_set()
    recorder.record(imported(1, spec))
    result = versions.spec_set("sv_01")
    assert result is not None
    assert content_hash(result) == versions.current_draft().hash


def test_ac4_spec_set_is_the_same_after_approval(recorder, versions):
    spec = full_set()
    recorder.record(imported(1, spec))
    recorder.record(approved(1, spec))
    assert versions.spec_set("sv_01") == spec


def test_ac5_versions_do_not_leak_into_each_other(recorder, versions):
    first = full_set()
    second = SpecSet(
        components=["core", "cli"],
        requirements=[req(2, title="Changed")],
        adrs=first.adrs,
    )
    recorder.record(imported(1, first))
    recorder.record(approved(1, first))
    recorder.record(imported(2, second))
    assert versions.spec_set("sv_01") == first
    assert versions.spec_set("sv_02") == second


def test_ac5_second_import_replaces_the_draft_content(recorder, versions):
    recorder.record(imported(1, full_set()))
    replaced = SpecSet(components=["core"], requirements=[req(3)], adrs=[])
    recorder.record(imported(1, replaced))
    assert versions.spec_set("sv_01") == replaced


def test_ac5_components_only_version_has_empty_requirements_and_adrs(recorder, versions):
    recorder.record(imported(1, SpecSet(components=["core", "cli"])))
    assert versions.spec_set("sv_01") == SpecSet(components=["core", "cli"])


def test_ac5_unknown_version_returns_none(recorder, versions):
    recorder.record(imported(1, full_set()))
    assert versions.spec_set("sv_09") is None


def test_ac6_spec_set_changes_no_row(db, recorder):
    spec = full_set()
    recorder.record(imported(1, spec))
    recorder.record(approved(1, spec))
    recorder.record(imported(2, SpecSet(components=["core"])))

    def snapshot():
        conn = sqlite3.connect(db)
        try:
            return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall() for t in TABLES}
        finally:
            conn.close()

    before = snapshot()
    adapter = SqliteSpecVersions(db)
    adapter.spec_set("sv_01")
    adapter.spec_set("sv_02")
    adapter.close()
    assert snapshot() == before
