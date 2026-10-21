"""TASK-076 AC1..AC6: the `resolve` command (docs/tasks/TASK-076-cli-resolve.md)."""

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
    PlanApprovedPayload,
    PlanCreatedPayload,
    TaskStateChangedPayload,
)
from openfactory.domain.states import TaskState

runner = CliRunner()

DB = Path(".openfactory/openfactory.db")
HASH = "a" * 64
CLI_SRC = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "cli.py"


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
        required_gates=["path_check", "ruff", "pytest", "gitleaks", "review"],
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


def seed(repo: Path, *, approved: bool, escalate: bool) -> None:
    """A plan holding AUTH-001 and AUTH-002; optionally approved with AUTH-001 escalated."""
    recorder = SqliteEventRecorder(repo / DB)

    def rec(stream: str, type_: EventType, payload: Any, actor: str = "orchestrator") -> None:
        recorder.record(
            Event.new(
                stream=stream,
                type=type_,
                payload=payload.model_dump(mode="json"),
                actor=actor,
            )
        )

    def move(task_id: str, a: TaskState, b: TaskState, reason: str | None = None) -> None:
        rec(
            f"task:{task_id}",
            EventType.TaskStateChanged,
            TaskStateChangedPayload(task_id=task_id, from_=a, to=b, reason=reason),
        )

    try:
        rec(
            "plan:plan_01",
            EventType.PlanCreated,
            PlanCreatedPayload(
                plan_id="plan_01",
                spec_version="sv_01",
                policy_hash=HASH,
                run_id="run_0001",
                tasks=[contract("AUTH-001"), contract("AUTH-002")],
            ),
        )
        if approved:
            rec(
                "plan:plan_01",
                EventType.PlanApproved,
                PlanApprovedPayload(plan_id="plan_01"),
                "human",
            )
            move("AUTH-001", TaskState.pending, TaskState.ready)
            if escalate:
                move("AUTH-001", TaskState.ready, TaskState.running)
                move("AUTH-001", TaskState.running, TaskState.escalated, "path violation")
    finally:
        recorder.close()


def query(repo: Path, sql: str) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(repo / DB)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def events(repo: Path) -> list[tuple[Any, ...]]:
    return query(
        repo,
        "SELECT seq, type, stream, actor, causation_id, event_id, payload FROM events ORDER BY seq",
    )


def escalated_repo(tmp_path: Path) -> Path:
    repo = init_repo(tmp_path)
    seed(repo, approved=True, escalate=True)
    return repo


@pytest.mark.parametrize(
    ("flag", "decision", "state", "attempt"),
    [("--retry", "retry", "ready", 0), ("--abandon", "abandon", "abandoned", 1)],
)
def test_ac1_ac2_resolve_records_two_events_and_prints_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flag: str,
    decision: str,
    state: str,
    attempt: int,
) -> None:
    repo = escalated_repo(tmp_path)
    before = len(events(repo))

    result = run_cli(repo, monkeypatch, "resolve", "AUTH-001", flag)

    assert result.exit_code == 0, result.output
    assert result.stdout == f"AUTH-001  {state}\n"
    assert result.stderr == ""
    new = events(repo)[before:]
    assert len(new) == 2
    (_, t1, s1, a1, c1, id1, p1), (_, t2, s2, a2, c2, _, p2) = new
    assert (t1, s1, a1, c1) == ("TaskResolved", "task:AUTH-001", "human", None)
    assert ast.literal_eval(p1.replace("null", "None")) == {
        "task_id": "AUTH-001",
        "decision": decision,
    }
    assert (t2, s2, a2, c2) == ("TaskStateChanged", "task:AUTH-001", "orchestrator", id1)
    assert ast.literal_eval(p2.replace("null", "None")) == {
        "task_id": "AUTH-001",
        "from": "escalated",
        "to": state,
        "reason": None,
    }
    row = query(repo, "SELECT state, attempt FROM tasks WHERE id = 'AUTH-001'")
    assert row == [(state, attempt)]
    assert not any(e[1] == "AgentRunStarted" for e in events(repo))


@pytest.mark.parametrize(
    ("setup", "args", "line"),
    [
        ("draft", ("AUTH-001", "--retry"), "no approved plan"),
        ("approved", ("ZZZ-999", "--retry"), "unknown task ZZZ-999"),
        ("approved", ("AUTH-002", "--abandon"), "AUTH-002 is pending, not escalated"),
    ],
)
def test_ac3_refusals_are_one_line_on_stderr_and_record_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setup: str, args: tuple[str, ...], line: str
) -> None:
    repo = init_repo(tmp_path)
    seed(repo, approved=setup == "approved", escalate=False)
    before = events(repo)

    result = run_cli(repo, monkeypatch, "resolve", *args)

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.splitlines() == [line]
    assert events(repo) == before


@pytest.mark.parametrize("flags", [(), ("--retry", "--abandon")])
def test_ac4_neither_or_both_flags_is_a_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flags: tuple[str, ...]
) -> None:
    repo = escalated_repo(tmp_path)
    before = events(repo)

    result = run_cli(repo, monkeypatch, "resolve", "AUTH-001", *flags)

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.strip() != ""
    assert "No such command" not in result.stderr
    assert events(repo) == before
    assert query(repo, "SELECT state FROM tasks WHERE id = 'AUTH-001'") == [("escalated",)]


def test_ac5_fails_without_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "plain"
    repo.mkdir()

    result = run_cli(repo, monkeypatch, "resolve", "AUTH-001", "--retry")

    assert result.exit_code == 1
    assert "run `openfactory init` first" in result.stderr
    assert result.stdout == ""
    assert not (repo / ".openfactory").exists()


def test_ac6_cli_wires_resolve_with_plans_and_recorder_only() -> None:
    tree = ast.parse(CLI_SRC.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "resolve")
    calls = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "resolve_task"
    ]
    assert len(calls) == 1
    assert {k.arg for k in calls[0].keywords} == {"plans", "recorder"}
    used = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    assert not used & {"git", "worktrees", "executor", "gates", "llm", "runner"}
