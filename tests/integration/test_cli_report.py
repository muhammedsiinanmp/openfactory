"""TASK-111 AC1..AC6: the `report` command (docs/tasks/TASK-111-report-command.md)."""

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType, StoredEvent
from openfactory.domain.models import Priority, Requirement, SpecSet
from openfactory.domain.payloads import (
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    CommitRecordedPayload,
    ImpactComputedPayload,
    PlanApprovedPayload,
    PlanCreatedPayload,
    SpecApprovedPayload,
    SpecImportedPayload,
    TaskStateChangedPayload,
)
from openfactory.domain.states import TaskState

runner = CliRunner()

DB = Path(".openfactory/openfactory.db")
HASH = "a" * 64
GATES = ["path_check", "ruff", "pytest", "gitleaks", "review"]
S = TaskState
HEADER = "| Plan | Kind | Runs | Tokens in | Tokens out | Cost USD |"
SEPARATOR = "| --- | --- | --- | --- | --- | --- |"


def req(id: str, deprecated: bool = False) -> Requirement:
    return Requirement(
        id=id,
        title=f"Title {id}",
        statement="Users can do it.",
        priority=Priority.must,
        components=["auth"],
        deprecated=deprecated,
    )


def contract(task_id: str, requirements: list[str]) -> TaskContract:
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

    def version(self, vid: str, reqs: list[Requirement], *, approved: bool = True) -> None:
        spec = SpecSet(components=["auth"], requirements=reqs, adrs=[])
        self.rec(
            f"spec:{vid}",
            EventType.SpecImported,
            SpecImportedPayload(spec_version=vid, hash=HASH, spec=spec),
        )
        if approved:
            self.rec(
                f"spec:{vid}",
                EventType.SpecApproved,
                SpecApprovedPayload(spec_version=vid, hash=HASH),
                "human",
            )

    def run(
        self,
        run_id: str,
        role: str,
        task_id: str | None = None,
        *,
        exit: str | None = "ok",
        tin: int = 10,
        tout: int = 5,
        cost: float = 0.5,
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
                    duration_s=1.0,
                    error=None,
                ),
                cause=last,
            )
        return last

    def plan(
        self,
        plan_id: str,
        vid: str,
        tasks: list[TaskContract],
        planner_run: str | None,
        *,
        cause: StoredEvent | None = None,
        **figures: Any,
    ) -> None:
        """A `PlanCreated` caused by its planner run (or by `cause`, the run's parent)."""
        last = None
        if planner_run is not None:
            last = self.run(planner_run, "planner", cause=cause, **figures)
        self.rec(
            f"plan:{plan_id}",
            EventType.PlanCreated,
            PlanCreatedPayload(
                plan_id=plan_id,
                spec_version=vid,
                policy_hash=HASH,
                run_id=planner_run or "run_0001",
                tasks=tasks,
            ),
            cause=last,
        )

    def approve(self, plan_id: str) -> None:
        self.rec(
            f"plan:{plan_id}", EventType.PlanApproved, PlanApprovedPayload(plan_id=plan_id), "human"
        )

    def move(self, task_id: str, *path: TaskState) -> None:
        for a, b in zip((S.pending, *path), path, strict=False):
            self.rec(
                f"task:{task_id}",
                EventType.TaskStateChanged,
                TaskStateChangedPayload(task_id=task_id, from_=a, to=b, reason=None),
            )

    def commit(self, sha_char: str, task_id: str, run_id: str) -> None:
        self.rec(
            f"task:{task_id}",
            EventType.CommitRecorded,
            CommitRecordedPayload(
                sha=sha_char * 40,
                task_id=task_id,
                run_id=run_id,
                branch=f"task/{task_id}",
                spec_version="sv_01",
                files=[],
            ),
        )

    def close(self) -> None:
        self.recorder.close()


def seeded(tmp_path: Path, build: Any) -> Path:
    repo = init_repo(tmp_path)
    s = Seeder(repo)
    try:
        build(s)
    finally:
        s.close()
    return repo


def event_count(repo: Path) -> int:
    conn = sqlite3.connect(repo / DB)
    try:
        return conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    finally:
        conn.close()


def pinned_world(s: Seeder) -> None:
    s.version("sv_01", [req("REQ-AUTH-010", deprecated=True), req("REQ-AUTH-002")])
    s.plan(
        "plan_01",
        "sv_01",
        [contract("AUTH-001", ["REQ-AUTH-002"])],
        "run_0001",
        tin=100,
        tout=50,
        cost=0.12346,
    )
    s.approve("plan_01")
    s.move("AUTH-001", S.ready, S.running, S.passed)
    s.run("run_0002", "implementer", "AUTH-001", tin=7, tout=3, cost=0.25)
    s.commit("a", "AUTH-001", "run_0002")


