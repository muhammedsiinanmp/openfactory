"""Traces port: read-only queries over `trace_links` and the task and requirement
projections.

See docs/spec/phase1-spec.md ("Domain model and storage", "Ids", the M5 paragraph;
"Traceability", "Queries"; "CLI commands", "Output"; "Spec diff and impact analysis",
"Step 3"), ADR-012, ADR-018 and ADR-019.
"""

from collections.abc import Collection
from typing import Protocol

from openfactory.domain.traces import FileTrace, ImpactTraversal, RequirementTrace


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

    def file_trace(self, path: str) -> FileTrace | None:
        """The commits that changed the file, their tasks, the requirements linked to
        those tasks and the ADRs those requirements are constrained by in the latest
        approved spec version; `None` when no commit changed the path. The path is
        compared as an exact string, with no normalisation.

        Commits are ordered by task id then sha, tasks by task id, requirements and ADRs
        by id; all as strings."""
        ...

    def impact_traversal(self, plan_id: str, seeds: Collection[str]) -> ImpactTraversal:
        """Step 3 of the impact analysis from the seed requirements, over the plan's
        tasks that are not `invalidated` or `abandoned`: the impacted tasks, with a
        requirement -> task `contract` link from a seed; the downstream tasks, the other
        such tasks that depend on an impacted or downstream one, transitively; the files
        their commits changed; and the tests tagged with a seed or whose file is one of
        those files.

        Each list is sorted as strings, without duplicates."""
        ...
