"""TASK-057 AC1..AC6: M3 close (see docs/tasks/TASK-057-m3-close-integration-test.md)."""

import json
import os
import sqlite3
import stat
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from openfactory.adapters.sqlite_recorder import SqliteEventRecorder

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
runner = CliRunner()

DB = Path(".openfactory/openfactory.db")
REQS = Path("specs/requirements.yaml")
ADR_1 = Path("specs/adrs/ADR-001-auth-method.md")
MAIN = Path("app/main.py")

TABLES = (
    "spec_versions",
    "requirements",
    "adrs",
    "plans",
    "tasks",
    "task_deps",
    "agent_runs",
    "gate_results",
    "commits",
)
ORDER = {
    "spec_versions": "id",
    "requirements": "spec_version, id",
    "adrs": "spec_version, id",
    "plans": "id",
    "tasks": "id",
    "task_deps": "task_id, depends_on",
    "agent_runs": "id",
    "gate_results": "run_id, gate",
    "commits": "sha",
}

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
      - id: AC-AUTH-001-2
        text: Invalid login returns 401.
"""
ADR_TEXT = "---\nid: ADR-001\nstatus: accepted\n---\nUsers are identified by membership number.\n"

OBJECTIVES = {
    "AUTH-001": "Add the login endpoint",
    "AUTH-002": "Add the one-time code",
    "AUTH-003": "Add the profile page",
}
CRITERIA = {"AUTH-001": "AC-AUTH-001-1", "AUTH-002": "AC-AUTH-001-2", "AUTH-003": "AC-AUTH-001-1"}
SUMMARIES = {
    "AUTH-001": "Added the login endpoint.",
    "AUTH-002": "Added the one-time code.",
    "AUTH-003": "Added the profile page.",
}
# What the stand-in implementer writes in each task's worktree.
FILES = {
    "AUTH-001": ["app/login.py"],
    "AUTH-002": ["app/otp.py"],
    "AUTH-003": ["app/x.py", "notes/todo.md"],
}
PLAN = {
    "tasks": [
        {
            "task_id": task_id,
            "objective": OBJECTIVES[task_id],
            "requirements": ["REQ-AUTH-001"],
            "acceptance_criteria": [CRITERIA[task_id]],
            "depends_on": ["AUTH-001"] if task_id == "AUTH-002" else [],
            "components": ["auth"],
            "role": "implementer",
            "allowed_paths": ["app/"],
            "forbidden_paths": [],
        }
        for task_id in OBJECTIVES
    ]
}

# The body of the stand-in `claude`; `LOG`, `PLANNER` and `AGENTS` are set above it.
CLAUDE_BODY = """
import hashlib, json, subprocess, sys
from pathlib import Path

data = sys.stdin.buffer.read()
cwd = Path.cwd()
if "--json-schema" in sys.argv:
    role, out = "planner", PLANNER
else:
    role = "implementer"
    task = cwd.name
    for name in FILES[task]:
        (cwd / name).parent.mkdir(parents=True, exist_ok=True)
        (cwd / name).write_text(f"# {task}\\n", encoding="utf-8")
    if task == "AUTH-002":
        subprocess.run(["git", "add", "-A"], check=True)
        subprocess.run(["git", "commit", "-q", "-m", "agent commit"], check=True)
    out = AGENTS[task]
entry = {"role": role, "cwd": str(cwd), "stdin_sha256": hashlib.sha256(data).hexdigest()}
with open(LOG, "a", encoding="utf-8") as f:
    f.write(json.dumps(entry) + "\\n")
