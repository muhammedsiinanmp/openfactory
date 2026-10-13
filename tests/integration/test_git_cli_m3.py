"""TASK-043 AC2-AC5: head_commit, tracked_files(worktree), stage_changes (real git, stand-in)."""

import json
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


@pytest.fixture(autouse=True)
def clean_git_env(monkeypatch):
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
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


def init_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "commit.gpgsign", "false")
    return repo


def make_repo(tmp_path, files=None):
    """A test repository with a first commit; returns (repo, BASE)."""
    repo = init_repo(tmp_path)
    for name, text in (files or {"README.md": "hi\n"}).items():
        write(repo, name, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "first")
    return repo, git(repo, "rev-parse", "HEAD").strip()


def add_worktree(tmp_path, repo, base):
    worktree = (tmp_path / "wt").resolve()
    git(repo, "worktree", "add", "-q", str(worktree), "-b", "openfactory/AUTH-002", base)
    return worktree


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


# AC2


def test_ac2_head_commit_is_the_sha_of_the_first_commit(tmp_path):
    from openfactory.adapters.git_cli import GitCli

    repo, base = make_repo(tmp_path)

    sha = GitCli(repo).head_commit()

    assert sha == base
    assert re.fullmatch(r"[0-9a-f]{40}", sha)


def test_ac2_head_commit_is_none_without_a_commit(tmp_path):
    from openfactory.adapters.git_cli import GitCli

    repo = init_repo(tmp_path)

    assert GitCli(repo).head_commit() is None


def test_ac2_head_commit_outside_a_repository_raises_git_error(tmp_path):
    from openfactory.adapters.git_cli import GitCli
    from openfactory.ports.git_provider import GitError

    plain = tmp_path / "plain"
    plain.mkdir()

    with pytest.raises(GitError):
        GitCli(plain).head_commit()


def test_ac2_head_commit_of_the_worktree_differs_from_the_checkout(tmp_path):
    from openfactory.adapters.git_cli import GitCli

    repo, base = make_repo(tmp_path)
    worktree = add_worktree(tmp_path, repo, base)
    write(worktree, "second.txt")
    git(worktree, "add", "-A")
    git(worktree, "commit", "-q", "-m", "second")
    second = git(worktree, "rev-parse", "HEAD").strip()

    git_cli = GitCli(repo)

    assert second != base
    assert git_cli.head_commit(worktree) == second
    assert git_cli.head_commit() == base


@pytest.mark.parametrize(
    ("exit_code", "stderr", "is_none"),
    [(1, "", True), (2, "", False), (1, "fatal: something\n", False)],
)
def test_ac2_head_commit_none_only_for_status_1_with_empty_stderr(
    tmp_path, exit_code, stderr, is_none
):
    from openfactory.adapters.git_cli import GitCli
    from openfactory.ports.git_provider import GitError

    repo = tmp_path / "repo"
    repo.mkdir()
    exe, _ = make_stand_in(tmp_path, exit_code=exit_code, stderr=stderr)

    if is_none:
        assert GitCli(repo, executable=exe).head_commit() is None
    else:
        with pytest.raises(GitError):
            GitCli(repo, executable=exe).head_commit()


# AC3


def test_ac3_tracked_files_of_the_worktree_not_the_checkout(tmp_path):
    from openfactory.adapters.git_cli import GitCli

    repo, base = make_repo(tmp_path, {"app/a.py": "a\n", "README.md": "hi\n"})
    worktree = add_worktree(tmp_path, repo, base)
    write(repo, "extra.py")
    git(repo, "add", "extra.py")
    write(worktree, "scratch.txt")

    git_cli = GitCli(repo)

    assert git_cli.tracked_files(worktree) == ["README.md", "app/a.py"]
    assert "extra.py" in git_cli.tracked_files()


# AC4


def test_ac4_stage_changes_lists_every_changed_path_once(tmp_path):
    from openfactory.adapters.git_cli import GitCli

    repo, base = make_repo(
        tmp_path,
        {"app/a.py": "a\n", "app/old.py": "old content\n", ".gitignore": "__pycache__/\n"},
    )
    worktree = add_worktree(tmp_path, repo, base)
    write(worktree, "app/a.py", "changed\n")
    write(worktree, "app/new.py")
    (worktree / "app" / "old.py").rename(worktree / "app" / "renamed.py")
    write(worktree, "app/__pycache__/a.pyc")
    write(worktree, "docs/c.md")
    git(worktree, "add", "docs/c.md")
    git(worktree, "commit", "-q", "-m", "docs")
    before = (git(repo, "status", "--porcelain"), git(repo, "rev-parse", "HEAD"))

    paths = GitCli(repo).stage_changes(worktree, base)

    assert sorted(paths) == [
        "app/a.py",
        "app/new.py",
        "app/old.py",
        "app/renamed.py",
        "docs/c.md",
    ]
    assert len(paths) == len(set(paths))
    status = git(worktree, "status", "--porcelain").splitlines()
    assert all(line[1] == " " for line in status)
    assert (git(repo, "status", "--porcelain"), git(repo, "rev-parse", "HEAD")) == before


def test_ac4_stage_changes_with_no_change_is_empty(tmp_path):
    from openfactory.adapters.git_cli import GitCli

    repo, base = make_repo(tmp_path)
    worktree = add_worktree(tmp_path, repo, base)

    assert GitCli(repo).stage_changes(worktree, base) == []


# AC5


def test_ac5_stage_changes_runs_add_then_diff_in_the_worktree(tmp_path):
    from openfactory.adapters.git_cli import GitCli

    repo = tmp_path / "repo"
    repo.mkdir()
    worktree = tmp_path / "wt"
    worktree.mkdir()
    base = "a" * 40
    exe, record = make_stand_in(tmp_path, stdout="b.py\0a dir/c.py\0")

    paths = GitCli(repo, executable=exe).stage_changes(worktree, base)

    assert paths == ["b.py", "a dir/c.py"]
    runs = starts(record)
    assert [r["args"] for r in runs] == [
        ["add", "-A"],
        ["diff", "--cached", "--name-only", "-z", "--no-renames", base],
    ]
    assert [r["cwd"] for r in runs] == [str(worktree.resolve())] * 2


def test_ac5_failed_add_raises_git_error_and_stops(tmp_path):
    from openfactory.adapters.git_cli import GitCli
    from openfactory.ports.git_provider import GitError

    repo = tmp_path / "repo"
    repo.mkdir()
    worktree = tmp_path / "wt"
    worktree.mkdir()
    exe, record = make_stand_in(
        tmp_path, exit_code=128, stderr="fatal: add failed\nhint: second line\n"
    )

    with pytest.raises(GitError) as caught:
        GitCli(repo, executable=exe).stage_changes(worktree, "a" * 40)

    assert str(caught.value).splitlines()[0].strip() != ""
    assert len(starts(record)) == 1


def test_ac5_head_commit_and_tracked_files_raise_git_error_on_failure(tmp_path):
    from openfactory.adapters.git_cli import GitCli
    from openfactory.ports.git_provider import GitError

    repo = tmp_path / "repo"
    repo.mkdir()
    worktree = tmp_path / "wt"
    worktree.mkdir()
    exe, _ = make_stand_in(tmp_path, exit_code=128, stderr="fatal: broken\nhint: more\n")
    git_cli = GitCli(repo, executable=exe)

    with pytest.raises(GitError) as head:
        git_cli.head_commit()
    with pytest.raises(GitError) as files:
        git_cli.tracked_files(worktree)

    assert str(head.value).splitlines()[0].strip() != ""
    assert str(files.value).splitlines()[0].strip() != ""
