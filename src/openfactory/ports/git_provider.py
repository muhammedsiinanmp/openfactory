"""GitProvider port: what the use cases read from the target repo's git.

See docs/spec/phase1-spec.md ("Domain model and storage", "Ids") and ADR-012.
"""

from typing import Protocol


class GitError(Exception):
    """The git command failed or could not be started; the text says how and is not empty."""


class GitProvider(Protocol):
    def tracked_files(self) -> list[str]:
        """The repo's tracked files, relative to its root with `/`, in git's order.

        A failed command raises `GitError`.
        """
        ...
