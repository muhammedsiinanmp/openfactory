"""TASK-106 AC1..AC6: M6 close (see docs/tasks/TASK-106-m6-close-integration-test.md).

One flow runs once per module: a first build of three tasks, then demo steps 6 to 9 on
the same repo: approve `sv_02`, `impact`, `replan`, `approve plan`, `run` and `status`,
then the rebuild of the projections. The stand-in `uv` execs the test interpreter's `ruff`
and `pytest`, so the gates and the collection use the real tools.
"""

import json
import os
import sqlite3
import stat
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from openfactory.adapters.sqlite_recorder import SqliteEventRecorder

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
runner = CliRunner()

DB = Path(".openfactory/openfactory.db")
REQS = Path("specs/requirements.yaml")
POLICIES = Path("specs/policies.yaml")
ADR_1 = Path("specs/adrs/ADR-001-auth-method.md")
MAIN = Path("app/main.py")
GITIGNORE = Path(".gitignore")
OLD = ("AUTH-001", "AUTH-002", "AUTH-003")

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
    "trace_links",
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
    "trace_links": "from_kind, from_id, to_kind, to_id, source",
}

REQ_AUTH_002 = """\
  - id: REQ-AUTH-002
    title: Config
    statement: The service reads its config.
    priority: must
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-002-1
        text: The config has a token lifetime.
      - id: AC-AUTH-002-2
        text: Tokens expire after the lifetime.
"""
REQS_V1 = (
    """\
components: [auth]
requirements:
  - id: REQ-AUTH-001
    title: Login
    statement: Users log in with a membership number.
    priority: must
    components: [auth]
    constrained_by: [ADR-001]
    acceptance_criteria:
      - id: AC-AUTH-001-1
        text: A valid membership number returns a JWT.
      - id: AC-AUTH-001-2
        text: An unknown membership number returns 401.
"""
    + REQ_AUTH_002
)
# Demo step 6: only REQ-AUTH-001 changes; one criterion edited, one removed, one added.
REQS_V2 = (
    """\
components: [auth]
requirements:
  - id: REQ-AUTH-001
    title: Login
    statement: Users log in with a one-time code.
    priority: must
    components: [auth]
    constrained_by: [ADR-001]
    acceptance_criteria:
      - id: AC-AUTH-001-1
        text: A valid one-time code returns a JWT.
      - id: AC-AUTH-001-3
        text: A one-time code is used once.
"""
    + REQ_AUTH_002
)
ADR_TEXT = "---\nid: ADR-001\nstatus: accepted\n---\nUsers are identified by membership number.\n"
POLICIES_TEXT = """\
protected_branches: [main, master]
forbidden_paths: []
max_attempts: 2
max_runtime_s: 1200
max_cost_usd: 1.50
"""


def contract(
    task_id: str, objective: str, req: str, criteria: list[str], deps: list[str]
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "objective": objective,
        "requirements": [req],
        "acceptance_criteria": criteria,
        "depends_on": deps,
        "components": ["auth"],
        "role": "implementer",
        "allowed_paths": ["app/", "tests/"],
        "forbidden_paths": [],
    }


PLAN = {
    "tasks": [
        contract("AUTH-001", "Add the config", "REQ-AUTH-002", ["AC-AUTH-002-1"], []),
        contract(
            "AUTH-002",
            "Add the login endpoint",
            "REQ-AUTH-001",
            ["AC-AUTH-001-1", "AC-AUTH-001-2"],
            ["AUTH-001"],
        ),
        contract("AUTH-003", "Add the token", "REQ-AUTH-002", ["AC-AUTH-002-2"], ["AUTH-002"]),
    ]
}
REPLAN = {
    "tasks": [
        contract(
            "AUTH-004",
            "Log in with a one-time code",
            "REQ-AUTH-001",
            ["AC-AUTH-001-1", "AC-AUTH-001-3"],
            ["AUTH-001"],
        ),
        contract(
            "AUTH-005", "Expire the one-time token", "REQ-AUTH-002", ["AC-AUTH-002-2"], ["AUTH-004"]
        ),
    ]
}
CLASSIFICATION = {
    "changes": [
        {
            "req_id": "REQ-AUTH-001",
            "kind": "replacement",
            "rationale": "Membership numbers give way to one-time codes.",
            "obsolete_criteria": ["AC-AUTH-001-1"],
            "new_work": ["OTP verify endpoint"],
        }
    ]
}


