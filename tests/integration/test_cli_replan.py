"""TASK-103 AC1..AC6: the `replan` command (docs/tasks/TASK-103-replan-command.md)."""

import ast
import json
import os
import sqlite3
import stat
import subprocess
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
import structlog
from typer.testing import CliRunner, Result

from openfactory.adapters.filesystem_spec_files import FilesystemSpecFiles
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.app.spec_loader import load_spec
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType
from openfactory.domain.models import SpecSet
from openfactory.domain.payloads import (
    ImpactComputedPayload,
    PlanApprovedPayload,
    PlanCreatedPayload,
    RequirementImpact,
    SpecApprovedPayload,
    SpecImportedPayload,
    TaskStateChangedPayload,
)
from openfactory.domain.spec_hash import content_hash

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "claude_envelope.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_SRC = REPO_ROOT / "src" / "openfactory" / "cli.py"
runner = CliRunner()

DB = Path(".openfactory/openfactory.db")
REQS = Path("specs/requirements.yaml")
POLICIES = Path("specs/policies.yaml")
HASH = "a" * 64
GATES = ["path_check", "ruff", "pytest", "gitleaks", "review"]

# AUTH-001 (REQ-AUTH-001): untouched, passed. AUTH-002 (REQ-AUTH-002): impacted, passed.
# AUTH-003 (REQ-AUTH-003): downstream, pending. REQ-AUTH-004 is added in sv_02.
REQUIREMENTS = """\
components: [auth]
requirements:
  - id: REQ-AUTH-001
    title: One
    statement: Users can log in.
    priority: must
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-001-1
        text: Criterion one.
  - id: REQ-AUTH-002
    title: Two
    statement: Users can refresh.
    priority: must
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-002-1
        text: Criterion two.
  - id: REQ-AUTH-003
    title: Three
    statement: Users can log out.
    priority: must
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-003-1
        text: Criterion three.
  - id: REQ-AUTH-004
    title: Four
    statement: Users can reset.
    priority: must
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-004-1
        text: Criterion four.
"""

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

GIT = """\
#!{python}
import sys
sys.stderr.write("fatal: first git line\\nsecond git line\\n")
sys.exit(128)
"""


def new_task(
    task_id: str,
    objective: str,
    requirements: Sequence[str],
    criteria: Sequence[str],
    depends_on: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "objective": objective,
        "requirements": list(requirements),
        "acceptance_criteria": list(criteria),
        "depends_on": list(depends_on),
        "components": ["auth"],
        "role": "implementer",
        "allowed_paths": ["app/"],
        "forbidden_paths": [],
    }


# Given out of id order; AUTH-005 depends on the untouched passed task.
GOOD = {
    "tasks": [
        new_task("AUTH-005", "Add reset", ["REQ-AUTH-004"], ["AC-AUTH-004-1"], ["AUTH-001"]),
        new_task(
            "AUTH-004",
            "Redo refresh and logout",
            ["REQ-AUTH-002", "REQ-AUTH-003"],
            ["AC-AUTH-002-1", "AC-AUTH-003-1"],
        ),
    ]
}
GOOD_LINES = ["AUTH-004  Redo refresh and logout", "AUTH-005  Add reset"]
# Rejected: an unknown dependency (and uncovered requirements).
FIRST_BAD = {
    "tasks": [new_task("AUTH-004", "Bad", ["REQ-AUTH-002"], ["AC-AUTH-002-1"], ["ZZZ-009"])]
}
# Rejected: an unknown requirement and an unknown criterion (and uncovered requirements).
SECOND_BAD = {"tasks": [new_task("AUTH-004", "Bad", ["REQ-NOPE-001"], ["AC-NOPE-1"])]}


def ok_reply(structured: Any) -> dict[str, Any]:
    envelope = json.loads(FIXTURE.read_text(encoding="utf-8"))
    envelope["structured_output"] = structured
    return {"stdout": json.dumps(envelope)}


class Claude:
    def __init__(self, record: Path) -> None:
        self.record = record

    def replies(self, *replies: dict[str, Any]) -> None:
        (self.record / "replies.json").write_text(json.dumps(replies), encoding="utf-8")

    def starts(self) -> int:
        path = self.record / "starts"
        return len(path.read_text()) if path.exists() else 0


