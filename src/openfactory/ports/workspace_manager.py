"""WorkspaceManager port: a task's worktree and branch in the target repo.

See docs/spec/phase1-spec.md ("Domain model and storage", "Ids"; "Execution",
"Per-task sequence" and "Base and branches") and ADR-014. A failed git command raises
`GitError` from the GitProvider port.
"""

from pathlib import Path
from typing import Protocol


class WorkspaceManager(Protocol):
    def create(self, task_id: str, base: str) -> Path:
        """Create the task's worktree on its new branch at the commit `base`.

        Gives the worktree's path relative to the repo, `.openfactory/worktrees/<task id>`.
        Nothing is removed first: a worktree or branch of the task that exists is a failed
        command, which raises `GitError`.
        """
        ...

    def remove(self, task_id: str) -> None:
        """Remove the task's worktree and branch, each only if it exists.

        Changed and untracked files in the worktree are lost. A failed command raises
        `GitError`.
        """
        ...

    def remove_worktree(self, task_id: str) -> None:
        """Remove the task's worktree if it exists; the branch stays.

        A failed command raises `GitError`.
        """
        ...
