"""TASK-056 AC1..AC5: the `run` command (see docs/tasks/TASK-056-cli-run.md)."""

import ast
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from openfactory.app.run import RunRefusal, RunReport, TaskRunResult
from openfactory.domain.states import TaskState

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "claude_envelope.json"
SRC = ROOT / "src" / "openfactory"
runner = CliRunner()

DB = Path(".openfactory/openfactory.db")
REQS = Path("specs/requirements.yaml")
ADR_1 = Path("specs/adrs/ADR-001-auth-method.md")
MAIN = Path("app/main.py")

REQS_TEXT = """\
components: [auth]
requirements:
  - id: REQ-AUTH-001
    title: Login
    statement: Users can log in.
    priority: must
    components: [auth]
    constrained_by: [ADR-001]
    acceptance_criteria:
      - id: AC-AUTH-001-1
        text: Valid login returns a JWT.
"""
ADR_TEXT = "---\nid: ADR-001\nstatus: accepted\n---\nUsers are identified by membership number.\n"
PLAN = {
    "tasks": [
        {
            "task_id": "AUTH-001",
            "objective": "Implement login",
            "requirements": ["REQ-AUTH-001"],
            "acceptance_criteria": ["AC-AUTH-001-1"],
            "depends_on": [],
            "components": ["auth"],
            "role": "implementer",
            "allowed_paths": ["app/"],
            "forbidden_paths": [],
        }
    ]
}
CLAUDE = """\
#!{python}
import sys
sys.stdin.buffer.read()
sys.stdout.write({reply!r})
"""


def invoke(*args: str):
    from openfactory.cli import app

    return runner.invoke(app, list(args))


@pytest.fixture(autouse=True)
def clean_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    bin_dir = tmp_path / "claude-bin"
    bin_dir.mkdir()
    envelope = json.loads(FIXTURE.read_text(encoding="utf-8"))
    reply = json.dumps({**envelope, "structured_output": PLAN})
    claude = bin_dir / "claude"
    claude.write_text(CLAUDE.format(python=sys.executable, reply=reply), encoding="utf-8")
    claude.chmod(claude.stat().st_mode | stat.S_IRWXU)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")


def write(repo: Path, path: Path, text: str) -> None:
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(text, encoding="utf-8")


def initialised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, git: bool = False) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    if git:
        write(repo, MAIN, "X = 1\n")
        subprocess.run(["git", "add", str(MAIN)], cwd=repo, check=True)
    assert invoke("init", str(repo)).exit_code == 0
    monkeypatch.chdir(repo)
    return repo


def with_approved_plan(repo: Path) -> None:
    write(repo, REQS, REQS_TEXT)
    write(repo, ADR_1, ADR_TEXT)
    assert invoke("approve", "spec").exit_code == 0
    assert invoke("plan").exit_code == 0
    assert invoke("approve", "plan").exit_code == 0


def event_count(repo: Path) -> int:
    conn = sqlite3.connect(repo / DB)
    try:
        return conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    finally:
        conn.close()


def result(task_id: str, state: TaskState, warning: str | None = None) -> TaskRunResult:
    return TaskRunResult(task_id=task_id, state=state, last_event_id=uuid4(), warning=warning)


class StandIn:
    def __init__(self, report: RunReport) -> None:
        self.report = report
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> RunReport:
        self.calls.append(kwargs)
        return self.report


def stubbed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, report: RunReport | None = None
) -> StandIn:
    initialised(tmp_path, monkeypatch)
    stand_in = StandIn(report or RunReport())
    monkeypatch.setattr("openfactory.cli.run_plan", stand_in)
    return stand_in


# ---- AC1: refusals before the repair, real wiring ----


def test_ac1_no_approved_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = initialised(tmp_path, monkeypatch)
    before = event_count(repo)

    r = invoke("run")

    assert r.stderr.splitlines() == ["no approved plan"]
    assert r.stdout == ""
    assert r.exit_code == 1
    assert event_count(repo) == before


def test_ac1_no_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = initialised(tmp_path, monkeypatch, git=True)
    with_approved_plan(repo)
    before = event_count(repo)

    r = invoke("run")

    assert r.stderr.splitlines() == ["repository has no commit"]
    assert r.stdout == ""
    assert r.exit_code == 1
    assert event_count(repo) == before


def test_ac1_git_failed_gives_the_first_line_of_the_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = initialised(tmp_path, monkeypatch, git=True)
    with_approved_plan(repo)
    shutil.rmtree(repo / ".git")
    before = event_count(repo)

    r = invoke("run")

    lines = r.stderr.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("git failed: ")
    assert len(lines[0]) > len("git failed: ")
    assert r.stdout == ""
    assert r.exit_code == 1
    assert event_count(repo) == before


# ---- AC2: task lines and exit codes ----


def test_ac2_lines_in_report_order_and_exit_1_when_any_task_did_not_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = RunReport(
        tasks=[
            result("AUTH-001", TaskState.passed),
            result("AUTH-003", TaskState.escalated),
            result("AUTH-002", TaskState.failed),
        ]
    )
    stubbed(tmp_path, monkeypatch, report)

    r = invoke("run")

    assert r.stdout.splitlines() == ["AUTH-001  passed", "AUTH-003  escalated", "AUTH-002  failed"]
    assert r.exit_code == 1


def test_ac2_all_passed_exits_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = RunReport(
        tasks=[result("AUTH-001", TaskState.passed), result("AUTH-002", TaskState.passed)]
    )
    stubbed(tmp_path, monkeypatch, report)

    r = invoke("run")

    assert r.stdout.splitlines() == ["AUTH-001  passed", "AUTH-002  passed"]
    assert r.stderr == ""
    assert r.exit_code == 0