def tagged_test(name: str, req: str) -> str:
    return (
        f'import pytest\n\n\n@pytest.mark.req("{req}")\n'
        f"def test_{name}() -> None:\n    assert True\n"
    )


# What the stand-in implementer writes, per task.
WRITES: dict[str, dict[str, str]] = {
    "AUTH-001": {
        "app/config.py": "LIFETIME_S = 3600\n",
        "tests/test_config.py": tagged_test("config", "REQ-AUTH-002"),
    },
    "AUTH-002": {
        "app/login.py": "def login(number: str) -> str:\n    return number\n",
        "tests/test_login.py": tagged_test("login", "REQ-AUTH-001"),
    },
    "AUTH-003": {
        "app/token.py": "def lifetime() -> int:\n    return 3600\n",
        "tests/test_token.py": tagged_test("token", "REQ-AUTH-002"),
    },
    "AUTH-004": {
        "app/login.py": "def login(code: str) -> str:\n    return code.strip()\n",
        "tests/test_login.py": tagged_test("otp_login", "REQ-AUTH-001"),
    },
    "AUTH-005": {
        "app/token.py": "def lifetime() -> int:\n    return 300\n",
        "tests/test_token.py": tagged_test("otp_lifetime", "REQ-AUTH-002"),
    },
}

# The body of the stand-in `claude`; the replies and `WRITES` are set above it. The
# worktree dir name is the task id.
CLAUDE_BODY = """
import sys
from pathlib import Path

data = sys.stdin.buffer.read()
cwd = Path.cwd()
if b"## Staged diff" in data:
    out = REVIEWER
elif b"You are the change classifier" in data:
    out = CLASSIFIER
elif b"## Replan instructions" in data:
    out = REPLANNER
elif "--json-schema" in sys.argv:
    out = PLANNER
else:
    out = AGENT
    for name, text in WRITES[cwd.name].items():
        (cwd / name).parent.mkdir(parents=True, exist_ok=True)
        (cwd / name).write_text(text, encoding="utf-8")
sys.stdout.buffer.write(out.encode("utf-8"))
"""

# Drops `run` and execs the test interpreter's tool: `uv run ruff check` runs `-m ruff check`.
UV = f'#!/bin/sh\nshift\nexec "{sys.executable}" -m "$@"\n'
GITLEAKS = "#!/bin/sh\nexit 0\n"


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def structured(reply: dict[str, Any]) -> str:
    return json.dumps({**fixture("claude_envelope.json"), "structured_output": reply})


def write_script(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IRWXU)


def stand_ins(bin_dir: Path) -> None:
    agent = json.dumps({**fixture("claude_agent_envelope.json"), "result": "Done."})
    reviewer = structured({"verdict": "approve", "comments": "Meets the contract."})
    head = f"#!{sys.executable}\nPLANNER = {structured(PLAN)!r}\n"
    head += f"REPLANNER = {structured(REPLAN)!r}\nCLASSIFIER = {structured(CLASSIFICATION)!r}\n"
    head += f"REVIEWER = {reviewer!r}\nAGENT = {agent!r}\nWRITES = {WRITES!r}\n"
    write_script(bin_dir / "claude", head + CLAUDE_BODY)
    write_script(bin_dir / "uv", UV)
    write_script(bin_dir / "gitleaks", GITLEAKS)


def invoke(*args: str):
    from openfactory.cli import app

    return runner.invoke(app, list(args))


def write(repo: Path, path: Path, text: str) -> None:
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(text, encoding="utf-8")


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return done.stdout


def query(repo: Path, sql: str) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(repo / DB)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def max_seq(repo: Path) -> int:
    return query(repo, "SELECT MAX(seq) FROM events")[0][0]


def events_between(repo: Path, after: int, upto: int) -> list[dict[str, Any]]:
    rows = query(
        repo,
        "SELECT seq, stream, type, payload FROM events"
        f" WHERE seq > {after} AND seq <= {upto} ORDER BY seq",
    )
    keys = ("seq", "stream", "type", "payload")
    events: list[dict[str, Any]] = [dict(zip(keys, row, strict=True)) for row in rows]
    for event in events:
        event["payload"] = json.loads(event["payload"])
    return events


def snapshot(repo: Path) -> dict[str, list[tuple[Any, ...]]]:
    """Every row of the ten projections, in primary-key order."""
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


