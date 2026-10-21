"""TASK-077 AC1..AC6: the `status` command (docs/tasks/TASK-077-status.md)."""

import ast
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import (
    AgentRunStartedPayload,
    GateEvaluatedPayload,
    PlanApprovedPayload,
    PlanCreatedPayload,
    TaskStateChangedPayload,
)
from openfactory.domain.states import TaskState

runner = CliRunner()

DB = Path(".openfactory/openfactory.db")
HASH = "a" * 64
CLI_SRC = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "cli.py"
GATES = ["path_check", "ruff", "pytest", "gitleaks", "review"]
S = TaskState


def contract(task_id: str) -> TaskContract:
    return TaskContract(
        task_id=task_id,
        objective=f"Do {task_id}",
        requirements=["REQ-AUTH-001"],
        acceptance_criteria=["AC-AUTH-001-1"],
        depends_on=[],
        components=["auth"],
        role="implementer",
        allowed_paths=["app/auth/**"],
        forbidden_paths=["specs/**"],
        required_gates=GATES,
        limits=Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.5),
    )


def run_cli(repo: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> Result:
    from openfactory.cli import app

    monkeypatch.chdir(repo)
    return runner.invoke(app, list(args))


def init_repo(tmp_path: Path) -> Path:
    from openfactory.cli import app

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    assert runner.invoke(app, ["init", str(repo)]).exit_code == 0
    return repo


class Seeder:
    def __init__(self, repo: Path) -> None:
        self.recorder = SqliteEventRecorder(repo / DB)

    def rec(self, stream: str, type_: EventType, payload: Any, actor: str = "orchestrator") -> None:
        self.recorder.record(
            Event.new(
                stream=stream, type=type_, payload=payload.model_dump(mode="json"), actor=actor
            )
        )

    def plan(self, task_ids: list[str], *, approved: bool = True) -> None:
        self.rec(
            "plan:plan_01",
            EventType.PlanCreated,
            PlanCreatedPayload(
                plan_id="plan_01",
                spec_version="sv_01",
                policy_hash=HASH,
                run_id="run_0001",
                tasks=[contract(t) for t in task_ids],
            ),
        )
        if approved:
            self.rec(
                "plan:plan_01",
                EventType.PlanApproved,
                PlanApprovedPayload(plan_id="plan_01"),
                "human",
            )

    def move(self, task_id: str, *states: TaskState) -> None:
        for a, b in zip(states, states[1:], strict=False):
            self.rec(
                f"task:{task_id}",
                EventType.TaskStateChanged,
                TaskStateChangedPayload(task_id=task_id, from_=a, to=b, reason=None),
            )

    def implementer_run(self, run_id: str, task_id: str, gates: dict[str, bool]) -> None:
        self.rec(
            f"run:{run_id}",
            EventType.AgentRunStarted,
            AgentRunStartedPayload(
                run_id=run_id,
                task_id=task_id,
                role="implementer",
                runtime="claude-code",
                context_hash=HASH,
            ),
        )
        for gate, passed in gates.items():
            self.rec(
                f"task:{task_id}",
                EventType.GateEvaluated,
                GateEvaluatedPayload(
                    run_id=run_id, task_id=task_id, gate=gate, passed=passed, output_path=None
                ),
            )

    def close(self) -> None:
        self.recorder.close()


def event_count(repo: Path) -> int:
    conn = sqlite3.connect(repo / DB)
    try:
        return conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    finally:
        conn.close()


def mixed_repo(tmp_path: Path) -> Path:
    repo = init_repo(tmp_path)
    s = Seeder(repo)
    try:
        s.plan(["AUTH-010", "AUTH-001", "AUTH-002"])
        # AUTH-001: one attempt, all five gates passing, passed.
        s.move("AUTH-001", S.pending, S.ready, S.running)
        s.implementer_run("run_0002", "AUTH-001", dict.fromkeys(GATES, True))
        s.move("AUTH-001", S.running, S.gating, S.passed)
        # AUTH-002: one attempt, path_check passed and ruff failed, failed.
        s.move("AUTH-002", S.pending, S.ready, S.running)
        s.implementer_run("run_0003", "AUTH-002", {"path_check": True, "ruff": False})
        s.move("AUTH-002", S.running, S.failed)
        # AUTH-010 stays pending with no run.
    finally:
        s.close()
    return repo


def test_ac1_ac2_ac3_one_line_per_task_in_string_order_with_gate_and_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = mixed_repo(tmp_path)

    result = run_cli(repo, monkeypatch, "status")

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    assert result.stdout.splitlines() == [
        "AUTH-001  passed  1/2  review passed",
        "AUTH-002  failed  1/2  ruff failed",
        "AUTH-010  pending  0/2  -",
    ]


def test_ac3_retried_task_shows_attempt_reset_to_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = init_repo(tmp_path)
    s = Seeder(repo)
    try:
        s.plan(["AUTH-001"])
        s.move("AUTH-001", S.pending, S.ready, S.running, S.failed, S.ready, S.running, S.failed)
        s.move("AUTH-001", S.failed, S.escalated)
    finally:
        s.close()
    before = run_cli(repo, monkeypatch, "status")
    assert before.stdout.splitlines()[0].startswith("AUTH-001  escalated  2/2")

    assert run_cli(repo, monkeypatch, "resolve", "AUTH-001", "--retry").exit_code == 0
    after = run_cli(repo, monkeypatch, "status")

    assert after.exit_code == 0
    assert after.stdout == "AUTH-001  ready  0/2  -\n"


def test_ac4_killed_run_is_shown_as_running_and_no_event_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = init_repo(tmp_path)
    s = Seeder(repo)
    try:
        s.plan(["AUTH-001"])
        s.move("AUTH-001", S.pending, S.ready, S.running)
        s.implementer_run("run_0002", "AUTH-001", {})
    finally:
        s.close()
    before = event_count(repo)

    result = run_cli(repo, monkeypatch, "status")

    assert result.exit_code == 0, result.output
    assert result.stdout == "AUTH-001  running  1/2  -\n"
    assert event_count(repo) == before


def test_ac4_cli_wires_status_with_plans_only() -> None:
    tree = ast.parse(CLI_SRC.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "status")
    calls = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "plan_status"
    ]
    assert len(calls) == 1
    assert {k.arg for k in calls[0].keywords} == {"plans"}
    used = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    assert not used & {"git", "worktrees", "executor", "gates", "llm", "runner", "recorder"}


def test_ac5_draft_only_plan_is_refused_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = init_repo(tmp_path)
    s = Seeder(repo)
    try:
        s.plan(["AUTH-001"], approved=False)
    finally:
        s.close()
    before = event_count(repo)

    result = run_cli(repo, monkeypatch, "status")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.splitlines() == ["no approved plan"]
    assert event_count(repo) == before


def test_ac6_fails_without_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "plain"
    repo.mkdir()

    result = run_cli(repo, monkeypatch, "status")

    assert result.exit_code == 1
    assert "run `openfactory init` first" in result.stderr
    assert result.stdout == ""
    assert not (repo / ".openfactory").exists()
