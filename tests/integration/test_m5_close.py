"""TASK-089 AC1..AC6: M5 close (see docs/tasks/TASK-089-m5-close-integration-test.md).

One flow runs once per module: a `run` killed after `AUTH-003`'s git commit and before its
`TestsCollected`, a restarting `run`, then `coverage`, `trace` and `why`, the rebuild of
the trace links from git and the rebuild of the projections. The stand-in `uv` execs the
test interpreter's `ruff` and `pytest`, so the gates and the collection use the real tools.
"""

import json
import os
import sqlite3
import stat
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from openfactory.adapters.git_cli import GitCli
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.app.rebuild_links import rebuild_links
from openfactory.domain.traces import TraceLink

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
runner = CliRunner()

DB = Path(".openfactory/openfactory.db")
REQS = Path("specs/requirements.yaml")
POLICIES = Path("specs/policies.yaml")
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
  - id: REQ-AUTH-002
    title: Config
    statement: The service reads its config.
    priority: must
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-002-1
        text: The config has a token lifetime.
"""
ADR_TEXT = "---\nid: ADR-001\nstatus: accepted\n---\nUsers are identified by membership number.\n"
POLICIES_TEXT = """\
protected_branches: [main, master]
forbidden_paths: []
max_attempts: 1
max_runtime_s: 1200
max_cost_usd: 1.50
"""

CONTRACTS: dict[str, tuple[str, str, str, list[str]]] = {
    "AUTH-001": ("Add the login endpoint", "REQ-AUTH-001", "AC-AUTH-001-1", []),
    "AUTH-002": ("Add the one-time code", "REQ-AUTH-001", "AC-AUTH-001-2", ["AUTH-001"]),
    "AUTH-003": ("Add the config", "REQ-AUTH-002", "AC-AUTH-002-1", []),
}
PLAN = {
    "tasks": [
        {
            "task_id": task_id,
            "objective": objective,
            "requirements": [req],
            "acceptance_criteria": [criterion],
            "depends_on": deps,
            "components": ["auth"],
            "role": "implementer",
            "allowed_paths": ["app/", "tests/"],
            "forbidden_paths": [],
        }
        for task_id, (objective, req, criterion, deps) in CONTRACTS.items()
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
        "app/login.py": "def login(name: str) -> str:\n    return name\n",
        "tests/test_login.py": tagged_test("login", "REQ-AUTH-001"),
    },
    "AUTH-002": {
        "app/login.py": "def login(name: str) -> str:\n    return name.strip()\n",
        "app/otp.py": 'def otp() -> str:\n    return "123456"\n',
        "tests/test_otp.py": (
            tagged_test("otp_tagged", "REQ-AUTH-001")
            + "\n\ndef test_otp_untagged() -> None:\n    assert True\n"
        ),
    },
    "AUTH-003": {
        "app/config.py": "LIFETIME_S = 3600\n",
        "tests/test_config.py": tagged_test("config", "REQ-AUTH-002"),
    },
}

# The body of the stand-in `claude`; `PLANNER`, `REVIEWER`, `AGENT` and `WRITES` are set
# above it. The worktree dir name is the task id.
CLAUDE_BODY = """
import sys
from pathlib import Path

data = sys.stdin.buffer.read()
cwd = Path.cwd()
if b"## Staged diff" in data:
    out = REVIEWER
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

# Runs `run` and kills its own process just before `AUTH-003`'s `TestsCollected`.
CHILD = textwrap.dedent(
    """
    import os, signal
    from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
    from openfactory.cli import app

    original = SqliteEventRecorder.record

    def record(self, event):
        p = event.payload
        if event.type.value == "TestsCollected" and p.get("task_id") == "AUTH-003":
            os.kill(os.getpid(), signal.SIGKILL)
        return original(self, event)

    SqliteEventRecorder.record = record
    app()
    """
)


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def write_script(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IRWXU)


