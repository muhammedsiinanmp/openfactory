"""Git worktree implementation of the WorkspaceManager port.

Starts one `git` process per command in the repo, as described under "Execution"
("Per-task sequence", "Base and branches") in docs/spec/phase1-spec.md and in ADR-014.
"""

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from openfactory.ports.git_provider import GitError
from openfactory.ports.workspace_manager import WorkspaceManager


class GitWorktree:
    def __init__(self, repo: Path, executable: str = "git") -> None:
        self.repo = repo
        self.executable = executable

    def create(self, task_id: str, base: str) -> Path:
        worktree = _worktree(task_id)
        self._checked(
            self._run("worktree", "add", worktree.as_posix(), "-b", _branch(task_id), base)
        )
        return worktree

    def remove(self, task_id: str) -> None:
        # The worktree goes first: git refuses to delete a branch a worktree has checked out.
        self.remove_worktree(task_id)
        branch = _branch(task_id)
        # Any non-zero status counts as no branch; a `create` that follows fails loudly.
        if self._run("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0:
            self._checked(self._run("branch", "-D", branch))

    def remove_worktree(self, task_id: str) -> None:
        worktree = _worktree(task_id)
        if (self.repo / worktree).is_dir():
            self._checked(self._run("worktree", "remove", "--force", worktree.as_posix()))

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self.executable, *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=self.repo,
                check=False,
            )
        except OSError as exc:
            raise GitError(f"git could not be started: {exc}") from exc

    def _checked(self, done: subprocess.CompletedProcess[str]) -> str:
        if done.returncode != 0:
            raise GitError(done.stderr.strip() or f"git exited with status {done.returncode}")
        return done.stdout


def _worktree(task_id: str) -> Path:
    return Path(".openfactory") / "worktrees" / task_id


def _branch(task_id: str) -> str:
    return f"openfactory/{task_id}"


if TYPE_CHECKING:
    _: type[WorkspaceManager] = GitWorktree
