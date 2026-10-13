"""TASK-044 AC2-AC5: reset_soft and commit (real git, stand-in)."""

import json
import os
import re
import subprocess
import sys

import pytest

STAND_IN = """\
#!{python}
import json, os, sys
from pathlib import Path

with Path({record!r}).open("a") as f:
    f.write(json.dumps({{"args": sys.argv[1:], "cwd": os.getcwd()}}) + "\\n")
sys.stderr.write({stderr!r})
sys.stdout.write({stdout!r})
sys.exit({exit_code!r})
"""

MESSAGE = (
    "AUTH-002: Implement login endpoint using membership number\n"
    "\n"
    "Added the login endpoint and its tests.\n"
    "\n"
    "Task: AUTH-002\n"
    "Plan: plan_0007\n"
    "Agent-Run: run_0091\n"
    "Spec: docs/spec/auth.md\n"
    "Gate: passed\n"
)


@pytest.fixture(autouse=True)
def clean_git_env(monkeypatch):
    for name in list(os.environ):
        if name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE") or name.startswith(
            ("GIT_AUTHOR_", "GIT_COMMITTER_")
        ):
            monkeypatch.delenv(name, raising=False)


def git(cwd, *args):
    done = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return done.stdout


def write(root, name, text="x\n"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_repo(tmp_path):
    """A test repository with a first commit holding app/a.py; returns (repo, BASE)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "commit.gpgsign", "false")
    write(repo, "app/a.py", "a\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "first")
    return repo, git(repo, "rev-parse", "HEAD").strip()


def add_worktree(tmp_path, repo, base):
    worktree = (tmp_path / "wt").resolve()
    git(repo, "worktree", "add", "-q", str(worktree), "-b", "openfactory/AUTH-002", base)
    return worktree


def agent_work(worktree):
    """Commit docs/c.md (the agent's commit); change app/a.py and write app/new.py, unadded."""
    write(worktree, "docs/c.md")
    git(worktree, "add", "docs/c.md")
    git(worktree, "commit", "-q", "-m", "agent")
    write(worktree, "app/a.py", "changed\n")
    write(worktree, "app/new.py")
    return git(worktree, "rev-parse", "HEAD").strip()


def checkout_state(repo):
    return (git(repo, "status", "--porcelain"), git(repo, "rev-parse", "HEAD"))


def make_stand_in(tmp_path, stdout="", exit_code=0, stderr=""):
    record = tmp_path / "record.jsonl"
    record.touch()
    script = tmp_path / "fake-git"
    script.write_text(
        STAND_IN.format(
            python=sys.executable,
            record=str(record),
            stderr=stderr,
            stdout=stdout,
            exit_code=exit_code,
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)
    return str(script), record


def starts(record):
    return [json.loads(line) for line in record.read_text().splitlines()]


def staged_ready(tmp_path):
    """Repo, BASE, worktree, AGENT after the steps of AC2."""
    from openfactory.adapters.git_cli import GitCli

    repo, base = make_repo(tmp_path)
    worktree = add_worktree(tmp_path, repo, base)
    agent = agent_work(worktree)
    git_cli = GitCli(repo)
    git_cli.stage_changes(worktree, base)
    git_cli.reset_soft(worktree, base)
    return repo, base, worktree, agent, git_cli


# AC2


def test_ac2_reset_soft_moves_the_branch_to_base_and_keeps_the_changes_staged(tmp_path):
    from openfactory.adapters.git_cli import GitCli

    repo, base = make_repo(tmp_path)
    worktree = add_worktree(tmp_path, repo, base)
    agent_work(worktree)
    before = checkout_state(repo)
    git_cli = GitCli(repo)
    first = git_cli.stage_changes(worktree, base)

    git_cli.reset_soft(worktree, base)

    assert git_cli.head_commit(worktree) == base
    assert git(repo, "rev-parse", "openfactory/AUTH-002").strip() == base
    staged = git(worktree, "diff", "--cached", "--name-only", base).split()
    assert sorted(staged) == ["app/a.py", "app/new.py", "docs/c.md"]
    assert git_cli.stage_changes(worktree, base) == first
    assert checkout_state(repo) == before


# AC3


def test_ac3_commit_makes_one_commit_on_base_with_the_message(tmp_path):
    repo, base, worktree, agent, git_cli = staged_ready(tmp_path)
    before = checkout_state(repo)

    sha = git_cli.commit(worktree, MESSAGE)

    assert re.fullmatch(r"[0-9a-f]{40}", sha)
    assert sha == git(worktree, "rev-parse", "HEAD").strip()
    assert sha != agent
    assert len(git(worktree, "rev-list", f"{base}..HEAD").splitlines()) == 1
    changed = git(worktree, "diff", "--name-only", base, "HEAD").split()
    assert sorted(changed) == ["app/a.py", "app/new.py", "docs/c.md"]
    assert git(worktree, "status", "--porcelain") == ""
    assert git(worktree, "log", "-1", "--format=%B").rstrip("\n") == MESSAGE.rstrip("\n")
    assert checkout_state(repo) == before


def test_ac3_commit_trailers_are_read_by_git(tmp_path):
    _, _, worktree, _, git_cli = staged_ready(tmp_path)

    git_cli.commit(worktree, MESSAGE)

    task = git(worktree, "log", "-1", "--format=%(trailers:key=Task,valueonly)")
    run = git(worktree, "log", "-1", "--format=%(trailers:key=Agent-Run,valueonly)")
    assert task.strip() == "AUTH-002"
    assert run.strip() == "run_0091"


# AC4


def test_ac4_commit_skips_failing_hooks_and_uses_the_configured_identity(tmp_path):
    from openfactory.adapters.git_cli import GitCli

    repo, base = make_repo(tmp_path)
    for hook in ("pre-commit", "commit-msg"):
        path = repo / ".git" / "hooks" / hook
        path.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        path.chmod(0o755)
    worktree = add_worktree(tmp_path, repo, base)
    write(worktree, "docs/c.md")
    git_cli = GitCli(repo)
    git_cli.stage_changes(worktree, base)

    sha = git_cli.commit(worktree, MESSAGE)

    assert re.fullmatch(r"[0-9a-f]{40}", sha)
    who = git(worktree, "log", "-1", "--format=%an <%ae>|%cn <%ce>").strip()
    assert who == "Test <test@example.com>|Test <test@example.com>"


# AC5


def test_ac5_reset_soft_runs_one_reset_in_the_worktree(tmp_path):
    from openfactory.adapters.git_cli import GitCli

    repo = tmp_path / "repo"
    repo.mkdir()
    worktree = tmp_path / "wt"
    worktree.mkdir()
    base = "a" * 40
    exe, record = make_stand_in(tmp_path)

    GitCli(repo, executable=exe).reset_soft(worktree, base)

    runs = starts(record)
    assert [r["args"] for r in runs] == [["reset", "--soft", base]]
    assert [r["cwd"] for r in runs] == [str(worktree.resolve())]


def test_ac5_commit_runs_commit_then_rev_parse_in_the_worktree(tmp_path):
    from openfactory.adapters.git_cli import GitCli

    repo = tmp_path / "repo"
    repo.mkdir()
    worktree = tmp_path / "wt"
    worktree.mkdir()
    sha = "b" * 40
    exe, record = make_stand_in(tmp_path, stdout=sha + "\n")

    result = GitCli(repo, executable=exe).commit(worktree, MESSAGE)

    assert result == sha
    runs = starts(record)
    assert [r["args"] for r in runs] == [
        ["commit", "--no-verify", "-m", MESSAGE],
        ["rev-parse", "--verify", "HEAD"],
    ]
    assert [r["cwd"] for r in runs] == [str(worktree.resolve())] * 2


def test_ac5_failures_raise_git_error_and_commit_stops_after_the_first_process(tmp_path):
    from openfactory.adapters.git_cli import GitCli
    from openfactory.ports.git_provider import GitError

    repo = tmp_path / "repo"
    repo.mkdir()
    worktree = tmp_path / "wt"
    worktree.mkdir()
    exe, record = make_stand_in(
        tmp_path, exit_code=128, stderr="fatal: it failed\nhint: second line\n"
    )
    git_cli = GitCli(repo, executable=exe)

    with pytest.raises(GitError) as reset:
        git_cli.reset_soft(worktree, "a" * 40)
    before = len(starts(record))
    with pytest.raises(GitError) as commit:
        git_cli.commit(worktree, MESSAGE)

    assert str(reset.value).splitlines()[0].strip() != ""
    assert str(commit.value).splitlines()[0].strip() != ""
    assert len(starts(record)) - before == 1


def test_ac5_commit_with_nothing_staged_raises_git_error(tmp_path):
    from openfactory.adapters.git_cli import GitCli
    from openfactory.ports.git_provider import GitError

    repo, base = make_repo(tmp_path)
    worktree = add_worktree(tmp_path, repo, base)
    git_cli = GitCli(repo)

    with pytest.raises(GitError) as caught:
        git_cli.commit(worktree, MESSAGE)

    assert str(caught.value).strip() != ""
    assert git_cli.head_commit(worktree) == base
