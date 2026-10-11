"""Git CLI implementation of the GitProvider port.

Starts `git ls-files -z` once per call in the repo, as described under "Task contract"
("Planning") in docs/spec/phase1-spec.md and in ADR-012.
"""

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from openfactory.ports.git_provider import GitError, GitProvider


class GitCli:
    def __init__(self, repo: Path, executable: str = "git") -> None:
        self.repo = repo
        self.executable = executable

    def tracked_files(self) -> list[str]:
        try:
            done = subprocess.run(
                # -z: names end with NUL and are never quoted or escaped.
                [self.executable, "ls-files", "-z"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=self.repo,
                check=False,
            )
        except OSError as exc:
            raise GitError(f"git could not be started: {exc}") from exc
        if done.returncode != 0:
            raise GitError(done.stderr.strip() or f"git exited with status {done.returncode}")
        return [name for name in done.stdout.split("\0") if name]


if TYPE_CHECKING:
    _: type[GitProvider] = GitCli
