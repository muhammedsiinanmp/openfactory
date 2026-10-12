"""TASK-037 AC6: `validate` and `approve spec` report a deleted requirement.

See docs/tasks/TASK-037-deleted-requirement-rule.md.
"""

import json
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
MESSAGE = "requirement 'REQ-AUTH-002' is deleted but tasks still reference it: AUTH-002"
VIOLATION_LINE = f"deleted-requirement  REQ-AUTH-002  {MESSAGE}"


def _req(n: int, deprecated: bool = False) -> str:
    return (
        f"  - id: REQ-AUTH-{n:03d}\n"
        f"    title: Req {n}\n"
        f"    statement: Statement {n}.\n"
        "    priority: must\n"
        + ("    deprecated: true\n" if deprecated else "")
        + f"    acceptance_criteria:\n      - id: AC-AUTH-{n:03d}-1\n        text: Works.\n"
    )


BOTH = "requirements:\n" + _req(1) + _req(2)
WITHOUT_002 = "requirements:\n" + _req(1)
RESTORED = "requirements:\n" + _req(1) + _req(2, deprecated=True)


def run_cli(repo: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> Result:
    from openfactory.cli import app

    monkeypatch.chdir(repo)
    return runner.invoke(app, list(args))


def make_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Repo with `sv_01` approved and a draft plan whose task AUTH-002 lists REQ-AUTH-002."""
    from openfactory.cli import app

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    assert runner.invoke(app, ["init", str(repo)]).exit_code == 0
    (repo / REQS).write_text(BOTH, encoding="utf-8")
    result = run_cli(repo, monkeypatch, "approve", "spec")
    assert result.exit_code == 0, result.output

    contract = TaskContract(
        task_id="AUTH-002",
        objective="Do AUTH-002",
        requirements=["REQ-AUTH-002"],
        acceptance_criteria=["AC-AUTH-002-1"],
        depends_on=[],
        components=["auth"],
        role="implementer",
        allowed_paths=["app/auth/**"],
        forbidden_paths=["specs/**"],
        required_gates=["path_check", "ruff", "pytest", "gitleaks", "review"],
        limits=Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.5),
    )
    payload = PlanCreatedPayload(
        plan_id="plan_01",
        spec_version="sv_01",
        policy_hash=HASH,
        run_id="run_0001",
        tasks=[contract],
    )
    recorder = SqliteEventRecorder(repo / DB)
    try:
        recorder.record(
            Event.new(
                stream="plan:plan_01",
                type=EventType.PlanCreated,
                payload=payload.model_dump(mode="json"),
                actor="orchestrator",
            )
        )
    finally:
        recorder.close()
    return repo


def events(repo: Path) -> list[tuple[str, str, dict[str, Any]]]:
    conn = sqlite3.connect(repo / DB)
    try:
        rows = conn.execute("SELECT type, stream, payload FROM events ORDER BY seq").fetchall()
    finally:
        conn.close()
    return [(t, s, json.loads(p)) for t, s, p in rows]


def test_ac6_validate_prints_the_violation_and_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path, monkeypatch)
    (repo / REQS).write_text(WITHOUT_002, encoding="utf-8")

    result = run_cli(repo, monkeypatch, "validate")

    assert result.exit_code == 1
    assert result.stdout.splitlines() == [VIOLATION_LINE, "1 violations, 0 policy problems"]


def test_ac6_approve_spec_refuses_and_a_deprecated_restore_approves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path, monkeypatch)
    (repo / REQS).write_text(WITHOUT_002, encoding="utf-8")

    refused = run_cli(repo, monkeypatch, "approve", "spec")

    assert refused.exit_code == 1
    assert refused.stdout.splitlines() == [VIOLATION_LINE, "1 violations, 0 policy problems"]
    stored = events(repo)
    assert not [e for e in stored if e[0] == "SpecApproved" and e[1] == "spec:sv_02"]
    last_type, last_stream, last_payload = stored[-1]
    assert (last_type, last_stream) == ("SpecValidated", "spec:sv_02")
    assert [(v["rule"], v["subject"]) for v in last_payload["violations"]] == [
        ("deleted-requirement", "REQ-AUTH-002")
    ]

    (repo / REQS).write_text(RESTORED, encoding="utf-8")
    approved = run_cli(repo, monkeypatch, "approve", "spec")

    assert approved.exit_code == 0, approved.output
    assert approved.stdout.splitlines() == ["0 violations, 0 policy problems", "approved sv_02"]
