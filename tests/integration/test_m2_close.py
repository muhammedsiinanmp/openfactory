"""TASK-038 AC1..AC6: M2 close (see docs/tasks/TASK-038-m2-close-integration-test.md)."""

import hashlib
import json
import os
import sqlite3
import stat
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from openfactory.adapters.sqlite_recorder import SqliteEventRecorder

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "claude_envelope.json"
runner = CliRunner()

DB = Path(".openfactory/openfactory.db")
REQS = Path("specs/requirements.yaml")
ADR_1 = Path("specs/adrs/ADR-001-auth-method.md")
MAIN = Path("app/main.py")
MAIN_TEXT = "SESSION_SECRET_MARKER = 1\n"
WARNING = "spec files differ from approved sv_01"

TABLES = ("spec_versions", "requirements", "adrs", "plans", "tasks", "task_deps", "agent_runs")
ORDER = {
    "spec_versions": "id",
    "requirements": "spec_version, id",
    "adrs": "spec_version, id",
    "plans": "id",
    "tasks": "id",
    "task_deps": "task_id, depends_on",
    "agent_runs": "id",
}

REQ_1 = """\
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
REQ_2 = """\
  - id: REQ-AUTH-002
    title: Logout
    statement: Users can end their session.
    priority: should
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-002-1
        text: Logout invalidates the JWT.
"""
HEADER = "components: [auth]\nrequirements:\n"
STATE_1 = HEADER + REQ_1 + REQ_2
STATE_2 = HEADER + REQ_1
ADR_1_TEXT = "---\nid: ADR-001\nstatus: accepted\n---\nUsers are identified by membership number.\n"

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
sys.stdout.write(replies[min(n, len(replies)) - 1])
"""

# Records what the command has written to standard error when `git` starts.
GIT = """\
#!{python}
import sys
from pathlib import Path

Path({record!r}).write_bytes(Path({stderr!r}).read_bytes())
sys.stdout.write("app/main.py\\0")
"""

BOTH = ("AC-AUTH-001-1", "AC-AUTH-001-2")


def task(
    task_id: str,
    objective: str,
    requirement: str,
    criteria: Sequence[str],
    depends_on: Sequence[str] = (),
    forbidden_paths: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "objective": objective,
        "requirements": [requirement],
        "acceptance_criteria": list(criteria),
        "depends_on": list(depends_on),
        "components": ["auth"],
        "role": "implementer",
        "allowed_paths": ["app/"],
        "forbidden_paths": list(forbidden_paths),
    }


LOGOUT = ("REQ-AUTH-002", ["AC-AUTH-002-1"])
# Rejected: one unknown dependency, nothing else.
R1 = {
    "tasks": [
        task("AUTH-001", "Implement login", "REQ-AUTH-001", BOTH, depends_on=["ZZZ-009"]),
        task("AUTH-002", "Implement logout", *LOGOUT),
    ]
}
R2 = {
    "tasks": [
        task("AUTH-003", "Reject bad logins", "REQ-AUTH-001", ["AC-AUTH-001-2"]),
        task("AUTH-002", "Implement logout", *LOGOUT, depends_on=["AUTH-001"]),
        task("AUTH-001", "Implement login", "REQ-AUTH-001", BOTH),
    ]
}
R3 = {
    "tasks": [
        task("DB-001", "Add the session table", *LOGOUT),
        task("AUTH-002", "Add the logout endpoint", *LOGOUT, depends_on=["AUTH-001"]),
        task(
            "AUTH-001",
            "Add the login endpoint",
            "REQ-AUTH-001",
            BOTH,
            forbidden_paths=["secrets/**"],
        ),
    ]
}


def envelope() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class Claude:
    def __init__(self, record: Path) -> None:
        self.record = record

    def replies(self, *structured: dict[str, Any]) -> None:
        replies = [json.dumps({**envelope(), "structured_output": s}) for s in structured]
        (self.record / "replies.json").write_text(json.dumps(replies), encoding="utf-8")

    def starts(self) -> int:
        path = self.record / "starts"
        return len(path.read_text()) if path.exists() else 0

    def prompt_bytes(self, n: int) -> bytes:
        return (self.record / f"prompt-{n}.txt").read_bytes()

    def prompt(self, n: int) -> str:
        return self.prompt_bytes(n).decode("utf-8")


