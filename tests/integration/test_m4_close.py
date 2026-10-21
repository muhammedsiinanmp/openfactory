"""TASK-078 AC1..AC6: M4 close (see docs/tasks/TASK-078-m4-close-integration-test.md).

One flow runs once per module: a `run` with a retry and two escalations, `resolve --retry`,
a second `run` and `status`. The stand-in `uv` execs the test interpreter's `ruff` and
`pytest`, so the gates judge the worktree with the real tools and the real plugin.
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
RUNS = ".openfactory/runs"
REQS = Path("specs/requirements.yaml")
ADR_1 = Path("specs/adrs/ADR-001-auth-method.md")
MAIN = Path("app/main.py")
GITIGNORE = Path(".gitignore")

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
    "AUTH-003": "Add the config",
}
CRITERIA = {"AUTH-001": "AC-AUTH-001-1", "AUTH-002": "AC-AUTH-001-2", "AUTH-003": "AC-AUTH-001-1"}
PLAN = {
    "tasks": [
        {
            "task_id": task_id,
            "objective": objective,
            "requirements": ["REQ-AUTH-001"],
            "acceptance_criteria": [CRITERIA[task_id]],
            "depends_on": ["AUTH-001"] if task_id == "AUTH-002" else [],
            "components": ["auth"],
            "role": "implementer",
            "allowed_paths": ["app/", "tests/"],
            "forbidden_paths": [],
        }
        for task_id, objective in OBJECTIVES.items()
    ]
}

SECRET = "SECRET_TOKEN="


def tagged_test(name: str) -> str:
    return (
        "import pytest\n\n\n"
        '@pytest.mark.req("REQ-AUTH-001")\n'
        f"def test_{name}() -> None:\n    assert True\n"
    )


LOGIN = "def login(name: str) -> str:\n    return name\n"
# What the stand-in implementer writes, per task and per start for that task (1-based).
WRITES: dict[str, dict[int, dict[str, str]]] = {
    "AUTH-001": {
        1: {"app/login.py": "import os\n\n\n" + LOGIN, "tests/test_login.py": tagged_test("login")},
        2: {"app/login.py": LOGIN, "tests/test_login.py": tagged_test("login")},
    },
    "AUTH-002": {
        n: {
            "app/otp.py": 'def otp() -> str:\n    return "123456"\n',
            "tests/test_otp.py": (
                tagged_test("otp") if n == 3 else "def test_otp() -> None:\n    assert True\n"
            ),
        }
        for n in (1, 2, 3)
    },
    "AUTH-003": {
        1: {
            "app/config.py": f'TOKEN = "{SECRET}abc123"\n',
            "tests/test_config.py": tagged_test("config"),
        },
    },
}

# The body of the stand-in `claude`; `LOG`, `PACKS`, `PLANNER`, `REVIEWER`, `AGENT` and
# `WRITES` are set above it. The worktree dir name is the task id; the start number for a
# task comes from the log.
CLAUDE_BODY = """
import hashlib, json, sys
from pathlib import Path

data = sys.stdin.buffer.read()
cwd = Path.cwd()
log = Path(LOG)
entries = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
if b"## Staged diff" in data:
    role, out = "reviewer", REVIEWER
elif "--json-schema" in sys.argv:
    role, out = "planner", PLANNER
else:
    role, out = "implementer", AGENT
    task = cwd.name
    n = 1 + sum(1 for e in entries if e["role"] == role and Path(e["cwd"]).name == task)
    for name, text in WRITES[task][n].items():
        (cwd / name).parent.mkdir(parents=True, exist_ok=True)
        (cwd / name).write_text(text, encoding="utf-8")
(Path(PACKS) / f"{len(entries) + 1}.txt").write_bytes(data)
entry = {
    "role": role,
    "cwd": str(cwd),
    "stdin_sha256": hashlib.sha256(data).hexdigest(),
    "failure_report": b"## Failure report of the previous attempt" in data,
}
with open(LOG, "a", encoding="utf-8") as f:
    f.write(json.dumps(entry) + "\\n")