sys.stdout.buffer.write(out.encode("utf-8"))
"""

# Runs `run` and kills its own process just before `AUTH-001` `gating` to `passed`.
CHILD = textwrap.dedent(
    """
    import os, signal
    from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
    from openfactory.cli import app

    original = SqliteEventRecorder.record

    def record(self, event):
        p = event.payload
        if p.get("task_id") == "AUTH-001" and ({kill}):
            os.kill(os.getpid(), signal.SIGKILL)
        return original(self, event)

    SqliteEventRecorder.record = record
    app()
    """
)
KILL_BEFORE_PASSED = 'event.type.value == "TaskStateChanged" and p.get("to") == "passed"'


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def agent_output(task_id: str) -> str:
    return json.dumps({**fixture("claude_agent_envelope.json"), "result": SUMMARIES[task_id]})


class Claude:
    def __init__(self, log: Path) -> None:
        self.log = log

    def starts(self, role: str = "implementer") -> list[dict[str, Any]]:
        if not self.log.exists():
            return []
        entries = [json.loads(line) for line in self.log.read_text().splitlines()]
        return [e for e in entries if e["role"] == role]


@pytest.fixture(autouse=True)
def claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Claude:
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    for name in list(os.environ):
        if name.startswith(("GIT_AUTHOR_", "GIT_COMMITTER_")):
            monkeypatch.delenv(name)
    log = tmp_path / "claude-starts.jsonl"
    planner = json.dumps({**fixture("claude_envelope.json"), "structured_output": PLAN})
    agents = {task_id: agent_output(task_id) for task_id in OBJECTIVES}
    head = f"#!{sys.executable}\nLOG = {str(log)!r}\nPLANNER = {planner!r}\n"
    head += f"AGENTS = {agents!r}\nFILES = {FILES!r}\n"
    bin_dir = tmp_path / "claude-bin"
    bin_dir.mkdir()
    path = bin_dir / "claude"
    path.write_text(head + CLAUDE_BODY, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IRWXU)
    gitleaks = bin_dir / "gitleaks"
    gitleaks.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    gitleaks.chmod(gitleaks.stat().st_mode | stat.S_IRWXU)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    return Claude(log)


def invoke(*args: str):
    from openfactory.cli import app

    return runner.invoke(app, list(args))


def write(repo: Path, path: Path, text: str) -> None:
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(text, encoding="utf-8")


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return done.stdout


def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repo with one commit, initialised, with `sv_01` and `plan_01` approved."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test Human")
    git(repo, "config", "user.email", "human@example.com")
    git(repo, "config", "commit.gpgsign", "false")
    write(repo, MAIN, "X = 1\n")
    git(repo, "add", str(MAIN))
    git(repo, "commit", "-q", "-m", "initial")
    assert invoke("init", str(repo)).exit_code == 0
    write(repo, REQS, REQS_TEXT)
    write(repo, ADR_1, ADR_TEXT)
    monkeypatch.chdir(repo)
    assert invoke("approve", "spec").exit_code == 0
    assert invoke("plan").exit_code == 0
    assert invoke("approve", "plan").exit_code == 0
    return repo


def killed_run(repo: Path, kill: str = KILL_BEFORE_PASSED) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", CHILD.format(kill=kill), "run"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def query(repo: Path, sql: str) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(repo / DB)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def max_seq(repo: Path) -> int:
    return query(repo, "SELECT MAX(seq) FROM events")[0][0]


def events_after(repo: Path, seq: int) -> list[dict[str, Any]]:
    rows = query(
        repo,
        "SELECT event_id, stream, type, payload, actor, causation_id FROM events"
        f" WHERE seq > {seq} ORDER BY seq",
    )
    keys: tuple[str, ...] = ("event_id", "stream", "type", "payload", "actor", "causation_id")
    events: list[dict[str, Any]] = [dict(zip(keys, row, strict=True)) for row in rows]
    for event in events:
        event["payload"] = json.loads(event["payload"])
    return events


def snapshot(repo: Path) -> dict[str, list[tuple[Any, ...]]]:
    """Every row of the nine projections, in primary-key order."""
    return {t: query(repo, f"SELECT * FROM {t} ORDER BY {ORDER[t]}") for t in TABLES}


def empty_projections(repo: Path) -> None:
    conn = sqlite3.connect(repo / DB)
    try:
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    finally:
        conn.close()


def rebuild(repo: Path) -> None:
    recorder = SqliteEventRecorder(repo / DB)
    try:
        recorder.rebuild()
    finally:
        recorder.close()


def message(repo: Path, sha: str) -> str:
    """The commit's message exactly as stored."""
    return git(repo, "cat-file", "commit", sha).split("\n\n", 1)[1]


def expected_message(task_id: str, run_id: str) -> str:
    return (
        f"{task_id}: {OBJECTIVES[task_id]}\n\n{SUMMARIES[task_id]}\n\n"
        + trailers(task_id, run_id)
        + "\n"
    )


def trailers(task_id: str, run_id: str) -> str:
    return (
        f"Task: {task_id}\nRequirements: REQ-AUTH-001\n"
        f"Acceptance-Criteria: {CRITERIA[task_id]}\nAgent-Run: {run_id}\nSpec-Version: sv_01"
    )


def tip(repo: Path, task_id: str) -> str:
    return git(repo, "rev-parse", f"openfactory/{task_id}").strip()


def task_commits(repo: Path, task_id: str) -> list[str]:
    """Commits on any `openfactory/*` branch whose `Task` trailer is `task_id`."""
    out = git(repo, "log", "--branches=openfactory/*", "--format=%H %(trailers:key=Task,valueonly)")
    return [line.split()[0] for line in out.splitlines() if line.split()[1:] == [task_id]]


def worktree(repo: Path, task_id: str) -> Path:
    return repo / ".openfactory" / "worktrees" / task_id