def stand_ins(bin_dir: Path) -> None:
    planner = json.dumps({**fixture("claude_envelope.json"), "structured_output": PLAN})
    agent = json.dumps({**fixture("claude_agent_envelope.json"), "result": "Done."})
    verdict = {"verdict": "approve", "comments": "Meets the contract."}
    reviewer = json.dumps({**fixture("claude_envelope.json"), "structured_output": verdict})
    head = f"#!{sys.executable}\nPLANNER = {planner!r}\nREVIEWER = {reviewer!r}\n"
    head += f"AGENT = {agent!r}\nWRITES = {WRITES!r}\n"
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


def event_count(repo: Path) -> int:
    return query(repo, "SELECT COUNT(*) FROM events")[0][0]


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


def trailer(repo: Path, sha: str, key: str) -> str:
    return git(repo, "log", "-1", f"--format=%(trailers:key={key},valueonly)", sha).strip()


def changed_files(repo: Path, sha: str) -> list[str]:
    out = git(repo, "diff-tree", "-r", "--no-renames", "--name-only", f"{sha}^", sha)
    return out.splitlines()


def trace_rows(repo: Path) -> set[TraceLink]:
    rows = query(repo, "SELECT from_kind, from_id, to_kind, to_id, source FROM trace_links")
    keys = ("from_kind", "from_id", "to_kind", "to_id", "source")
    return {TraceLink.model_validate(dict(zip(keys, row, strict=True))) for row in rows}


def link(from_kind: str, from_id: str, to_kind: str, to_id: str, source: str) -> TraceLink:
    return TraceLink.model_validate(
        {
            "from_kind": from_kind,
            "from_id": from_id,
            "to_kind": to_kind,
            "to_id": to_id,
            "source": source,
        }
    )


@dataclass
class Flow:
    repo: Path
    child: subprocess.CompletedProcess[str]
    seq_after_kill: int
    second_run: Any = None
    seq_after_second: int = 0
    seq_before_reads: int = 0
    count_before_reads: int = 0
    coverage: Any = None
    trace_one: Any = None
    trace_two: Any = None
    why_login: Any = None
    why_files: dict[str, Any] = field(default_factory=dict[str, Any])
    seq_after_reads: int = 0
    count_after_reads: int = 0
    rebuilt: set[TraceLink] = field(default_factory=set[TraceLink])
    links: set[TraceLink] = field(default_factory=set[TraceLink])
    before: dict[str, list[tuple[Any, ...]]] = field(default_factory=dict[str, Any])
    emptied: dict[str, list[tuple[Any, ...]]] = field(default_factory=dict[str, Any])
    after: dict[str, list[tuple[Any, ...]]] = field(default_factory=dict[str, Any])
    projection_state: list[tuple[Any, ...]] = field(default_factory=list[tuple[Any, ...]])
    events_before: list[tuple[Any, ...]] = field(default_factory=list[tuple[Any, ...]])
    events_after: list[tuple[Any, ...]] = field(default_factory=list[tuple[Any, ...]])


