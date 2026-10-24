"""TASK-090 AC5: recording an ImpactComputed validates it and changes no projection
(docs/tasks/TASK-090-impact-computed-payload.md)."""

import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from openfactory.adapters.sqlite_plans import SqlitePlans
from openfactory.adapters.sqlite_projector import SqliteProjector
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
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
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    CommitRecordedPayload,
    PlanApprovedPayload,
    PlanCreatedPayload,
    SpecApprovedPayload,
    SpecImportedPayload,
    TaskStateChangedPayload,
)

HASH = "a" * 64
GOOD = {
    "from_version": "sv_01",
    "to_version": "sv_02",
    "run_id": "run_0002",
    "requirements": [
        {
            "id": "REQ-AUTH-001",
            "change": "modified",
            "kind": "behavioral",
            "rationale": "why",
            "obsolete_criteria": ["AC1"],
            "new_work": ["do it"],
        }
    ],
    "adrs": [{"id": "ADR-001", "change": "modified"}],
    "tasks": ["AUTH-001"],
    "downstream": [],
    "files": ["a.py"],
    "tests": ["tests/test_a.py::test_x"],
}


def ev(stream, type, payload, actor="orchestrator"):
    return Event(
        event_id=uuid4(),
        stream=stream,
        type=type,
        payload=payload,
        actor=actor,
        created_at=datetime.now(UTC),
    )


def impact(payload):
    return ev("spec:sv_02", EventType.ImpactComputed, payload)


def all_rows(db) -> dict[str, list]:
    conn = sqlite3.connect(db)
    try:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        return {
            n: conn.execute(f'SELECT * FROM "{n}" ORDER BY 1, 2').fetchall()
            for n in names
            if n not in ("events", "projection_state", "sqlite_sequence")
        }
    finally:
        conn.close()


def setup_events():
    spec = SpecSet(
        components=["auth"],
        requirements=[
            Requirement(
                id="REQ-AUTH-001",
                title="T",
                statement="S",
                priority=Priority.must,
                deprecated=False,
                constrained_by=["ADR-001"],
                components=["auth"],
                acceptance_criteria=[AcceptanceCriterion(id="AC1", text="x")],
            )
        ],
        adrs=[Adr(id="ADR-001", status=AdrStatus.accepted, body="b")],
    )
    task = TaskContract(
        task_id="AUTH-001",
        objective="Do the work",
        requirements=["REQ-AUTH-001"],
        acceptance_criteria=["AC-AUTH-001-1"],
        depends_on=[],
        components=["auth"],
        role="implementer",
        allowed_paths=["app/**"],
        forbidden_paths=[".env"],
        required_gates=["path_check", "ruff", "pytest", "gitleaks", "review"],
        limits=Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.5),
    )
    imported = SpecImportedPayload(spec_version="sv_01", hash=HASH, spec=spec)
    approved = SpecApprovedPayload(spec_version="sv_01", hash=HASH)
    created = PlanCreatedPayload(
        plan_id="plan_01", spec_version="sv_01", policy_hash=HASH, run_id="run_0001", tasks=[task]
    )
    return [
        ev("sv_01", EventType.SpecImported, imported.model_dump(mode="json")),
        ev("sv_01", EventType.SpecApproved, approved.model_dump(mode="json"), actor="human"),
        ev("plan:plan_01", EventType.PlanCreated, created.model_dump(mode="json")),
        ev(
            "plan:plan_01",
            EventType.PlanApproved,
            PlanApprovedPayload(plan_id="plan_01").model_dump(mode="json"),
            actor="human",
        ),
    ]


def test_task090_ac5_an_impact_computed_event_is_recorded_and_changes_no_projection(
    tmp_path,
) -> None:
    db = tmp_path / "events.db"
    recorder = SqliteEventRecorder(db)
    try:
        for e in setup_events():
            recorder.record(e)
        before = all_rows(db)
        assert any(before.values())
        stored = recorder.record(impact(GOOD))
        assert stored.type == "ImpactComputed"
        assert stored.stream == "spec:sv_02"
        assert all_rows(db) == before
    finally:
        recorder.close()


@pytest.mark.parametrize(
    "bad",
    [
        {k: v for k, v in GOOD.items() if k != "files"},
        {**GOOD, "extra": 1},
        {**GOOD, "requirements": [{**GOOD["requirements"][0], "kind": None}]},
    ],
    ids=["missing-files", "unknown-key", "modified-without-kind"],
)
def test_task090_ac5_a_payload_the_model_rejects_raises_and_writes_nothing(tmp_path, bad) -> None:
    db = tmp_path / "events.db"
    recorder = SqliteEventRecorder(db)
    try:
        before = all_rows(db)
        with pytest.raises(ValidationError):
            recorder.record(impact(bad))
        assert all_rows(db) == before
        conn = sqlite3.connect(db)
        try:
            assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
        finally:
            conn.close()
    finally:
        recorder.close()


