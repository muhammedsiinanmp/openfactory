"""TASK-079 AC3: recording a TestsCollected validates it; TASK-080 AC1..AC6: the trace_links
projection (docs/tasks/TASK-080-trace-links-projection.md)."""

import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from openfactory.adapters.sqlite_projector import SqliteProjector
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.adapters.sqlite_store import SqliteEventStore
from openfactory.domain.contracts import Limits, TaskContract
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
    CollectedTest,
    CommitRecordedPayload,
    PlanApprovedPayload,
    PlanCreatedPayload,
    SpecApprovedPayload,
    SpecImportedPayload,
    TaskResolvedPayload,
    TaskStateChangedPayload,
)
from openfactory.domain.payloads import (
    TestsCollectedPayload as CollectedPayload,
)

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
        after = all_rows(db)
        assert before["trace_links"] == []
        assert after.pop("trace_links") == [
            ("test", "tests/test_a.py::test_x", "file", "tests/test_a.py", "test_tag")
        ]
        before.pop("trace_links")
        assert after == before
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


HASH = "a" * 64
HASH_2 = "b" * 64
SHA = "b" * 40
SHA_2 = "c" * 40
SHA_3 = "d" * 40


def ev(stream, type, payload, actor="orchestrator"):
    return Event(
        event_id=uuid4(),
        stream=stream,
        type=type,
        payload=payload,
        actor=actor,
        created_at=datetime.now(UTC),
    )


def requirement(req_id, constrained_by, deprecated=False):
    return Requirement(
        id=req_id,
        title="T",
        statement="S",
        priority=Priority.must,
        deprecated=deprecated,
        constrained_by=list(constrained_by),
        components=["auth"],
        acceptance_criteria=[AcceptanceCriterion(id="AC1", text="x")],
    )


def imported(version, digest, requirements):
    spec = SpecSet(
        components=["auth"],
        requirements=requirements,
        adrs=[Adr(id="ADR-001", status=AdrStatus.accepted, body="b")],
    )
    payload = SpecImportedPayload(spec_version=version, hash=digest, spec=spec)
    return ev(version, EventType.SpecImported, payload.model_dump(mode="json"))


def approved(version, digest):
    payload = SpecApprovedPayload(spec_version=version, hash=digest).model_dump(mode="json")
    return ev(version, EventType.SpecApproved, payload, actor="human")


def contract(task_id, requirements, depends_on=()):
    return TaskContract(
        task_id=task_id,
        objective="Do the work",
        requirements=list(requirements),
        acceptance_criteria=["AC-AUTH-001-1"],
        depends_on=list(depends_on),
        components=["auth"],
        role="implementer",
        allowed_paths=["app/**"],
        forbidden_paths=[".env"],
        required_gates=["path_check", "ruff", "pytest", "gitleaks", "review"],
        limits=Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.5),
    )


def plan_created(plan_id, tasks):
    payload = PlanCreatedPayload(
        plan_id=plan_id, spec_version="sv_01", policy_hash=HASH, run_id="run_0001", tasks=tasks
    ).model_dump(mode="json")
    return ev(f"plan:{plan_id}", EventType.PlanCreated, payload)


def plan_approved(plan_id):
    payload = PlanApprovedPayload(plan_id=plan_id).model_dump(mode="json")
    return ev(f"plan:{plan_id}", EventType.PlanApproved, payload, actor="human")


def commit_recorded(sha=SHA, task_id="AUTH-002", run_id="run_0002", files=("a.py", "b.py")):
    payload = CommitRecordedPayload(
        sha=sha,
        task_id=task_id,
        run_id=run_id,
        branch=f"openfactory/{task_id}",
        spec_version="sv_01",
        files=list(files),
    ).model_dump(mode="json")
    return ev(f"task:{task_id}", EventType.CommitRecorded, payload)


def collected(tests, task_id="AUTH-002", run_id="run_0002"):
    payload = CollectedPayload(
        run_id=run_id,
        task_id=task_id,
        tests=[CollectedTest(node_id=n, file=f, req=r) for n, f, r in tests],
    ).model_dump(mode="json")
    return ev(f"task:{task_id}", EventType.TestsCollected, payload)


def state_changed(task_id, from_, to):
    payload = TaskStateChangedPayload.model_validate(
        {
            "task_id": task_id,
            "from": from_,
            "to": to,
            "reason": "requirement changed" if to == "invalidated" else None,
        }
    ).model_dump(mode="json")
    return ev(f"task:{task_id}", EventType.TaskStateChanged, payload)