def _script(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)


@pytest.fixture(autouse=True)
def claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Claude]:
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    record = tmp_path / "claude-record"
    record.mkdir()
    bin_dir = tmp_path / "claude-bin"
    bin_dir.mkdir()
    _script(bin_dir / "claude", CLAUDE.format(python=sys.executable, record=str(record)))
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    stand_in = Claude(record)
    stand_in.replies(ok_reply(GOOD))
    yield stand_in
    structlog.reset_defaults()


def fake_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "git-bin"
    bin_dir.mkdir()
    _script(bin_dir / "git", GIT.format(python=sys.executable))
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")


def run_replan(repo: Path, monkeypatch: pytest.MonkeyPatch) -> Result:
    from openfactory.cli import app

    monkeypatch.chdir(repo)
    return runner.invoke(app, ["replan"])


def init_repo(tmp_path: Path) -> Path:
    from openfactory.cli import app

    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "main.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "app/main.py"], cwd=repo, check=True)
    assert runner.invoke(app, ["init", str(repo)]).exit_code == 0
    (repo / REQS).write_text(REQUIREMENTS, encoding="utf-8")
    return repo


def contract(task_id: str, req_n: int, depends_on: list[str]) -> TaskContract:
    return TaskContract(
        task_id=task_id,
        objective=f"Do {task_id}",
        requirements=[f"REQ-AUTH-00{req_n}"],
        acceptance_criteria=[f"AC-AUTH-00{req_n}-1"],
        depends_on=depends_on,
        components=["auth"],
        role="implementer",
        allowed_paths=["app/**"],
        forbidden_paths=["specs/**"],
        required_gates=GATES,
        limits=Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.5),
    )


def seed(
    repo: Path,
    *,
    plan: bool = True,
    impact: str = "good",
) -> None:
    """Seed sv_01 and sv_02 (matching the spec files), plan_01 and one ImpactComputed."""
    spec = load_spec(FilesystemSpecFiles(repo / "specs")).spec
    assert spec is not None
    older = SpecSet(
        components=spec.components,
        requirements=[r for r in spec.requirements if r.id != "REQ-AUTH-004"],
        adrs=spec.adrs,
    )
    recorder = SqliteEventRecorder(repo / DB)

    def rec(stream: str, type_: EventType, payload: Any, actor: str = "orchestrator") -> None:
        recorder.record(
            Event.new(
                stream=stream, type=type_, payload=payload.model_dump(mode="json"), actor=actor
            )
        )

    try:
        for vid, version_spec, digest in (
            ("sv_01", older, HASH),
            ("sv_02", spec, content_hash(spec)),
        ):
            rec(
                f"spec:{vid}",
                EventType.SpecImported,
                SpecImportedPayload(spec_version=vid, hash=digest, spec=version_spec),
            )
            rec(
                f"spec:{vid}",
                EventType.SpecApproved,
                SpecApprovedPayload(spec_version=vid, hash=digest),
                "human",
            )
        if plan:
            rec(
                "plan:plan_01",
                EventType.PlanCreated,
                PlanCreatedPayload(
                    plan_id="plan_01",
                    spec_version="sv_01",
                    policy_hash=HASH,
                    run_id="run_0001",
                    tasks=[
                        contract("AUTH-001", 1, []),
                        contract("AUTH-002", 2, []),
                        contract("AUTH-003", 3, ["AUTH-002"]),
                    ],
                ),
            )
            rec(
                "plan:plan_01",
                EventType.PlanApproved,
                PlanApprovedPayload(plan_id="plan_01"),
                "human",
            )
            for task_id in ("AUTH-001", "AUTH-002"):
                steps = ["pending", "ready", "running", "gating", "passed"]
                for a, b in zip(steps, steps[1:], strict=False):
                    rec(
                        f"task:{task_id}",
                        EventType.TaskStateChanged,
                        TaskStateChangedPayload.model_validate(
                            {"task_id": task_id, "from": a, "to": b, "reason": None}
                        ),
                    )
        if impact != "none":
            added = RequirementImpact(
                id="REQ-AUTH-004",
                change="added",
                kind=None,
                rationale=None,
                obsolete_criteria=[],
                new_work=[],
            )
            removed = RequirementImpact(
                id="REQ-AUTH-009",
                change="removed",
                kind=None,
                rationale=None,
                obsolete_criteria=[],
                new_work=[],
            )
            nothing = impact == "nothing"
            rec(
                "spec:sv_02",
                EventType.ImpactComputed,
                ImpactComputedPayload(
                    from_version="sv_00" if impact == "other_from" else "sv_01",
                    to_version="sv_02",
                    run_id=None,
                    requirements=[removed] if nothing else [added],
                    adrs=[],
                    tasks=[] if nothing else ["AUTH-002"],
                    downstream=[] if nothing else ["AUTH-003"],
                    files=[],
                    tests=[],
                ),
            )
    finally:
        recorder.close()


