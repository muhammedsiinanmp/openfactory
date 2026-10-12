"""TASK-036 AC1..AC5: the `approve plan` command (docs/tasks/TASK-036-cli-approve-plan.md)."""

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import PlanCreatedPayload

runner = CliRunner()

DB = Path(".openfactory/openfactory.db")
REQS = Path("specs/requirements.yaml")
HASH = "a" * 64

VALID_REQUIREMENTS = """\
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
      - id: AC-AUTH-001-2
        text: Invalid login is refused.
"""


def contract(task_id: str, depends_on: tuple[str, ...] = ()) -> TaskContract:
    return TaskContract(
        task_id=task_id,
        objective=f"Do {task_id}",
        requirements=["REQ-AUTH-001"],
        acceptance_criteria=["AC-AUTH-001-1"],
        depends_on=list(depends_on),
        components=["auth"],
        role="implementer",
        allowed_paths=["app/auth/**"],
        forbidden_paths=["specs/**"],
        required_gates=["path_check", "ruff", "pytest", "gitleaks", "review"],
        limits=Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.5),
    )


CONTRACTS = [
    contract("DB-001"),
    contract("AUTH-002", ("AUTH-001",)),
    contract("AUTH-001"),
    contract("AUTH-010"),
]


def run_cli(repo: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> Result:
    from openfactory.cli import app

    monkeypatch.chdir(repo)
    return runner.invoke(app, list(args))


def make_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Initialised repo with `sv_01` approved."""
    from openfactory.cli import app

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    assert runner.invoke(app, ["init", str(repo)]).exit_code == 0
    (repo / REQS).write_text(VALID_REQUIREMENTS, encoding="utf-8")
    result = run_cli(repo, monkeypatch, "approve", "spec")
    assert result.exit_code == 0, result.output
    return repo


def record_draft(repo: Path, plan_id: str = "plan_01", spec_version: str = "sv_01") -> None:
    payload = PlanCreatedPayload(
        plan_id=plan_id,
        spec_version=spec_version,
        policy_hash=HASH,
        run_id="run_0001",
        tasks=CONTRACTS,
    )
    recorder = SqliteEventRecorder(repo / DB)
    try:
        recorder.record(
            Event.new(
                stream=f"plan:{plan_id}",
                type=EventType.PlanCreated,
                payload=payload.model_dump(mode="json"),
                actor="orchestrator",
            )
        )
    finally:
        recorder.close()


def query(repo: Path, sql: str) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(repo / DB)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def events(repo: Path) -> list[tuple[str, str, str, str | None, str]]:
    rows = query(
        repo, "SELECT type, stream, actor, causation_id, event_id FROM events ORDER BY seq"
    )
    return [tuple(r) for r in rows]  # type: ignore[misc]


def task_states(repo: Path) -> dict[str, str]:
    return dict(query(repo, "SELECT id, state FROM tasks"))


def test_ac1_prints_ready_lines_then_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path, monkeypatch)
    record_draft(repo)

    result = run_cli(repo, monkeypatch, "approve", "plan")

    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "AUTH-001  ready",
        "AUTH-010  ready",
        "DB-001  ready",
        "approved plan_01",
    ]
    assert result.stderr == ""


def test_ac2_records_events_and_projections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path, monkeypatch)
    record_draft(repo)
    before = len(events(repo))

    assert run_cli(repo, monkeypatch, "approve", "plan").exit_code == 0

    new = events(repo)[before:]
    assert [(t, s, a) for t, s, a, _, _ in new] == [
        ("PlanApproved", "plan:plan_01", "human"),
        ("TaskStateChanged", "task:AUTH-001", "orchestrator"),
        ("TaskStateChanged", "task:AUTH-010", "orchestrator"),
        ("TaskStateChanged", "task:DB-001", "orchestrator"),
    ]
    assert len(new) == 4
    approved_id = new[0][4]
    assert new[0][3] is None
    assert [c for _, _, _, c, _ in new[1:]] == [approved_id] * 3
    assert query(repo, "SELECT status FROM plans WHERE id = 'plan_01'") == [("approved",)]
    assert task_states(repo) == {
        "AUTH-001": "ready",
        "AUTH-002": "pending",
        "AUTH-010": "ready",
        "DB-001": "ready",
    }


def test_ac3_no_plan_at_all(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path, monkeypatch)
    before = events(repo)

    result = run_cli(repo, monkeypatch, "approve", "plan")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.strip() == "no draft plan"
    assert events(repo) == before


def test_ac3_second_run_after_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path, monkeypatch)
    record_draft(repo)
    assert run_cli(repo, monkeypatch, "approve", "plan").exit_code == 0
    before = events(repo)

    result = run_cli(repo, monkeypatch, "approve", "plan")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.strip() == "no draft plan"
    assert events(repo) == before


def test_ac4_stale_draft_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path, monkeypatch)
    record_draft(repo)
    (repo / REQS).write_text(
        VALID_REQUIREMENTS.replace("Users can log in.", "Users can sign in."), encoding="utf-8"
    )
    result = run_cli(repo, monkeypatch, "approve", "spec")
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[-1] == "approved sv_02"
    before = events(repo)

    result = run_cli(repo, monkeypatch, "approve", "plan")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.strip() == "plan_01 was made for sv_01; run openfactory plan"
    assert events(repo) == before
    assert query(repo, "SELECT status FROM plans WHERE id = 'plan_01'") == [("draft",)]
    assert set(task_states(repo).values()) == {"pending"}
    assert len(task_states(repo)) == 4


def test_ac5_fails_without_init_and_creates_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "plain"
    repo.mkdir()

    result = run_cli(repo, monkeypatch, "approve", "plan")

    assert result.exit_code == 1
    assert "run `openfactory init` first" in result.stderr
    assert result.stdout == ""
    assert not (repo / ".openfactory").exists()