def tip(repo: Path, task_id: str) -> str:
    return git(repo, "rev-parse", f"openfactory/{task_id}").strip()


def parent(repo: Path, sha: str) -> str:
    return git(repo, "rev-parse", f"{sha}^").strip()


def trailer(repo: Path, sha: str, key: str) -> str:
    return git(repo, "log", "-1", f"--format=%(trailers:key={key},valueonly)", sha).strip()


@dataclass
class Flow:
    repo: Path
    first_run: Any = None
    seq_before_change: int = 0
    commits_before: list[tuple[Any, ...]] = field(default_factory=list[tuple[Any, ...]])
    tips_before: dict[str, str] = field(default_factory=dict[str, str])
    approve_spec: Any = None
    seq_after_approve_spec: int = 0
    impact: Any = None
    seq_after_impact: int = 0
    replan: Any = None
    seq_after_replan: int = 0
    plans_after_replan: list[tuple[Any, ...]] = field(default_factory=list[tuple[Any, ...]])
    tasks_after_replan: list[tuple[Any, ...]] = field(default_factory=list[tuple[Any, ...]])
    approve_plan: Any = None
    seq_after_approve_plan: int = 0
    tasks_after_approve: list[tuple[Any, ...]] = field(default_factory=list[tuple[Any, ...]])
    second_run: Any = None
    seq_after_run: int = 0
    status: Any = None
    seq_after_status: int = 0
    before: dict[str, list[tuple[Any, ...]]] = field(default_factory=dict[str, Any])
    emptied: dict[str, list[tuple[Any, ...]]] = field(default_factory=dict[str, Any])
    after: dict[str, list[tuple[Any, ...]]] = field(default_factory=dict[str, Any])
    projection_state: list[tuple[Any, ...]] = field(default_factory=list[tuple[Any, ...]])
    events_before: list[tuple[Any, ...]] = field(default_factory=list[tuple[Any, ...]])
    events_after: list[tuple[Any, ...]] = field(default_factory=list[tuple[Any, ...]])


@pytest.fixture(scope="module")
def flow(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Flow]:
    base = tmp_path_factory.mktemp("m6")
    with pytest.MonkeyPatch.context() as mp:
        for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "ANTHROPIC_API_KEY"):
            mp.delenv(name, raising=False)
        for name in ("PYTEST_ADDOPTS", "PYTHONPATH", "VIRTUAL_ENV"):
            mp.delenv(name, raising=False)
        for name in list(os.environ):
            if name.startswith(("GIT_AUTHOR_", "GIT_COMMITTER_")):
                mp.delenv(name)
        bin_dir = base / "bin"
        bin_dir.mkdir()
        stand_ins(bin_dir)
        mp.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")

        repo = base / "repo"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.name", "Test Human")
        git(repo, "config", "user.email", "human@example.com")
        git(repo, "config", "commit.gpgsign", "false")
        write(repo, MAIN, "X = 1\n")
        write(repo, GITIGNORE, ".venv\n__pycache__/\n.pytest_cache/\n.ruff_cache/\n")
        git(repo, "add", str(MAIN), str(GITIGNORE))
        git(repo, "commit", "-q", "-m", "initial")
        assert invoke("init", str(repo)).exit_code == 0
        write(repo, REQS, REQS_V1)
        write(repo, ADR_1, ADR_TEXT)
        write(repo, POLICIES, POLICIES_TEXT)
        mp.chdir(repo)
        assert invoke("approve", "spec").exit_code == 0
        assert invoke("plan").exit_code == 0
        assert invoke("approve", "plan").exit_code == 0
        f = Flow(repo=repo)
        f.first_run = invoke("run")

        f.seq_before_change = max_seq(repo)
        f.commits_before = query(repo, "SELECT sha, task_id, run_id FROM commits ORDER BY task_id")
        f.tips_before = {task_id: tip(repo, task_id) for task_id in OLD}

        write(repo, REQS, REQS_V2)
        f.approve_spec = invoke("approve", "spec")
        f.seq_after_approve_spec = max_seq(repo)
        f.impact = invoke("impact")
        f.seq_after_impact = max_seq(repo)
        f.replan = invoke("replan")
        f.seq_after_replan = max_seq(repo)
        f.plans_after_replan = query(repo, "SELECT id, status FROM plans ORDER BY id")
        f.tasks_after_replan = query(repo, "SELECT id, state FROM tasks ORDER BY id")
        f.approve_plan = invoke("approve", "plan")
        f.seq_after_approve_plan = max_seq(repo)
        f.tasks_after_approve = query(repo, "SELECT id, plan_id, state FROM tasks ORDER BY id")
        f.second_run = invoke("run")
        f.seq_after_run = max_seq(repo)
        f.status = invoke("status")
        f.seq_after_status = max_seq(repo)

        f.before = snapshot(repo)
        f.events_before = query(repo, "SELECT * FROM events ORDER BY seq")
        empty_projections(repo)
        f.emptied = snapshot(repo)
        rebuild(repo)
        f.after = snapshot(repo)
        f.projection_state = query(repo, "SELECT id, last_seq FROM projection_state")
        f.events_after = query(repo, "SELECT * FROM events ORDER BY seq")
        yield f


