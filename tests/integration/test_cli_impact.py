"""TASK-096 AC1..AC6: the `impact` command (docs/tasks/TASK-096-impact-command.md)."""

import ast
import json
import os
import sqlite3
import stat
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import structlog
from typer.testing import CliRunner, Result

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
    CollectedTest,
    CommitRecordedPayload,
    PlanApprovedPayload,
    PlanCreatedPayload,
    SpecApprovedPayload,
    SpecImportedPayload,
    TestsCollectedPayload,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "claude_envelope.json"
CLI_SRC = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "cli.py"
runner = CliRunner()

DB = Path(".openfactory/openfactory.db")
HASH = "a" * 64
GATES = ["path_check", "ruff", "pytest", "gitleaks", "review"]

CLAUDE = """\
#!{python}
import json, sys
from pathlib import Path

rec = Path({record!r})
with (rec / "starts").open("a") as f:
    f.write("x")
n = len((rec / "starts").read_text())
(rec / f"prompt-{{n}}.txt").write_bytes(sys.stdin.buffer.read())
replies = json.loads((rec / "replies.json").read_text())
reply = replies[min(n, len(replies)) - 1]
sys.stderr.write(reply.get("stderr", ""))
sys.stdout.write(reply.get("stdout", ""))
sys.exit(reply.get("exit", 0))
"""


def ok_reply(structured: Any) -> dict[str, Any]:
    envelope = json.loads(FIXTURE.read_text(encoding="utf-8"))
    envelope["structured_output"] = structured
    return {"stdout": json.dumps(envelope)}


def change(req_id: str, kind: str, new_work: list[str]) -> dict[str, Any]:
    return {
        "req_id": req_id,
        "kind": kind,
        "rationale": "because",
        "obsolete_criteria": ["AC-SHARED-1"],
        "new_work": new_work,
    }


GOOD = {
    "changes": [
        change("REQ-M-1", "replacement", ["OTP issue endpoint"]),
        change("REQ-M-2", "behavioral", ["attempt rate limit", "OTP verify endpoint"]),
    ]
}
SCHEMA_BAD = {"bogus": 1}
# Two modified requirements with no entry: two rejection lines.
MISSING_BAD = {"changes": []}
FIRST_REJECTION = "missing-requirement  REQ-M-1  modified requirement 'REQ-M-1' has no entry"


class Claude:
    def __init__(self, record: Path) -> None:
        self.record = record

    def replies(self, *replies: dict[str, Any]) -> None:
        (self.record / "replies.json").write_text(json.dumps(replies), encoding="utf-8")

    def starts(self) -> int:
        path = self.record / "starts"
        return len(path.read_text()) if path.exists() else 0


