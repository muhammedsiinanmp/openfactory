"""TASK-105 AC1..AC5: `approve plan` after a replan (docs/tasks/TASK-105-*.md)."""

import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from openfactory.adapters.filesystem_spec_files import FilesystemSpecFiles
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.app.spec_loader import load_spec
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import (
    ImpactComputedPayload,
    PlanApprovedPayload,
    PlanCreatedPayload,
    RequirementImpact,
    SpecApprovedPayload,
    SpecImportedPayload,
    TaskStateChangedPayload,
)
from openfactory.domain.spec_hash import content_hash

runner = CliRunner()

DB = Path(".openfactory/openfactory.db")
REQS = Path("specs/requirements.yaml")
HASH = "a" * 64
GATES = ["path_check", "ruff", "pytest", "gitleaks", "review"]

# AUTH-001 (REQ-AUTH-001): untouched, passed. AUTH-002 (REQ-AUTH-002): impacted, passed.
# AUTH-003 (REQ-AUTH-003): downstream, pending. REQ-AUTH-004 is added in sv_02.
REQUIREMENTS = """\
components: [auth]
requirements:
  - id: REQ-AUTH-001
    title: One
    statement: Users can log in.
    priority: must
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-001-1
        text: Criterion one.
  - id: REQ-AUTH-002
    title: Two
    statement: Users can refresh.
    priority: must
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-002-1
        text: Criterion two.
  - id: REQ-AUTH-003
    title: Three
    statement: Users can log out.
    priority: must
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-003-1
        text: Criterion three.
  - id: REQ-AUTH-004
    title: Four
    statement: Users can reset.
    priority: must
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-004-1
        text: Criterion four.
"""


def init_repo(tmp_path: Path) -> Path:
    from openfactory.cli import app

    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "main.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "app/main.py"], cwd=repo, check=True)
    assert runner.invoke(app, ["init", str(repo)]).exit_code == 0
    (repo / REQS).write_text(REQUIREMENTS, encoding="utf-8")
    return repo


def contract(task_id: str, req_n: int, depends_on: list[str]) -> TaskContract:
    return TaskContract(
        task_id=task_id,
        objective=f"Do {task_id}",
        requirements=[f"REQ-AUTH-00{req_n}"],
        acceptance_criteria=[f"AC-AUTH-00{req_n}-1"],
        depends_on=depends_on,
        components=["auth"],
        role="implementer",
        allowed_paths=["app/**"],
        forbidden_paths=["specs/**"],
        required_gates=GATES,
        limits=Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.5),
    )


def run_approve(repo: Path, monkeypatch: pytest.MonkeyPatch) -> Result:
    from openfactory.cli import app

    monkeypatch.chdir(repo)
    return runner.invoke(app, ["approve", "plan"])


def seed(repo: Path, *, busy: str | None = None, later_spec: bool = False) -> None:
    """Seed sv_01/sv_02, approved plan_01, three ImpactComputed events and draft plan_02."""
    spec = load_spec(FilesystemSpecFiles(repo / "specs")).spec
    assert spec is not None
    recorder = SqliteEventRecorder(repo / DB)

    def rec(stream: str, type_: EventType, payload: Any, actor: str = "orchestrator") -> None:
        recorder.record(
            Event.new(
                stream=stream, type=type_, payload=payload.model_dump(mode="json"), actor=actor
            )
        )

    def move(task_id: str, steps: list[str]) -> None:
        for a, b in zip(steps, steps[1:], strict=False):
            rec(
                f"task:{task_id}",
                EventType.TaskStateChanged,
                TaskStateChangedPayload.model_validate(
                    {"task_id": task_id, "from": a, "to": b, "reason": None}
                ),
            )

    def impact(from_version: str, tasks: list[str], downstream: list[str]) -> None:
        rec(
            "spec:sv_02",
            EventType.ImpactComputed,
            ImpactComputedPayload(
                from_version=from_version,
                to_version="sv_02",
                run_id=None,
                requirements=[
                    RequirementImpact(
                        id="REQ-AUTH-004",
                        change="added",
                        kind=None,
                        rationale=None,
                        obsolete_criteria=[],
                        new_work=[],
                    )
                ],
                adrs=[],
                tasks=tasks,
                downstream=downstream,
                files=[],
                tests=[],
            ),
        )

    try:
        versions = ["sv_01", "sv_02"] + (["sv_03"] if later_spec else [])
        for vid in versions:
            digest = HASH if vid == "sv_01" else content_hash(spec) if vid == "sv_02" else "b" * 64
            rec(
                f"spec:{vid}",
                EventType.SpecImported,
                SpecImportedPayload(spec_version=vid, hash=digest, spec=spec),
            )
            rec(
                f"spec:{vid}",
                EventType.SpecApproved,
                SpecApprovedPayload(spec_version=vid, hash=digest),
                "human",
            )
            if vid == "sv_02":
                break
        rec(
            "plan:plan_01",
            EventType.PlanCreated,
            PlanCreatedPayload(
                plan_id="plan_01",
                spec_version="sv_01",
                policy_hash=HASH,
                run_id="run_0001",
                tasks=[
                    contract("AUTH-001", 1, []),
                    contract("AUTH-002", 2, []),
                    contract("AUTH-003", 3, ["AUTH-002"]),
                ],
            ),
        )
        rec("plan:plan_01", EventType.PlanApproved, PlanApprovedPayload(plan_id="plan_01"), "human")
        for task_id in ("AUTH-001", "AUTH-002"):
            move(task_id, ["pending", "ready", "running", "gating", "passed"])
        if busy:
            move(
                "AUTH-003",
                ["pending", "ready", busy]
                if busy == "running"
                else ["pending", "ready", "running", "gating"],
            )
        impact("sv_01", ["AUTH-002"], ["AUTH-003"])
        impact("sv_00", ["AUTH-001"], [])
        rec(
            "plan:plan_02",
            EventType.PlanCreated,
            PlanCreatedPayload(
                plan_id="plan_02",
                spec_version="sv_02",
                policy_hash=HASH,
                run_id="run_0002",
                tasks=[
                    contract("AUTH-004", 4, ["AUTH-001"]),
                    contract("AUTH-005", 4, ["AUTH-004"]),
                ],
            ),
        )
        impact("sv_01", ["AUTH-001"], [])
        if later_spec:
            digest = "b" * 64
            rec(
                "spec:sv_03",
                EventType.SpecImported,
                SpecImportedPayload(spec_version="sv_03", hash=digest, spec=spec),
            )
            rec(
                "spec:sv_03",
                EventType.SpecApproved,
                SpecApprovedPayload(spec_version="sv_03", hash=digest),
                "human",
            )
    finally:
        recorder.close()


