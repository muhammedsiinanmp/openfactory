"""RunFiles port: the files of a run under `.openfactory/runs/<run id>/`.

See docs/spec/phase1-spec.md ("Domain model and storage", "Ids"; "Gates and
remediation") and ADR-014. Gate output goes through it.
"""

from pathlib import Path
from typing import Protocol


class RunFiles(Protocol):
    def write(self, run_id: str, name: str, text: str) -> Path:
        """Write `text` to the file `name` of the run.

        Gives the file's path relative to the repo, `.openfactory/runs/<run id>/<name>`.
        The run's directory is created when it is missing; a file of that name is replaced.
        """
        ...