def test_task090_ac5_rebuild_of_a_log_with_an_impact_computed_gives_identical_rows(
    tmp_path,
) -> None:
    db = tmp_path / "events.db"
    recorder = SqliteEventRecorder(db)
    try:
        stored = [recorder.record(e) for e in [*setup_events(), impact(GOOD)]]
        before = all_rows(db)
        conn = sqlite3.connect(db)
        try:
            SqliteProjector(conn).rebuild(stored)
            conn.commit()
        finally:
            conn.close()
        assert all_rows(db) == before
    finally:
        recorder.close()


# TASK-097: a replan's PlanApproved supersedes the approved plan and moves its tasks
# (docs/tasks/TASK-097-projector-plan-supersede.md)

SHA = "b" * 40
OLD_STATES = {
    "AUTH-001": "passed",
    "AUTH-002": "ready",
    "AUTH-003": "pending",
    "AUTH-004": "escalated",
    "AUTH-005": "abandoned",
    "AUTH-006": "invalidated",
}


def contract(n: int, depends_on: list[str] | None = None) -> TaskContract:
    tid = f"AUTH-{n:03d}"
    return TaskContract(
        task_id=tid,
        objective=f"Do {tid}",
        requirements=["REQ-AUTH-001"],
        acceptance_criteria=[f"AC-{tid}-1"],
        depends_on=depends_on or [],
        components=["auth"],
        role="implementer",
        allowed_paths=["app/**"],
        forbidden_paths=[".env"],
        required_gates=["path_check", "ruff", "pytest", "gitleaks", "review"],
        limits=Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.5),
    )


def spec_events(version: str) -> list[Event]:
    base = setup_events()
    imported = SpecImportedPayload.model_validate(base[0].payload).model_copy(
        update={"spec_version": version}
    )
    approved = SpecApprovedPayload(spec_version=version, hash=HASH)
    return [
        ev(version, EventType.SpecImported, imported.model_dump(mode="json")),
        ev(version, EventType.SpecApproved, approved.model_dump(mode="json"), actor="human"),
    ]


def plan_created(plan_id: str, spec: str, run: str, tasks: list[TaskContract]) -> Event:
    payload = PlanCreatedPayload(
        plan_id=plan_id, spec_version=spec, policy_hash=HASH, run_id=run, tasks=tasks
    )
    return ev(f"plan:{plan_id}", EventType.PlanCreated, payload.model_dump(mode="json"))


def plan_approved(plan_id: str) -> Event:
    payload = PlanApprovedPayload(plan_id=plan_id)
    return ev(f"plan:{plan_id}", EventType.PlanApproved, payload.model_dump(mode="json"), "human")


def state_change(task_id: str, from_: str, to: str) -> Event:
    payload = TaskStateChangedPayload(
        task_id=task_id, from_=from_, to=to, reason="spec changed" if to == "invalidated" else None
    )
    return ev(f"task:{task_id}", EventType.TaskStateChanged, payload.model_dump(mode="json"))


def first_plan_events() -> list[Event]:
    """sv_01 approved, plan_01 (AUTH-001..006) approved, tasks moved into OLD_STATES, one
    costed run with a commit for AUTH-001."""
    tasks = [contract(1)] + [contract(n, ["AUTH-001"]) for n in range(2, 7)]
    started = AgentRunStartedPayload(
        run_id="run_0002",
        task_id="AUTH-001",
        role="implementer",
        runtime="claude",
        context_hash=HASH,
    )
    finished = AgentRunFinishedPayload(
        run_id="run_0002",
        exit="ok",
        model="m",
        tokens_in=1,
        tokens_out=2,
        cost_usd=0.5,
        duration_s=3.0,
        error=None,
    )
    commit = CommitRecordedPayload(
        sha=SHA,
        task_id="AUTH-001",
        run_id="run_0002",
        branch="task/AUTH-001",
        spec_version="sv_01",
        files=["app/a.py"],
    )
    events = [
        *spec_events("sv_01"),
        plan_created("plan_01", "sv_01", "run_0001", tasks),
        plan_approved("plan_01"),
        state_change("AUTH-001", "pending", "ready"),
        state_change("AUTH-001", "ready", "running"),
        ev("run:run_0002", EventType.AgentRunStarted, started.model_dump(mode="json")),
        ev("run:run_0002", EventType.AgentRunFinished, finished.model_dump(mode="json")),
        ev("task:AUTH-001", EventType.CommitRecorded, commit.model_dump(mode="json")),
        state_change("AUTH-001", "running", "passed"),
        state_change("AUTH-002", "pending", "ready"),
        state_change("AUTH-004", "pending", "escalated"),
        state_change("AUTH-005", "pending", "abandoned"),
        state_change("AUTH-006", "pending", "invalidated"),
    ]
    return events


def replan_events() -> list[Event]:
    """sv_02 approved, draft plan_02 with new task AUTH-010 depending on the passed AUTH-001."""
    return [
        *spec_events("sv_02"),
        plan_created("plan_02", "sv_02", "run_0003", [contract(10, ["AUTH-001"])]),
    ]


