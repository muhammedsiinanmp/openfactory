"""Git CLI implementation of the GitProvider port.

Starts one `git` process per command, in the repo or in a worktree, as described under
"Task contract" ("Planning") and "Execution" in docs/spec/phase1-spec.md and in ADR-012
and ADR-014.
"""

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from openfactory.ports.git_provider import GitError, GitProvider


class GitCli:
    def __init__(self, repo: Path, executable: str = "git") -> None:
        self.repo = repo
        self.executable = executable

    def tracked_files(self, worktree: Path | None = None) -> list[str]:
        # -z: names end with NUL and are never quoted or escaped.
        done = self._run(worktree, "ls-files", "-z")
        return _names(self._checked(done))

    def head_commit(self, worktree: Path | None = None) -> str | None:
        done = self._run(worktree, "rev-parse", "--verify", "--quiet", "HEAD")
        # Status 1 with nothing on standard error is how --quiet reports no commit.
        if done.returncode == 1 and not done.stderr.strip():
            return None
        return self._checked(done).strip()

    def stage_changes(self, worktree: Path, base: str) -> list[str]:
        self._checked(self._run(worktree, "add", "-A"))
        done = self._run(worktree, "diff", "--cached", "--name-only", "-z", "--no-renames", base)
        return _names(self._checked(done))

    def _run(self, worktree: Path | None, *args: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self.executable, *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                # A relative worktree path is taken against the repo, an absolute one as it is.
                cwd=self.repo if worktree is None else self.repo / worktree,
                check=False,
            )
        except OSError as exc:
            raise GitError(f"git could not be started: {exc}") from exc

    def _checked(self, done: subprocess.CompletedProcess[str]) -> str:
        if done.returncode != 0:
            raise GitError(done.stderr.strip() or f"git exited with status {done.returncode}")
        return done.stdout


def _names(output: str) -> list[str]:
    return [name for name in output.split("\0") if name]


if TYPE_CHECKING:
    _: type[GitProvider] = GitCli