@pytest.fixture(scope="module")
def flow(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Flow]:
    base = tmp_path_factory.mktemp("m5")
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
        write(repo, REQS, REQS_TEXT)
        write(repo, ADR_1, ADR_TEXT)
        write(repo, POLICIES, POLICIES_TEXT)
        mp.chdir(repo)
        assert invoke("approve", "spec").exit_code == 0
        assert invoke("plan").exit_code == 0
        assert invoke("approve", "plan").exit_code == 0

        child = subprocess.run(
            [sys.executable, "-c", CHILD, "run"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        f = Flow(repo=repo, child=child, seq_after_kill=max_seq(repo))
        f.second_run = invoke("run")
        f.seq_after_second = max_seq(repo)

        f.seq_before_reads = max_seq(repo)
        f.count_before_reads = event_count(repo)
        f.coverage = invoke("coverage")
        f.trace_one = invoke("trace", "REQ-AUTH-001")
        f.trace_two = invoke("trace", "REQ-AUTH-002")
        f.why_login = invoke("why", "app/login.py")
        for (sha,) in query(repo, "SELECT sha FROM commits ORDER BY sha"):
            for path in changed_files(repo, sha):
                f.why_files.setdefault(path, invoke("why", path))
        f.seq_after_reads = max_seq(repo)
        f.count_after_reads = event_count(repo)

        f.rebuilt = rebuild_links(git=GitCli(repo))
        f.links = trace_rows(repo)

        f.before = snapshot(repo)
        f.events_before = query(repo, "SELECT * FROM events ORDER BY seq")
        empty_projections(repo)
        f.emptied = snapshot(repo)
        rebuild(repo)
        f.after = snapshot(repo)
        f.projection_state = query(repo, "SELECT id, last_seq FROM projection_state")
        f.events_after = query(repo, "SELECT * FROM events ORDER BY seq")
        yield f


def task_events(events: list[dict[str, Any]], task_id: str) -> list[dict[str, Any]]:
    return [e for e in events if e["payload"].get("task_id") == task_id]


def test_ac1_killed_run_leaves_an_orphan_commit_and_the_restart_escalates(flow: Flow) -> None:
    repo = flow.repo
    assert flow.child.returncode == -9
    s2, s3 = tip(repo, "AUTH-002"), tip(repo, "AUTH-003")
    assert git(repo, "rev-parse", f"{s3}^").strip() == s2
    assert trailer(repo, s3, "Task") == "AUTH-003"
    assert trailer(repo, s3, "Agent-Run") == "run_0006"
    first = task_events(events_between(repo, 0, flow.seq_after_kill), "AUTH-003")
    assert not [e for e in first if e["type"] in ("TestsCollected", "CommitRecorded")]

    assert flow.second_run.stdout == ""
    assert flow.second_run.stderr == ""
    assert flow.second_run.exit_code == 0
    repair = events_between(repo, flow.seq_after_kill, flow.seq_after_second)
    assert [
        (e["stream"], e["type"], e["payload"]["from"], e["payload"]["to"], e["payload"]["reason"])
        for e in repair
    ] == [
        ("task:AUTH-003", "TaskStateChanged", "gating", "failed", "interrupted"),
        ("task:AUTH-003", "TaskStateChanged", "failed", "escalated", "attempts exhausted"),
    ]
    assert {(e["actor"], e["causation_id"]) for e in repair} == {("orchestrator", None)}
    assert tip(repo, "AUTH-003") == s3

    s1 = tip(repo, "AUTH-001")
    assert query(repo, "SELECT sha, task_id, run_id FROM commits ORDER BY task_id") == [
        (s1, "AUTH-001", "run_0002"),
        (s2, "AUTH-002", "run_0004"),
    ]
    tags = {(tl.from_id, tl.to_kind, tl.to_id) for tl in flow.links if tl.source == "test_tag"}
    assert tags == {
        ("tests/test_login.py::test_login", "file", "tests/test_login.py"),
        ("tests/test_otp.py::test_otp_tagged", "file", "tests/test_otp.py"),
        ("tests/test_otp.py::test_otp_untagged", "file", "tests/test_otp.py"),
        ("tests/test_login.py::test_login", "requirement", "REQ-AUTH-001"),
        ("tests/test_otp.py::test_otp_tagged", "requirement", "REQ-AUTH-001"),
    }


def test_ac2_coverage_names_the_requirement_with_no_passing_tagged_test(flow: Flow) -> None:
    assert flow.coverage.stdout == "REQ-AUTH-002\n"
    assert flow.coverage.stderr == ""
    assert flow.coverage.exit_code == 0


def test_ac3_trace_of_both_requirements(flow: Flow) -> None:
    s1, s2 = tip(flow.repo, "AUTH-001"), tip(flow.repo, "AUTH-002")
    assert flow.trace_one.stdout.splitlines() == [
        "task  AUTH-001  passed",
        "task  AUTH-002  passed",
        f"commit  {s1}  AUTH-001",
        f"commit  {s2}  AUTH-002",
        "file  app/login.py",
        "file  app/otp.py",
        "file  tests/test_login.py",
        "file  tests/test_otp.py",
        "test  tests/test_login.py::test_login  tagged",
        "test  tests/test_otp.py::test_otp_tagged  tagged",
        "test  tests/test_otp.py::test_otp_untagged  file",
    ]
    assert flow.trace_one.stderr == ""
    assert flow.trace_one.exit_code == 0
    assert flow.trace_two.stdout == "task  AUTH-003  escalated\n"
    assert flow.trace_two.stderr == ""
    assert flow.trace_two.exit_code == 0


def test_ac4_every_file_of_a_recorded_commit_resolves_in_why(flow: Flow) -> None:
    repo = flow.repo
    s1, s2 = tip(repo, "AUTH-001"), tip(repo, "AUTH-002")
    assert flow.why_login.stdout.splitlines() == [
        f"commit  {s1}  AUTH-001",
        f"commit  {s2}  AUTH-002",
        "task  AUTH-001  passed",
        "task  AUTH-002  passed",
        "requirement  REQ-AUTH-001",
        "adr  ADR-001",
    ]
    assert flow.why_login.exit_code == 0

    recorded = query(repo, "SELECT sha, task_id FROM commits ORDER BY sha")
    events = events_between(repo, 0, flow.seq_after_second)
    for sha, task_id in recorded:
        (commit_event,) = [
            e for e in events if e["type"] == "CommitRecorded" and e["payload"]["sha"] == sha
        ]
        files = changed_files(repo, sha)
        assert sorted(files) == sorted(commit_event["payload"]["files"])
        requirements = [r.strip() for r in trailer(repo, sha, "Requirements").split(",")]
        for path in files:
            result = flow.why_files[path]
            lines = result.stdout.splitlines()
            assert result.exit_code == 0
            assert f"commit  {sha}  {task_id}" in lines
            assert f"task  {task_id}  passed" in lines
            for req in requirements:
                assert f"requirement  {req}" in lines


def test_ac5_rebuild_from_git_equals_the_trace_links_apart_from_the_orphan(flow: Flow) -> None:
    repo = flow.repo
    s1, s2, s3 = tip(repo, "AUTH-001"), tip(repo, "AUTH-002"), tip(repo, "AUTH-003")
    orphan = {
        link("requirement", "REQ-AUTH-002", "task", "AUTH-003", "contract"),
        link("task", "AUTH-003", "run", "run_0006", "trailer"),
        link("run", "run_0006", "commit", s3, "trailer"),
        link("commit", s3, "file", "app/config.py", "diff"),
        link("commit", s3, "file", "tests/test_config.py", "diff"),
    }
    tasks = {"AUTH-001", "AUTH-002"}
    runs = {tl.to_id for tl in flow.links if tl.source == "trailer" and tl.from_id in tasks}
    commits = {tl.to_id for tl in flow.links if tl.source == "trailer" and tl.from_id in runs}
    recorded = {
        tl
        for tl in flow.links
        if (tl.from_kind, tl.to_kind, tl.source) == ("requirement", "task", "contract")
        and tl.to_id in tasks
        or (tl.from_kind, tl.source) == ("task", "trailer")
        and tl.from_id in tasks
        or (tl.from_kind, tl.source) == ("run", "trailer")
        and tl.from_id in runs
        or (tl.from_kind, tl.source) == ("commit", "diff")
        and tl.from_id in commits
    }

    assert orphan <= flow.rebuilt
    assert flow.rebuilt - orphan == recorded
    assert link("requirement", "REQ-AUTH-002", "task", "AUTH-003", "contract") in flow.links
    assert not [
        tl for tl in flow.links if tl.source in ("trailer", "diff") and s3 in (tl.from_id, tl.to_id)
    ]
    shared = {
        link("requirement", "REQ-AUTH-001", "task", "AUTH-001", "contract"),
        link("requirement", "REQ-AUTH-001", "task", "AUTH-002", "contract"),
        link("commit", s1, "file", "app/login.py", "diff"),
        link("commit", s2, "file", "app/login.py", "diff"),
    }
    assert shared <= flow.rebuilt
    assert shared <= recorded


def test_ac6_reads_record_nothing_and_rebuild_gives_identical_projections(flow: Flow) -> None:
    assert flow.seq_after_reads == flow.seq_before_reads
    assert flow.count_after_reads == flow.count_before_reads

    assert all(flow.before[t] for t in TABLES)
    assert flow.emptied == {t: [] for t in TABLES}
    assert flow.emptied != flow.before
    for table in TABLES:
        assert flow.after[table] == flow.before[table]
    assert flow.projection_state == [(1, flow.seq_after_reads)]
    assert flow.events_after == flow.events_before