FENCE = "```"
PINNED_STDOUT = f"""\
# OpenFactory report

plan plan_01 · spec sv_01

## Requirements

### REQ-AUTH-002  Title REQ-AUTH-002

{FENCE}
task  AUTH-001  passed
commit  {"a" * 40}  AUTH-001
{FENCE}

### REQ-AUTH-010  Title REQ-AUTH-010 (deprecated)

{FENCE}
{FENCE}

## Cost

{HEADER}
{SEPARATOR}
| plan_01 | build | 2 | 107 | 53 | 0.3735 |
| total |  | 2 | 107 | 53 | 0.3735 |
"""


def replan_world(s: Seeder) -> None:
    s.version("sv_01", [req("REQ-AUTH-001")])
    s.plan(
        "plan_01",
        "sv_01",
        [contract("AUTH-001", ["REQ-AUTH-001"]), contract("AUTH-002", ["REQ-AUTH-001"])],
        "run_0001",
        tin=100,
        tout=50,
        cost=0.1,
    )
    s.approve("plan_01")
    s.move("AUTH-001", S.ready, S.running, S.passed)
    s.move("AUTH-002", S.ready, S.running, S.passed)
    s.run("run_0002", "implementer", "AUTH-001", tin=10, tout=5, cost=0.2)
    s.run("run_0003", "implementer", "AUTH-002", tin=20, tout=5, cost=0.3)
    s.commit("a", "AUTH-001", "run_0002")
    s.commit("b", "AUTH-002", "run_0003")
    # The replan, as the real use cases record it: classifier run, then ImpactComputed caused
    # by it, then the planner run caused by that, then PlanCreated caused by the planner run.
    s.version("sv_02", [req("REQ-AUTH-001")])
    classifier = s.run("run_0004", "classifier", None, tin=7, tout=1, cost=0.05)
    impact = s.rec(
        "spec:sv_02",
        EventType.ImpactComputed,
        ImpactComputedPayload(
            from_version="sv_01",
            to_version="sv_02",
            run_id="run_0004",
            requirements=[],
            adrs=[],
            tasks=["AUTH-002"],
            downstream=[],
            files=[],
            tests=[],
        ),
        cause=classifier,
    )
    s.plan(
        "plan_02",
        "sv_02",
        [contract("AUTH-004", ["REQ-AUTH-001"])],
        "run_0005",
        cause=impact,
        tin=30,
        tout=3,
        cost=0.15,
    )
    s.approve("plan_02")
    s.rec(
        "task:AUTH-002",
        EventType.TaskStateChanged,
        TaskStateChangedPayload(
            task_id="AUTH-002", from_=S.passed, to=S.invalidated, reason="spec changed"
        ),
    )
    s.run("run_0006", "implementer", "AUTH-004", tin=4, tout=2, cost=0.5)
    s.commit("c", "AUTH-004", "run_0006")
    s.move("AUTH-004", S.ready, S.running, S.passed)


def test_ac1_draft_plan_only_is_refused_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def build(s: Seeder) -> None:
        s.version("sv_01", [req("REQ-AUTH-001")])
        s.plan("plan_01", "sv_01", [contract("AUTH-001", ["REQ-AUTH-001"])], "run_0001")

    repo = seeded(tmp_path, build)

    result = run_cli(repo, monkeypatch, "report")

    assert result.exit_code == 1
    assert result.stderr == "no approved plan\n"
    assert result.stdout == ""


def test_ac1_fails_without_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "plain"
    repo.mkdir()

    result = run_cli(repo, monkeypatch, "report")

    assert result.exit_code == 1
    assert "run `openfactory init` first" in result.stderr
    assert result.stdout == ""
    assert not (repo / ".openfactory").exists()


def test_ac2_ac3_ac4_full_stdout_is_pinned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = seeded(tmp_path, pinned_world)

    result = run_cli(repo, monkeypatch, "report")

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    assert result.stdout == PINNED_STDOUT


def test_ac2_plan_line_names_the_latest_approved_spec_before_any_replan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def build(s: Seeder) -> None:
        pinned_world(s)
        s.version("sv_02", [req("REQ-AUTH-002")])

    repo = seeded(tmp_path, build)

    result = run_cli(repo, monkeypatch, "report")

    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[:3] == [
        "# OpenFactory report",
        "",
        "plan plan_01 · spec sv_02",
    ]


