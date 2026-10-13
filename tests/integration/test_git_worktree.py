"""TASK-045 AC2-AC5: GitWorktree (real git, stand-in)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

STAND_IN = """\
#!{python}
import json, os, sys
from pathlib import Path

with Path({record!r}).open("a") as f:
    f.write(json.dumps({{"args": sys.argv[1:], "cwd": os.getcwd()}}) + "\\n")
sys.stderr.write({stderr!r})
sys.exit({exit_code!r})
"""

WT = ".openfactory/worktrees/AUTH-002"


@pytest.fixture(autouse=True)
def clean_git_env(monkeypatch):
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(name, raising=False)


def git(cwd, *args, check=True):
    done = subprocess.run(
        ["git", *args], cwd=cwd, check=check, capture_output=True, text=True, encoding="utf-8"
    )
    return done.stdout


def write(root, name, text="x\n"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def commit_file(root, name, text="y\n"):
    write(root, name, text)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", f"add {name}")
    return git(root, "rev-parse", "HEAD").strip()


def make_repo(tmp_path):
    """A test repository; returns (repo, BASE, TIP)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "commit.gpgsign", "false")
    write(repo, ".openfactory/.gitignore", "*\n")
    write(repo, "app/a.py", "a\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "first")
    base = git(repo, "rev-parse", "HEAD").strip()
    tip = commit_file(repo, "app/b.py")
    return repo, base, tip


def checkout_state(repo):
    return (
        git(repo, "status", "--porcelain"),
        git(repo, "rev-parse", "HEAD"),
        git(repo, "branch", "--show-current"),
    )


def worktree_count(repo):
    out = git(repo, "worktree", "list", "--porcelain")
    return len([line for line in out.splitlines() if line.startswith("worktree ")])


def branch_exists(repo, name):
    done = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"],
        cwd=repo,
        capture_output=True,
    )
    return done.returncode == 0


def make_stand_in(tmp_path, exit_code=0, stderr=""):
    record = tmp_path / "record.jsonl"
    record.touch()
    script = tmp_path / "fake-git"
    script.write_text(
        STAND_IN.format(
            python=sys.executable, record=str(record), stderr=stderr, exit_code=exit_code
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)
    return str(script), record


def starts(record):
    return [json.loads(line) for line in record.read_text().splitlines()]


# AC2


def test_ac2_create_makes_the_worktree_from_base_and_leaves_the_checkout_alone(
    tmp_path, monkeypatch
):
    from openfactory.adapters.git_cli import GitCli
    from openfactory.adapters.git_worktree import GitWorktree

    repo, base, tip = make_repo(tmp_path)
    write(repo, "app/draft.py")
    before = checkout_state(repo)

    path = GitWorktree(repo).create("AUTH-002", base)

    assert path == Path(WT)
    worktree = repo / path
    assert (worktree / "app" / "a.py").is_file()
    assert not (worktree / "app" / "draft.py").exists()
    assert git(worktree, "rev-parse", "HEAD").strip() == base != tip
    assert git(worktree, "branch", "--show-current").strip() == "openfactory/AUTH-002"
    monkeypatch.chdir(tmp_path)
    assert GitCli(repo).head_commit(path) == base
    assert checkout_state(repo) == before


# AC3


def test_ac3_remove_deletes_worktree_and_branch_and_makes_the_agent_commit_unreachable(
    tmp_path,
):
    from openfactory.adapters.git_worktree import GitWorktree

    repo, base, tip = make_repo(tmp_path)
    manager = GitWorktree(repo)
    worktree = repo / manager.create("AUTH-002", base)
    agent = commit_file(worktree, "docs/c.md")
    write(worktree, "app/a.py", "changed\n")
    write(worktree, "app/new.py")
    before = checkout_state(repo)

    manager.remove("AUTH-002")

    assert not worktree.exists()
    assert worktree_count(repo) == 1
    assert not branch_exists(repo, "openfactory/AUTH-002")
    assert git(repo, "branch", "--contains", agent).strip() == ""
    again = repo / manager.create("AUTH-002", tip)
    assert git(again, "rev-parse", "HEAD").strip() == tip
    manager.remove("AUTH-002")
    assert checkout_state(repo) == before


def test_ac3_remove_does_nothing_without_worktree_and_branch_and_removes_a_lone_branch(
    tmp_path,
):
    from openfactory.adapters.git_worktree import GitWorktree

    repo, base, _ = make_repo(tmp_path)
    manager = GitWorktree(repo)

    manager.remove("AUTH-002")
    git(repo, "branch", "openfactory/AUTH-002", base)
    manager.remove("AUTH-002")

    assert not branch_exists(repo, "openfactory/AUTH-002")


# AC4


def test_ac4_remove_worktree_keeps_the_branch_and_its_commit(tmp_path):
    from openfactory.adapters.git_worktree import GitWorktree

    repo, base, _ = make_repo(tmp_path)
    manager = GitWorktree(repo)
    worktree = repo / manager.create("AUTH-002", base)
    done = commit_file(worktree, "docs/c.md")

    manager.remove_worktree("AUTH-002")
    manager.remove_worktree("AUTH-002")

    assert not worktree.exists()
    assert git(repo, "rev-parse", "openfactory/AUTH-002").strip() == done
    second = repo / manager.create("AUTH-003", done)
    assert git(second, "rev-parse", "HEAD").strip() == done


# AC5


def test_ac5_create_runs_one_worktree_add_in_the_repo(tmp_path):
    from openfactory.adapters.git_worktree import GitWorktree

    repo = tmp_path / "repo"
    repo.mkdir()
    base = "a" * 40
    exe, record = make_stand_in(tmp_path)

    GitWorktree(repo, executable=exe).create("AUTH-002", base)

    runs = starts(record)
    assert [r["args"] for r in runs] == [
        ["worktree", "add", WT, "-b", "openfactory/AUTH-002", base]
    ]
    assert [r["cwd"] for r in runs] == [str(repo.resolve())]


def test_ac5_failures_raise_git_error_with_the_git_texts(tmp_path):
    from openfactory.adapters.git_worktree import GitWorktree
    from openfactory.ports.git_provider import GitError

    repo = tmp_path / "repo"
    repo.mkdir()
    base = "a" * 40
    exe, _ = make_stand_in(tmp_path, exit_code=128, stderr="fatal: one\nhint: two\n")
    with pytest.raises(GitError) as with_text:
        GitWorktree(repo, executable=exe).create("AUTH-002", base)
    assert str(with_text.value) == "fatal: one\nhint: two"

    silent = tmp_path / "silent"
    silent.mkdir()
    exe, _ = make_stand_in(silent, exit_code=128)
    with pytest.raises(GitError) as empty:
        GitWorktree(repo, executable=exe).create("AUTH-002", base)
    assert str(empty.value) == "git exited with status 128"

    with pytest.raises(GitError) as missing:
        GitWorktree(repo, executable=str(tmp_path / "nope")).create("AUTH-002", base)
    assert str(missing.value).startswith("git could not be started: ")


def test_ac5_create_on_a_sha_that_is_no_commit_raises_git_error(tmp_path):
    from openfactory.adapters.git_worktree import GitWorktree
    from openfactory.ports.git_provider import GitError

    repo, _, _ = make_repo(tmp_path)

    with pytest.raises(GitError) as caught:
        GitWorktree(repo).create("AUTH-002", "a" * 40)

    assert str(caught.value).strip() != ""
