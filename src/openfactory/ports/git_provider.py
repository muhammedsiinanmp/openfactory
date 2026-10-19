"""GitProvider port: what the use cases read from and stage in the target repo's git.

See docs/spec/phase1-spec.md ("Domain model and storage", "Ids"; "Execution"), ADR-012
and ADR-014.
"""

from pathlib import Path
from typing import Protocol


class GitError(Exception):
    """The git command failed or could not be started; the text says how and is not empty."""


class GitProvider(Protocol):
    def tracked_files(self, worktree: Path | None = None) -> list[str]:
        """The tracked files, relative to the root with `/`, in git's order.

        `worktree` is the worktree to read; `None` is the repo the provider was made for.
        A failed command raises `GitError`.
        """
        ...

    def head_commit(self, worktree: Path | None = None) -> str | None:
        """The sha of the commit `HEAD` points at, or `None` when it points at no commit.

        `worktree` is the worktree to read; `None` is the repo the provider was made for.
        A failed command raises `GitError`.
        """
        ...

    def stage_changes(self, worktree: Path, base: str) -> list[str]:
        """Stage every change in `worktree`, then give the paths that differ from `base`.

        The paths are relative to the root with `/`, in git's order: they cover untracked
        files, both names of a rename and anything committed since `base`, and leave out
        what the repo ignores. A failed command raises `GitError`.
        """
        ...

    def reset_soft(self, worktree: Path, base: str) -> None:
        """Move the branch checked out in `worktree` to `base` and keep the changes staged.

        A failed command raises `GitError`.
        """
        ...

    def commit(self, worktree: Path, message: str) -> str:
        """Commit what is staged in `worktree` with `message`; the sha of the new commit.

        The repo's hooks for checking a commit are skipped and its configured identity is
        used. A failed command, as when nothing is staged, raises `GitError`.
        """
        ...

    def staged_diff(self, worktree: Path, base: str) -> str:
        """The text of `git diff --cached <base>` in `worktree`, for the reviewer.

        Bytes that are not valid UTF-8 come back as replacement characters. A failed
        command raises `GitError`.
        """
        ...
