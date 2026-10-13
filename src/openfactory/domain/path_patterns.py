"""Path patterns and the path check: one glob syntax for contracts and the policy.

See docs/spec/phase1-spec.md ("Task contract": "Path patterns"; "Execution": "The path
check") and ADR-014. A pattern is matched against a whole path relative to the repo root,
with `/` separators, case-sensitively. `*`, `?` and a whole segment `**` are the only
special forms; every other character matches itself.
"""

from collections.abc import Sequence

from openfactory.domain.contracts import TaskContract


def _segment_matches(pattern: str, name: str) -> bool:
    if not pattern:
        return not name
    head, rest = pattern[0], pattern[1:]
    if head == "*":
        return any(_segment_matches(rest, name[i:]) for i in range(len(name) + 1))
    return bool(name) and head in ("?", name[0]) and _segment_matches(rest, name[1:])


def _segments_match(pattern: Sequence[str], path: Sequence[str]) -> bool:
    if not pattern:
        return not path
    head, rest = pattern[0], pattern[1:]
    if head == "**":
        return any(_segments_match(rest, path[i:]) for i in range(len(path) + 1))
    return bool(path) and _segment_matches(head, path[0]) and _segments_match(rest, path[1:])


def matches(pattern: str, path: str) -> bool:
    """Whether `pattern` matches `path`, a path relative to the repo root."""
    if pattern.endswith("/"):
        pattern += "**"
    if "/" not in pattern:
        pattern = "**/" + pattern
    return _segments_match(pattern.split("/"), path.split("/"))


def matches_any(patterns: Sequence[str], path: str) -> bool:
    """Whether at least one of `patterns` matches `path`."""
    return any(matches(pattern, path) for pattern in patterns)


def violating_paths(changed_paths: Sequence[str], contract: TaskContract) -> list[str]:
    """The changed paths that match a forbidden pattern or no allowed pattern, in input order."""
    return [
        path
        for path in changed_paths
        if matches_any(contract.forbidden_paths, path)
        or not matches_any(contract.allowed_paths, path)
    ]
