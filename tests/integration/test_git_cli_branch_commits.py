"""TASK-087 AC1-AC5: GitCli.branch_commits (real git with linked worktrees, stand-in git)."""

import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from openfactory.adapters.git_cli import GitCli
from openfactory.domain.commit_message import build_commit_message
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
    write(repo, "app/a.py", "a\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "first")
    return repo


def head(cwd):
    return git(cwd, "rev-parse", "HEAD").strip()


def add_worktree(tmp_path, repo, branch, base="main"):
    worktree = (tmp_path / ("wt-" + branch.replace("/", "-"))).resolve()
    git(repo, "worktree", "add", "-q", str(worktree), "-b", branch, base)
    return worktree


def commit(worktree, message, files=None, remove=(), allow_empty=False):
    for name, text in (files or {}).items():
        write(worktree, name, text)
    for name in remove:
        git(worktree, "rm", "-q", name)
    git(worktree, "add", "-A")
    args = ["commit", "-q", "-F", "-"]
    if allow_empty:
        args.append("--allow-empty")
    git(worktree, *args, input=message)
    return head(worktree)


def task_message(task_id="AUTH-002"):
    contract = SimpleNamespace(
        task_id=task_id,
        objective="Do it",
        requirements=["REQ-A-1", "REQ-A-2"],
        acceptance_criteria=["AC1", "AC2"],
    )
    return build_commit_message(contract, "Body text.", "run_0091", "1.17")


def by_sha(commits):
    return {c.sha: c for c in commits}


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


# AC1


def test_task087_branch_commit_is_frozen_and_forbids_extra_fields():
    from openfactory.domain.git_history import BranchCommit

    commit_ = BranchCommit(sha="abc", trailers=[("Task", "T-1")], files=["a"])
    with pytest.raises(ValidationError):
        commit_.sha = "other"
    with pytest.raises(ValidationError):
        BranchCommit(sha="abc", trailers=[], files=[], extra=1)


def test_task087_domain_module_imports_no_outer_layer():
    import ast
    from pathlib import Path

    from openfactory.domain import git_history

    tree = ast.parse(Path(git_history.__file__).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    bad = [
        n
        for n in names
        if n.startswith(("openfactory.ports", "openfactory.adapters", "openfactory.app"))
    ]
    assert bad == []


def test_task087_listing_leaves_head_refs_and_index_unchanged(tmp_path):
    repo = make_repo(tmp_path)
    wt = add_worktree(tmp_path, repo, "openfactory/A")
    commit(wt, task_message(), {"x.py": "1\n"})
    write(repo, "staged.py")
    git(repo, "add", "staged.py")
    before = (
        head(repo),
        git(repo, "for-each-ref"),
        git(repo, "ls-files", "-s"),
        git(repo, "status", "--porcelain"),
    )

    GitCli(repo).branch_commits()

    after = (
        head(repo),
        git(repo, "for-each-ref"),
        git(repo, "ls-files", "-s"),
        git(repo, "status", "--porcelain"),
    )
    assert after == before


# AC2


def test_task087_lists_commits_of_openfactory_branches_once_each(tmp_path):
    repo = make_repo(tmp_path)
    base = head(repo)
    wa = add_worktree(tmp_path, repo, "openfactory/A")
    a1 = commit(wa, task_message("A"), {"a1.py": "1\n"})
    a2 = commit(wa, task_message("A"), {"a2.py": "2\n"})
    wb = add_worktree(tmp_path, repo, "openfactory/B")
    b1 = commit(wb, task_message("B"), {"b1.py": "1\n"})

    commits = GitCli(repo).branch_commits()

    shas = [c.sha for c in commits]
    assert len(shas) == len(set(shas))
    assert set(shas) == {base, a1, a2, b1}


def test_task087_leaves_out_main_other_branches_and_deleted_branches(tmp_path):
    repo = make_repo(tmp_path)
    wa = add_worktree(tmp_path, repo, "openfactory/A")
    a1 = commit(wa, task_message("A"), {"a1.py": "1\n"})
    write(repo, "m.py")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "main only")
    main_only = head(repo)
    wf = add_worktree(tmp_path, repo, "feature/x")
    feature_only = commit(wf, "feature\n", {"f.py": "1\n"})
    wd = add_worktree(tmp_path, repo, "openfactory/D")
    deleted_only = commit(wd, task_message("D"), {"d.py": "1\n"})
    git(repo, "worktree", "remove", "--force", str(wd))
    git(repo, "branch", "-D", "openfactory/D")

    shas = {c.sha for c in GitCli(repo).branch_commits()}

    assert a1 in shas
    assert not {main_only, feature_only, deleted_only} & shas


def test_task087_repo_without_openfactory_branch_gives_empty_list(tmp_path):
    repo = make_repo(tmp_path)

    assert GitCli(repo).branch_commits() == []


# AC3


def test_task087_trailers_of_a_build_commit_message_in_order(tmp_path):
    repo = make_repo(tmp_path)
    wt = add_worktree(tmp_path, repo, "openfactory/A")
    sha = commit(wt, task_message("AUTH-002"), {"x.py": "1\n"})

    found = by_sha(GitCli(repo).branch_commits())[sha]

    assert found.trailers == [
        ("Task", "AUTH-002"),
        ("Requirements", "REQ-A-1, REQ-A-2"),
        ("Acceptance-Criteria", "AC1, AC2"),
        ("Agent-Run", "run_0091"),
        ("Spec-Version", "1.17"),
    ]


def test_task087_folded_trailer_is_unfolded_and_body_lines_are_not_trailers(tmp_path):
    repo = make_repo(tmp_path)
    wt = add_worktree(tmp_path, repo, "openfactory/A")
    message = (
        "Subject\n\nNote: this is body text\n\nSecond paragraph.\n\n"
        "Task: T-1\nRequirements: REQ-A-1,\n REQ-A-2\n"
    )
    sha = commit(wt, message, {"x.py": "1\n"})

    found = by_sha(GitCli(repo).branch_commits())[sha]

    assert found.trailers == [("Task", "T-1"), ("Requirements", "REQ-A-1, REQ-A-2")]


def test_task087_commit_without_trailers_gives_empty_list(tmp_path):
    repo = make_repo(tmp_path)
    wt = add_worktree(tmp_path, repo, "openfactory/A")
    sha = commit(wt, "Just a subject\n\nSome: body\n\nplain text\n", {"x.py": "1\n"})

    assert by_sha(GitCli(repo).branch_commits())[sha].trailers == []


# AC4


def test_task087_files_are_added_modified_and_deleted_paths(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, "app/gone.py")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "second")
    wt = add_worktree(tmp_path, repo, "openfactory/A")
    sha = commit(
        wt, task_message(), {"app/a.py": "changed\n", "docs/new.md": "n\n"}, remove=["app/gone.py"]
    )

    found = by_sha(GitCli(repo).branch_commits())[sha]

    assert set(found.files) == {"app/a.py", "docs/new.md", "app/gone.py"}
    assert len(found.files) == 3


