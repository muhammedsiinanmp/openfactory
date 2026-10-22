"""TASK-084 AC1..AC6: the `trace` command (docs/tasks/TASK-084-trace.md)."""

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


def full_world(s: Seeder) -> None:
    s.version("sv_01", [req("REQ-A-1"), req("REQ-A-2")])
    s.plan(
        "sv_01",
        [
            contract("AUTH-010", ["REQ-A-1"]),
            contract("AUTH-002", ["REQ-A-1"]),
            contract("AUTH-003", ["REQ-A-2"]),
        ],
    )
    s.move("AUTH-010", TaskState.ready, TaskState.running, TaskState.passed)
    s.move("AUTH-002", TaskState.ready)
    s.commit("b", "AUTH-010", "run_0002", ["app/z.py", "app/shared.py"])
    s.commit("e", "AUTH-010", "run_0003", ["app/shared.py", "app/a.py"])
    s.commit("f", "AUTH-002", "run_0004", ["app/m.py"])
    s.commit("9", "AUTH-003", "run_0005", ["other/x.py"])
    s.tests(
        ("t.py::test_2", "tests/other.py", ["REQ-A-1"]),
        ("t.py::test_10", "app/m.py", []),
        ("t.py::test_3", "app/shared.py", ["REQ-A-1"]),
        ("t.py::test_1", "tests/other.py", ["REQ-A-1"]),
        ("t.py::outside", "other/x.py", []),
        ("t.py::other_req", "other/x.py", ["REQ-A-2"]),
    )


def test_ac1_ac2_prints_the_four_groups_in_order_sorted_as_strings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = seeded(tmp_path, full_world)

    result = run_cli(repo, monkeypatch, "trace", "REQ-A-1")

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    assert result.stdout.splitlines() == [
        "task  AUTH-002  ready",
        "task  AUTH-010  passed",
        f"commit  {'f' * 40}  AUTH-002",
        f"commit  {'b' * 40}  AUTH-010",
        f"commit  {'e' * 40}  AUTH-010",
        "file  app/a.py",
        "file  app/m.py",
        "file  app/shared.py",
        "file  app/z.py",
        "test  t.py::test_1  tagged",
        "test  t.py::test_10  file",
        "test  t.py::test_2  tagged",
        "test  t.py::test_3  tagged",
    ]


def test_ac3_a_requirement_with_no_links_prints_nothing_and_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = seeded(tmp_path, lambda s: s.version("sv_01", [req("REQ-A-1")]))

    result = run_cli(repo, monkeypatch, "trace", "REQ-A-1")

    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert result.stderr == ""


@pytest.mark.parametrize("draft_only", [False, True])
def test_ac4_unknown_requirement_is_refused_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, draft_only: bool
) -> None:
    def build(s: Seeder) -> None:
        s.version("sv_01", [req("REQ-A-1")])
        s.version("sv_02", [req("REQ-DRAFT-1")], approved=False)

    repo = seeded(tmp_path, build)
    rid = "REQ-DRAFT-1" if draft_only else "REQ-NONE-9"

    result = run_cli(repo, monkeypatch, "trace", rid)

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == f"unknown requirement {rid}\n"


@pytest.mark.parametrize("rid", ["REQ-OLD-1", "REQ-DEP-1"])
def test_ac4_old_approved_or_deprecated_requirement_is_not_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rid: str
) -> None:
    def build(s: Seeder) -> None:
        s.version("sv_01", [req("REQ-OLD-1"), req("REQ-DEP-1")])
        s.version("sv_02", [req("REQ-DEP-1", True)])

    repo = seeded(tmp_path, build)

    result = run_cli(repo, monkeypatch, "trace", rid)

    assert result.exit_code == 0, result.output
    assert result.stderr == ""


def test_ac5_records_no_event_and_leaves_the_running_task_alone(
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

    repo = seeded(tmp_path, build)
    before = event_count(repo)

    result = run_cli(repo, monkeypatch, "trace", "REQ-AUTH-001")

    assert result.exit_code == 0, result.output
    assert result.stdout == "task  AUTH-001  running\n"
    assert event_count(repo) == before
    assert run_cli(repo, monkeypatch, "status").stdout.startswith("AUTH-001  running")


def test_ac5_cli_wires_trace_with_traces_only() -> None:
    tree = ast.parse(CLI_SRC.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "trace")
    calls = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "trace_requirement"
    ]
    assert len(calls) == 1
    assert {k.arg for k in calls[0].keywords} == {"traces"}
    used = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    assert not used & {"git", "worktrees", "executor", "gates", "llm", "runner", "recorder"}


def test_ac6_fails_without_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "plain"
    repo.mkdir()

    result = run_cli(repo, monkeypatch, "trace", "REQ-AUTH-001")

    assert result.exit_code == 1
    assert "run `openfactory init` first" in result.stderr
    assert result.stdout == ""
    assert not (repo / ".openfactory").exists()