def resolved(task_id, decision):
    payload = TaskResolvedPayload(task_id=task_id, decision=decision).model_dump(mode="json")
    return ev(f"task:{task_id}", EventType.TaskResolved, payload, actor="human")


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


@pytest.fixture
def feed(projector, store):
    def apply(*events):
        stored = [store.append(e) for e in events]
        for s in stored:
            projector.apply(s)
        return stored

    return apply


def links(conn, source=None):
    sql = "SELECT * FROM trace_links"
    args: tuple = ()
    if source:
        sql += " WHERE source = ?"
        args = (source,)
    return conn.execute(sql + " ORDER BY 1, 2, 3, 4, 5", args).fetchall()


# AC1


def test_ac1_trace_links_has_no_fk_or_check_and_create_tables_is_idempotent(conn, projector, feed):
    assert conn.execute("PRAGMA table_info(trace_links)").fetchall()
    assert conn.execute("PRAGMA foreign_key_list(trace_links)").fetchall() == []
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'trace_links'").fetchone()[0]
    assert "CHECK" not in sql.upper()
    feed(commit_recorded())
    before = links(conn)
    assert before
    projector.create_tables()
    assert links(conn) == before


# AC2


def test_ac2_spec_approved_writes_requirement_to_adr_links(conn, feed):
    reqs = [
        requirement("REQ-AUTH-001", ["ADR-001", "ADR-002"]),
        requirement("REQ-AUTH-002", ["ADR-009"], deprecated=True),
        requirement("REQ-AUTH-003", []),
    ]
    feed(imported("sv_01", HASH, reqs))
    assert links(conn) == []
    feed(approved("sv_01", HASH))
    assert links(conn) == [
        ("requirement", "REQ-AUTH-001", "adr", "ADR-001", "spec"),
        ("requirement", "REQ-AUTH-001", "adr", "ADR-002", "spec"),
        ("requirement", "REQ-AUTH-002", "adr", "ADR-009", "spec"),
    ]


def test_ac2_a_later_approved_version_replaces_spec_rows_only(conn, feed):
    feed(imported("sv_01", HASH, [requirement("REQ-AUTH-001", ["ADR-001"])]))
    feed(approved("sv_01", HASH))
    feed(commit_recorded())
    feed(imported("sv_02", HASH_2, [requirement("REQ-AUTH-001", ["ADR-003"])]))
    feed(approved("sv_02", HASH_2))
    assert links(conn, "spec") == [("requirement", "REQ-AUTH-001", "adr", "ADR-003", "spec")]
    assert {r[4] for r in links(conn)} == {"spec", "trailer", "diff"}


# AC3


def test_ac3_plan_created_alone_writes_no_contract_rows(conn, feed):
    feed(plan_created("plan_01", [contract("AUTH-001", ["REQ-AUTH-001"])]))
    assert links(conn, "contract") == []


def test_ac3_approved_plan_writes_contract_rows_of_its_tasks_only(conn, feed):
    feed(plan_created("plan_01", [contract("OLD-001", ["REQ-OLD-001"])]))
    feed(
        plan_created(
            "plan_02",
            [
                contract("AUTH-001", ["REQ-AUTH-001"]),
                contract("AUTH-002", ["REQ-AUTH-001", "REQ-AUTH-002"], ["AUTH-001"]),
            ],
        )
    )
    feed(plan_approved("plan_02"))
    assert links(conn, "contract") == [
        ("requirement", "REQ-AUTH-001", "task", "AUTH-001", "contract"),
        ("requirement", "REQ-AUTH-001", "task", "AUTH-002", "contract"),
        ("requirement", "REQ-AUTH-002", "task", "AUTH-002", "contract"),
        ("task", "AUTH-002", "task", "AUTH-001", "contract"),
    ]


# AC4


def test_ac4_commit_recorded_writes_trailer_and_diff_rows(conn, feed):
    feed(commit_recorded())
    assert links(conn) == [
        ("commit", SHA, "file", "a.py", "diff"),
        ("commit", SHA, "file", "b.py", "diff"),
        ("run", "run_0002", "commit", SHA, "trailer"),
        ("task", "AUTH-002", "run", "run_0002", "trailer"),
    ]


