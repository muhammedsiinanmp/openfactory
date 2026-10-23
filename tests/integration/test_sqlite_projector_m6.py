"""TASK-090 AC5: recording an ImpactComputed validates it and changes no projection
(docs/tasks/TASK-090-impact-computed-payload.md)."""

import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

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
    PlanApprovedPayload,
    PlanCreatedPayload,
    SpecApprovedPayload,
    SpecImportedPayload,
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
