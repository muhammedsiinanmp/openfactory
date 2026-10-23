"""TASK-088 AC1-AC5: rebuild_links with a fake GitProvider
(docs/tasks/TASK-088-rebuild-links-from-git.md)."""

import ast
import inspect
from pathlib import Path

from openfactory.domain.git_history import BranchCommit
from openfactory.domain.traces import TraceLink

S1 = "a" * 40
S2 = "b" * 40
S3 = "c" * 40
CLI_SRC = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "cli.py"


class FakeGit:
    def __init__(self, commits):
        self.commits = commits
        self.calls = []

    def branch_commits(self):
        self.calls.append("branch_commits")
        return self.commits

    def __getattr__(self, name):
        raise AssertionError(f"unexpected GitProvider call: {name}")


def rebuild(*commits):
    from openfactory.app.rebuild_links import rebuild_links

    return rebuild_links(git=FakeGit(list(commits)))


def link(*fields):
    return TraceLink(
        from_kind=fields[0], from_id=fields[1], to_kind=fields[2], to_id=fields[3], source=fields[4]
    )


def full(sha=S1, task="AUTH-002", run="run_0091", reqs="REQ-A-1, REQ-A-2", files=("a.py",)):
    return BranchCommit(
        sha=sha,
        trailers=[
            ("Task", task),
            ("Requirements", reqs),
            ("Acceptance-Criteria", "AC1, AC2"),
            ("Agent-Run", run),
            ("Spec-Version", "1.17"),
        ],
        files=list(files),
    )


# AC1


def test_task088_ac1_commits_without_a_task_trailer_give_no_links():
    no_trailers = BranchCommit(sha=S1, trailers=[], files=["x.py"])
    no_task = BranchCommit(
        sha=S2,
        trailers=[("Requirements", "REQ-A-1"), ("Agent-Run", "run_0001")],
        files=["y.py"],
    )

    assert rebuild(no_trailers, no_task) == set()


def test_task088_ac1_empty_listing_gives_empty_set_and_one_call_only():
    from openfactory.app.rebuild_links import rebuild_links

    fake = FakeGit([full()])
    rebuild_links(git=fake)

    assert fake.calls == ["branch_commits"]
    assert rebuild() == set()


# AC2


def test_task088_ac2_each_requirement_gives_a_contract_link_and_nothing_else_from_the_list():
    links = rebuild(full(files=()))

    contract = {x for x in links if x.source == "contract"}
    assert contract == {
        link("requirement", "REQ-A-1", "task", "AUTH-002", "contract"),
        link("requirement", "REQ-A-2", "task", "AUTH-002", "contract"),
    }
    assert {x.source for x in links} == {"contract", "trailer"}
    assert len(links) == 4


# AC3


def test_task088_ac3_task_run_and_run_commit_trailer_links():
    links = rebuild(full(reqs="REQ-A-1", files=()))

    assert links == {
        link("requirement", "REQ-A-1", "task", "AUTH-002", "contract"),
        link("task", "AUTH-002", "run", "run_0091", "trailer"),
        link("run", "run_0091", "commit", S1, "trailer"),
    }


def test_task088_ac3_two_tasks_give_their_own_links_and_duplicates_collapse():
    first = full(sha=S1, task="T-1", run="run_0001", reqs="REQ-A-1", files=())
    second = full(sha=S2, task="T-2", run="run_0002", reqs="REQ-A-1", files=())
    again = full(sha=S3, task="T-1", run="run_0001", reqs="REQ-A-1", files=())

    links = rebuild(first, second, again)

    assert link("task", "T-1", "run", "run_0001", "trailer") in links
    assert link("task", "T-2", "run", "run_0002", "trailer") in links
    assert link("run", "run_0001", "commit", S1, "trailer") in links
    assert link("run", "run_0001", "commit", S3, "trailer") in links
    assert link("run", "run_0002", "commit", S2, "trailer") in links
    # The shared links appear once: 2 contract + 2 task->run + 3 run->commit.
    assert len(links) == 7


# AC4


def test_task088_ac4_each_file_gives_a_diff_link_with_the_path_unchanged():
    links = rebuild(full(files=("app/a.py", "my dir/b c.py", "café.py")))

    diff = {x for x in links if x.source == "diff"}
    assert diff == {
        link("commit", S1, "file", "app/a.py", "diff"),
        link("commit", S1, "file", "my dir/b c.py", "diff"),
        link("commit", S1, "file", "café.py", "diff"),
    }


# Open question 1


def test_task088_oq1_no_agent_run_gives_no_trailer_links_but_keeps_the_rest():
    commit = BranchCommit(
        sha=S1,
        trailers=[("Task", "T-1"), ("Requirements", "REQ-A-1")],
        files=["a.py"],
    )

    assert rebuild(commit) == {
        link("requirement", "REQ-A-1", "task", "T-1", "contract"),
        link("commit", S1, "file", "a.py", "diff"),
    }


def test_task088_oq1_no_requirements_gives_no_contract_links_but_keeps_the_rest():
    commit = BranchCommit(
        sha=S1,
        trailers=[("Task", "T-1"), ("Agent-Run", "run_0001")],
        files=["a.py"],
    )

    assert rebuild(commit) == {
        link("task", "T-1", "run", "run_0001", "trailer"),
        link("run", "run_0001", "commit", S1, "trailer"),
        link("commit", S1, "file", "a.py", "diff"),
    }


# AC5


def test_task088_ac5_module_imports_no_adapter_cli_or_sqlite_and_takes_only_git():
    from openfactory.app import rebuild_links as module

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    assert [n for n in names if n.startswith(("openfactory.adapters", "openfactory.cli"))] == []
    assert "sqlite3" not in names
    assert list(inspect.signature(module.rebuild_links).parameters) == ["git"]


def test_task088_ac5_cli_defines_no_command_that_calls_the_rebuild():
    text = CLI_SRC.read_text(encoding="utf-8")

    assert "rebuild_links" not in text
