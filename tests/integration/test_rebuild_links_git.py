"""TASK-088 AC4-AC6: rebuild_links on real git and against the projector
(docs/tasks/TASK-088-rebuild-links-from-git.md)."""

import os
import sqlite3
import subprocess
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from openfactory.adapters.git_cli import GitCli
from openfactory.adapters.sqlite_projector import SqliteProjector
from openfactory.adapters.sqlite_store import SqliteEventStore
from openfactory.domain.commit_message import build_commit_message
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import (
    CommitRecordedPayload,
    PlanApprovedPayload,
    PlanCreatedPayload,
)
from openfactory.domain.traces import TraceLink


@pytest.fixture(autouse=True)
def clean_git_env(monkeypatch):
    for name in list(os.environ):
        if name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE") or name.startswith(
            ("GIT_AUTHOR_", "GIT_COMMITTER_")
        ):
            monkeypatch.delenv(name, raising=False)


def git(cwd, *args, input=None):
    done = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        input=input,
    )
    return done.stdout


def write(root, name, text="x\n"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "commit.gpgsign", "false")
    write(repo, "app/a.py", "a\nb\nc\nd\ne\nf\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "first")
    return repo


def head(cwd):
    return git(cwd, "rev-parse", "HEAD").strip()


def add_worktree(tmp_path, repo, branch):
    worktree = (tmp_path / ("wt-" + branch.replace("/", "-"))).resolve()
    git(repo, "worktree", "add", "-q", str(worktree), "-b", branch, "main")
    return worktree


def commit(worktree, message, files=None):
    for name, text in (files or {}).items():
        write(worktree, name, text)
    git(worktree, "add", "-A")
    git(worktree, "commit", "-q", "-F", "-", input=message)
    return head(worktree)


def message(task_id, run_id, requirements):
    contract = SimpleNamespace(
        task_id=task_id,
        objective="Do it",
        requirements=requirements,
        acceptance_criteria=["AC1"],
    )
    return build_commit_message(contract, "Body.", run_id, "1.17")


def link(*fields):
    return TraceLink(
        from_kind=fields[0], from_id=fields[1], to_kind=fields[2], to_id=fields[3], source=fields[4]
    )


def commit_links(sha, task_id, run_id, requirements, files):
    return (
        {link("requirement", r, "task", task_id, "contract") for r in requirements}
        | {
            link("task", task_id, "run", run_id, "trailer"),
            link("run", run_id, "commit", sha, "trailer"),
        }
        | {link("commit", sha, "file", f, "diff") for f in files}
    )


# AC4


def test_task088_ac4_two_branches_give_exactly_the_links_of_their_task_commits(tmp_path):
    from openfactory.app.rebuild_links import rebuild_links

    repo = make_repo(tmp_path)
    wa = add_worktree(tmp_path, repo, "openfactory/A")
    a1 = commit(wa, message("A", "run_0001", ["REQ-A-1", "REQ-A-2"]), {"one.py": "1\n"})
    git(wa, "mv", "app/a.py", "app/renamed.py")
    a2 = commit(wa, message("A", "run_0002", ["REQ-A-1"]))
    wb = add_worktree(tmp_path, repo, "openfactory/B")
    b1 = commit(wb, message("B", "run_0003", ["REQ-B-1"]), {"b.py": "1\n", "my dir/c d.py": "2\n"})
    write(repo, "main_only.py")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "main only")

    links = rebuild_links(git=GitCli(repo))

    assert links == (
        commit_links(a1, "A", "run_0001", ["REQ-A-1", "REQ-A-2"], ["one.py"])
        | commit_links(a2, "A", "run_0002", ["REQ-A-1"], ["app/a.py", "app/renamed.py"])
        | commit_links(b1, "B", "run_0003", ["REQ-B-1"], ["b.py", "my dir/c d.py"])
    )


# AC5


def test_task088_ac5_a_call_changes_no_event_or_trace_link_row(tmp_path):
    from openfactory.app.rebuild_links import rebuild_links
    from openfactory.cli import app

    repo = make_repo(tmp_path)
    assert CliRunner().invoke(app, ["init", str(repo)]).exit_code == 0
    wt = add_worktree(tmp_path, repo, "openfactory/A")
    commit(wt, message("A", "run_0001", ["REQ-A-1"]), {"one.py": "1\n"})
    db = repo / ".openfactory" / "openfactory.db"

    def counts():
        conn = sqlite3.connect(db)
        try:
            return tuple(
                conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("events", "trace_links")
            )
        finally:
            conn.close()

    before = counts()
    assert rebuild_links(git=GitCli(repo))
    assert counts() == before


# AC6: the rebuild and the projector write the same shape


def task_contract(task_id, requirements):
    return TaskContract(
        task_id=task_id,
        objective="Do the work",
        requirements=requirements,
        acceptance_criteria=["AC-1"],
        depends_on=[],
        components=["auth"],
        role="implementer",
        allowed_paths=["app/**"],
        forbidden_paths=[".env"],
        required_gates=["path_check", "ruff", "pytest", "gitleaks", "review"],
        limits=Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.5),
    )


def ev(stream, type_, payload, actor="orchestrator"):
    return Event(
        event_id=uuid4(),
        stream=stream,
        type=type_,
        payload=payload,
        actor=actor,
        created_at=datetime.now(UTC),
    )


def test_task088_ac6_rebuilt_links_equal_the_rows_the_projector_writes(tmp_path):
    from openfactory.app.rebuild_links import rebuild_links

    repo = make_repo(tmp_path)
    wt = add_worktree(tmp_path, repo, "openfactory/AUTH-002")
    files = {"one.py": "1\n", "pkg/two.py": "2\n"}
    sha = commit(wt, message("AUTH-002", "run_0091", ["REQ-A-1", "REQ-A-2"]), files)
    rebuilt = rebuild_links(git=GitCli(repo))

    store = SqliteEventStore(tmp_path / "events.db")
    conn = sqlite3.connect(tmp_path / "projections.db")
    try:
        projector = SqliteProjector(conn)
        projector.create_tables()
        plan = PlanCreatedPayload(
            plan_id="plan_01",
            spec_version="sv_01",
            policy_hash="a" * 64,
            run_id="run_0001",
            tasks=[task_contract("AUTH-002", ["REQ-A-1", "REQ-A-2"])],
        ).model_dump(mode="json")
        recorded = CommitRecordedPayload(
            sha=sha,
            task_id="AUTH-002",
            run_id="run_0091",
            branch="openfactory/AUTH-002",
            spec_version="sv_01",
            files=sorted(files),
        ).model_dump(mode="json")
        for event in (
            ev("plan:plan_01", EventType.PlanCreated, plan),
            ev(
                "plan:plan_01",
                EventType.PlanApproved,
                PlanApprovedPayload(plan_id="plan_01").model_dump(mode="json"),
                actor="human",
            ),
            ev("task:AUTH-002", EventType.CommitRecorded, recorded),
        ):
            projector.apply(store.append(event))
        rows = conn.execute(
            "SELECT from_kind, from_id, to_kind, to_id, source FROM trace_links"
            " WHERE source IN ('contract', 'trailer', 'diff') ORDER BY 1, 2, 3, 4, 5"
        ).fetchall()
    finally:
        conn.close()
        store.close()

    assert rows
    assert {TraceLink(**dict(zip(TraceLink.model_fields, row, strict=True))) for row in rows} == (
        rebuilt
    )
