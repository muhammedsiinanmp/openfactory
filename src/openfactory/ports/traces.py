"""Traces port: read-only queries over `trace_links` and the task and requirement
projections.

See docs/spec/phase1-spec.md ("Domain model and storage", "Ids", the M5 paragraph;
"Traceability", "Queries"; "CLI commands", "Output"), ADR-012 and ADR-018.
"""

from typing import Protocol

from openfactory.domain.traces import RequirementTrace


class Traces(Protocol):
    def untested_requirements(self, spec_version: str) -> list[str]:
        """The ids, sorted as strings, of the spec version's requirements that are not
        deprecated and have no `test_tag` link from a test."""
        ...

    def requirement_trace(self, requirement_id: str) -> RequirementTrace | None:
        """The requirement's tasks, their commits, those commits' files and the related
        tests; `None` when no approved spec version has the requirement (a deprecated
        one counts).

        Tasks are ordered by task id, commits by task id then sha, files by path, and
        tests, tagged and file tests in one list, by node id; all as strings. A test
        both tagged and in one of the files appears once, as tagged."""
        ...
