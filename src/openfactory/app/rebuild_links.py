"""Rebuild of trace links from git: the links the trailers and diffs of platform commits give.

See docs/spec/phase1-spec.md ("Traceability", the paragraph after "Commit trailers") and
ADR-018 ("Rebuild from git"). It reads the commits reachable from the `openfactory/*`
branches once and keeps those with a `Task` trailer. Each gives requirement → task
(`contract`) per id in `Requirements`, task → run and run → commit (`trailer`) from `Task`,
`Agent-Run` and the sha, and commit → file (`diff`) per changed path. A missing trailer
gives no links of its own. Keys match exactly and the first value of a repeated key wins.
It is a function, not a command: it writes nothing and returns the links.
"""

from openfactory.domain.git_history import BranchCommit
from openfactory.domain.traces import TraceLink
from openfactory.ports.git_provider import GitProvider


def rebuild_links(*, git: GitProvider) -> set[TraceLink]:
    links: set[TraceLink] = set()
    for commit in git.branch_commits():
        links |= _commit_links(commit)
    return links


def _commit_links(commit: BranchCommit) -> set[TraceLink]:
    trailers: dict[str, str] = {}
    for key, value in commit.trailers:
        trailers.setdefault(key, value)
    task = trailers.get("Task")
    if task is None:
        return set()
    links = {
        TraceLink(
            from_kind="requirement", from_id=req, to_kind="task", to_id=task, source="contract"
        )
        for req in (piece.strip() for piece in trailers.get("Requirements", "").split(","))
        if req
    }
    run = trailers.get("Agent-Run")
    if run is not None:
        links.add(
            TraceLink(from_kind="task", from_id=task, to_kind="run", to_id=run, source="trailer")
        )
        links.add(
            TraceLink(
                from_kind="run", from_id=run, to_kind="commit", to_id=commit.sha, source="trailer"
            )
        )
    links |= {
        TraceLink(from_kind="commit", from_id=commit.sha, to_kind="file", to_id=path, source="diff")
        for path in commit.files
    }
    return links
