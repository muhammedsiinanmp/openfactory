"""TASK-030 AC2-AC4: git CLI adapter, real git and a stand-in executable."""

import json
import subprocess
import sys

import pytest

STAND_IN = """\
#!{python}
import json, os, sys
from pathlib import Path

rec = Path({record!r})
with (rec / "starts").open("a") as f:
    f.write("x")
(rec / "args.json").write_text(json.dumps(sys.argv[1:]), encoding="utf-8")
(rec / "cwd.txt").write_text(os.getcwd(), encoding="utf-8")
sys.stderr.write({stderr!r})
sys.stdout.write({stdout!r})
sys.exit({exit_code!r})
"""


@pytest.fixture(autouse=True)
def clean_git_env(monkeypatch):
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(name, raising=False)


def make_repo(tmp_path, added=(), untracked=()):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    for name in (*added, *untracked):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")
    if added:
        subprocess.run(["git", "add", *added], cwd=repo, check=True)
    return repo


def make_stand_in(tmp_path, stdout="", exit_code=0, stderr=""):
    record = tmp_path / "record"
    record.mkdir(exist_ok=True)
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
    return len((record / "starts").read_text())


def test_ac2_returns_tracked_files_only(tmp_path):
    from openfactory.adapters.git_cli import GitCli

    repo = make_repo(tmp_path, added=["a.py", "pkg/b.py"], untracked=["notes.txt"])

    assert GitCli(repo).tracked_files() == ["a.py", "pkg/b.py"]


def test_ac2_reads_repo_not_the_process_working_directory(tmp_path, monkeypatch):
    from openfactory.adapters.git_cli import GitCli

    repo = make_repo(tmp_path, added=["a.py", "pkg/b.py"])
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert GitCli(repo).tracked_files() == ["a.py", "pkg/b.py"]


def test_ac2_empty_repository_gives_empty_list(tmp_path):
    from openfactory.adapters.git_cli import GitCli

    repo = make_repo(tmp_path)

    assert GitCli(repo).tracked_files() == []


def test_ac3_reads_names_the_stand_in_prints_in_order(tmp_path):
    from openfactory.adapters.git_cli import GitCli

    repo = tmp_path / "repo"
    repo.mkdir()
    exe, record = make_stand_in(tmp_path, stdout="z/last.py\0a first.py\0")

    names = GitCli(repo, executable=exe).tracked_files()

    assert names == ["z/last.py", "a first.py"]
    assert starts(record) == 1
    assert json.loads((record / "args.json").read_text())[0] == "ls-files"
    assert (record / "cwd.txt").read_text() == str(repo.resolve())


@pytest.mark.parametrize(
    ("exit_code", "stderr"),
    [(128, "fatal: not a git repository\nhint: second line\n"), (1, "")],
)
def test_ac4_failed_command_raises_git_error_with_text(tmp_path, exit_code, stderr):
    from openfactory.adapters.git_cli import GitCli
    from openfactory.ports.git_provider import GitError

    repo = tmp_path / "repo"
    repo.mkdir()
    exe, record = make_stand_in(tmp_path, exit_code=exit_code, stderr=stderr)

    with pytest.raises(GitError) as caught:
        GitCli(repo, executable=exe).tracked_files()

    assert str(caught.value).splitlines()[0].strip() != ""
    assert starts(record) == 1


def test_ac4_directory_that_is_not_a_repository_raises_git_error(tmp_path):
    from openfactory.adapters.git_cli import GitCli
    from openfactory.ports.git_provider import GitError

    plain = tmp_path / "plain"
    plain.mkdir()

    with pytest.raises(GitError):
        GitCli(plain).tracked_files()