def test_ac4_a_second_task_adds_rows_and_keeps_the_first(conn, feed):
    feed(commit_recorded())
    first = links(conn)
    feed(commit_recorded(SHA_2, "AUTH-003", "run_0003", ["c.py"]))
    assert len(links(conn)) == len(first) + 3
    assert set(first) <= set(links(conn))
    assert ("task", "AUTH-003", "run", "run_0003", "trailer") in links(conn)


# AC5


def test_ac5_collected_writes_file_and_requirement_rows(conn, feed):
    feed(
        collected(
            [
                ("t.py::a", "t.py", ["REQ-AUTH-001"]),
                ("t.py::b", "t.py", []),
                ("u.py::c", "u.py", ["REQ-AUTH-001", "REQ-AUTH-002"]),
            ]
        )
    )
    assert links(conn) == [
        ("test", "t.py::a", "file", "t.py", "test_tag"),
        ("test", "t.py::a", "requirement", "REQ-AUTH-001", "test_tag"),
        ("test", "t.py::b", "file", "t.py", "test_tag"),
        ("test", "u.py::c", "file", "u.py", "test_tag"),
        ("test", "u.py::c", "requirement", "REQ-AUTH-001", "test_tag"),
        ("test", "u.py::c", "requirement", "REQ-AUTH-002", "test_tag"),
    ]


def test_ac5_a_second_collection_replaces_test_tag_rows_only(conn, feed):
    feed(imported("sv_01", HASH, [requirement("REQ-AUTH-001", ["ADR-001"])]))
    feed(approved("sv_01", HASH))
    feed(plan_created("plan_01", [contract("AUTH-001", ["REQ-AUTH-001"])]))
    feed(plan_approved("plan_01"))
    feed(commit_recorded())
    feed(collected([("t.py::a", "t.py", ["REQ-AUTH-001"])]))
    others = [r for r in links(conn) if r[4] != "test_tag"]
    assert {r[4] for r in others} == {"spec", "contract", "trailer", "diff"}
    feed(collected([("v.py::z", "v.py", [])]))
    assert links(conn, "test_tag") == [("test", "v.py::z", "file", "v.py", "test_tag")]
    assert [r for r in links(conn) if r[4] != "test_tag"] == others


# AC6


def test_ac6_a_link_written_twice_is_stored_once(conn, feed):
    feed(plan_created("plan_01", [contract("AUTH-001", ["REQ-AUTH-001", "REQ-AUTH-001"])]))
    feed(plan_approved("plan_01"))
    assert links(conn, "contract") == [
        ("requirement", "REQ-AUTH-001", "task", "AUTH-001", "contract")
    ]
    feed(collected([("t.py::a", "t.py", ["REQ-AUTH-001", "REQ-AUTH-001"])]))
    assert len(links(conn, "test_tag")) == 2
    feed(commit_recorded(SHA))
    feed(commit_recorded(SHA_2))
    assert links(conn, "trailer") == [
        ("run", "run_0002", "commit", SHA, "trailer"),
        ("run", "run_0002", "commit", SHA_2, "trailer"),
        ("task", "AUTH-002", "run", "run_0002", "trailer"),
    ]


@pytest.mark.parametrize("kind", ["abandoned", "invalidated", "resolve-abandon"])
def test_ac6_abandon_and_invalidate_remove_no_link(conn, feed, kind):
    feed(plan_created("plan_01", [contract("AUTH-002", ["REQ-AUTH-001"])]))
    feed(plan_approved("plan_01"))
    feed(commit_recorded())
    before = links(conn)
    assert before
    if kind == "resolve-abandon":
        feed(resolved("AUTH-002", "abandon"))
    else:
        feed(state_changed("AUTH-002", "ready", kind))
    assert links(conn) == before


def test_ac6_rebuild_gives_identical_links(conn, projector, feed):
    stored = feed(
        imported("sv_01", HASH, [requirement("REQ-AUTH-001", ["ADR-001"])]),
        approved("sv_01", HASH),
        plan_created(
            "plan_01",
            [
                contract("AUTH-001", ["REQ-AUTH-001"]),
                contract("AUTH-002", ["REQ-AUTH-001"], ["AUTH-001"]),
            ],
        ),
        plan_approved("plan_01"),
        collected([("t.py::a", "t.py", ["REQ-AUTH-001"])]),
        commit_recorded(),
    )
    before = links(conn)
    assert {r[4] for r in before} == {"spec", "contract", "trailer", "diff", "test_tag"}
    projector.rebuild(stored)
    assert links(conn) == before
