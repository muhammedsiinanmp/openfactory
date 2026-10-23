"""Git CLI implementation of the GitProvider port.

Starts one `git` process per command, in the repo or in a worktree, as described under
"Task contract" ("Planning") and "Execution" in docs/spec/phase1-spec.md and in ADR-012
and ADR-014.
"""

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from openfactory.domain.git_history import BranchCommit
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

    def reset_soft(self, worktree: Path, base: str) -> None:
        self._checked(self._run(worktree, "reset", "--soft", base))

    def commit(self, worktree: Path, message: str) -> str:
        self._checked(self._run(worktree, "commit", "--no-verify", "-m", message))
        return self._checked(self._run(worktree, "rev-parse", "--verify", "HEAD")).strip()

    def staged_diff(self, worktree: Path, base: str) -> str:
        # The diff holds file contents, which need not be UTF-8; it only feeds a prompt.
        return self._checked(self._run(worktree, "diff", "--cached", base, errors="replace"))

    def branch_commits(self) -> list[BranchCommit]:
        # Each record is RS, sha, US, trailers, US, then NUL; with -z the names follow
        # after a newline, each ending with NUL. A commit with no files has no names.
        done = self._run(
            None,
            "log",
            "--branches=openfactory/*",
            "--no-renames",
            "--name-only",
            "-z",
            "--format=%x1e%H%x1f%(trailers:only,unfold)%x1f",
        )
        commits: list[BranchCommit] = []
        for record in self._checked(done).split("\x1e")[1:]:
            sha, trailers, names = record.split("\x1f", 2)
            commits.append(
                BranchCommit(
                    sha=sha,
                    trailers=[_trailer(line) for line in trailers.splitlines() if line],
                    files=_names(names.removeprefix("\0").removeprefix("\n")),
                )
            )
        return commits

    def _run(
        self, worktree: Path | None, *args: str, errors: str = "strict"
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self.executable, *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors=errors,
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


def _trailer(line: str) -> tuple[str, str]:
    # With `only`, git writes every trailer back as `key: value`.
    key, _, value = line.partition(": ")
    return key, value


if TYPE_CHECKING:
    _: type[GitProvider] = GitCli