def query(db, sql: str) -> list:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def record_all(recorder, events) -> None:
    for e in events:
        recorder.record(e)


def test_task097_ac1_a_replan_approval_supersedes_the_earlier_approved_plan(tmp_path) -> None:
    db = tmp_path / "events.db"
    recorder = SqliteEventRecorder(db)
    try:
        record_all(recorder, [*first_plan_events(), *replan_events(), plan_approved("plan_02")])
    finally:
        recorder.close()
    assert query(db, "SELECT id, spec_version, status FROM plans ORDER BY id") == [
        ("plan_01", "sv_01", "superseded"),
        ("plan_02", "sv_02", "approved"),
    ]
    assert query(db, "SELECT COUNT(*) FROM plans WHERE status = 'approved'") == [(1,)]
    plans = SqlitePlans(db)
    try:
        approved = plans.approved()
        assert approved is not None
        assert approved.id == "plan_02"
    finally:
        plans.close()


def test_task097_ac2_every_task_of_the_superseded_plan_moves_unchanged(tmp_path) -> None:
    db = tmp_path / "events.db"
    recorder = SqliteEventRecorder(db)
    tables = ["task_deps", "commits", "agent_runs", "gate_results"]
    cols = "id, state, objective, contract, attempt, cost_usd"
    try:
        record_all(recorder, [*first_plan_events(), *replan_events()])
        old_tasks = query(db, f"SELECT {cols} FROM tasks WHERE plan_id = 'plan_01' ORDER BY id")
        before = [query(db, f"SELECT * FROM {t} ORDER BY 1, 2") for t in tables]
        assert {r[0]: r[1] for r in old_tasks} == OLD_STATES
        assert any(r[4] > 0 and r[5] > 0 for r in old_tasks)
        recorder.record(plan_approved("plan_02"))
    finally:
        recorder.close()
    ids = list(OLD_STATES)
    in_list = ", ".join(repr(i) for i in ids)
    moved = query(db, f"SELECT {cols} FROM tasks WHERE id IN ({in_list}) ORDER BY id")
    assert moved == old_tasks
    assert query(db, "SELECT DISTINCT plan_id FROM tasks WHERE id <> 'AUTH-010'") == [("plan_02",)]
    assert [query(db, f"SELECT * FROM {t} ORDER BY 1, 2") for t in tables] == before
    plans = SqlitePlans(db)
    try:
        assert [t.id for t in plans.tasks("plan_02")] == [*ids, "AUTH-010"]
        assert plans.tasks("plan_01") == []
    finally:
        plans.close()


def test_task097_ac3_existing_links_stay_and_only_the_new_tasks_links_are_added(tmp_path) -> None:
    db = tmp_path / "events.db"
    recorder = SqliteEventRecorder(db)
    sql = "SELECT * FROM trace_links ORDER BY 1, 2, 3, 4, 5"
    try:
        record_all(recorder, [*first_plan_events(), *replan_events()])
        before = query(db, sql)
        recorder.record(plan_approved("plan_02"))
    finally:
        recorder.close()
    after = query(db, sql)
    assert set(before) <= set(after)
    assert len(after) == len(set(after))
    added = set(after) - set(before)
    assert added == {
        ("requirement", "REQ-AUTH-001", "task", "AUTH-010", "contract"),
        ("task", "AUTH-010", "task", "AUTH-001", "contract"),
    }


def test_task097_ac4_an_approval_with_no_approved_plan_moves_and_supersedes_nothing(
    tmp_path,
) -> None:
    db = tmp_path / "events.db"
    recorder = SqliteEventRecorder(db)
    try:
        record_all(
            recorder,
            [
                *spec_events("sv_01"),
                plan_created("plan_01", "sv_01", "run_0001", [contract(1), contract(2)]),
                plan_created("plan_02", "sv_01", "run_0002", [contract(3)]),
                plan_approved("plan_02"),
            ],
        )
    finally:
        recorder.close()
    assert query(db, "SELECT id, status FROM plans ORDER BY id") == [
        ("plan_01", "superseded"),
        ("plan_02", "approved"),
    ]
    assert query(db, "SELECT id, plan_id FROM tasks ORDER BY id") == [("AUTH-003", "plan_02")]


def test_task097_ac5_rebuild_of_a_log_with_a_replan_gives_identical_rows(tmp_path) -> None:
    db = tmp_path / "events.db"
    recorder = SqliteEventRecorder(db)
    try:
        events = [*first_plan_events(), *replan_events(), plan_approved("plan_02")]
        stored = [recorder.record(e) for e in events]
        before = all_rows(db)
        assert any(r[1] == "plan_02" for r in before["tasks"] if r[0] == "AUTH-001")
        conn = sqlite3.connect(db)
        try:
            SqliteProjector(conn).rebuild(stored)
            conn.commit()
        finally:
            conn.close()
        assert all_rows(db) == before
    finally:
        recorder.close()
