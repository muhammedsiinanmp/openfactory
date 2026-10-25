"""TASK-109 AC1..AC6: the `stats` command (docs/tasks/TASK-109-stats.md)."""

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType, StoredEvent
from openfactory.domain.payloads import (
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    PlanApprovedPayload,
    PlanCreatedPayload,
    TaskResolvedPayload,
    TaskStateChangedPayload,
)
from openfactory.domain.states import TaskState

runner = CliRunner()

DB = Path(".openfactory/openfactory.db")
HASH = "a" * 64
GATES = ["path_check", "ruff", "pytest", "gitleaks", "review"]
S = TaskState
LATENCY_NONE = "latency  p50  -  p95  -"


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

    def rec(
        self,
        stream: str,
        type_: EventType,
        payload: Any,
        actor: str = "orchestrator",
        cause: StoredEvent | None = None,
    ) -> StoredEvent:
        return self.recorder.record(
            Event.new(
                stream=stream,
                type=type_,
                payload=payload.model_dump(mode="json"),
                actor=actor,
                causation_id=cause.event_id if cause else None,
            )
        )

    def run(
        self,
        run_id: str,
        role: str,
        task_id: str | None = None,
        *,
        exit: str | None = "ok",
        tin: int | None = 10,
        tout: int | None = 5,
        cost: float | None = 0.5,
        dur: float = 2.0,
        cause: StoredEvent | None = None,
    ) -> StoredEvent:
        last = self.rec(
            f"run:{run_id}",
            EventType.AgentRunStarted,
            AgentRunStartedPayload(
                run_id=run_id,
                task_id=task_id,
                role=role,
                runtime="claude-code",
                context_hash=HASH,
            ),
            cause=cause,
        )
        if exit is not None:
            last = self.rec(
                f"run:{run_id}",
                EventType.AgentRunFinished,
                AgentRunFinishedPayload(
                    run_id=run_id,
                    exit=exit,
                    model=None,
                    tokens_in=tin,
                    tokens_out=tout,
                    cost_usd=cost,
                    duration_s=dur,
                    error=None,
                ),
                cause=last,
            )
        return last

    def plan(self, plan_id: str, task_ids: list[str], planner_run: str, **figures: Any) -> None:
        last = self.run(planner_run, "planner", **figures)
        self.rec(
            f"plan:{plan_id}",
            EventType.PlanCreated,
            PlanCreatedPayload(
                plan_id=plan_id,
                spec_version="sv_01",
                policy_hash=HASH,
                run_id=planner_run,
                tasks=[contract(t) for t in task_ids],
            ),
            cause=last,
        )

    def approve(self, plan_id: str) -> None:
        self.rec(
            f"plan:{plan_id}", EventType.PlanApproved, PlanApprovedPayload(plan_id=plan_id), "human"
        )

    def move(self, task_id: str, *states: TaskState) -> None:
        for a, b in zip(states, states[1:], strict=False):
            self.rec(
                f"task:{task_id}",
                EventType.TaskStateChanged,
                TaskStateChangedPayload(task_id=task_id, from_=a, to=b, reason=None),
            )

    def close(self) -> None:
        self.recorder.close()


def event_count(repo: Path) -> int:
    conn = sqlite3.connect(repo / DB)
    try:
        return conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    finally:
        conn.close()


def full_repo(tmp_path: Path) -> Path:
    repo = init_repo(tmp_path)
    s = Seeder(repo)
    try:
        s.plan(
            "plan_01", ["AUTH-010", "AUTH-002"], "run_0001", tin=100, tout=50, cost=0.12346, dur=3.0
        )
        s.approve("plan_01")
        s.run("run_0002", "implementer", "AUTH-010", tin=7, tout=3, cost=0.25, dur=4.0)
        s.run("run_0003", "reviewer", "AUTH-010", tin=None, tout=None, cost=None, dur=1.0)
        s.run("run_0004", "implementer", "AUTH-002", exit="error", dur=9.0)
        s.run("run_0005", "implementer", "AUTH-002", exit=None)  # unfinished
        # a retry resolution: earlier runs still count
        s.rec(
            "task:AUTH-002",
            EventType.TaskResolved,
            TaskResolvedPayload(task_id="AUTH-002", decision="retry"),
            "human",
        )
        s.run(
            "run_0006", "implementer", "AUTH-002", exit="timeout", tin=1, tout=1, cost=0.0, dur=7.0
        )
    finally:
        s.close()
    return repo


