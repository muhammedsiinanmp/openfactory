"""TASK-081 AC2 to AC6: SqliteTraces.untested_requirements
(docs/tasks/TASK-081-traces-port.md)."""

import sqlite3

import pytest

from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.adapters.sqlite_traces import SqliteTraces
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType
from openfactory.domain.models import Priority, Requirement, SpecSet
from openfactory.domain.payloads import (
    CollectedTest,
    PlanApprovedPayload,
    PlanCreatedPayload,
    SpecImportedPayload,
    TestsCollectedPayload,
)

HASH = "a" * 64
GATES = ["path_check", "ruff", "pytest", "gitleaks", "review"]


def req(id, deprecated=False):
    return Requirement(
        id=id,
        title=f"Title {id}",
        statement="Users can do it.",
        priority=Priority.must,
        components=["auth"],
        deprecated=deprecated,
    )


def ev(stream, type_, payload, actor="orchestrator"):
    return Event.new(
        stream=stream, type=type_, payload=payload.model_dump(mode="json"), actor=actor
    )


def imported(version, requirements):
    spec = SpecSet(components=["auth"], requirements=list(requirements), adrs=[])
    payload = SpecImportedPayload(spec_version=version, hash=HASH, spec=spec)
    return ev(f"spec:{version}", EventType.SpecImported, payload)


def collected(*tests):
    payload = TestsCollectedPayload(
        run_id="run_0002",
        task_id="AUTH-001",
        tests=[CollectedTest(node_id=n, file=f, req=r) for n, f, r in tests],
    )
    return ev("task:AUTH-001", EventType.TestsCollected, payload)


def contract(task_id, requirements):
    return TaskContract(
        task_id=task_id,
        objective=f"Do {task_id}",
        requirements=requirements,
        acceptance_criteria=["AC-AUTH-001-1"],
        depends_on=[],
        components=["auth"],
        role="implementer",
        allowed_paths=["app/auth/**"],
        forbidden_paths=["specs/**"],
        required_gates=GATES,
        limits=Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.5),
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
def traces(db, recorder):
    adapter = SqliteTraces(db)
    yield adapter
    adapter.close()


# AC2: untested requirements of a version


def test_ac2_untagged_requirements_are_returned(recorder, traces):
    recorder.record(imported("sv_01", [req("REQ-A-1"), req("REQ-A-2"), req("REQ-A-3")]))
    recorder.record(
        collected(
            ("t.py::test_one", "t.py", ["REQ-A-1"]),
            ("t.py::test_untagged", "t.py", []),
        )
    )
    assert traces.untested_requirements("sv_01") == ["REQ-A-2", "REQ-A-3"]


def test_ac2_all_tagged_gives_empty_list(recorder, traces):
    recorder.record(imported("sv_01", [req("REQ-A-1"), req("REQ-A-2")]))
    recorder.record(collected(("t.py::test_one", "t.py", ["REQ-A-1", "REQ-A-2"])))
    assert traces.untested_requirements("sv_01") == []


# AC3: deprecated requirements


def test_ac3_deprecated_requirements_are_never_returned(recorder, traces):
    recorder.record(
        imported(
            "sv_01",
            [req("REQ-A-1"), req("REQ-A-2", deprecated=True), req("REQ-A-3", deprecated=True)],
        )
    )
    recorder.record(collected(("t.py::test_dep", "t.py", ["REQ-A-3"])))
    assert traces.untested_requirements("sv_01") == ["REQ-A-1"]


# AC4: only test_tag links from a test count


def test_ac4_a_contract_link_does_not_count_as_a_test(recorder, traces):
    recorder.record(imported("sv_01", [req("REQ-A-1"), req("REQ-A-2")]))
    created = PlanCreatedPayload(
        plan_id="plan_01",
        spec_version="sv_01",
        policy_hash=HASH,
        run_id="run_0001",
        tasks=[contract("AUTH-001", ["REQ-A-1"])],
    )
    recorder.record(ev("plan:plan_01", EventType.PlanCreated, created))
    recorder.record(
        ev("plan:plan_01", EventType.PlanApproved, PlanApprovedPayload(plan_id="plan_01"), "human")
    )
    assert traces.untested_requirements("sv_01") == ["REQ-A-1", "REQ-A-2"]


def test_ac4_a_later_collection_that_drops_a_tag_returns_the_requirement(recorder, traces):
    recorder.record(imported("sv_01", [req("REQ-A-1"), req("REQ-A-2")]))
    recorder.record(collected(("t.py::test_one", "t.py", ["REQ-A-1", "REQ-A-2"])))
    assert traces.untested_requirements("sv_01") == []
    recorder.record(collected(("t.py::test_one", "t.py", ["REQ-A-1"])))
    assert traces.untested_requirements("sv_01") == ["REQ-A-2"]


# AC5: per version, sorted as strings


def test_ac5_each_version_returns_only_its_own_requirements(recorder, traces):
    recorder.record(imported("sv_01", [req("REQ-A-1"), req("REQ-A-2")]))
    recorder.record(imported("sv_02", [req("REQ-B-1"), req("REQ-A-2")]))
    recorder.record(collected(("t.py::test_one", "t.py", ["REQ-A-2"])))
    assert traces.untested_requirements("sv_01") == ["REQ-A-1"]
    assert traces.untested_requirements("sv_02") == ["REQ-B-1"]


def test_ac5_unknown_version_gives_empty_list(recorder, traces):
    recorder.record(imported("sv_01", [req("REQ-A-1")]))
    assert traces.untested_requirements("sv_09") == []


def test_ac5_ids_are_sorted_as_strings(recorder, traces):
    ids = ["REQ-A-2", "REQ-A-10", "REQ-A-1", "REQ-B-1", "REQ-A-20"]
    recorder.record(imported("sv_01", [req(i) for i in ids]))
    assert traces.untested_requirements("sv_01") == sorted(ids)
    assert traces.untested_requirements("sv_01")[:3] == ["REQ-A-1", "REQ-A-10", "REQ-A-2"]


# AC6: read-only


def snapshot(db):
    conn = sqlite3.connect(db)
    try:
        names = [
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY 1")
        ]
        return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall() for t in names}
    finally:
        conn.close()


def test_ac6_the_read_changes_no_row_and_creates_no_table(db, recorder):
    recorder.record(imported("sv_01", [req("REQ-A-1"), req("REQ-A-2")]))
    recorder.record(collected(("t.py::test_one", "t.py", ["REQ-A-1"])))
    before = snapshot(db)
    adapter = SqliteTraces(db)
    adapter.untested_requirements("sv_01")
    adapter.untested_requirements("sv_09")
    adapter.close()
    assert snapshot(db) == before
    assert "trace_links" in before


def test_ac6_a_database_without_projections_raises_operational_error(db):
    adapter = SqliteTraces(db)
    try:
        with pytest.raises(sqlite3.OperationalError):
            adapter.untested_requirements("sv_01")
    finally:
        adapter.close()