@pytest.fixture(autouse=True)
def claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Claude]:
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    record = tmp_path / "claude-record"
    record.mkdir()
    bin_dir = tmp_path / "claude-bin"
    bin_dir.mkdir()
    script = bin_dir / "claude"
    script.write_text(CLAUDE.format(python=sys.executable, record=str(record)), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    stand_in = Claude(record)
    stand_in.replies(ok_reply(GOOD))
    yield stand_in
    structlog.reset_defaults()


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


def req(
    id: str,
    statement: str = "Users can do it.",
    *,
    criteria: list[str] | None = None,
    deprecated: bool = False,
) -> Requirement:
    return Requirement(
        id=id,
        title=f"Title {id}",
        statement=statement,
        priority=Priority.must,
        components=["auth"],
        acceptance_criteria=[AcceptanceCriterion(id=c, text=f"text {c}") for c in criteria or []],
        deprecated=deprecated,
    )


def contract(task_id: str, requirements: list[str], depends_on: list[str]) -> TaskContract:
    return TaskContract(
        task_id=task_id,
        objective=f"Do {task_id}",
        requirements=requirements,
        acceptance_criteria=["AC-AUTH-001-1"],
        depends_on=depends_on,
        components=["auth"],
        role="implementer",
        allowed_paths=["app/**"],
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

    def version(self, vid: str, reqs: list[Requirement], adrs: list[Adr] | None = None) -> None:
        spec = SpecSet(components=["auth"], requirements=reqs, adrs=adrs or [])
        self.rec(
            f"spec:{vid}",
            EventType.SpecImported,
            SpecImportedPayload(spec_version=vid, hash=HASH, spec=spec),
        )
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
            "task:AUTH-001",
            EventType.TestsCollected,
            TestsCollectedPayload(
                run_id="run_0009",
                task_id="AUTH-001",
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


def world(s: Seeder) -> None:
    shared = ["AC-SHARED-1", "AC-OTHER-1"]
    s.version(
        "sv_01",
        [
            req("REQ-D-1"),
            req("REQ-M-1", "old", criteria=shared),
            req("REQ-M-2", "old", criteria=shared),
            req("REQ-R-1"),
            req("REQ-U-1"),
        ],
        [
            Adr(id="ADR-001", status=AdrStatus.accepted, body="old"),
            Adr(id="ADR-002", status=AdrStatus.accepted, body="same"),
        ],
    )
    s.version(
        "sv_02",
        [
            req("REQ-D-1", deprecated=True),
            req("REQ-M-1", "new", criteria=shared),
            req("REQ-M-2", "new", criteria=shared),
            req("REQ-N-1"),
            req("REQ-U-1"),
        ],
        [
            Adr(id="ADR-001", status=AdrStatus.accepted, body="new"),
            Adr(id="ADR-002", status=AdrStatus.accepted, body="same"),
        ],
    )
    s.plan(
        "sv_01",
        [
            contract("AUTH-004", ["REQ-U-1"], ["AUTH-001"]),
            contract("AUTH-003", ["REQ-R-1"], []),
            contract("AUTH-002", ["REQ-M-2"], []),
            contract("AUTH-001", ["REQ-M-1"], []),
        ],
    )
    s.commit("1", "AUTH-001", "run_0002", ["app/b.py", "app/a.py"])
    s.commit("3", "AUTH-003", "run_0003", ["app/c.py"])
    s.commit("4", "AUTH-004", "run_0004", ["app/d.py"])
    s.tests(
        ("tests/test_b.py::test_two", "tests/test_b.py", ["REQ-M-2"]),
        ("tests/test_a.py::test_one", "tests/test_a.py", ["REQ-M-1"]),
        ("tests/test_u.py::test_unrelated", "tests/test_u.py", ["REQ-U-1"]),
    )


def no_modified_world(s: Seeder) -> None:
    s.version("sv_01", [req("REQ-D-1"), req("REQ-R-1"), req("REQ-U-1")])
    s.version("sv_02", [req("REQ-D-1", deprecated=True), req("REQ-N-1"), req("REQ-U-1")])
    s.plan("sv_01", [contract("AUTH-001", ["REQ-R-1"], [])])


def rows(repo: Path, sql: str) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(repo / DB)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def event_count(repo: Path) -> int:
    return rows(repo, "SELECT COUNT(*) FROM events")[0][0]


def types(repo: Path) -> list[str]:
    return [r[0] for r in rows(repo, "SELECT type FROM events ORDER BY seq")]


EXPECTED = [
    "requirement  REQ-D-1  deprecated  -",
    "requirement  REQ-M-1  modified  replacement",
    "requirement  REQ-M-2  modified  behavioral",
    "requirement  REQ-N-1  added  -",
    "requirement  REQ-R-1  removed  -",
    "adr  ADR-001  modified",
    "task  AUTH-001",
    "task  AUTH-002",
    "task  AUTH-003",
    "downstream  AUTH-004",
    "file  app/a.py",
    "file  app/b.py",
    "file  app/c.py",
    "file  app/d.py",
    "test  tests/test_a.py::test_one",
    "test  tests/test_b.py::test_two",
    "obsolete  AC-SHARED-1",
    "new-work  REQ-M-1  OTP issue endpoint",
    "new-work  REQ-M-2  OTP verify endpoint",
    "new-work  REQ-M-2  attempt rate limit",
    "impact sv_01..sv_02",
]


def test_task096_ac1_prints_the_report_groups_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = seeded(tmp_path, world)

    result = run_cli(repo, monkeypatch, "impact")

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    assert result.stdout.splitlines() == EXPECTED


def test_task096_ac2_records_the_classifier_run_then_impact_computed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> None:
    repo = seeded(tmp_path, world)
    before = types(repo)

    assert run_cli(repo, monkeypatch, "impact").exit_code == 0

    assert types(repo)[len(before) :] == ["AgentRunStarted", "AgentRunFinished", "ImpactComputed"]
    assert claude.starts() == 1
    started = rows(repo, "SELECT payload FROM events WHERE type = 'AgentRunStarted'")
    assert json.loads(started[-1][0])["role"] == "classifier"
    streams = rows(repo, "SELECT stream FROM events WHERE type = 'ImpactComputed'")
    assert streams == [("spec:sv_02",)]


def test_task096_ac2_without_a_modified_requirement_makes_no_call_and_records_each_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> None:
    repo = seeded(tmp_path, no_modified_world)

    first = run_cli(repo, monkeypatch, "impact")
    second = run_cli(repo, monkeypatch, "impact")

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert claude.starts() == 0
    lines = first.stdout.splitlines()
    assert second.stdout.splitlines() == lines
    assert lines[0] == "requirement  REQ-D-1  deprecated  -"
    assert all(line.endswith("  -") for line in lines if line.startswith("requirement  "))
    assert not [line for line in lines if line.startswith(("obsolete", "new-work"))]
    assert lines[-1] == "impact sv_01..sv_02"
    assert types(repo).count("ImpactComputed") == 2
    assert "AgentRunStarted" not in types(repo)[-3:]


def refusal_world_no_plan(s: Seeder) -> None:
    s.version("sv_01", [req("REQ-U-1")])


def refusal_world_no_change(s: Seeder) -> None:
    s.version("sv_01", [req("REQ-U-1")])
    s.plan("sv_01", [contract("AUTH-001", ["REQ-U-1"], [])])


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (refusal_world_no_plan, "no approved plan\n"),
        (refusal_world_no_change, "no spec change since sv_01\n"),
    ],
)
def test_task096_ac3_refuses_with_one_line_and_no_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude, build, message: str
) -> None:  # noqa: ANN001
    repo = seeded(tmp_path, build)
    before = event_count(repo)

    result = run_cli(repo, monkeypatch, "impact")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == message
    assert event_count(repo) == before
    assert claude.starts() == 0