sys.stdout.buffer.write(out.encode("utf-8"))
"""

# Drops `run` and execs the test interpreter's tool: `uv run ruff check` runs `-m ruff check`.
UV = f'#!/bin/sh\nshift\nexec "{sys.executable}" -m "$@"\n'
# A finding when the staged change holds the marker, as `--exit-code 3` gives.
GITLEAKS = f"""#!/bin/sh
if git diff --cached | grep -q '{SECRET}'; then
  echo "finding: {SECRET}"
  exit 3
fi
exit 0
"""


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def write_script(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IRWXU)


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
        "SELECT event_id, stream, type, payload, actor, causation_id FROM events"
        f" WHERE seq > {after} AND seq <= {upto} ORDER BY seq",
    )
    keys = ("event_id", "stream", "type", "payload", "actor", "causation_id")
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


@dataclass
class RebuildCheck:
    before: dict[str, list[tuple[Any, ...]]]
    emptied: dict[str, list[tuple[Any, ...]]]
    after: dict[str, list[tuple[Any, ...]]]
    projection_state: list[tuple[Any, ...]]
    max_seq: int
    events_before: list[tuple[Any, ...]]
    events_after: list[tuple[Any, ...]]


def rebuild_check(repo: Path) -> RebuildCheck:
    """Snapshot, empty the projections, rebuild and snapshot again."""
    before = snapshot(repo)
    events_before = query(repo, "SELECT * FROM events ORDER BY seq")
    empty_projections(repo)
    emptied = snapshot(repo)
    rebuild(repo)
    return RebuildCheck(
        before=before,
        emptied=emptied,
        after=snapshot(repo),
        projection_state=query(repo, "SELECT id, last_seq FROM projection_state"),
        max_seq=max_seq(repo),
        events_before=events_before,
        events_after=query(repo, "SELECT * FROM events ORDER BY seq"),
    )


def tip(repo: Path, task_id: str) -> str:
    return git(repo, "rev-parse", f"openfactory/{task_id}").strip()


def run_cost(repo: Path, *run_ids: str) -> float:
    ids = ", ".join(f"'{r}'" for r in run_ids)
    return query(repo, f"SELECT SUM(cost_usd) FROM agent_runs WHERE id IN ({ids})")[0][0]


@dataclass
class Flow:
    repo: Path
    log: Path
    packs: Path
    initial: str
    seq_before_run: int = 0
    first_run: Any = None
    seq_after_run: int = 0
    first_check: RebuildCheck | None = None
    first_tasks: list[tuple[Any, ...]] = field(default_factory=list[tuple[Any, ...]])
    resolved: Any = None
    resolved_task: list[tuple[Any, ...]] = field(default_factory=list[tuple[Any, ...]])
    seq_after_resolve: int = 0
    second_run: Any = None
    seq_after_second: int = 0
    status: Any = None
    seq_after_status: int = 0
    final_check: RebuildCheck | None = None

    def starts(self) -> list[dict[str, Any]]:
        lines = self.log.read_text(encoding="utf-8").splitlines()
        return [{**json.loads(line), "n": i} for i, line in enumerate(lines, 1)]

    def implementer_starts(self) -> list[dict[str, Any]]:
        return [s for s in self.starts() if s["role"] == "implementer"]

    def pack(self, start: dict[str, Any]) -> str:
        return (self.packs / f"{start['n']}.txt").read_text(encoding="utf-8")


def stand_ins(bin_dir: Path, log: Path, packs: Path) -> None:
    planner = json.dumps({**fixture("claude_envelope.json"), "structured_output": PLAN})
    agent = json.dumps({**fixture("claude_agent_envelope.json"), "result": "Done."})
    verdict = {"verdict": "approve", "comments": "Meets the contract."}
    reviewer = json.dumps({**fixture("claude_envelope.json"), "structured_output": verdict})
    head = f"#!{sys.executable}\nLOG = {str(log)!r}\nPACKS = {str(packs)!r}\n"
    head += f"PLANNER = {planner!r}\nREVIEWER = {reviewer!r}\nAGENT = {agent!r}\n"
    head += f"WRITES = {WRITES!r}\n"
    write_script(bin_dir / "claude", head + CLAUDE_BODY)
    write_script(bin_dir / "uv", UV)
    write_script(bin_dir / "gitleaks", GITLEAKS)


@pytest.fixture(scope="module")
def flow(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Flow]:
    base = tmp_path_factory.mktemp("m4")
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
        packs = base / "packs"
        packs.mkdir()
        log = base / "claude-starts.jsonl"
        stand_ins(bin_dir, log, packs)
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
        write(repo, REQS, REQS_TEXT)
        write(repo, ADR_1, ADR_TEXT)
        mp.chdir(repo)
        assert invoke("approve", "spec").exit_code == 0
        assert invoke("plan").exit_code == 0
        assert invoke("approve", "plan").exit_code == 0

        f = Flow(repo=repo, log=log, packs=packs, initial=git(repo, "rev-parse", "HEAD").strip())
        f.seq_before_run = max_seq(repo)
        f.first_run = invoke("run")
        f.seq_after_run = max_seq(repo)
        f.first_tasks = query(repo, "SELECT id, state, attempt, cost_usd FROM tasks ORDER BY id")
        f.first_check = rebuild_check(repo)

        f.resolved = invoke("resolve", "AUTH-002", "--retry")
        f.seq_after_resolve = max_seq(repo)
        f.resolved_task = query(
            repo, "SELECT state, attempt, cost_usd FROM tasks WHERE id = 'AUTH-002'"
        )
        f.second_run = invoke("run")
        f.seq_after_second = max_seq(repo)
        f.status = invoke("status")
        f.seq_after_status = max_seq(repo)
        f.final_check = rebuild_check(repo)
        yield f


def first_run_events(flow: Flow) -> list[dict[str, Any]]:
    return events_between(flow.repo, flow.seq_before_run, flow.seq_after_run)


def moves(events: list[dict[str, Any]], task_id: str) -> list[dict[str, Any]]:
    return [
        e for e in events if e["stream"] == f"task:{task_id}" and e["type"] == "TaskStateChanged"
    ]


def shape(event: dict[str, Any]) -> tuple[Any, ...]:
    p = event["payload"]
    return (p["from"], p["to"], p["reason"])


def test_ac1_first_run_retries_and_escalates(flow: Flow) -> None:
    result = flow.first_run
    assert result.stdout.splitlines() == [
        "AUTH-001  passed",
        "AUTH-002  escalated",
        "AUTH-003  escalated",
    ]
    assert result.stderr == ""
    assert result.exit_code == 1

    starts = flow.implementer_starts()[:5]
    assert [Path(s["cwd"]).name for s in starts] == [
        "AUTH-001",
        "AUTH-001",
        "AUTH-002",
        "AUTH-002",
        "AUTH-003",
    ]
    started = [
        e
        for e in first_run_events(flow)
        if e["type"] == "AgentRunStarted" and e["payload"]["role"] == "implementer"
    ]
    assert [s["stdin_sha256"] for s in starts] == [e["payload"]["context_hash"] for e in started]
    reviewers = [
        e
        for e in first_run_events(flow)
        if e["type"] == "AgentRunStarted" and e["payload"]["role"] == "reviewer"
    ]
    assert [e["payload"]["run_id"] for e in reviewers] == ["run_0004"]
    reviewer_starts = [s for s in flow.starts() if s["role"] == "reviewer"]
    assert len(reviewer_starts) == 2  # one per run: AUTH-001 now, AUTH-002 in the second


def test_ac2_gate_results_files_and_commits(flow: Flow) -> None:
    repo = flow.repo
    rows = flow.first_check
    assert rows is not None
    gate_rows = [(r[0], r[1], r[2]) for r in rows.before["gate_results"]]
    assert gate_rows == [
        ("run_0002", "gitleaks", 1),
        ("run_0002", "path_check", 1),
        ("run_0002", "pytest", 1),
        ("run_0002", "ruff", 0),
        ("run_0003", "gitleaks", 1),
        ("run_0003", "path_check", 1),
        ("run_0003", "pytest", 1),
        ("run_0003", "review", 1),
        ("run_0003", "ruff", 1),
        ("run_0005", "gitleaks", 1),
        ("run_0005", "path_check", 1),
        ("run_0005", "pytest", 0),
        ("run_0005", "ruff", 1),
        ("run_0006", "gitleaks", 1),
        ("run_0006", "path_check", 1),
        ("run_0006", "pytest", 0),
        ("run_0006", "ruff", 1),
        ("run_0007", "gitleaks", 0),
        ("run_0007", "path_check", 1),
        ("run_0007", "pytest", 1),
        ("run_0007", "ruff", 1),
    ]
    for run_id, gate, _, output_path in rows.before["gate_results"]:
        expected = None if gate == "path_check" else f"{RUNS}/{run_id}/{gate}.txt"
        assert output_path == expected

    ruff = (repo / RUNS / "run_0002" / "ruff.txt").read_text(encoding="utf-8")
    assert ruff.splitlines()[0] == "$ uv run ruff check"
    assert "F401" in ruff
    pytest_text = (repo / RUNS / "run_0005" / "pytest.txt").read_text(encoding="utf-8")
    assert pytest_text.endswith("no tagged test in a changed file: REQ-AUTH-001\n")
    review = (repo / RUNS / "run_0003" / "review.txt").read_text(encoding="utf-8")
    assert review.startswith("verdict: approve\n")

    assert [(r[1], r[2]) for r in rows.before["commits"]] == [("AUTH-001", "run_0003")]
    first = tip(repo, "AUTH-001")
    assert git(repo, "rev-parse", f"{first}^").strip() == flow.initial
    trailer = git(repo, "log", "-1", "--format=%(trailers:key=Agent-Run,valueonly)", first)
    assert trailer.strip() == "run_0003"


def test_ac3_events_packs_and_task_rows(flow: Flow) -> None:
    events = first_run_events(flow)
    assert {e["actor"] for e in events} == {"orchestrator"}

    one = moves(events, "AUTH-001")
    assert [shape(e) for e in one] == [
        ("ready", "running", None),
        ("running", "gating", None),
        ("gating", "failed", "ruff"),
        ("failed", "ready", None),
        ("ready", "running", None),
        ("running", "gating", None),
        ("gating", "passed", None),
    ]
    assert one[3]["causation_id"] == one[2]["event_id"]
    assert one[4]["causation_id"] == one[3]["event_id"]

    two = moves(events, "AUTH-002")
    assert [shape(e) for e in two] == [
        ("pending", "ready", None),
        ("ready", "running", None),
        ("running", "gating", None),
        ("gating", "failed", "pytest"),
        ("failed", "ready", None),
        ("ready", "running", None),
        ("running", "gating", None),
        ("gating", "failed", "pytest"),
        ("failed", "escalated", "attempts exhausted"),
    ]
    assert two[4]["causation_id"] == two[3]["event_id"]
    assert two[8]["causation_id"] == two[7]["event_id"]

    assert [shape(e) for e in moves(events, "AUTH-003")] == [
        ("ready", "running", None),
        ("running", "gating", None),
        ("gating", "failed", "secret found"),
        ("failed", "escalated", "secret found"),
    ]

    starts = flow.implementer_starts()
    retry = flow.pack(starts[1])
    assert "## Failure report of the previous attempt" in retry
    assert "reason: ruff\n" in retry
    block = retry.split('<gate name="ruff">', 1)[1].split("</gate>", 1)[0]
    assert "F401" in block
    assert [s["failure_report"] for s in starts[:5]] == [False, True, False, True, False]

    repo = flow.repo
    costs = {
        "AUTH-001": run_cost(repo, "run_0002", "run_0003", "run_0004"),
        "AUTH-002": run_cost(repo, "run_0005", "run_0006"),
        "AUTH-003": run_cost(repo, "run_0007"),
    }
    assert [(r[0], r[1], r[2]) for r in flow.first_tasks] == [
        ("AUTH-001", "passed", 2),
        ("AUTH-002", "escalated", 2),
        ("AUTH-003", "escalated", 1),
    ]
    for task_id, _, _, cost in flow.first_tasks:
        assert cost == pytest.approx(costs[task_id])


def test_ac4_resolve_retry_then_a_passing_run(flow: Flow) -> None:
    repo = flow.repo
    assert flow.resolved.stdout == "AUTH-002  ready\n"
    assert flow.resolved.exit_code == 0
    resolved = events_between(repo, flow.seq_after_run, flow.seq_after_resolve)
    assert [(e["type"], e["actor"]) for e in resolved] == [
        ("TaskResolved", "human"),
        ("TaskStateChanged", "orchestrator"),
    ]
    assert resolved[0]["payload"] == {"task_id": "AUTH-002", "decision": "retry"}
    assert shape(resolved[1]) == ("escalated", "ready", None)
    assert resolved[1]["causation_id"] == resolved[0]["event_id"]
    assert flow.resolved_task == [("ready", 0, 0)]

    assert flow.second_run.stdout == "AUTH-002  passed\n"
    assert flow.second_run.stderr == ""
    assert flow.second_run.exit_code == 0
    starts = flow.implementer_starts()
    assert [Path(s["cwd"]).name for s in starts[5:]] == ["AUTH-002"]
    third = flow.pack(starts[5])
    assert "reason: pytest\n" in third
    assert "no tagged test in a changed file: REQ-AUTH-001" in third

    assert query(repo, "SELECT state FROM tasks WHERE id = 'AUTH-003'") == [("escalated",)]
    attempt, cost = query(repo, "SELECT attempt, cost_usd FROM tasks WHERE id = 'AUTH-002'")[0]
    assert attempt == 1
    assert cost == pytest.approx(run_cost(repo, "run_0008", "run_0009"))
    assert query(repo, "SELECT id, task_id, role FROM agent_runs WHERE id >= 'run_0008'") == [
        ("run_0008", "AUTH-002", "implementer"),
        ("run_0009", "AUTH-002", "reviewer"),
    ]

    second = tip(repo, "AUTH-002")
    assert git(repo, "rev-parse", f"{second}^").strip() == tip(repo, "AUTH-001")
    out = git(repo, "log", "--branches=openfactory/*", "--format=%(trailers:key=Task,valueonly)")
    assert [line for line in out.splitlines() if line.strip() == "AUTH-002"] == ["AUTH-002"]


def test_ac5_status_after_the_second_run(flow: Flow) -> None:
    assert flow.status.stdout.splitlines() == [
        "AUTH-001  passed  2/2  review passed",
        "AUTH-002  passed  1/2  review passed",
        "AUTH-003  escalated  1/2  gitleaks failed",
    ]
    assert flow.status.stderr == ""
    assert flow.status.exit_code == 0
    assert flow.seq_after_status == flow.seq_after_second


@pytest.mark.parametrize("which", ["first_check", "final_check"])
def test_ac6_rebuild_gives_identical_projections(flow: Flow, which: str) -> None:
    check: RebuildCheck | None = getattr(flow, which)
    assert check is not None
    assert all(check.before[t] for t in TABLES)
    assert check.emptied == {t: [] for t in TABLES}
    assert check.emptied != check.before
    for table in TABLES:
        assert check.after[table] == check.before[table]
    assert check.projection_state == [(1, check.max_seq)]
    assert check.events_after == check.events_before