def test_ac1_ac2_ac3_ac4_full_output_in_group_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = full_repo(tmp_path)

    result = run_cli(repo, monkeypatch, "stats")

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    assert result.stdout.splitlines() == [
        "task  AUTH-002  3  11  6  0.5000  16.0",
        "task  AUTH-010  2  7  3  0.2500  5.0",
        "plan  plan_01  6  118  59  0.8735  24.0",
        "role  implementer  4  18  9  0.7500  20.0",
        "role  planner  1  100  50  0.1235  3.0",
        "role  reviewer  1  0  0  0.0000  1.0",
        "latency  p50  3.0  p95  4.0",
    ]


def test_ac2_replan_line_has_its_own_runs_and_classifier_runs_not_the_builds_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = init_repo(tmp_path)
    s = Seeder(repo)
    try:
        s.plan("plan_01", ["AUTH-001"], "run_0001", tin=1, tout=1, cost=0.1, dur=1.0)
        s.approve("plan_01")
        s.run("run_0002", "implementer", "AUTH-001", tin=50, tout=1, cost=0.5, dur=1.0)
        classifier = s.run("run_0003", "classifier", None, tin=20, tout=1, cost=0.2, dur=1.0)
        from openfactory.domain.payloads import ImpactComputedPayload

        impact = s.rec(
            "spec:sv_02",
            EventType.ImpactComputed,
            ImpactComputedPayload(
                from_version="sv_01",
                to_version="sv_02",
                run_id=None,
                requirements=[],
                adrs=[],
                tasks=[],
                downstream=[],
                files=[],
                tests=[],
            ),
            cause=classifier,
        )
        planner = s.run("run_0004", "planner", None, tin=3, tout=1, cost=0.3, dur=1.0, cause=impact)
        s.rec(
            "plan:plan_02",
            EventType.PlanCreated,
            PlanCreatedPayload(
                plan_id="plan_02",
                spec_version="sv_02",
                policy_hash=HASH,
                run_id="run_0004",
                tasks=[contract("AUTH-002")],
            ),
            cause=planner,
        )
    finally:
        s.close()

    lines = run_cli(repo, monkeypatch, "stats").stdout.splitlines()

    assert "plan  plan_01  2  51  2  0.6000  2.0" in lines
    assert "plan  plan_02  2  23  2  0.5000  2.0" in lines
    assert lines.index("plan  plan_01  2  51  2  0.6000  2.0") < lines.index(
        "plan  plan_02  2  23  2  0.5000  2.0"
    )


def test_ac4_single_ok_run_gives_one_decimal_for_both_percentiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = init_repo(tmp_path)
    s = Seeder(repo)
    try:
        s.run("run_0001", "implementer", "AUTH-001", dur=2.34)
    finally:
        s.close()

    result = run_cli(repo, monkeypatch, "stats")

    assert result.stdout.splitlines()[-1] == "latency  p50  2.3  p95  2.3"


def test_ac4_finished_runs_none_ok_give_dashes_after_the_other_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = init_repo(tmp_path)
    s = Seeder(repo)
    try:
        s.run("run_0001", "implementer", "AUTH-001", exit="error", dur=2.0)
    finally:
        s.close()

    lines = run_cli(repo, monkeypatch, "stats").stdout.splitlines()

    assert lines[0].startswith("task  AUTH-001  1  ")
    assert lines[-1] == LATENCY_NONE


def test_ac5_no_run_prints_only_the_empty_latency_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = init_repo(tmp_path)

    result = run_cli(repo, monkeypatch, "stats")

    assert result.exit_code == 0, result.output
    assert result.stdout == LATENCY_NONE + "\n"
    assert result.stderr == ""


def test_ac5_killed_run_is_not_repaired_and_no_event_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = init_repo(tmp_path)
    s = Seeder(repo)
    try:
        s.plan("plan_01", ["AUTH-001"], "run_0001")
        s.approve("plan_01")
        s.move("AUTH-001", S.pending, S.ready, S.running)
        s.run("run_0002", "implementer", "AUTH-001", exit=None)
    finally:
        s.close()
    before = event_count(repo)

    result = run_cli(repo, monkeypatch, "stats")

    assert result.exit_code == 0, result.output
    assert "task  AUTH-001  1  0  0  0.0000  0.0" in result.stdout.splitlines()
    assert event_count(repo) == before
    status = run_cli(repo, monkeypatch, "status")
    assert status.stdout.startswith("AUTH-001  running")


def test_ac6_fails_without_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "plain"
    repo.mkdir()

    result = run_cli(repo, monkeypatch, "stats")

    assert result.exit_code == 1
    assert "run `openfactory init` first" in result.stderr
    assert result.stdout == ""
    assert not (repo / ".openfactory").exists()