def seeded(tmp_path: Path, **kwargs: Any) -> Path:
    repo = init_repo(tmp_path)
    seed(repo, **kwargs)
    return repo


def edit_statement(repo: Path) -> None:
    text = (repo / REQS).read_text(encoding="utf-8")
    (repo / REQS).write_text(text.replace("log in.", "sign in."), encoding="utf-8")


def break_policy(repo: Path) -> None:
    with (repo / POLICIES).open("a", encoding="utf-8") as f:
        f.write("bogus_key: 1\n")


def query(repo: Path, sql: str) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(repo / DB)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def event_count(repo: Path) -> int:
    return query(repo, "SELECT COUNT(*) FROM events")[0][0]


def event_types(repo: Path) -> list[str]:
    return [r[0] for r in query(repo, "SELECT type FROM events ORDER BY seq")]


def test_task103_ac1_prints_the_new_tasks_and_records_a_draft_for_the_latest_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = seeded(tmp_path)
    before = event_types(repo)

    result = run_replan(repo, monkeypatch)

    assert result.stdout.splitlines() == [*GOOD_LINES, "created plan_02"]
    assert result.stderr == ""
    assert result.exit_code == 0
    assert event_types(repo)[len(before) :] == [
        "AgentRunStarted",
        "AgentRunFinished",
        "PlanCreated",
    ]
    started = query(repo, "SELECT payload FROM events WHERE type = 'AgentRunStarted'")
    assert json.loads(started[-1][0])["role"] == "planner"
    created = query(repo, "SELECT payload FROM events WHERE type = 'PlanCreated' ORDER BY seq")
    payload = json.loads(created[-1][0])
    assert payload["plan_id"] == "plan_02"
    assert payload["spec_version"] == "sv_02"
    assert sorted(t["task_id"] for t in payload["tasks"]) == ["AUTH-004", "AUTH-005"]
    states = query(repo, "SELECT id, state FROM tasks WHERE plan_id = 'plan_01' ORDER BY id")
    assert states == [("AUTH-001", "passed"), ("AUTH-002", "passed"), ("AUTH-003", "pending")]


def test_task103_ac2_a_second_replan_supersedes_the_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = seeded(tmp_path)

    assert run_replan(repo, monkeypatch).exit_code == 0
    second = run_replan(repo, monkeypatch)

    assert second.stdout.splitlines() == [*GOOD_LINES, "created plan_03"]
    assert second.exit_code == 0
    assert query(repo, "SELECT id, status FROM plans ORDER BY id") == [
        ("plan_01", "approved"),
        ("plan_02", "superseded"),
        ("plan_03", "draft"),
    ]


