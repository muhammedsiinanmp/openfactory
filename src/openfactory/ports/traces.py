"""Traces port: read-only queries over `trace_links` and the requirement projection.

See docs/spec/phase1-spec.md ("Domain model and storage", "Ids", the M5 paragraph;
"Traceability", "Queries"; "CLI commands", "Output"), ADR-012 and ADR-018.
"""

from typing import Protocol


class Traces(Protocol):
    def untested_requirements(self, spec_version: str) -> list[str]:
        """The ids, sorted as strings, of the spec version's requirements that are not
        deprecated and have no `test_tag` link from a test."""
        ...
