"""TASK-034 AC1..AC6: the `plan` command (see docs/tasks/TASK-034-cli-plan.md)."""

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

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "claude_envelope.json"
runner = CliRunner()

DB = Path(".openfactory/openfactory.db")
REQS = Path("specs/requirements.yaml")
POLICIES = Path("specs/policies.yaml")

VALID_REQUIREMENTS = """\
components: [auth]
requirements:
  - id: REQ-AUTH-001
    title: Login
    statement: Users can log in.
    priority: must
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-001-1
        text: Valid login returns a JWT.
      - id: AC-AUTH-001-2
        text: Invalid login returns 401.
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


def task(
    task_id: str,
    objective: str,
    depends_on: Sequence[str] = (),
    criteria: Sequence[str] = ("AC-AUTH-001-1", "AC-AUTH-001-2"),
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "objective": objective,
        "requirements": ["REQ-AUTH-001"],
        "acceptance_criteria": list(criteria),
        "depends_on": list(depends_on),
        "components": ["auth"],
        "role": "implementer",
        "allowed_paths": ["app/"],
        "forbidden_paths": [],
    }


GOOD = {
    "tasks": [
        task("AUTH-002", "Add token refresh", depends_on=["AUTH-001"]),
        task("AUTH-001", "Implement login endpoint"),
    ]
}
# Rejected: one unknown dependency, nothing else.
FIRST_BAD = {"tasks": [task("AUTH-001", "Implement login", depends_on=["ZZZ-009"])]}
# Rejected: unknown requirement, unknown criterion and more.
SECOND_BAD = {
    "tasks": [
        {
            **task("BAD-001", "Bad", criteria=("AC-NOPE-1",)),
            "requirements": ["REQ-NOPE-001"],
        }
    ]
}
GOOD_LINES = ["AUTH-001  Implement login endpoint", "AUTH-002  Add token refresh"]


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

    def prompt(self, n: int) -> str:
        return (self.record / f"prompt-{n}.txt").read_text(encoding="utf-8")


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


def make_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, approve: bool = True) -> Path:
    from openfactory.cli import app

    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "main.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "app/main.py"], cwd=repo, check=True)
    assert runner.invoke(app, ["init", str(repo)]).exit_code == 0
    (repo / REQS).write_text(VALID_REQUIREMENTS, encoding="utf-8")
    monkeypatch.chdir(repo)
    if approve:
        assert runner.invoke(app, ["approve", "spec"]).exit_code == 0
    return repo


def run_plan() -> Result:
    from openfactory.cli import app

    return runner.invoke(app, ["plan"])


def approve_plan_01(repo: Path) -> None:
    from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
    from openfactory.domain.events import Event, EventType

    assert run_plan().exit_code == 0
    recorder = SqliteEventRecorder(repo / DB)
    try:
        recorder.record(
            Event.new(
                stream="plan:plan_01",
                type=EventType.PlanApproved,
                payload={"plan_id": "plan_01"},
                actor="human",
            )
        )
    finally:
        recorder.close()


def break_policy(repo: Path) -> None:
    with (repo / POLICIES).open("a", encoding="utf-8") as f:
        f.write("bogus_key: 1\n")


def edit_statement(repo: Path) -> None:
    text = (repo / REQS).read_text(encoding="utf-8")
    (repo / REQS).write_text(text.replace("log in.", "sign in."), encoding="utf-8")


def query(repo: Path, sql: str) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(repo / DB)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def events(repo: Path) -> list[tuple[str, dict[str, Any]]]:
    rows = query(repo, "SELECT type, payload FROM events ORDER BY seq")
    return [(t, json.loads(p)) for t, p in rows]


def event_types(repo: Path) -> list[str]:
    return [t for t, _ in events(repo)]


def expected_rejections(reply: dict[str, Any]) -> list[str]:
    from openfactory.adapters.filesystem_spec_files import FilesystemSpecFiles
    from openfactory.app.spec_loader import load_spec
    from openfactory.domain.contracts import PlannerReply
    from openfactory.domain.plan_checks import check_plan, rejection_lines

    spec = load_spec(FilesystemSpecFiles(Path("specs"))).spec
    assert spec is not None
    return rejection_lines(check_plan(PlannerReply.model_validate(reply).tasks, spec))


def test_ac1_prints_task_lines_and_status_and_records_the_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
):
    repo = make_repo(tmp_path, monkeypatch)
    before = event_types(repo)

    result = run_plan()

    assert result.stdout.splitlines() == [*GOOD_LINES, "created plan_01"]
    assert result.stderr == ""
    assert result.exit_code == 0
    assert event_types(repo)[len(before) :] == [
        "AgentRunStarted",
        "AgentRunFinished",
        "PlanCreated",
    ]
    created = [p for t, p in events(repo) if t == "PlanCreated"]
    assert created[0]["spec_version"] == "sv_01"
    assert query(repo, "SELECT id, status FROM plans") == [("plan_01", "draft")]
    assert "app/main.py" in claude.prompt(1)


def test_ac2_no_approved_spec_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
):
    repo = make_repo(tmp_path, monkeypatch, approve=False)
    break_policy(repo)
    before = event_types(repo)

    result = run_plan()

    assert result.stdout == ""
    assert result.stderr.splitlines() == ["no approved spec version"]
    assert result.exit_code == 1
    assert claude.starts() == 0
    assert event_types(repo) == before


def test_ac2_invalid_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude):
    repo = make_repo(tmp_path, monkeypatch)
    approve_plan_01(repo)
    break_policy(repo)
    before, starts = event_types(repo), claude.starts()

    result = run_plan()

    assert result.stdout == ""
    assert result.stderr.splitlines() == ["policy is invalid; run openfactory validate"]
    assert result.exit_code == 1
    assert claude.starts() == starts
    assert event_types(repo) == before


def test_ac2_approved_plan_writes_no_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
):
    repo = make_repo(tmp_path, monkeypatch)
    approve_plan_01(repo)
    edit_statement(repo)
    before, starts = event_types(repo), claude.starts()

    result = run_plan()

    assert result.stdout == ""
    assert result.stderr.splitlines() == ["plan_01 is already approved; use replan"]
    assert result.exit_code == 1
    assert claude.starts() == starts
    assert event_types(repo) == before


def test_ac2_not_initialised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)

    result = run_plan()

    assert result.stdout == ""
    assert "run `openfactory init` first" in result.stderr
    assert result.exit_code == 1
    assert claude.starts() == 0


def test_ac3_edited_statement_warns_and_carries_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = make_repo(tmp_path, monkeypatch)
    edit_statement(repo)

    result = run_plan()

    assert result.stderr.splitlines() == ["spec files differ from approved sv_01"]
    assert result.stdout.splitlines()[-1] == "created plan_01"
    assert result.exit_code == 0


def test_ac3_unloadable_spec_files_warn_and_carry_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = make_repo(tmp_path, monkeypatch)
    (repo / REQS).write_text("requirements: [unclosed\n", encoding="utf-8")

    result = run_plan()

    assert result.stderr.splitlines() == ["spec files differ from approved sv_01"]
    assert result.stdout.splitlines()[-1] == "created plan_01"
    assert result.exit_code == 0


def test_ac3_warning_comes_before_a_git_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = make_repo(tmp_path, monkeypatch)
    edit_statement(repo)
    fake_git(tmp_path, monkeypatch)

    result = run_plan()

    lines = result.stderr.splitlines()
    assert lines[0] == "spec files differ from approved sv_01"
    assert lines[1].startswith("git ls-files failed: ")
    assert len(lines) == 2
    assert result.exit_code == 1


def test_ac4_second_rejected_reply_prints_its_rejections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
):
    repo = make_repo(tmp_path, monkeypatch)
    claude.replies(ok_reply(FIRST_BAD), ok_reply(SECOND_BAD))
    before = event_types(repo)
    second = expected_rejections(SECOND_BAD)
    first_only = [line for line in expected_rejections(FIRST_BAD) if line not in second]
    assert len(second) >= 2
    assert first_only

    result = run_plan()

    assert result.stdout.splitlines() == second
    for line in first_only:
        assert line not in result.stdout
    assert "created" not in result.stdout
    assert result.exit_code == 1
    assert claude.starts() == 2
    assert event_types(repo)[len(before) :] == [
        "AgentRunStarted",
        "AgentRunFinished",
        "AgentRunStarted",
        "AgentRunFinished",
    ]
    assert query(repo, "SELECT id FROM plans") == []


def test_ac5_git_failure_names_the_first_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
):
    repo = make_repo(tmp_path, monkeypatch)
    before = event_types(repo)
    fake_git(tmp_path, monkeypatch)

    result = run_plan()

    assert result.stdout == ""
    assert result.stderr.splitlines() == ["git ls-files failed: fatal: first git line"]
    assert result.exit_code == 1
    assert claude.starts() == 0
    assert event_types(repo) == before


def test_ac5_planner_failure_names_the_first_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
):
    repo = make_repo(tmp_path, monkeypatch)
    claude.replies({"exit": 1, "stderr": "claude broke\nsecond claude line\n"})
    before = event_types(repo)

    result = run_plan()

    assert result.stdout == ""
    assert result.stderr.splitlines() == ["planner call failed: claude broke"]
    assert result.exit_code == 1
    assert claude.starts() == 1
    assert event_types(repo)[len(before) :] == ["AgentRunStarted", "AgentRunFinished"]
    finished = events(repo)[-1][1]
    assert finished["exit"] == "error"
    assert "claude broke" in finished["error"]
    assert "second claude line" in finished["error"]


def test_ac6_api_key_warning_is_one_json_line_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    make_repo(tmp_path, monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-secret-value")

    result = run_plan()

    assert result.stdout.splitlines() == [*GOOD_LINES, "created plan_01"]
    assert result.exit_code == 0
    lines = result.stderr.splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["event"] == "anthropic_api_key_removed"
    assert entry["level"] == "warning"
    assert "sk-test-secret-value" not in result.stdout
    assert "sk-test-secret-value" not in result.stderr
