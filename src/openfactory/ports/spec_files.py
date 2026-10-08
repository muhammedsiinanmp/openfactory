"""SpecFiles port: the text of the spec files.

See docs/spec/phase1-spec.md ("Spec input format", "Loading"). The port is read-only and
returns plain text; parsing YAML and ADR front matter happens in the application layer.
Paths are POSIX-style and relative to `specs/`.
"""

from typing import Protocol


class SpecFiles(Protocol):
    def read(self, path: str) -> str | None:
        """Return the text of the file at `path`, or `None` if it does not exist.

        An existing empty file returns the empty string. Line endings are returned as
        they are in the file.
        """
        ...

    def list_adrs(self) -> list[str]:
        """Return the paths of the `*.md` files directly in `adrs/`, in ascending order.

        A missing or empty `adrs/` directory gives an empty list.
        """
        ...