def test_first_build_passes_all_three_tasks(flow: Flow) -> None:
    assert flow.first_run.exit_code == 0
    assert flow.first_run.stdout.splitlines() == [
        "AUTH-001  passed",
        "AUTH-002  passed",
        "AUTH-003  passed",
    ]


def test_ac1_impact_shows_the_impacted_subgraph(flow: Flow) -> None:
    assert flow.approve_spec.exit_code == 0
    assert flow.approve_spec.stdout.splitlines()[-1] == "approved sv_02"

    assert flow.impact.stderr == ""
    assert flow.impact.exit_code == 0
    assert flow.impact.stdout.splitlines() == [
        "requirement  REQ-AUTH-001  modified  replacement",
        "task  AUTH-002",
        "downstream  AUTH-003",
        "file  app/login.py",
        "file  app/token.py",
        "file  tests/test_login.py",
        "file  tests/test_token.py",
        "test  tests/test_login.py::test_login",
        "test  tests/test_token.py::test_token",
        "obsolete  AC-AUTH-001-1",
        "obsolete  AC-AUTH-001-2",
        "new-work  REQ-AUTH-001  OTP verify endpoint",
        "impact sv_01..sv_02",
    ]

    events = events_between(flow.repo, flow.seq_after_approve_spec, flow.seq_after_impact)
    assert [e["type"] for e in events] == ["AgentRunStarted", "AgentRunFinished", "ImpactComputed"]
    started, finished, computed = events
    assert started["payload"]["run_id"] == "run_0008"
    assert started["payload"]["role"] == "classifier"
    assert started["payload"].get("task_id") is None
    assert finished["payload"]["run_id"] == "run_0008"
    assert computed["stream"] == "spec:sv_02"
    p = computed["payload"]
    assert (p["from_version"], p["to_version"], p["run_id"]) == ("sv_01", "sv_02", "run_0008")


def test_ac2_replan_drafts_only_the_new_tasks_and_invalidates_nothing(flow: Flow) -> None:
    assert flow.replan.stderr == ""
    assert flow.replan.exit_code == 0
    assert flow.replan.stdout.splitlines() == [
        "AUTH-004  Log in with a one-time code",
        "AUTH-005  Expire the one-time token",
        "created plan_02",
    ]

    events = events_between(flow.repo, flow.seq_after_impact, flow.seq_after_replan)
    (started,) = [e for e in events if e["type"] == "AgentRunStarted"]
    assert started["payload"]["run_id"] == "run_0009"
    (created,) = [e for e in events if e["type"] == "PlanCreated"]
    assert created["payload"]["plan_id"] == "plan_02"
    assert created["payload"]["spec_version"] == "sv_02"
    assert sorted(t["task_id"] for t in created["payload"]["tasks"]) == ["AUTH-004", "AUTH-005"]

    since_change = events_between(flow.repo, flow.seq_before_change, flow.seq_after_replan)
    assert not [e for e in since_change if e["type"] == "TaskStateChanged"]
    assert ("plan_01", "approved") in flow.plans_after_replan
    old_tasks = [row for row in flow.tasks_after_replan if row[0] in OLD]
    assert old_tasks == [(task_id, "passed") for task_id in OLD]