def test_ac3_headings_follow_the_latest_version_in_string_order_and_match_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def build(s: Seeder) -> None:
        s.version("sv_01", [req("REQ-OLD-1"), req("REQ-AUTH-010")])
        s.version(
            "sv_02",
            [req("REQ-AUTH-010"), req("REQ-AUTH-002", deprecated=True), req("REQ-AUTH-001")],
        )
        s.plan(
            "plan_01",
            "sv_01",
            [contract("AUTH-001", ["REQ-AUTH-010"]), contract("AUTH-002", ["REQ-OLD-1"])],
            "run_0001",
        )
        s.approve("plan_01")
        s.move("AUTH-001", S.ready, S.running)
        s.commit("d", "AUTH-001", "run_0002")

    repo = seeded(tmp_path, build)

    result = run_cli(repo, monkeypatch, "report")

    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    headings = [line for line in lines if line.startswith("### ")]
    assert headings == [
        "### REQ-AUTH-001  Title REQ-AUTH-001",
        "### REQ-AUTH-002  Title REQ-AUTH-002 (deprecated)",
        "### REQ-AUTH-010  Title REQ-AUTH-010",
    ]
    assert "REQ-OLD-1" not in result.stdout
    for rid in ("REQ-AUTH-001", "REQ-AUTH-002", "REQ-AUTH-010"):
        trace = run_cli(repo, monkeypatch, "trace", rid).stdout.splitlines()
        at = next(i for i, line in enumerate(lines) if line.startswith(f"### {rid}  "))
        assert lines[at + 1] == ""
        assert lines[at + 2] == FENCE
        assert lines[at + 3 : at + 3 + len(trace)] == trace
        assert lines[at + 3 + len(trace)] == FENCE


def test_ac4_no_run_gives_zero_rows_and_a_draft_plan_has_no_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def build(s: Seeder) -> None:
        s.version("sv_01", [req("REQ-AUTH-001")])
        s.plan("plan_01", "sv_01", [contract("AUTH-001", ["REQ-AUTH-001"])], None)
        s.approve("plan_01")
        s.plan("plan_02", "sv_01", [contract("AUTH-002", ["REQ-AUTH-001"])], None)

    repo = seeded(tmp_path, build)

    result = run_cli(repo, monkeypatch, "report")

    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[-4:] == [
        HEADER,
        SEPARATOR,
        "| plan_01 | build | 0 | 0 | 0 | 0.0000 |",
        "| total |  | 0 | 0 | 0 | 0.0000 |",
    ]


def test_ac5_trace_and_report_after_a_supersede_show_the_invalidated_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = seeded(tmp_path, replan_world)
    expected = [
        "task  AUTH-001  passed",
        "task  AUTH-002  invalidated",
        "task  AUTH-004  passed",
        f"commit  {'a' * 40}  AUTH-001",
        f"commit  {'b' * 40}  AUTH-002",
        f"commit  {'c' * 40}  AUTH-004",
    ]

    trace = run_cli(repo, monkeypatch, "trace", "REQ-AUTH-001")
    result = run_cli(repo, monkeypatch, "report")

    assert trace.stdout.splitlines() == expected
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[2] == "plan plan_02 · spec sv_02"
    at = lines.index("### REQ-AUTH-001  Title REQ-AUTH-001")
    assert lines[at + 2 : at + 4 + len(expected)] == [FENCE, *expected, FENCE]
    assert lines[-5:] == [
        HEADER,
        SEPARATOR,
        "| plan_01 | build | 3 | 130 | 60 | 0.6000 |",
        "| plan_02 | replan | 3 | 41 | 6 | 0.7000 |",
        "| total |  | 6 | 171 | 66 | 1.3000 |",
    ]


def test_ac6_killed_run_is_not_repaired_and_no_event_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def build(s: Seeder) -> None:
        s.version("sv_01", [req("REQ-AUTH-001")])
        s.plan("plan_01", "sv_01", [contract("AUTH-001", ["REQ-AUTH-001"])], "run_0001")
        s.approve("plan_01")
        s.move("AUTH-001", S.ready, S.running)
        s.run("run_0002", "implementer", "AUTH-001", exit=None)

    repo = seeded(tmp_path, build)
    before = event_count(repo)

    result = run_cli(repo, monkeypatch, "report")

    assert result.exit_code == 0, result.output
    assert event_count(repo) == before
    assert run_cli(repo, monkeypatch, "status").stdout.startswith("AUTH-001  running")
    conn = sqlite3.connect(repo / DB)
    try:
        row = conn.execute("SELECT ended_at, exit FROM agent_runs WHERE id = 'run_0002'").fetchone()
    finally:
        conn.close()
    assert row == (None, None)