def script(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)


@pytest.fixture(autouse=True)
def claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Claude:
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    record = tmp_path / "claude-record"
    record.mkdir()
    bin_dir = tmp_path / "claude-bin"
    bin_dir.mkdir()
    script(bin_dir / "claude", CLAUDE.format(python=sys.executable, record=str(record)))
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    return Claude(record)


def run(*args: str):
    from openfactory.cli import app

    return runner.invoke(app, list(args))


def write(repo: Path, path: Path, text: str) -> None:
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(text, encoding="utf-8")


def make_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Step 0: a git repo with one added file, initialised, with `sv_01` approved."""
    repo = tmp_path / "repo"
    write(repo, MAIN, MAIN_TEXT)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", str(MAIN)], cwd=repo, check=True)
    assert run("init", str(repo)).exit_code == 0
    write(repo, REQS, STATE_1)
    write(repo, ADR_1, ADR_1_TEXT)
    monkeypatch.chdir(repo)
    assert run("approve", "spec").exit_code == 0
    return repo


def flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> tuple[Path, dict[int, Any], dict[int, int]]:
    """Run steps 0 to 3 of the record's flow.

    Returns the repo, each step's result, and the stand-in's start count after each step.
    """
    repo = make_repo(tmp_path, monkeypatch)
    steps: dict[int, Any] = {}
    starts: dict[int, int] = {}
    claude.replies(R1, R2, R3)
    steps[1] = run("plan")
    starts[1] = claude.starts()
    steps[2] = run("plan")
    starts[2] = claude.starts()
    steps[3] = run("approve", "plan")
    starts[3] = claude.starts()
    return repo, steps, starts


def query(repo: Path, sql: str) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(repo / DB)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def event_rows(repo: Path) -> list[tuple[Any, ...]]:
    return query(repo, "SELECT * FROM events ORDER BY seq")


def snapshot(repo: Path) -> dict[str, list[tuple[Any, ...]]]:
    """Every row of the seven projections, in primary-key order."""
    return {t: query(repo, f"SELECT * FROM {t} ORDER BY {ORDER[t]}") for t in TABLES}


def state_rows(repo: Path) -> list[tuple[Any, ...]]:
    return query(repo, "SELECT id, last_seq FROM projection_state")


def max_seq(repo: Path) -> int:
    return query(repo, "SELECT MAX(seq) FROM events")[0][0]


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


def flow_events(repo: Path) -> list[dict[str, Any]]:
    """The events of steps 1 to 3, as `events` prints them."""
    result = run("events")
    assert result.exit_code == 0
    objs = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(objs) == 14
    assert [o["seq"] for o in objs] == sorted(o["seq"] for o in objs)
    return objs[3:]


def test_ac1_plan_retries_plans_again_and_the_plan_is_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> None:
    repo, steps, starts = flow(tmp_path, monkeypatch, claude)

    assert steps[1].stdout.splitlines() == [
        "AUTH-001  Implement login",
        "AUTH-002  Implement logout",
        "AUTH-003  Reject bad logins",
        "created plan_01",
    ]
    assert steps[1].stderr == ""
    assert steps[1].exit_code == 0
    assert starts[1] == 2

    rejection = flow_events(repo)[1]["payload"]["error"]
    assert rejection
    assert rejection in claude.prompt(2)
    assert rejection not in claude.prompt(1)
    for n in (1, 2):
        assert str(MAIN) in claude.prompt(n)
        assert "SESSION_SECRET_MARKER" not in claude.prompt(n)

    assert steps[2].stdout.splitlines() == [
        "AUTH-001  Add the login endpoint",
        "AUTH-002  Add the logout endpoint",
        "DB-001  Add the session table",
        "created plan_02",
    ]
    assert steps[2].stderr == ""
    assert steps[2].exit_code == 0
    assert starts[2] == 3

    assert steps[3].stdout.splitlines() == ["AUTH-001  ready", "DB-001  ready", "approved plan_02"]
    assert steps[3].stderr == ""
    assert steps[3].exit_code == 0
    assert starts[3] == 3


def test_ac2_events_prints_the_log_the_commands_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> None:
    repo, _, _ = flow(tmp_path, monkeypatch, claude)

    objs = flow_events(repo)

    run_pair = ("AgentRunStarted", "AgentRunFinished")
    assert [o["type"] for o in objs] == [
        *run_pair,
        *run_pair,
        "PlanCreated",
        *run_pair,
        "PlanCreated",
        *("PlanApproved", "TaskStateChanged", "TaskStateChanged"),
    ]
    assert [o["stream"] for o in objs] == [
        *["run:run_0001"] * 2,
        *["run:run_0002"] * 2,
        "plan:plan_01",
        *["run:run_0003"] * 2,
        "plan:plan_02",
        "plan:plan_02",
        "task:AUTH-001",
        "task:DB-001",
    ]
    assert [o["actor"] for o in objs] == [
        "human" if o["type"] == "PlanApproved" else "orchestrator" for o in objs
    ]
    approved = objs[8]["event_id"]
    for i, o in enumerate(objs):
        if i in (0, 5, 8):
            expected = None
        elif i > 8:
            expected = approved
        else:
            expected = objs[i - 1]["event_id"]
        assert o["causation_id"] == expected

    finished = [o["payload"] for o in objs if o["type"] == "AgentRunFinished"]
    assert [p["exit"] for p in finished] == ["ok", "ok", "ok"]
    rejected = finished[0]["error"].splitlines()
    assert len(rejected) == 1
    assert rejected[0].startswith("unknown-dependency  AUTH-001  ")
    assert "ZZZ-009" in rejected[0]
    assert [p["error"] for p in finished[1:]] == [None, None]

    plan_01, plan_02 = (o["payload"] for o in objs if o["type"] == "PlanCreated")
    assert (plan_01["spec_version"], plan_01["run_id"]) == ("sv_01", "run_0002")
    assert [t["task_id"] for t in plan_01["tasks"]] == ["AUTH-001", "AUTH-002", "AUTH-003"]
    assert plan_02["run_id"] == "run_0003"
    assert [t["task_id"] for t in plan_02["tasks"]] == ["AUTH-001", "AUTH-002", "DB-001"]
    assert len(plan_01["policy_hash"]) == 64
    int(plan_01["policy_hash"], 16)
    assert plan_02["policy_hash"] == plan_01["policy_hash"]

    for o in objs[9:]:
        assert (o["payload"]["from"], o["payload"]["to"]) == ("pending", "ready")
        assert o["payload"]["reason"] is None


def test_ac3_projections_hold_the_approved_plan_its_tasks_and_the_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> None:
    repo, _, _ = flow(tmp_path, monkeypatch, claude)

    assert query(repo, "SELECT id, spec_version, status FROM plans ORDER BY id") == [
        ("plan_01", "sv_01", "superseded"),
        ("plan_02", "sv_01", "approved"),
    ]
    assert query(repo, "SELECT id, plan_id, state, attempt FROM tasks ORDER BY id") == [
        ("AUTH-001", "plan_02", "ready", 0),
        ("AUTH-002", "plan_02", "pending", 0),
        ("DB-001", "plan_02", "ready", 0),
    ]
    assert query(repo, "SELECT task_id, depends_on FROM task_deps") == [("AUTH-002", "AUTH-001")]

    contract = json.loads(query(repo, "SELECT contract FROM tasks WHERE id = 'AUTH-001'")[0][0])
    assert contract["required_gates"] == ["path_check", "ruff", "pytest", "gitleaks", "review"]
    assert contract["limits"] == {"max_runtime_s": 1200, "max_attempts": 2, "max_cost_usd": 1.5}
    assert contract["forbidden_paths"] == [
        "specs/**",
        ".openfactory/**",
        ".env",
        ".env.*",
        "secrets/**",
    ]

    reported = envelope()
    usage = reported["usage"]
    (model,) = reported["modelUsage"]
    tokens_in = (
        usage["input_tokens"]
        + usage["cache_creation_input_tokens"]
        + usage["cache_read_input_tokens"]
    )
    runs = query(
        repo,
        "SELECT id, task_id, role, runtime, exit, model, tokens_in, tokens_out, cost_usd,"
        " duration_s, context_hash, started_at, ended_at FROM agent_runs ORDER BY id",
    )
    assert [r[0] for r in runs] == ["run_0001", "run_0002", "run_0003"]
    for n, row in enumerate(runs, start=1):
        assert row[1:10] == (
            None,
            "planner",
            "claude-code",
            "ok",
            model,
            tokens_in,
            usage["output_tokens"],
            reported["total_cost_usd"],
            reported["duration_ms"] / 1000,
        )
        assert row[10] == hashlib.sha256(claude.prompt_bytes(n)).hexdigest()
        assert row[11] is not None
        assert row[12] is not None
    assert state_rows(repo) == [(1, max_seq(repo))]


def test_ac4_rebuild_from_the_log_gives_identical_projections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> None:
    repo, _, _ = flow(tmp_path, monkeypatch, claude)
    before = snapshot(repo)
    assert all(before[t] for t in TABLES)
    events_before = event_rows(repo)

    empty_projections(repo)
    assert snapshot(repo) == {t: [] for t in TABLES}
    assert snapshot(repo) != before

    rebuild(repo)

    after = snapshot(repo)
    for table in TABLES:
        assert after[table] == before[table]
    assert state_rows(repo) == [(1, max_seq(repo))]
    assert event_rows(repo) == events_before


def test_ac5_validate_and_plan_run_on_the_rebuilt_projections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> None:
    repo, _, starts = flow(tmp_path, monkeypatch, claude)
    empty_projections(repo)
    rebuild(repo)
    write(repo, REQS, STATE_2)
    seq_before = max_seq(repo)

    validated = run("validate")

    out = validated.stdout.splitlines()
    assert validated.exit_code == 1
    assert len(out) == 2
    assert out[0].startswith("deleted-requirement  REQ-AUTH-002  ")
    assert out[0].endswith("AUTH-002, DB-001")
    assert out[1] == "1 violations, 0 policy problems"
    assert query(
        repo, f"SELECT type, stream FROM events WHERE seq > {seq_before} ORDER BY seq"
    ) == [
        ("SpecImported", "spec:sv_02"),
        ("SpecValidated", "spec:sv_02"),
    ]
    seq_validated = max_seq(repo)

    refused = run("plan")

    assert refused.stdout == ""
    assert refused.stderr.splitlines() == ["plan_02 is already approved; use replan"]
    assert refused.exit_code == 1
    assert claude.starts() == starts[3]
    assert max_seq(repo) == seq_validated


def test_ac6_warning_is_written_before_git_ls_files_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: Claude
) -> None:
    repo = make_repo(tmp_path, monkeypatch)
    write(repo, REQS, STATE_1.replace("log in.", "sign in."))
    claude.replies(R2)
    record, stderr_file = tmp_path / "stderr-at-git-start", tmp_path / "stderr"
    bin_dir = tmp_path / "git-bin"
    bin_dir.mkdir()
    git = GIT.format(python=sys.executable, record=str(record), stderr=str(stderr_file))
    script(bin_dir / "git", git)

    # A child process: under `CliRunner` standard error is held in memory, out of git's reach.
    with stderr_file.open("w", encoding="utf-8") as err:
        child = subprocess.run(
            [sys.executable, "-c", "from openfactory.cli import app; app()", "plan"],
            cwd=repo,
            # The stand-in `git` is on the child's `PATH` only.
            env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
            stdout=subprocess.PIPE,
            stderr=err,
            text=True,
            check=False,
        )

    assert record.read_text(encoding="utf-8").splitlines() == [WARNING]
    assert child.returncode == 0
    assert child.stdout.splitlines()[-1] == "created plan_01"
    assert stderr_file.read_text(encoding="utf-8").splitlines() == [WARNING]