def test_ac3_approve_plan_invalidates_the_impacted_tasks_and_supersedes(flow: Flow) -> None:
    assert flow.approve_plan.exit_code == 0
    assert flow.approve_plan.stdout.splitlines() == [
        "AUTH-002  invalidated",
        "AUTH-003  invalidated",
        "AUTH-004  ready",
        "approved plan_02",
    ]

    events = events_between(flow.repo, flow.seq_after_replan, flow.seq_after_approve_plan)
    invalidations = [
        e for e in events if e["type"] == "TaskStateChanged" and e["payload"]["to"] == "invalidated"
    ]
    assert [(e["payload"]["task_id"], e["payload"]["reason"]) for e in invalidations] == [
        ("AUTH-002", "spec change sv_02"),
        ("AUTH-003", "spec change sv_02"),
    ]

    plans = query(flow.repo, "SELECT id, status FROM plans ORDER BY id")
    assert plans == [("plan_01", "superseded"), ("plan_02", "approved")]
    assert flow.tasks_after_approve == [
        ("AUTH-001", "plan_02", "passed"),
        ("AUTH-002", "plan_02", "invalidated"),
        ("AUTH-003", "plan_02", "invalidated"),
        ("AUTH-004", "plan_02", "ready"),
        ("AUTH-005", "plan_02", "pending"),
    ]


def test_ac4_run_executes_only_the_new_tasks_from_the_chain_tip(flow: Flow) -> None:
    repo = flow.repo
    assert flow.second_run.exit_code == 0
    assert flow.second_run.stdout.splitlines() == ["AUTH-004  passed", "AUTH-005  passed"]

    events = events_between(repo, flow.seq_after_approve_plan, flow.seq_after_run)
    named = {e["payload"]["task_id"] for e in events if e["payload"].get("task_id")}
    assert named == {"AUTH-004", "AUTH-005"}
    implementers = [
        (e["payload"]["run_id"], e["payload"]["task_id"])
        for e in events
        if e["type"] == "AgentRunStarted" and e["payload"]["role"] == "implementer"
    ]
    assert implementers == [("run_0010", "AUTH-004"), ("run_0012", "AUTH-005")]

    s3, s4, s5 = flow.tips_before["AUTH-003"], tip(repo, "AUTH-004"), tip(repo, "AUTH-005")
    assert parent(repo, s4) == s3
    assert parent(repo, s5) == s4
    assert trailer(repo, s4, "Task") == "AUTH-004"
    assert trailer(repo, s5, "Task") == "AUTH-005"
    assert trailer(repo, s4, "Spec-Version") == "sv_02"
    assert trailer(repo, s5, "Spec-Version") == "sv_02"

    commits = query(repo, "SELECT sha, task_id, run_id FROM commits ORDER BY task_id")
    assert commits == [
        *flow.commits_before,
        (s4, "AUTH-004", "run_0010"),
        (s5, "AUTH-005", "run_0012"),
    ]


def test_ac5_untouched_tasks_keep_their_state_and_commits(flow: Flow) -> None:
    repo = flow.repo
    old_commits = query(
        repo,
        "SELECT sha, task_id, run_id FROM commits"
        " WHERE task_id IN ('AUTH-001', 'AUTH-002', 'AUTH-003') ORDER BY task_id",
    )
    assert len(flow.commits_before) == 3
    assert old_commits == flow.commits_before
    assert {task_id: tip(repo, task_id) for task_id in OLD} == flow.tips_before

    later = events_between(repo, flow.seq_before_change, flow.seq_after_run)
    assert not [e for e in later if e["stream"] == "task:AUTH-001"]
    for task_id in ("AUTH-002", "AUTH-003"):
        (only,) = [e for e in later if e["stream"] == f"task:{task_id}"]
        assert only["type"] == "TaskStateChanged"
        assert only["payload"]["to"] == "invalidated"

    assert flow.status.exit_code == 0
    assert flow.status.stdout.splitlines() == [
        "AUTH-001  passed  1/2  review passed",
        "AUTH-002  invalidated  1/2  review passed",
        "AUTH-003  invalidated  1/2  review passed",
        "AUTH-004  passed  1/2  review passed",
        "AUTH-005  passed  1/2  review passed",
    ]


def test_ac6_rebuild_gives_identical_projections(flow: Flow) -> None:
    assert all(flow.before[t] for t in TABLES)
    assert flow.emptied == {t: [] for t in TABLES}
    assert flow.emptied != flow.before
    for table in TABLES:
        assert flow.after[table] == flow.before[table]
    assert flow.projection_state == [(1, flow.seq_after_status)]
    assert flow.events_after == flow.events_before