def test_task087_rename_lists_old_and_new_path(tmp_path):
    repo = make_repo(tmp_path)
    wt = add_worktree(tmp_path, repo, "openfactory/A")
    git(wt, "mv", "app/a.py", "app/renamed.py")
    sha = commit(wt, task_message())

    found = by_sha(GitCli(repo).branch_commits())[sha]

    assert set(found.files) == {"app/a.py", "app/renamed.py"}


def test_task087_path_with_space_and_non_ascii_comes_back_unquoted(tmp_path):
    repo = make_repo(tmp_path)
    wt = add_worktree(tmp_path, repo, "openfactory/A")
    sha = commit(wt, task_message(), {"my dir/a b.py": "1\n", "café.py": "1\n"})

    found = by_sha(GitCli(repo).branch_commits())[sha]

    assert set(found.files) == {"my dir/a b.py", "café.py"}


def test_task087_second_commit_lists_only_its_own_paths(tmp_path):
    repo = make_repo(tmp_path)
    wt = add_worktree(tmp_path, repo, "openfactory/A")
    first = commit(wt, task_message(), {"one.py": "1\n"})
    second = commit(wt, task_message(), {"two.py": "2\n"})

    commits = by_sha(GitCli(repo).branch_commits())

    assert set(commits[first].files) == {"one.py"}
    assert set(commits[second].files) == {"two.py"}


def test_task087_commit_listing_no_files_still_comes_back_with_empty_files(tmp_path):
    repo = make_repo(tmp_path)
    wt = add_worktree(tmp_path, repo, "openfactory/A")
    empty = commit(wt, task_message(), allow_empty=True)
    after = commit(wt, task_message(), {"y.py": "1\n"})

    commits = by_sha(GitCli(repo).branch_commits())

    assert commits[empty].files == []
    assert commits[empty].trailers[0] == ("Task", "AUTH-002")
    assert commits[after].files == ["y.py"]


# AC5


def test_task087_starts_one_git_log_process_in_the_repo(tmp_path):
    script, record = make_stand_in(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()

    result = GitCli(repo, executable=script).branch_commits()

    assert result == []
    runs = [json.loads(line) for line in record.read_text().splitlines()]
    assert len(runs) == 1
    assert runs[0]["args"][0] == "log"
    assert "--branches=openfactory/*" in runs[0]["args"]
    assert "--no-renames" in runs[0]["args"]
    assert os.path.realpath(runs[0]["cwd"]) == os.path.realpath(repo)


@pytest.mark.parametrize(
    ("stderr", "message"),
    [
        ("  fatal: bad object\nmore\n", "fatal: bad object\nmore"),
        ("", "git exited with status 3"),
    ],
)
def test_task087_non_zero_exit_raises_git_error(tmp_path, stderr, message):
    script, _ = make_stand_in(tmp_path, exit_code=3, stderr=stderr)
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(GitError) as raised:
        GitCli(repo, executable=script).branch_commits()

    assert str(raised.value) == message


def test_task087_git_that_cannot_be_started_raises_git_error(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(GitError, match="^git could not be started: "):
        GitCli(repo, executable=str(tmp_path / "missing-git")).branch_commits()