def assert_rebuild_identical(repo: Path) -> None:
    before = snapshot(repo)
    assert all(before[t] for t in TABLES)
    events_before = query(repo, "SELECT * FROM events ORDER BY seq")

    empty_projections(repo)
    assert snapshot(repo) == {t: [] for t in TABLES}
    assert snapshot(repo) != before

    rebuild(repo)

    after = snapshot(repo)
    for table in TABLES:
        assert after[table] == before[table]
    assert query(repo, "SELECT id, last_seq FROM projection_state") == [(1, max_seq(repo))]
    assert query(repo, "SELECT * FROM events ORDER BY seq") == events_before


# ---- Flow A: one uninterrupted `run` ----


def flow_a(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Any, int, str]:
    """Returns the repo, the `run` result, the last `seq` before it and the initial commit."""
    repo = setup(tmp_path, monkeypatch)
    seq = max_seq(repo)
    initial = git(repo, "rev-parse", "HEAD").strip()
    return repo, invoke("run"), seq, initial


def test_ac1_run_takes_the_tasks_in_order_through_the_stand_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> None:
    repo, result, seq, _ = flow_a(tmp_path, monkeypatch)

    assert result.stdout.splitlines() == [
        "AUTH-001  passed",
        "AUTH-002  passed",
        "AUTH-003  escalated",
    ]
    assert result.stderr == ""
    assert result.exit_code == 1

    starts = claude.starts()
    order = ["AUTH-001", "AUTH-002", "AUTH-003"]
    assert [Path(s["cwd"]) for s in starts] == [worktree(repo, t).resolve() for t in order]
    started = [e for e in events_after(repo, seq) if e["type"] == "AgentRunStarted"]
    assert [e["payload"]["task_id"] for e in started] == order
    assert [s["stdin_sha256"] for s in starts] == [e["payload"]["context_hash"] for e in started]


def test_ac2_branches_and_commits_on_real_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = setup(tmp_path, monkeypatch)
    initial = git(repo, "rev-parse", "HEAD").strip()
    branch = git(repo, "symbolic-ref", "HEAD").strip()
    invoke("run")

    first, second = tip(repo, "AUTH-001"), tip(repo, "AUTH-002")
    assert git(repo, "rev-parse", f"{first}^").strip() == initial
    assert git(repo, "rev-parse", f"{second}^").strip() == first
    assert "agent commit" not in git(repo, "log", "--format=%s", "openfactory/AUTH-002")
    assert tip(repo, "AUTH-003") == second

    for sha, task_id, run_id in ((first, "AUTH-001", "run_0002"), (second, "AUTH-002", "run_0003")):
        assert message(repo, sha) == expected_message(task_id, run_id)
        only = git(repo, "log", "-1", "--format=%(trailers:only)", sha)
        assert [line for line in only.splitlines() if line] == trailers(task_id, run_id).split("\n")
        changed = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", sha)
        assert changed.splitlines() == FILES[task_id]

    assert not worktree(repo, "AUTH-001").exists()
    assert not worktree(repo, "AUTH-002").exists()
    assert git(repo, "rev-parse", "HEAD").strip() == initial
    assert git(repo, "symbolic-ref", "HEAD").strip() == branch
    assert not (repo / "app" / "login.py").exists()


def task_group(task_id: str, run_id: str, passed: bool) -> list[tuple[Any, ...]]:
    stream, run = f"task:{task_id}", f"run:{run_id}"
    events: list[tuple[Any, ...]] = [
        (stream, "TaskStateChanged", "ready", "running", None),
        (run, "AgentRunStarted"),
        (run, "AgentRunFinished"),
        (stream, "TaskStateChanged", "running", "gating", None),
        (stream, "GateEvaluated"),
    ]
    if passed:
        return [
            *events,
            (stream, "CommitRecorded"),
            (stream, "TaskStateChanged", "gating", "passed", None),
        ]
    return [
        *events,
        (stream, "TaskStateChanged", "gating", "failed", "path_check"),
        (stream, "TaskStateChanged", "failed", "escalated", "path violation"),
    ]


def shape(event: dict[str, Any]) -> tuple[Any, ...]:
    if event["type"] == "TaskStateChanged":
        p = event["payload"]
        return (event["stream"], event["type"], p["from"], p["to"], p["reason"])
    return (event["stream"], event["type"])


