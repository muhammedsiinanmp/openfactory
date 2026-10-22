"""TASK-086 AC1..AC5: the `why` command (docs/tasks/TASK-086-why.md)."""

import ast
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType
from openfactory.domain.models import Priority, Requirement, SpecSet
from openfactory.domain.payloads import (
    AgentRunStartedPayload,
    CollectedTest,
    CommitRecordedPayload,
    PlanApprovedPayload,
    PlanCreatedPayload,
    SpecApprovedPayload,
    SpecImportedPayload,
    TaskStateChangedPayload,
    TestsCollectedPayload,
)
from openfactory.domain.states import TaskState

runner = CliRunner()

DB = Path(".openfactory/openfactory.db")
HASH = "a" * 64
CLI_SRC = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "cli.py"
GATES = ["path_check", "ruff", "pytest", "gitleaks", "review"]


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


def req(id: str, adrs: list[str] | None = None) -> Requirement:
    return Requirement(
        id=id,
        title=f"Title {id}",
        statement="Users can do it.",
        priority=Priority.must,
        components=["auth"],
        constrained_by=adrs or [],
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


class Seeder:
    def __init__(self, repo: Path) -> None:
        self.recorder = SqliteEventRecorder(repo / DB)

    def rec(self, stream: str, type_: EventType, payload, actor: str = "orchestrator") -> None:  # noqa: ANN001
        self.recorder.record(
            Event.new(
                stream=stream, type=type_, payload=payload.model_dump(mode="json"), actor=actor
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

    def plan(self, vid: str, tasks: list[TaskContract]) -> None:
        self.rec(
            "plan:plan_01",
            EventType.PlanCreated,
            PlanCreatedPayload(
                plan_id="plan_01",
                spec_version=vid,
                policy_hash=HASH,
                run_id="run_0001",
                tasks=tasks,
            ),
        )
        self.rec(
            "plan:plan_01", EventType.PlanApproved, PlanApprovedPayload(plan_id="plan_01"), "human"
        )

    def move(self, task_id: str, *path: TaskState) -> None:
        for a, b in zip((TaskState.pending, *path), path, strict=False):
            self.rec(
                f"task:{task_id}",
                EventType.TaskStateChanged,
                TaskStateChangedPayload(task_id=task_id, from_=a, to=b, reason=None),
            )

    def commit(self, sha_char: str, task_id: str, run_id: str, files: list[str]) -> None:
        self.rec(
            f"task:{task_id}",
            EventType.CommitRecorded,
            CommitRecordedPayload(
                sha=sha_char * 40,
                task_id=task_id,
                run_id=run_id,
                branch=f"task/{task_id}",
                spec_version="sv_01",
                files=files,
            ),
        )

    def tests(self, *tests: tuple[str, str, list[str]]) -> None:
        self.rec(
            "task:AUTH-010",
            EventType.TestsCollected,
            TestsCollectedPayload(
                run_id="run_0009",
                task_id="AUTH-010",
                tests=[CollectedTest(node_id=n, file=f, req=r) for n, f, r in tests],
            ),
        )

    def close(self) -> None:
        self.recorder.close()


def seeded(tmp_path: Path, build) -> Path:  # noqa: ANN001
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


def world(s: Seeder) -> None:
    s.version(
        "sv_01",
        [req("REQ-A-1", ["ADR-001"]), req("REQ-A-2", ["ADR-001"])],
    )
    s.version(
        "sv_02",
        [req("REQ-A-1", ["ADR-010", "ADR-002"]), req("REQ-A-2", ["ADR-002"])],
    )
    s.plan(
        "sv_02",
        [
            contract("AUTH-010", ["REQ-A-1", "REQ-A-2"]),
            contract("AUTH-002", ["REQ-A-1"]),
            contract("AUTH-003", ["REQ-A-2"]),
        ],
    )
    s.move("AUTH-010", TaskState.ready, TaskState.running, TaskState.passed)
    s.move("AUTH-002", TaskState.ready)
    s.commit("e", "AUTH-010", "run_0002", ["app/shared.py"])
    s.commit("b", "AUTH-010", "run_0003", ["app/shared.py", "app/a.py"])
    s.commit("f", "AUTH-002", "run_0004", ["app/shared.py"])
    s.commit("9", "AUTH-003", "run_0005", ["other/x.py"])
    s.tests(("t.py::only", "tests/only.py", ["REQ-A-1"]))


def test_ac1_ac2_prints_the_four_groups_in_order_with_latest_version_adrs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = seeded(tmp_path, world)

    result = run_cli(repo, monkeypatch, "why", "app/shared.py")

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    assert result.stdout.splitlines() == [
        f"commit  {'f' * 40}  AUTH-002",
        f"commit  {'b' * 40}  AUTH-010",
        f"commit  {'e' * 40}  AUTH-010",
        "task  AUTH-002  ready",
        "task  AUTH-010  passed",
        "requirement  REQ-A-1",
        "requirement  REQ-A-2",
        "adr  ADR-002",
        "adr  ADR-010",
    ]


@pytest.mark.parametrize("path", ["no/such.py", "./app/shared.py", "app/", "app", "tests/only.py"])
def test_ac3_a_path_no_commit_changed_is_refused_as_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    repo = seeded(tmp_path, world)

    result = run_cli(repo, monkeypatch, "why", path)

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == f"no commit changed {path}\n"


def test_ac3_the_exact_changed_path_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = seeded(tmp_path, world)

    assert run_cli(repo, monkeypatch, "why", "app/a.py").exit_code == 0


def test_ac4_records_no_event_and_leaves_the_running_task_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def build(s: Seeder) -> None:
        s.version("sv_01", [req("REQ-AUTH-001")])
        s.plan("sv_01", [contract("AUTH-001", ["REQ-AUTH-001"])])
        s.move("AUTH-001", TaskState.ready, TaskState.running)
        s.rec(
            "run:run_0002",
            EventType.AgentRunStarted,
            AgentRunStartedPayload(
                run_id="run_0002",
                task_id="AUTH-001",
                role="implementer",
                runtime="claude-code",
                context_hash=HASH,
            ),
        )
        s.commit("a", "AUTH-001", "run_0002", ["app/auth/login.py"])

    repo = seeded(tmp_path, build)
    before = event_count(repo)

    result = run_cli(repo, monkeypatch, "why", "app/auth/login.py")

    assert result.exit_code == 0, result.output
    assert "task  AUTH-001  running" in result.stdout.splitlines()
    assert event_count(repo) == before
    assert run_cli(repo, monkeypatch, "status").stdout.startswith("AUTH-001  running")


def test_ac4_cli_wires_why_with_traces_only() -> None:
    tree = ast.parse(CLI_SRC.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "why")
    calls = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "why_file"
    ]
    assert len(calls) == 1
    assert {k.arg for k in calls[0].keywords} == {"traces"}
    used = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    assert not used & {"git", "worktrees", "executor", "gates", "llm", "runner", "recorder"}


def test_ac5_fails_without_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "plain"
    repo.mkdir()

    result = run_cli(repo, monkeypatch, "why", "app/auth/login.py")

    assert result.exit_code == 1
    assert "run `openfactory init` first" in result.stderr
    assert result.stdout == ""
    assert not (repo / ".openfactory").exists()
