"""Filesystem implementation of the RunFiles port.

See docs/spec/phase1-spec.md ("Domain model and storage", "Ids"; "Gates and
remediation") and ADR-014.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from openfactory.ports.run_files import RunFiles


class FilesystemRunFiles:
    """Writes run files under `repo/.openfactory/runs/`; `repo` is the target repo's root."""

    def __init__(self, repo: Path) -> None:
        self._repo = repo

    def write(self, run_id: str, name: str, text: str) -> Path:
        path = Path(".openfactory/runs") / run_id / name
        file = self._repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        # Bytes, so the file is the text as given on every platform.
        file.write_bytes(text.encode("utf-8"))
        return path


if TYPE_CHECKING:
    _: type[RunFiles] = FilesystemRunFiles