def test_ac2_no_task_taken_prints_nothing_and_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stubbed(tmp_path, monkeypatch)

    r = invoke("run")

    assert r.stdout == ""
    assert r.exit_code == 0


# ---- AC3: --task and its refusals ----


@pytest.mark.parametrize(("args", "expected"), [(["run"], None), (["run", "--task", "X"], "X")])
def test_ac3_task_option_reaches_run_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, args: list[str], expected: str | None
) -> None:
    stand_in = stubbed(tmp_path, monkeypatch)

    invoke(*args)

    assert len(stand_in.calls) == 1
    assert stand_in.calls[0]["task_id"] == expected


@pytest.mark.parametrize(
    ("refusal", "detail", "line"),
    [
        (RunRefusal.unknown_task, "X", "unknown task X"),
        (RunRefusal.not_ready, "failed", "X is failed, not ready"),
    ],
)
def test_ac3_task_refusals_follow_the_repair_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, refusal: RunRefusal, detail: str, line: str
) -> None:
    report = RunReport(refusal=refusal, detail=detail, warnings=["repair warning"])
    stubbed(tmp_path, monkeypatch, report)

    r = invoke("run", "--task", "X")

    assert r.stderr.splitlines() == ["repair warning", line]
    assert r.stdout == ""
    assert r.exit_code == 1


# ---- AC4: warnings ----

CHILD = textwrap.dedent(
    """
    from uuid import uuid4
    import openfactory.cli as cli
    from openfactory.app.run import RunReport, TaskRunResult
    from openfactory.domain.states import TaskState

    def task(task_id, warning=None):
        return TaskRunResult(
            task_id=task_id, state=TaskState.passed, last_event_id=uuid4(), warning=warning
        )

    cli.run_plan = lambda **kwargs: RunReport(
        warnings=["repair warning"],
        tasks=[task("AUTH-001", "worktree of AUTH-001 not removed: boom"), task("AUTH-002")],
    )
    cli.app()
    """
)


def test_ac4_warnings_are_ordered_around_the_task_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = initialised(tmp_path, monkeypatch)

    # A child process with both streams on one pipe: `CliRunner` cannot show their order.
    child = subprocess.run(
        [sys.executable, "-c", CHILD, "run"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )

    assert child.stdout.splitlines() == [
        "repair warning",
        "AUTH-001  passed",
        "worktree of AUTH-001 not removed: boom",
        "AUTH-002  passed",
    ]
    assert child.returncode == 0


def test_ac4_warnings_go_to_stderr_and_do_not_change_the_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = RunReport(
        warnings=["repair warning"],
        tasks=[result("AUTH-001", TaskState.passed, "worktree of AUTH-001 not removed: boom")],
    )
    stubbed(tmp_path, monkeypatch, report)

    r = invoke("run")

    assert r.stdout.splitlines() == ["AUTH-001  passed"]
    assert r.stderr.splitlines() == ["repair warning", "worktree of AUTH-001 not removed: boom"]
    assert r.exit_code == 0


# ---- AC5: init check and layering ----


def test_ac5_run_needs_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)

    r = invoke("run")

    assert r.stderr.splitlines() == ["run `openfactory init` first"]
    assert r.stdout == ""
    assert r.exit_code == 1


def test_ac5_cli_is_the_only_module_importing_adapters_and_app() -> None:
    both: list[str] = []
    for path in SRC.rglob("*.py"):
        modules: list[str] = []
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
        if any(m.startswith("openfactory.adapters") for m in modules) and any(
            m.startswith("openfactory.app") for m in modules
        ):
            both.append(path.name)
    assert both == ["cli.py"]


# ---- TASK-067: `<tool> not found` ----


def test_task067_tool_not_found_line_from_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = RunReport(refusal=RunRefusal.tool_not_found, detail="gitleaks")
    stubbed(tmp_path, monkeypatch, report)

    r = invoke("run")

    assert r.stderr.splitlines() == ["gitleaks not found"]
    assert r.stdout == ""
    assert r.exit_code == 1


@pytest.mark.parametrize(("linked", "missing"), [((), "uv"), (("uv",), "gitleaks")])
def test_task067_real_wiring_refuses_with_the_first_missing_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, linked: tuple[str, ...], missing: str
) -> None:
    repo = initialised(tmp_path, monkeypatch, git=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x"],
        cwd=repo,
        check=True,
    )
    with_approved_plan(repo)
    only = tmp_path / "only-bin"
    only.mkdir()
    for name in ("git", *linked):
        found = shutil.which(name)
        assert found
        (only / name).symlink_to(found)
    monkeypatch.setenv("PATH", str(only))
    before = event_count(repo)

    r = invoke("run")

    assert r.stderr.splitlines() == [f"{missing} not found"]
    assert r.stdout == ""
    assert r.exit_code == 1
    assert event_count(repo) == before


def test_task067_run_passes_process_gates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from openfactory.adapters.process_gates import ProcessGates

    stand_in = stubbed(tmp_path, monkeypatch)

    invoke("run")

    assert isinstance(stand_in.calls[0]["gates"], ProcessGates)


def test_task070_run_passes_a_claude_code_llm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from openfactory.adapters.claude_code_llm import ClaudeCodeLLM

    stand_in = stubbed(tmp_path, monkeypatch)

    invoke("run")

    assert isinstance(stand_in.calls[0]["llm"], ClaudeCodeLLM)
