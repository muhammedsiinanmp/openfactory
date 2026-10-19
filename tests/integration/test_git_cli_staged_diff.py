"""TASK-063 AC2-AC3: GitCli.staged_diff (real git with a linked worktree, stand-in git)."""

import json
import os
import subprocess
import sys

import pytest

from openfactory.adapters.git_cli import GitCli
from openfactory.ports.git_provider import GitError

STAND_IN = """\
#!{python}
import json, os, sys
from pathlib import Path

with Path({record!r}).open("a") as f:
    f.write(json.dumps({{"args": sys.argv[1:], "cwd": os.getcwd()}}) + "\\n")
sys.stderr.write({stderr!r})
sys.stdout.buffer.write({stdout!r})
sys.exit({exit_code!r})
"""


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


def make_stand_in(tmp_path, stdout=b"", exit_code=0, stderr=""):
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


def test_ac2_staged_diff_equals_git_diff_cached_and_leaves_out_unstaged_files(tmp_path):
    repo, base = make_repo(tmp_path)
    worktree = add_worktree(tmp_path, repo, base)
    write(worktree, "app/a.py", "changed\n")
    write(worktree, "app/new.py", "new file\n")
    git_cli = GitCli(repo)
    git_cli.stage_changes(worktree, base)
    write(worktree, ".cache/junk.txt", "late\n")

    text = git_cli.staged_diff(worktree, base)

    assert text == git(worktree, "diff", "--cached", base)
    assert "app/a.py" in text
    assert "+changed" in text
    assert "app/new.py" in text
    assert "+new file" in text
    assert "junk.txt" not in text


def test_ac2_staged_diff_is_empty_when_nothing_is_staged(tmp_path):
    repo, base = make_repo(tmp_path)
    worktree = add_worktree(tmp_path, repo, base)
    git_cli = GitCli(repo)
    git_cli.stage_changes(worktree, base)

    assert git_cli.staged_diff(worktree, base) == ""


# AC3


def test_ac3_staged_diff_starts_one_process_with_the_arguments_in_the_worktree(tmp_path):
    script, record = make_stand_in(tmp_path, stdout=b"diff text\n")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "wt").mkdir()

    text = GitCli(repo, executable=script).staged_diff(repo / "wt", "abc123")

    assert text == "diff text\n"
    runs = starts(record)
    assert len(runs) == 1
    assert runs[0]["args"] == ["diff", "--cached", "abc123"]
    assert os.path.realpath(runs[0]["cwd"]) == os.path.realpath(repo / "wt")


def test_ac3_non_utf8_standard_output_comes_back_with_replacement_characters(tmp_path):
    script, _ = make_stand_in(tmp_path, stdout=b"+caf\xe9 ok\n")
    repo = tmp_path / "repo"
    repo.mkdir()

    text = GitCli(repo, executable=script).staged_diff(repo, "abc123")

    assert text == "+caf� ok\n"


@pytest.mark.parametrize(
    ("stderr", "message"),
    [
        ("  fatal: bad revision 'abc123'\nmore\n", "fatal: bad revision 'abc123'\nmore"),
        ("", "git exited with status 3"),
    ],
)
def test_ac3_non_zero_exit_raises_git_error(tmp_path, stderr, message):
    script, _ = make_stand_in(tmp_path, exit_code=3, stderr=stderr)
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(GitError) as raised:
        GitCli(repo, executable=script).staged_diff(repo, "abc123")

    assert str(raised.value) == message


def test_ac3_git_that_cannot_be_started_raises_git_error(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(GitError, match="^git could not be started: "):
        GitCli(repo, executable=str(tmp_path / "missing-git")).staged_diff(repo, "abc123")
