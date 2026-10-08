"""Filesystem implementation of the SpecFiles port.

See docs/spec/phase1-spec.md ("Spec input format", "Loading").
"""

from pathlib import Path


class FilesystemSpecFiles:
    """Reads spec files from `specs_dir`, the `specs/` directory itself."""

    def __init__(self, specs_dir: Path) -> None:
        self._specs_dir = specs_dir

    def read(self, path: str) -> str | None:
        file = self._specs_dir / path
        if not file.is_file():
            return None
        # newline="" keeps line endings as they are; the loader normalises the ADR body.
        with file.open(encoding="utf-8", newline="") as f:
            return f.read()

    def list_adrs(self) -> list[str]:
        return sorted(f"adrs/{p.name}" for p in (self._specs_dir / "adrs").glob("*.md"))