def seeded(tmp_path: Path, **kwargs: Any) -> Path:
    repo = init_repo(tmp_path)
    seed(repo, **kwargs)
    return repo


def query(repo: Path, sql: str) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(repo / DB)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def event_count(repo: Path) -> int:
    return query(repo, "SELECT COUNT(*) FROM events")[0][0]


def test_task105_ac1_prints_invalidated_then_ready_then_the_status_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = seeded(tmp_path)

    result = run_approve(repo, monkeypatch)

    assert result.stdout.splitlines() == [
        "AUTH-002  invalidated",
        "AUTH-003  invalidated",
        "AUTH-004  ready",
        "approved plan_02",
    ]
    assert result.stderr == ""
    assert result.exit_code == 0


def test_task105_ac2_records_the_events_and_moves_the_tasks_to_the_new_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = seeded(tmp_path)
    before = event_count(repo)

    assert run_approve(repo, monkeypatch).exit_code == 0

    rows = query(
        repo,
        f"SELECT event_id, stream, type, payload, actor, causation_id FROM events "
        f"WHERE seq > (SELECT MAX(seq) FROM events) - {event_count(repo) - before} ORDER BY seq",
    )
    assert [(r[1], r[2], r[4]) for r in rows] == [
        ("plan:plan_02", "PlanApproved", "human"),
        ("task:AUTH-002", "TaskStateChanged", "orchestrator"),
        ("task:AUTH-003", "TaskStateChanged", "orchestrator"),
        ("task:AUTH-004", "TaskStateChanged", "orchestrator"),
    ]
    approved_id = rows[0][0]
    assert rows[0][5] is None
    assert all(r[5] == approved_id for r in rows[1:])
    changes = [json.loads(r[3]) for r in rows[1:]]
    assert [(c["from"], c["to"], c["reason"]) for c in changes] == [
        ("passed", "invalidated", "spec change sv_02"),
        ("pending", "invalidated", "spec change sv_02"),
        ("pending", "ready", None),
    ]
    assert query(repo, "SELECT id, status FROM plans ORDER BY id") == [
        ("plan_01", "superseded"),
        ("plan_02", "approved"),
    ]
    assert query(repo, "SELECT id, plan_id, state FROM tasks ORDER BY id") == [
        ("AUTH-001", "plan_02", "passed"),
        ("AUTH-002", "plan_02", "invalidated"),
        ("AUTH-003", "plan_02", "invalidated"),
        ("AUTH-004", "plan_02", "ready"),
        ("AUTH-005", "plan_02", "pending"),
    ]


def test_task105_ac3_uses_the_latest_impact_recorded_before_the_draft_from_the_approved_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = seeded(tmp_path)
    kinds = query(
        repo,
        "SELECT seq, type, json_extract(payload, '$.from_version') FROM events "
        "WHERE type IN ('ImpactComputed', 'PlanCreated') ORDER BY seq",
    )
    assert [(k[1], k[2]) for k in kinds] == [
        ("PlanCreated", None),
        ("ImpactComputed", "sv_01"),
        ("ImpactComputed", "sv_00"),
        ("PlanCreated", None),
        ("ImpactComputed", "sv_01"),
    ]

    result = run_approve(repo, monkeypatch)

    invalidated = [ln for ln in result.stdout.splitlines() if ln.endswith("invalidated")]
    assert invalidated == ["AUTH-002  invalidated", "AUTH-003  invalidated"]
    assert query(repo, "SELECT state FROM tasks WHERE id = 'AUTH-001'") == [("passed",)]


def test_task105_ac4_stale_draft_after_a_replan_says_run_replan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = seeded(tmp_path, later_spec=True)
    before = event_count(repo)

    result = run_approve(repo, monkeypatch)

    assert result.stderr == "plan_02 was made for sv_02; run openfactory replan\n"
    assert result.stdout == ""
    assert result.exit_code == 1
    assert event_count(repo) == before


@pytest.mark.parametrize("state", ["running", "gating"])
def test_task105_ac5_a_busy_downstream_task_is_refused_naming_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    repo = seeded(tmp_path, busy=state)
    before = event_count(repo)

    result = run_approve(repo, monkeypatch)

    assert result.stderr == f"AUTH-003 is {state}; run openfactory run first\n"
    assert result.stdout == ""
    assert result.exit_code == 1
    assert event_count(repo) == before
    assert query(repo, "SELECT status FROM plans WHERE id = 'plan_02'") == [("draft",)]
