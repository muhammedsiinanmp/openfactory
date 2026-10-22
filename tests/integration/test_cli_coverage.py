"""TASK-082 AC1..AC6: the `coverage` command (docs/tasks/TASK-082-coverage.md)."""

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

    def tag(self, *req_ids: str) -> None:
        self.rec(
            "task:AUTH-001",
            EventType.TestsCollected,
            TestsCollectedPayload(
                run_id="run_0002",
                task_id="AUTH-001",
                tests=[
                    CollectedTest(
                        node_id=f"tests/test_a.py::test_{r}", file="tests/test_a.py", req=[r]
                    )
                    for r in req_ids
                ],
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


def test_ac1_prints_the_untagged_non_deprecated_requirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def build(s: Seeder) -> None:
        s.version("sv_01", [req("REQ-AUTH-001"), req("REQ-AUTH-002"), req("REQ-AUTH-003", True)])
        s.tag("REQ-AUTH-001")

    repo = seeded(tmp_path, build)

    result = run_cli(repo, monkeypatch, "coverage")

    assert result.exit_code == 0, result.output
    assert result.stdout == "REQ-AUTH-002\n"
    assert result.stderr == ""


def test_ac2_everything_covered_prints_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def build(s: Seeder) -> None:
        s.version("sv_01", [req("REQ-AUTH-001"), req("REQ-AUTH-002"), req("REQ-AUTH-003", True)])
        s.tag("REQ-AUTH-001", "REQ-AUTH-002")

    repo = seeded(tmp_path, build)

    result = run_cli(repo, monkeypatch, "coverage")

    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert result.stderr == ""


def test_ac3_latest_approved_only_in_string_order_ignoring_a_later_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def build(s: Seeder) -> None:
        s.version("sv_01", [req("REQ-OLD-1")])
        s.version("sv_02", [req("REQ-A-2"), req("REQ-A-10"), req("REQ-A-1")])
        s.version("sv_03", [req("REQ-DRAFT-1")], approved=False)

    repo = seeded(tmp_path, build)

    result = run_cli(repo, monkeypatch, "coverage")

    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == ["REQ-A-1", "REQ-A-10", "REQ-A-2"]


@pytest.mark.parametrize("with_draft", [False, True])
def test_ac4_no_approved_version_is_refused_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, with_draft: bool
) -> None:
    def build(s: Seeder) -> None:
        if with_draft:
            s.version("sv_01", [req("REQ-AUTH-001")], approved=False)

    repo = seeded(tmp_path, build)

    result = run_cli(repo, monkeypatch, "coverage")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == "no approved spec version\n"


def test_ac5_records_no_event_and_leaves_the_running_task_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = TaskContract(
        task_id="AUTH-001",
        objective="Do AUTH-001",
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

    def build(s: Seeder) -> None:
        s.version("sv_01", [req("REQ-AUTH-001")])
        s.rec(
            "plan:plan_01",
            EventType.PlanCreated,
            PlanCreatedPayload(
                plan_id="plan_01",
                spec_version="sv_01",
                policy_hash=HASH,
                run_id="run_0001",
                tasks=[contract],
            ),
        )
        s.rec(
            "plan:plan_01", EventType.PlanApproved, PlanApprovedPayload(plan_id="plan_01"), "human"
        )
        for a, b in [
            (TaskState.pending, TaskState.ready),
            (TaskState.ready, TaskState.running),
        ]:
            s.rec(
                "task:AUTH-001",
                EventType.TaskStateChanged,
                TaskStateChangedPayload(task_id="AUTH-001", from_=a, to=b, reason=None),
            )
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

    result = run_cli(repo, monkeypatch, "coverage")

    assert result.exit_code == 0, result.output
    assert result.stdout == "REQ-AUTH-001\n"
    assert event_count(repo) == before
    status = run_cli(repo, monkeypatch, "status")
    assert status.stdout.startswith("AUTH-001  running")


def test_ac5_cli_wires_coverage_with_versions_and_traces_only() -> None:
    tree = ast.parse(CLI_SRC.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "coverage")
    calls = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "requirement_coverage"
    ]
    assert len(calls) == 1
    assert {k.arg for k in calls[0].keywords} == {"versions", "traces"}
    used = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    assert not used & {"git", "worktrees", "executor", "gates", "llm", "runner", "recorder"}


def test_ac6_fails_without_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "plain"
    repo.mkdir()

    result = run_cli(repo, monkeypatch, "coverage")

    assert result.exit_code == 1
    assert "run `openfactory init` first" in result.stderr
    assert result.stdout == ""
    assert not (repo / ".openfactory").exists()