def test_ac3_events_projections_and_run_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _, seq, _ = flow_a(tmp_path, monkeypatch)

    events = events_after(repo, seq)
    assert len(events) == 22
    assert [shape(e) for e in events] == [
        *task_group("AUTH-001", "run_0002", passed=True),
        ("task:AUTH-002", "TaskStateChanged", "pending", "ready", None),
        *task_group("AUTH-002", "run_0003", passed=True),
        *task_group("AUTH-003", "run_0004", passed=False),
    ]
    assert {e["actor"] for e in events} == {"orchestrator"}
    for i, event in enumerate(events):
        expected = None if i in (0, 15) else events[i - 1]["event_id"]
        assert event["causation_id"] == expected

    assert query(repo, "SELECT id, state, attempt FROM tasks ORDER BY id") == [
        ("AUTH-001", "passed", 1),
        ("AUTH-002", "passed", 1),
        ("AUTH-003", "escalated", 1),
    ]
    assert query(
        repo,
        "SELECT id, task_id, role, exit FROM agent_runs WHERE role = 'implementer' ORDER BY id",
    ) == [
        ("run_0002", "AUTH-001", "implementer", "ok"),
        ("run_0003", "AUTH-002", "implementer", "ok"),
        ("run_0004", "AUTH-003", "implementer", "ok"),
    ]
    output_path = ".openfactory/runs/run_0004/path_check.txt"
    assert query(repo, "SELECT * FROM gate_results ORDER BY run_id, gate") == [
        ("run_0002", "path_check", 1, None),
        ("run_0003", "path_check", 1, None),
        ("run_0004", "path_check", 0, output_path),
    ]
    assert query(repo, "SELECT sha, task_id, run_id, branch FROM commits ORDER BY task_id") == [
        (tip(repo, "AUTH-001"), "AUTH-001", "run_0002", "openfactory/AUTH-001"),
        (tip(repo, "AUTH-002"), "AUTH-002", "run_0003", "openfactory/AUTH-002"),
    ]

    run_dir = repo / ".openfactory" / "runs" / "run_0004"
    assert (run_dir / "transcript.json").read_bytes() == agent_output("AUTH-003").encode()
    assert (repo / output_path).parent == run_dir
    assert (run_dir / "path_check.txt").read_text(encoding="utf-8").splitlines() == [
        "notes/todo.md"
    ]


def test_ac4_rebuild_after_flow_a_gives_identical_projections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _, _, _ = flow_a(tmp_path, monkeypatch)

    assert_rebuild_identical(repo)


# ---- Flow B: a killed `run`, then a restart ----


def test_ac5_killed_run_restarts_without_a_second_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> None:
    repo = setup(tmp_path, monkeypatch)

    child = killed_run(repo)

    assert child.returncode == -9
    last = events_after(repo, max_seq(repo) - 1)[0]
    assert (last["type"], last["payload"]["task_id"]) == ("CommitRecorded", "AUTH-001")
    assert query(repo, "SELECT state FROM tasks WHERE id = 'AUTH-001'") == [("gating",)]
    seq = max_seq(repo)

    result = invoke("run")

    assert result.stdout.splitlines() == ["AUTH-002  passed", "AUTH-003  escalated"]
    assert result.exit_code == 1
    events = events_after(repo, seq)
    assert [shape(e) for e in events[:2]] == [
        ("task:AUTH-001", "TaskStateChanged", "gating", "passed", None),
        ("task:AUTH-002", "TaskStateChanged", "pending", "ready", None),
    ]
    assert [e["causation_id"] for e in events[:2]] == [None, None]
    assert not worktree(repo, "AUTH-001").exists()
    assert [Path(s["cwd"]).name for s in claude.starts()] == ["AUTH-001", "AUTH-002", "AUTH-003"]
    assert task_commits(repo, "AUTH-001") == [
        git(repo, "rev-parse", f"{tip(repo, 'AUTH-002')}^").strip()
    ]
    assert query(repo, "SELECT task_id FROM commits ORDER BY task_id") == [
        ("AUTH-001",),
        ("AUTH-002",),
    ]

    assert_rebuild_identical(repo)


def test_ac6_task_refusal_after_a_repair_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> None:
    repo = setup(tmp_path, monkeypatch)
    assert killed_run(repo).returncode == -9
    git(repo, "worktree", "lock", ".openfactory/worktrees/AUTH-001")
    seq = max_seq(repo)

    refused = invoke("run", "--task", "ZZZ-999")

    lines = refused.stderr.splitlines()
    assert len(lines) == 2
    prefix = "worktree of AUTH-001 not removed: "
    assert lines[0].startswith(prefix)
    assert len(lines[0]) > len(prefix)
    assert lines[1] == "unknown task ZZZ-999"
    assert refused.stdout == ""
    assert refused.exit_code == 1
    assert [shape(e) for e in events_after(repo, seq)] == [
        ("task:AUTH-001", "TaskStateChanged", "gating", "passed", None),
        ("task:AUTH-002", "TaskStateChanged", "pending", "ready", None),
    ]
    assert len(claude.starts()) == 1

    git(repo, "worktree", "unlock", ".openfactory/worktrees/AUTH-001")
    result = invoke("run")

    assert result.stdout.splitlines() == ["AUTH-002  passed", "AUTH-003  escalated"]
    assert len(task_commits(repo, "AUTH-001")) == 1