def test_task096_ac4_two_rejected_replies_report_the_last_runs_first_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> None:
    claude.replies(ok_reply(SCHEMA_BAD), ok_reply(MISSING_BAD))
    repo = seeded(tmp_path, world)

    result = run_cli(repo, monkeypatch, "impact")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == f"classifier call failed: {FIRST_REJECTION}\n"
    assert claude.starts() == 2
    assert types(repo).count("AgentRunStarted") == 2
    assert "ImpactComputed" not in types(repo)


def test_task096_ac4_a_failed_process_reports_the_first_error_line_and_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> None:
    claude.replies({"stderr": "boom first line\nsecond line\n", "exit": 3})
    repo = seeded(tmp_path, world)

    result = run_cli(repo, monkeypatch, "impact")

    assert result.exit_code == 1
    assert result.stdout == ""
    finished = rows(repo, "SELECT payload FROM events WHERE type = 'AgentRunFinished'")
    assert len(finished) == 1
    error = json.loads(finished[0][0])["error"]
    assert result.stderr == f"classifier call failed: {error.splitlines()[0]}\n"
    assert "boom first line" in error
    assert claude.starts() == 1
    assert "ImpactComputed" not in types(repo)


def test_task096_ac5_fails_without_init(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> None:
    repo = tmp_path / "plain"
    repo.mkdir()

    result = run_cli(repo, monkeypatch, "impact")

    assert result.exit_code == 1
    assert "run `openfactory init` first" in result.stderr
    assert result.stdout == ""
    assert not (repo / ".openfactory").exists()
    assert claude.starts() == 0


def test_task096_ac6_cli_wires_impact_with_compute_impact_only() -> None:
    tree = ast.parse(CLI_SRC.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "impact")
    calls = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "compute_impact"
    ]
    assert len(calls) == 1
    used = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    assert not used & {"git", "worktrees", "executor", "gates", "runner"}