def test_task103_ac2_second_rejected_reply_prints_only_its_sorted_rejections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> None:
    claude.replies(ok_reply(FIRST_BAD), ok_reply(SECOND_BAD))
    repo = seeded(tmp_path)
    before = event_types(repo)

    result = run_replan(repo, monkeypatch)

    lines = result.stdout.splitlines()
    assert result.exit_code == 1
    assert len(lines) >= 2
    assert lines == sorted(lines, key=lambda line: tuple(line.split("  ", 2)))
    assert all(len(line.split("  ", 2)) == 3 for line in lines)
    assert any(line.startswith("unknown-requirement  ") for line in lines)
    assert "ZZZ-009" not in result.stdout
    assert "created" not in result.stdout
    assert claude.starts() == 2
    assert event_types(repo)[len(before) :] == [
        "AgentRunStarted",
        "AgentRunFinished",
        "AgentRunStarted",
        "AgentRunFinished",
    ]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"plan": False, "impact": "none"}, "no approved plan\n"),
        ({"impact": "none"}, "run openfactory impact first\n"),
        ({"impact": "other_from"}, "run openfactory impact first\n"),
        ({"impact": "nothing"}, "nothing to replan\n"),
    ],
)
def test_task103_ac3_early_refusals_are_one_line_with_no_event_and_no_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    claude: Claude,
    kwargs: dict[str, Any],
    message: str,
) -> None:
    repo = seeded(tmp_path, **kwargs)
    edit_statement(repo)
    before = event_count(repo)

    result = run_replan(repo, monkeypatch)

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == message
    assert event_count(repo) == before
    assert claude.starts() == 0


def test_task103_ac4_invalid_policy_refuses_without_the_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> None:
    repo = seeded(tmp_path)
    edit_statement(repo)
    break_policy(repo)

    result = run_replan(repo, monkeypatch)

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == "policy is invalid; run openfactory validate\n"
    assert claude.starts() == 0


def test_task103_ac4_edited_spec_files_warn_and_carry_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = seeded(tmp_path)
    edit_statement(repo)

    result = run_replan(repo, monkeypatch)

    assert result.stderr == "spec files differ from approved sv_02\n"
    assert result.stdout.splitlines()[-1] == "created plan_02"
    assert result.exit_code == 0


def test_task103_ac4_the_warning_comes_before_a_git_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> None:
    repo = seeded(tmp_path)
    edit_statement(repo)
    before = event_count(repo)
    fake_git(tmp_path, monkeypatch)

    result = run_replan(repo, monkeypatch)

    assert result.stderr.splitlines() == [
        "spec files differ from approved sv_02",
        "git ls-files failed: fatal: first git line",
    ]
    assert result.stdout == ""
    assert result.exit_code == 1
    assert claude.starts() == 0
    assert event_count(repo) == before


def test_task103_ac5_planner_failure_names_the_first_error_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> None:
    claude.replies({"exit": 1, "stderr": "claude broke\nsecond claude line\n"})
    repo = seeded(tmp_path)

    result = run_replan(repo, monkeypatch)

    finished = query(repo, "SELECT payload FROM events WHERE type = 'AgentRunFinished'")
    error = json.loads(finished[-1][0])["error"]
    assert "second claude line" in error
    assert result.stderr == f"planner call failed: {error.splitlines()[0]}\n"
    assert result.stdout == ""
    assert result.exit_code == 1
    assert "PlanCreated" not in event_types(repo)[-3:]
    assert event_types(repo).count("PlanCreated") == 1  # only the seeded plan_01


def test_task103_ac5_fails_without_init(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()

    result = run_replan(plain, monkeypatch)

    assert result.exit_code == 1
    assert "run `openfactory init` first" in result.stderr
    assert result.stdout == ""
    assert not (plain / ".openfactory").exists()
    assert claude.starts() == 0


def test_task103_ac6_cli_wires_replan_with_the_two_use_cases_only() -> None:
    tree = ast.parse(CLI_SRC.read_text(encoding="utf-8"))
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "replan" in funcs
    assert "_prepare_and_create_replan" in funcs
    path = [funcs["replan"], funcs["_prepare_and_create_replan"]]
    called = {
        getattr(n.func, "id", None) for fn in path for n in ast.walk(fn) if isinstance(n, ast.Call)
    }
    assert {"prepare_replan", "create_replan"} <= called
    names = {
        (n.id if isinstance(n, ast.Name) else n.attr).lower()
        for fn in path
        for n in ast.walk(fn)
        if isinstance(n, ast.Name | ast.Attribute)
    }
    assert not [n for n in names if any(w in n for w in ("worktree", "executor", "gate"))]


def test_task103_ac6_no_inner_layer_file_changes() -> None:
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "main",
            "--",
            "src/openfactory/app",
            "src/openfactory/domain",
            "src/openfactory/ports",
            "src/openfactory/adapters",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
